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


# ── 은퇴 이후 생활비 (참조.연간 생활비 탭) ──────────────────────────────────
# 이 탭은 사용자가 수시로 값을 바꾸므로 행번호를 하드코딩하지 않고 B/C 라벨로 찾는다.
RETIRE_TAB = "참조.연간 생활비"

# '월평균 생활비 카테고리'와 1:1로 비교할 은퇴 후 예산 섹션의 구분 라벨.
# 기존 월간/연간(도넛) 항목과 완전히 분리 — 이 라벨 아래 행만 category_budget으로 모은다.
CATEGORY_MARKER = "카테고리예산"


def fetch_retirement_expense(today: Optional[date] = None) -> Dict[str, Any]:
    """참조.연간 생활비 → 은퇴 후 월·연 생활비 계획. 실패 시 {} (섹션만 숨김).

    구조(라벨 기준): B열=구분('월간'/'연간'/'카테고리예산'/소계 라벨), C열=항목명, D열=금액.
      월간 고정 항목(보험·생활비·국민연금·주거비 등) + 연간 비정기 항목(재산세·건보료 등)
      + '카테고리예산' 섹션(월평균 카테고리 비교용 은퇴 예산 — 월 금액)
      소계: '월간 고정 생활비'(월 고정 합) · '평균 월간 생활비' · '연간 사용예산'
    반환 {monthly_items, annual_items, category_budget, monthly_fixed, avg_monthly,
          annual_budget, monthly_ex_tax, annual_ex_tax}.
    """
    today = today or date.today()
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 은퇴 생활비 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(RETIRE_TAB)
        # 카테고리예산 섹션을 표 아래에 덧붙일 여유를 두고 넉넉히 읽는다 (기존 A1:M24 → A1:M60).
        grid = ws.get("A1:M60", value_render_option="UNFORMATTED_VALUE")

        monthly_items: List[Dict] = []
        annual_items: List[Dict] = []
        category_budget: Dict[str, int] = {}   # 월평균 카테고리 비교용 은퇴 예산 (월 금액)
        s: Dict[str, int] = {}
        section = None
        _SUMMARY_C = {"세금제외 연생활비": "annual_ex_tax", "세금제외 월생활비": "monthly_ex_tax"}
        _SUMMARY_B = {"월간 고정 생활비": "monthly_fixed", "평균 월간 생활비": "avg_monthly",
                      "연간 사용예산": "annual_budget"}
        for row in grid:
            b = str(row[1]).strip() if len(row) > 1 else ""
            c = str(row[2]).strip() if len(row) > 2 else ""
            d = row[3] if len(row) > 3 else None
            dv = float(d) if isinstance(d, (int, float)) else None
            if b == "월간":
                section = "monthly"
            elif b == "연간":
                section = "annual"
            elif b == CATEGORY_MARKER:
                section = "category"
            if b in _SUMMARY_B and dv is not None:
                s[_SUMMARY_B[b]] = round(dv)
            if c in _SUMMARY_C and dv is not None:
                s[_SUMMARY_C[c]] = round(dv)
            # 항목 행: C=이름, D=값 (소계·요약 라벨은 제외)
            if c and dv is not None and c not in _SUMMARY_C and b not in _SUMMARY_B:
                if section == "monthly":
                    monthly_items.append({"name": c, "amount": round(dv)})
                elif section == "annual":
                    annual_items.append({"name": c, "amount": round(dv)})
                elif section == "category":
                    category_budget[c] = round(dv)

        if not monthly_items and not annual_items and not category_budget:
            print("WARN: 참조.연간 생활비 항목 없음 — 은퇴 생활비 생략")
            return {}
        # 소계가 시트에 없으면 항목에서 계산 (안전망)
        s.setdefault("monthly_fixed", sum(i["amount"] for i in monthly_items))
        annual_irregular = sum(i["amount"] for i in annual_items)
        s.setdefault("annual_budget", s["monthly_fixed"] * 12 + annual_irregular)
        s.setdefault("avg_monthly", round(s["annual_budget"] / 12))
        out = {"monthly_items": monthly_items, "annual_items": annual_items,
               "annual_irregular": annual_irregular, **s}
        if category_budget:
            out["category_budget"] = category_budget   # 시트에 섹션 없으면 프론트가 하드코딩 폴백
        print(f"OK: 은퇴 생활비 — 월평균 {s['avg_monthly']/1e4:,.0f}만 · "
              f"연 {s['annual_budget']/1e4:,.0f}만 (월고정 {s['monthly_fixed']/1e4:,.0f} + "
              f"연비정기 {annual_irregular/1e4:,.0f})"
              + (f" · 카테고리예산 {len(category_budget)}종" if category_budget else ""))
        return out
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 은퇴 생활비 읽기 실패 ({type(e).__name__}: {e})")
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
