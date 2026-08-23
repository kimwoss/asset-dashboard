# -*- coding: utf-8 -*-
"""관심 뉴스 — 신뢰하는 경제매체 RSS만 직접 받아 우리 주제로 추린다.

왜 매체를 고정하나. 종전에는 구글 뉴스 검색 RSS를 썼는데, 검색은 무엇이 들어올지
통제할 수 없다. 2026-08-23에 '카지노 산업의 경영 실제로 비교해본 결과 체험'
(pekergyo.com)이 배당ETF 태그를 달고 3위에 올랐고, 반대로 미국증시·FIRE는 하루
종일 0건이었다. 스팸을 블랙리스트로 막는 건 끝없는 두더지잡기다.

그래서 반대로 뒤집었다 — **매체를 화이트리스트로 고정**하고 그 안에서만 고른다.
경제 전문 매체의 섹션 피드는 편집자가 이미 한 번 걸러 둔 것이라, 출처 품질이
구조적으로 보장된다. 종합 피드(머니투데이·조선비즈 전체)는 스포츠·연예가 섞여
쓰지 않는다 — 실측에서 야구·예능 기사가 최상단에 올라왔다.

고르는 순서
  1) 매체별 RSS를 받는다 (섹션 피드 우선)
  2) 우리 관심 주제(TOPICS)에 걸리는 것만 남긴다
  3) 같은 사건 중복 제거 + 한 매체 쏠림 방지
  4) 신선도순으로 MIN~MAX건

실패는 조용히 넘어간다 — 한 매체가 죽어도 나머지로 채운다.
"""
from __future__ import annotations

import email.utils
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))

