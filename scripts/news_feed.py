# -*- coding: utf-8 -*-
"""분당부부 관심 뉴스 — Google News RSS에서 주제별 최신 기사만 골라온다.

체크포인트의 뉴스가 계속 옛것으로 떠 있던 이유: 뉴스가 07:00 모닝 리포트에서 하루 한 번만
왔다. 이 모듈을 30분 실시간 잡(update_live.py)에 붙여, 두 사람 관심 주제로 쿼리해
최신 기사만 신선하게 갱신한다. 오래된 기사는 카테고리별 max_age로 잘라낸다
(사용자 확인: 예전 뉴스가 뜨는 게 핵심 불만이었다).

Google News RSS는 키·CORS 문제가 없다 (CI 서버에서 파이썬이 직접 받는다). 새 의존성 없이
stdlib(urllib·xml)만 쓴다. AI 인사이트는 넣지 않는다 — 30분마다 AI를 돌릴 이유가 없고,
대신 어떤 관심사에 걸렸는지 카테고리 태그로 맥락을 준다.
"""
import email.utils
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))

# 관심 카테고리 — (태그, 쿼리, 최신 인정 시간h, 이 카테고리 최대 노출수)
# 사용자 선택(2026-07): 보유 ETF·배당 / 미국 증시 / 환율·금리·연준 / FIRE·이주.
# max_age는 카테고리 성격에 맞춘다: 시장뉴스는 짧게(신선), 라이프스타일은 길게(저빈도).
CATEGORIES = [
    {"tag": "배당ETF",   "q": "SCHD 미국배당다우존스 배당 ETF",       "max_h": 120, "take": 2},
    {"tag": "미국증시",   "q": "뉴욕증시 나스닥 반도체",               "max_h": 48,  "take": 2},
    {"tag": "환율·금리",  "q": "원달러 환율 미국 기준금리 연준",        "max_h": 48,  "take": 2},
    {"tag": "FIRE·이주",  "q": "파이어족 조기은퇴 해외 한달살기 이주",   "max_h": 240, "take": 1},
]
MAX_ITEMS = 6
_DUP_JACCARD = 0.45   # 토큰 겹침이 이 이상이면 같은 사건(언론사만 다른 중복)으로 본다
_UA = {"User-Agent": "Mozilla/5.0 (compatible; asset-dashboard/1.0)"}
# 어느 기사에나 흔해 변별력 없는 토큰 — 유사도 계산에서 뺀다
_STOP = {"기자", "종합", "속보", "뉴스", "미국", "증시", "상승", "하락", "전망", "돌파"}


def _tokens(title: str) -> set:
    """중복 판별용 토큰 집합 — 언론사 접미사·기호 제거 후 2자 이상 단어."""
    t = re.sub(r"\s*-\s*[^-]+$", "", title)                 # 끝의 ' - 언론사' 제거
    t = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", t.lower())
    return {w for w in t.split() if len(w) >= 2 and w not in _STOP}


def _is_dup(toks: set, tag: str, seen: List[tuple]) -> bool:
    """이미 뽑은 기사와 같은 사건인가.

    ① 토큰 겹침(자카드)이 크거나, ② 같은 카테고리에서 6자 이상 고유명사를 공유하면 중복.
    ②가 필요한 이유: '미래에셋 TIGER 미국배당다우존스 4조원 돌파'와 '미래 … 4조 돌파'는
    같은 사건인데 미래에셋/미래·4조원/4조로 토큰이 갈려 자카드만으론 안 걸린다.
    긴 고유명사(미국배당다우존스 등)를 같은 주제에서 공유하면 사실상 같은 기사다.
    """
    for prev_tok, prev_tag in seen:
        union = toks | prev_tok
        if union and len(toks & prev_tok) / len(union) >= _DUP_JACCARD:
            return True
        if tag == prev_tag and any(len(w) >= 6 for w in (toks & prev_tok)):
            return True
    return False


