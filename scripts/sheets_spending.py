# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > 시각화 탭의 '상세항목별 지출 금액' → 월간 생활비.

시각화 A35:N52 블록은 '2026년' 탭(월별 가계부)에서 INDEX/MATCH로 끌어온 파생표다.
원본이 아니라 이 블록을 읽는 이유: 부호가 이미 지출=양수로 정규화돼 있고,
월 12칸이 한 줄로 정렬돼 있어 파싱이 단순하다. 원본 '2026년'은 달마다 7열씩
블록이 옆으로 이어져 훨씬 다루기 어렵다.

블록 구조
  36행  C~N = 2026년 1월 ~ 12월
  37행  투자
  38행  대출/이자/보험
  39~51행  소비 (A39='소비' 이후 A열은 비어 있어 fill-down으로 그룹을 잇는다)
  52행  합계 = SUM(37:51)

분배 제외 — 사용자 확인(2026-07). 1~6월은 월 389,000원 고정이지만 7월부터
+2,996,500원으로 부호가 뒤집혀 '대출/이자/보험'을 정확히 상쇄한다. 아직 확정되지
않은 달의 고정비를 미리 깔고 되돌리는 플러그이지 소비가 아니다. 합계에서 빼되
값은 버리지 않고 excluded로 넘겨 표 하단에서 확인할 수 있게 한다.
"""
from datetime import date
from typing import Any, Dict, List, Optional

import sheets_fire  # 인증·스프레드시트 ID 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "시각화"

BLOCK = "A35:N52"
HEAD_ROW = 36              # C~N에 월 헤더
FIRST_ROW, LAST_ROW = 37, 51
MONTH_COL_FIRST = 2        # C열 (0-indexed) = 1월
MONTHS = 12

SPEND_GROUP = "소비"       # 이 그룹만 '생활비'로 센다 (투자·대출은 참고 지표)
EXCLUDED = {"분배"}        # 위 docstring 참조


def _num(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def fetch_spending(today: Optional[date] = None) -> Dict[str, Any]:
    """{year, months, categories, excluded, extra, total} — 실패 시 {} (탭만 숨김)."""
    today = today or date.today()
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 월간 생활비 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK, value_render_option="UNFORMATTED_VALUE")

        def row(r1: int) -> List:
            i = r1 - 35  # 블록이 35행부터 시작
            return grid[i] if 0 <= i < len(grid) else []

        def label(r1: int, c0: int) -> str:
            r = row(r1)
            return str(r[c0]).strip() if len(r) > c0 else ""

        # 표시 구간: 1월 ~ 이번 달 (미래 달은 0이거나 플러그값이라 뺀다)
        last_m = MONTHS if today.year > 2026 else min(today.month, MONTHS)
        if today.year < 2026:
            print("WARN: 시각화 블록은 2026년 전용 — 월간 생활비 생략")
            return {}
        cols = [MONTH_COL_FIRST + i for i in range(last_m)]
        months = [f"2026-{i+1:02d}" for i in range(last_m)]

        spend: List[Dict] = []
        excluded: List[Dict] = []
        extra: List[Dict] = []
        group = ""
        for r in range(FIRST_ROW, LAST_ROW + 1):
            group = label(r, 0) or group          # A열 fill-down
            name = label(r, 1) or group
            values = [round(_num(row(r)[c])) if len(row(r)) > c else 0 for c in cols]
            item = {"name": name, "values": values}
            if group != SPEND_GROUP:
                extra.append({**item, "group": group})
            elif name in EXCLUDED:
                excluded.append(item)
            else:
                spend.append(item)

        if not spend:
            print("WARN: 시각화 소비 항목 없음 — 월간 생활비 생략")
            return {}

        total = [sum(c["values"][i] for c in spend) for i in range(last_m)]
        out = {
            "year": 2026,
            "months": months,
            "categories": spend,
            "excluded": excluded,
            "extra": extra,
            "total": total,
        }
        print(f"OK: 월간 생활비 {last_m}개월 · 카테고리 {len(spend)}종 · "
              f"{months[-1]} {total[-1]/1e4:,.0f}만원"
              + (f" (분배 제외)" if excluded else ""))
        return out
    except Exception as e:  # noqa: BLE001 — 자산추적을 죽이지 않는다
        print(f"WARN: 월간 생활비 읽기 실패 ({type(e).__name__}: {e})")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_spending()
    if d:
        w = max(len(c["name"]) for c in d["categories"])
        print("  " + " " * w + "".join(f"{m[5:]:>10}" for m in d["months"]))
        for c in d["categories"] + d["excluded"]:
            mark = "*" if c in d["excluded"] else " "
            print(f"{mark} {c['name']:<{w}}" + "".join(f"{v:>10,}" for v in c["values"]))
        print("  " + "합계".ljust(w) + "".join(f"{v:>10,}" for v in d["total"]))