# ── 신뢰 매체 (2026-08-23 실측으로 살아 있는 피드만) ─────────────────────────
# 종합 피드는 넣지 않는다. 경제·증권 섹션이 있는 곳만.
FEEDS = [
    {"name": "연합인포맥스", "url": "https://news.einfomax.co.kr/rss/allArticle.xml"},
    {"name": "연합뉴스",    "url": "https://www.yna.co.kr/rss/economy.xml"},
    {"name": "한국경제",    "url": "https://www.hankyung.com/feed/economy"},
    {"name": "한경 마켓",   "url": "https://www.hankyung.com/feed/finance"},
    {"name": "매일경제",    "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "매경 증권",   "url": "https://www.mk.co.kr/rss/50200011/"},
]

# ── 우리 관심 주제 — 제목에 걸리면 그 태그를 단다 (앞선 것이 우선) ───────────
TOPICS = [
    # 키워드는 좁게. 넓히면 엉뚱한 기사가 딸려 온다 — '달러' 하나로 '탄자니아 AI 사업에
    # 1.7억달러 차관'이, '주택' 하나로 '주택용지 확보방안' 정치 기사가 들어왔다(2026-08-23).
    # 우리가 알고 싶은 건 '우리 돈이 걸린 시장'이지 정책 일반이 아니다.
    ("배당ETF",  ("SCHD", "배당", "ETF", "리츠", "분배금", "월배당")),
    ("환율·금리", ("환율", "원달러", "원·달러", "달러·원", "기준금리", "금리 인상",
                  "금리 인하", "연준", "FOMC", "금통위", "한국은행", "국채", "채권시장",
                  "잭슨홀", "물가 상승률", "소비자물가")),
    ("미국증시",  ("뉴욕증시", "나스닥", "S&P", "다우지수", "월가", "엔비디아",
                  "미국 증시", "테슬라", "애플", "빅테크")),
    ("국내증시",  ("코스피", "코스닥", "외국인 순매수", "기관 순매수", "증시 전망",
                  "주가 급등", "주가 급락")),
    ("부동산",   ("아파트", "전세", "집값", "부동산 시장", "청약", "분양", "매매가",
                  "주택 공급", "재건축", "전셋값")),
    ("은퇴·자산", ("파이어족", "조기은퇴", "노후 준비", "연금", "자산관리", "재테크",
                  "퇴직연금")),
]

MIN_ITEMS = 5          # 하루 최소 이만큼 — 못 채우면 기간을 넓혀 다시 훑는다
MAX_ITEMS = 8
MAX_AGE_H = 36         # 기본 신선도 창
PER_FEED = 2           # 한 매체가 화면을 독차지하지 않게
_DUP_JACCARD = 0.45    # 토큰 겹침이 이 이상이면 같은 사건으로 본다
_UA = {"User-Agent": "Mozilla/5.0 (compatible; asset-dashboard/1.0)"}
_STOP = {"기자", "종합", "속보", "뉴스", "미국", "증시", "상승", "하락", "전망", "돌파"}
# 경제면에도 섞여 드는 잡음 — 제목에 있으면 버린다
# 경제면에도 섞여 드는 잡음. 정치·행정 기사는 우리 돈과 무관해 뺀다 —
# 키워드를 조여도 '與·野 주택 공급 논의'류는 계속 걸려 들어왔다.
_JUNK = ("부고", "인사]", "동정]", "포토]", "영상]", "카지노", "토토", "홀덤",
         "與", "野", "국정감사", "대통령실", "국회", "의원", "장관", "차관",
         "野당", "여당", "야당", "청문회")


def _tokens(title: str) -> set:
    t = re.sub(r"[^\w가-힣 ]", " ", title or "")
    return {w for w in t.split() if len(w) >= 2 and w not in _STOP}


def _is_dup(toks: set, seen: List[set]) -> bool:
    for s in seen:
        if not toks or not s:
            continue
        j = len(toks & s) / len(toks | s)
        if j >= _DUP_JACCARD:
            return True
    return False


def _topic_of(title: str) -> Optional[str]:
    """제목이 어느 관심 주제에 닿는가. 어디에도 안 닿으면 None (버린다)."""
    t = (title or "").lower()
    for tag, kws in TOPICS:
        if any(k.lower() in t for k in kws):
            return tag
    return None


def _clean(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    t = t.replace("&quot;", '"').replace("&amp;", "&").replace("&#39;", "'")
    return t


def _parse_dt(raw: str) -> Optional[datetime]:
    """RSS pubDate → aware datetime. 매체마다 형식이 다르다.

    연합인포맥스는 '2026-08-23 13:00:16'처럼 타임존이 없다 — KST로 읽는다.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = email.utils.parsedate_to_datetime(raw)
        return d if d.tzinfo else d.replace(tzinfo=KST)
    except Exception:  # noqa: BLE001
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def _rel_time(dt: datetime, now: datetime) -> str:
    m = max(0, int((now - dt).total_seconds() // 60))
    if m < 60:
        return f"{max(m, 1)}분 전"
    if m < 60 * 24:
        return f"{m // 60}시간 전"
    return f"{m // (60 * 24)}일 전"


def _fetch_feed(feed: Dict, now: datetime, max_h: float) -> List[Dict]:
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(feed["url"], headers=_UA), timeout=15).read()
        root = ET.fromstring(raw)
    except Exception as e:  # noqa: BLE001 — 한 매체가 죽어도 나머지로 채운다
        print(f"WARN: 뉴스 '{feed['name']}' 조회 실패 ({type(e).__name__}: {e})")
        return []

    out: List[Dict] = []
    for it in root.iter("item"):
        dt = _parse_dt(it.findtext("pubDate", ""))
        if not dt:
            continue
        age_h = (now - dt).total_seconds() / 3600
        if age_h < -1 or age_h > max_h:
            continue
        title = _clean(it.findtext("title", ""))
        if not title or any(j in title for j in _JUNK):
            continue
        tag = _topic_of(title)
        if not tag:
            continue                      # 경제면이어도 우리 주제가 아니면 버린다
        out.append({"title": title, "source": feed["name"],
                    "link": (it.findtext("link", "") or "").strip(),
                    "tag": tag, "age_h": age_h,
                    "published": _rel_time(dt, now), "_tok": _tokens(title)})
    out.sort(key=lambda x: x["age_h"])
    return out


def _collect(now: datetime, max_h: float) -> List[Dict]:
    picked: List[Dict] = []
    seen: List[set] = []
    per: Dict[str, int] = {}
    pools = [_fetch_feed(f, now, max_h) for f in FEEDS]

    # 매체를 돌아가며 하나씩 — 한 곳이 상위를 쓸어가지 않게(라운드 로빈)
    for rnd in range(PER_FEED):
        for pool in pools:
            for it in pool:
                if it.get("_used") or per.get(it["source"], 0) > rnd:
                    continue
                if _is_dup(it["_tok"], seen):
                    it["_used"] = True
                    continue
                it["_used"] = True
                seen.append(it["_tok"])
                per[it["source"]] = per.get(it["source"], 0) + 1
                picked.append(it)
                break
    return picked


def fetch_news() -> List[Dict[str, Any]]:
    """신뢰 매체에서 관심 주제 기사만 → 신선도순 MIN~MAX건. 실패 시 []."""
    now = datetime.now(KST)
    picked = _collect(now, MAX_AGE_H)
    # 못 채웠으면 기간만 넓힌다. 매체·주제 기준은 절대 풀지 않는다 —
    # 개수를 채우려고 아무거나 들이면 안 채우느니만 못하다.
    if len(picked) < MIN_ITEMS:
        picked = _collect(now, MAX_AGE_H * 4)

    picked.sort(key=lambda x: x["age_h"])
    for it in picked:
        it.pop("_tok", None); it.pop("age_h", None); it.pop("_used", None)
    print(f"OK: 뉴스 {len(picked)}건 / 매체 {len({p['source'] for p in picked})}곳")
    return picked[:MAX_ITEMS]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for i, n in enumerate(fetch_news(), 1):
        print(f"{i}. [{n['tag']}] {n['title']}")
        print(f"   {n['source']} · {n['published']}")