def _clean_title(title: str, source: str) -> str:
    """'제목 - 언론사' → '제목' (source가 접미사와 겹칠 때만 자른다)."""
    m = re.match(r"^(.*?)\s*-\s*([^-]+)$", title)
    if m and source and m.group(2).strip().startswith(source.strip()[:4]):
        return m.group(1).strip()
    return title.strip()


def _rel_time(dt: datetime, now: datetime) -> str:
    h = (now - dt).total_seconds() / 3600
    if h < 1:
        return f"{int(h*60)}분 전"
    if h < 24:
        return f"{int(h)}시간 전"
    return f"{int(h//24)}일 전"


def _fetch_category(cat: Dict, now: datetime) -> List[Dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": cat["q"], "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=15).read()
        root = ET.fromstring(raw)
    except Exception as e:  # noqa: BLE001 — 한 카테고리 실패가 전체를 막지 않는다
        print(f"WARN: 뉴스 '{cat['tag']}' 조회 실패 ({type(e).__name__}: {e})")
        return []
    items: List[Dict] = []
    for it in root.iter("item"):
        pub = it.findtext("pubDate", "")
        try:
            dt = email.utils.parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        age_h = (now.astimezone(timezone.utc) - dt).total_seconds() / 3600
        if age_h < 0 or age_h > cat["max_h"]:
            continue  # 오래된 기사 제거 — '예전 뉴스' 방지의 핵심
        src_el = it.find("{*}source")
        source = (src_el.text if src_el is not None else "").strip()
        title = it.findtext("title", "").strip()
        items.append({
            "title": _clean_title(title, source),
            "source": source,
            "link": it.findtext("link", "").strip(),
            "tag": cat["tag"],
            "age_h": age_h,
            "published": _rel_time(dt, now.astimezone(timezone.utc)),
            "_tok": _tokens(title),
        })
    items.sort(key=lambda x: x["age_h"])  # 카테고리 내 최신순
    return items[: cat["take"] * 3]  # 중복 제거 여유분 포함


def fetch_news() -> List[Dict[str, Any]]:
    """관심 카테고리별 최신 뉴스 → 신선도순 최대 MAX_ITEMS건. 실패 시 []."""
    now = datetime.now(KST)
    per_cat = {c["tag"]: _fetch_category(c, now) for c in CATEGORIES}

    take = {c["tag"]: c["take"] for c in CATEGORIES}
    picked: List[Dict] = []
    seen: List[tuple] = []
    tag_cnt: Dict[str, int] = {}

    def add(it: Dict) -> None:
        seen.append((it["_tok"], it["tag"]))
        tag_cnt[it["tag"]] = tag_cnt.get(it["tag"], 0) + 1
        picked.append(it)

    # 1) 카테고리별 상위 take개 (다양성 보장, 같은 사건 중복은 건너뜀)
    for cat in CATEGORIES:
        for it in per_cat.get(cat["tag"], []):
            if tag_cnt.get(cat["tag"], 0) >= cat["take"]:
                break
            if not _is_dup(it["_tok"], it["tag"], seen):
                add(it)
    # 2) 자리가 남으면 최신순으로 채우되 카테고리 한도는 지킨다.
    #    한도를 넘겨 같은 주제 3~4개로 채우면 '나스닥 1.4%↓'류 중복 헤드라인만 늘어난다 —
    #    6개를 억지로 채우기보다 다양성 있는 4~5개가 낫다.
    if len(picked) < MAX_ITEMS:
        rest = sorted((it for lst in per_cat.values() for it in lst), key=lambda x: x["age_h"])
        for it in rest:
            if len(picked) >= MAX_ITEMS:
                break
            if tag_cnt.get(it["tag"], 0) >= take.get(it["tag"], 1):
                continue
            if not _is_dup(it["_tok"], it["tag"], seen):
                add(it)

    picked.sort(key=lambda x: x["age_h"])          # 최종 신선도순
    for it in picked:
        it.pop("_tok", None)
        it.pop("age_h", None)
    return picked[:MAX_ITEMS]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for i, n in enumerate(fetch_news(), 1):
        print(f"{i}. [{n['tag']}] {n['title']}")
        print(f"   {n['source']} · {n['published']}")
