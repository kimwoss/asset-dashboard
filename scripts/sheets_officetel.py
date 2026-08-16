# -*- coding: utf-8 -*-
"""★아파트 투자_Master > '(ing)2027년 오피스텔' → '다음 후보집' 웹 탭.

내년 이사 후보 오피스텔의 타입 카탈로그와, 기준(전세 9억 이하·전용 13평 이상)을
통과한 매물을 시트에서 그대로 읽어 온다. 다른 탭들과 같은 원칙 — 시트가 원본,
웹은 미러링. 매물을 더하거나 고치려면 시트에 쓰면 되고 다음 동기화 때 반영된다.

매물 수집은 사람이 한다. 네이버·KB·직방·호갱노노·아실 전부 robots.txt로 자동수집을
금지하고 있어(2026-08 확인) 긁어오지 않는다.

파싱은 3행 헤더 라벨 기준 — 열이 밀리거나 항목이 늘어도 따라가도록.
"""
import re
from typing import Any, Dict, List, Optional

import sheets_fire  # 인증 재사용 (같은 서비스 계정)
import molit_deals   # 국토부 실거래 (호가와 나란히 보여주기 위함)

SPREADSHEET_ID = "15m6P8BWXeMfsxIKdT4lh-2agRf9nYyQ-cnfu1HIRRts"
TAB = "(ing)2027년 오피스텔"
BLOCK = "A1:BZ200"   # 매물이 늘어도, 열을 더해도 잘리지 않게 넉넉히.
                     # BD→BH→BI로 세 번 잘렸다. 시트 끝까지 잡는 편이 낫다.

HEADER_ROW_LABEL = "지역"       # 이 라벨이 있는 행이 헤더
PRICE_CAP_MAN = 90_000          # 환산전세 9억 (만원)
AREA_MIN_PY = 13.0              # 전용 13평


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).replace(",", "").replace("₩", "").replace("원", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _col_map(header: List[str]) -> Dict[str, int]:
    """헤더 라벨 → 열 인덱스. 시트에서 열이 이동해도 이름으로 찾는다."""
    out: Dict[str, int] = {}
    for i, h in enumerate(header):
        k = str(h).strip()
        if k and k not in out:
            out[k] = i
    return out


def fetch_officetel() -> Dict[str, Any]:
    """{criteria, updated_at, items[], summary} — 실패 시 빈 dict (탭 숨김)."""
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK)
        # 매물링크는 =HYPERLINK("url","매물 보기") 수식이라 기본 조회로는 표시문구만 온다.
        # 그대로 href에 넣으면 상대경로가 되어 대시보드에서 404가 났다. 수식을 따로 읽어
        # URL을 뽑는다.
        formulas = ws.get(BLOCK, value_render_option="FORMULA")
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 오피스텔 탭 읽기 실패 ({e})")
        return {}

    grid = [list(r) + [""] * (78 - len(r)) for r in grid]
    formulas = [list(r) + [""] * (78 - len(r)) for r in formulas]
    criteria = ""
    hdr_i = None
    for i, row in enumerate(grid):
        if str(row[0]).strip() == "검색기준":
            criteria = str(row[1]).strip()
        if str(row[0]).strip() == HEADER_ROW_LABEL:
            hdr_i = i
            break
    if hdr_i is None:
        print("WARN: 오피스텔 탭 헤더('지역') 없음")
        return {}

    c = _col_map(grid[hdr_i])
    need = ("오피스텔명", "타입", "전용면적(평)", "보증금", "월세", "환산전세")
    if any(k not in c for k in need):
        print(f"WARN: 오피스텔 탭 헤더 불일치 — {sorted(c)[:12]}")
        return {}

    g = lambda row, key: row[c[key]] if key in c and c[key] < len(row) else ""

    def link_of(i: int, key: str = "매물링크") -> str:
        """HYPERLINK 수식에서 URL만 추출. 셀에 URL이 그대로 있으면 그대로 쓴다."""
        j = c.get(key)
        if j is None or i >= len(formulas) or j >= len(formulas[i]):
            return ""
        raw = str(formulas[i][j]).strip()
        m = re.search(r'HYPERLINK\(\s*"([^"]+)"', raw, re.I)
        if m:
            return m.group(1)
        return raw if raw.startswith("http") else ""
    items: List[Dict[str, Any]] = []
    for ri, row in enumerate(grid[hdr_i + 1:], start=hdr_i + 1):
        name = str(g(row, "오피스텔명")).strip()
        if not name:
            continue
        dep, mon = _num(g(row, "보증금")), _num(g(row, "월세"))
        area = _num(g(row, "전용면적(평)"))
        # 전용률은 시트가 % 서식이라 표시값('49%')으로 온다. 서식이 풀리면 0.49로 오므로
        # 둘 다 0~1로 맞춘다 — 화면에서 4900%가 되는 사고를 막는다.
        ratio = _num(str(g(row, "전용률")).replace("%", "").strip())
        if ratio and ratio > 1:
            ratio /= 100
        conv = None if dep is None else dep + (mon or 0) / 40 * 10_000
        listed = dep is not None
        ok = bool(listed and area and conv is not None
                  and conv <= PRICE_CAP_MAN and area >= AREA_MIN_PY)
        items.append({
            "region":   str(g(row, "지역")).strip(),
            "name":     name,
            "type":     str(g(row, "타입")).strip(),
            "units":    _num(g(row, "세대수")),
            "supply":   _num(g(row, "공급면적(평)")),
            "area":     area,
            "age":      _num(g(row, "년차")),
            "floor":    str(g(row, "층수")).strip(),
            "facing":   str(g(row, "향")).strip(),
            "toGangnam": str(g(row, "강남역")).strip(),
            "asof":     str(g(row, "업데이트일자")).strip(),
            "deposit":  dep,
            "monthly":  mon,
            "converted": conv,
            "listed":   listed,
            "ok":       ok,
            "note":     str(g(row, "비고")).strip(),
            "link":     link_of(ri),
            "rooms":    str(g(row, "구조")).strip(),
            "bath":     str(g(row, "욕실")).strip(),
            "recent":   str(g(row, "최근 시세")).strip(),
            "count":    _num(g(row, "매물 수")) or 0,
            # 타입 제원 — 네이버 '면적 정보' 패널에서 온다. 매물이 없는 타입도 채워진다.
            "ratio":    ratio,
            "plan":     link_of(ri, "평면도"),
            "sale":     str(g(row, "매매시세")).strip(),
            # 베스트 매물 별점 — 시세 대비·층·향·실거주 적합을 4시간 잡이 매겨 둔 값
            "stars":    str(g(row, "추천")).strip(),
            "why":      str(g(row, "추천근거")).strip(),
        })

    # 실거래 붙이기 — 각 타입 행에 '어느 버킷을 보면 되는지'만 달아 두고,
    # 실제 거래 목록은 deals에 한 번만 담는다(같은 타입 행이 여러 개라 중복 방지).
    deals = molit_deals.fetch_deals(months=12)
    for x in items:
        if x["area"]:
            k = molit_deals.bucket_key(x["name"], x["area"])
            x["bucket"] = k if k in deals else ""
        else:
            x["bucket"] = ""

    live = [x for x in items if x["ok"]]
    return {
        "criteria": criteria,
        "cap_man": PRICE_CAP_MAN,
        "area_min": AREA_MIN_PY,
        "items": items,
        "deals": deals,
        "summary": {
            "total": len(items),
            "listed": sum(1 for x in items if x["listed"]),
            "ok": len(live),
            "min_conv": min((x["converted"] for x in live), default=None),
            "buildings": len({x["name"] for x in items}),
        },
    }
