# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > 시각화 탭의 '상세항목별 지출 금액' → 월간 생활비.

시각화 블록은 '2026년' 탭(월별 가계부)에서 INDEX/MATCH로 끌어온 파생표다.
원본이 아니라 이 블록을 읽는 이유: 부호가 이미 지출=양수로 정규화돼 있고,
월 12칸이 한 줄로 정렬돼 있어 파싱이 단순하다.

블록 구조 (2026-07 사용자 재정리)
  헤더행  A='항목'  B='상세항목'  C~N = 2026년 1월 ~ 12월
  고정비  대출 · 보험 · 주거 · 구독 · 세금 · 용돈   (A열='고정비')
  변동비  생활 · 외식 · 쇼핑 · 미용 · 여행 · 교통 · 경조 · 모임 · 가족 · 기타 (A열='변동비')
  합계    = SUM(항목들)

행 위치는 하드코딩하지 않는다 — 사용자가 시각화를 재정리하면 행이 밀리므로,
'항목' 헤더행을 라벨로 찾아 그 아래부터 '합계'가 나올 때까지 읽는다.

생활비 집계 범위(사용자 확정 2026-07): 고정비+변동비 전부, 단 '대출'만 제외.
대출 상환은 소비가 아니라 부채 상환이고 은퇴 시 소멸하므로 뺀다. 값은 버리지 않고
excluded로 넘겨 표 하단에서 대조할 수 있게 한다.
"""
from datetime import date
from typing import Any, Dict, List, Optional

import sheets_fire  # 인증·스프레드시트 ID 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "시각화"

BLOCK = "A35:N60"          # 표 아래(합계·향후 행)까지 넉넉히 — 헤더는 라벨로 찾는다
HEADER_A = "항목"          # 헤더행 A열 라벨 — 이 행 아래부터 항목
STOP_LABEL = "합계"        # A/B에 이 라벨이 오면 항목 끝
MONTH_COL_FIRST = 2        # C열 (0-indexed) = 1월
MONTHS = 12

EXCLUDED = {"대출"}        # 대출 상환은 부채 상환이라 생활비에서 제외 (위 docstring)


def _num(v: Any) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _cell(row: List, c0: int) -> Any:
    return row[c0] if len(row) > c0 else ""


def fetch_spending(today: Optional[date] = None) -> Dict[str, Any]:
    """{year, months, categories, excluded, extra, total} — 실패 시 {} (탭만 숨김)."""
    today = today or date.today()
    try:
        if today.year < 2026:
            print("WARN: 시각화 블록은 2026년 전용 — 월간 생활비 생략")
            return {}
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 월간 생활비 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK, value_render_option="UNFORMATTED_VALUE")

        # 헤더행('항목')을 라벨로 찾는다 — 행이 밀려도 추적 가능
        hr = next((i for i, r in enumerate(grid) if _s(_cell(r, 0)) == HEADER_A), None)
        if hr is None:
            print(f"WARN: 시각화 헤더('{HEADER_A}') 못 찾음 — 월간 생활비 생략")
            return {}

        # 표시 구간: 1월 ~ 이번 달 (미래 달은 0이라 뺀다)
        last_m = MONTHS if today.year > 2026 else min(today.month, MONTHS)
        cols = [MONTH_COL_FIRST + i for i in range(last_m)]
        months = [f"2026-{i+1:02d}" for i in range(last_m)]

        spend: List[Dict] = []
        excluded: List[Dict] = []
        group = ""
        for r in grid[hr + 1:]:
            a, name = _s(_cell(r, 0)), _s(_cell(r, 1))
            if a == STOP_LABEL or name == STOP_LABEL:
                break                              # 합계 행 — 항목 끝
            group = a or group                     # A열 fill-down (고정비/변동비)
            if not name:
                continue
            values = [round(_num(_cell(r, c))) for c in cols]
            item = {"name": name, "values": values, "group": group}
            (excluded if name in EXCLUDED else spend).append(item)

        if not spend:
            print("WARN: 시각화 소비 항목 없음 — 월간 생활비 생략")
            return {}

        total = [sum(c["values"][i] for c in spend) for i in range(last_m)]

        # 아직 손대지 않은 달은 빼고 보여준다 — 달이 바뀌는 날(예: 8월 1일) 사용자가 가계부를
        # 쓰기 전이면 '8월 0원 · 월평균 대비 −100%'처럼 보여 오해를 준다. '2026년' 탭에 그 달
        # 숫자를 넣는 순간 시각화 수식이 채워지고 다음 갱신에서 자동으로 등장한다.
        trimmed = 0
        while last_m > 1 and total[last_m - 1] == 0:
            last_m -= 1
            trimmed += 1
        if trimmed:
            months, total = months[:last_m], total[:last_m]
            for c in spend + excluded:
                c["values"] = c["values"][:last_m]
            print(f"INFO: 아직 입력 전인 {trimmed}개월은 표시에서 제외 (마지막 표시 {months[-1]})")

        out = {
            "year": 2026,
            "months": months,
            "categories": spend,
            "excluded": excluded,
            "extra": [],
            "total": total,
        }
        ex_names = "·".join(c["name"] for c in excluded)
        print(f"OK: 월간 생활비 {last_m}개월 · 카테고리 {len(spend)}종 · "
              f"{months[-1]} {total[-1]/1e4:,.0f}만원"
              + (f" ({ex_names} 제외)" if excluded else ""))
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

# '생활비' 한 줄에 뭉쳐 있는 금액의 세부 내역 위치 (같은 행 F~N=이름, 아랫행 F~N=금액)
LIVING_LABEL = "생활비"
LIVING_COL_FIRST, LIVING_COL_LAST = 5, 14   # F~O (0-indexed) — O열 '기부'까지 넣어야 합이 맞는다


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
        # 카테고리예산 섹션을 표 아래에 덧붙일 여유를 두고 넉넉히 읽는다 (기존 A1:M24 → A1:O60).
        # O열까지 읽어야 '생활비' 세부(외식~기부)가 잘리지 않고 덩어리 합계와 정확히 맞는다.
        grid = ws.get("A1:O60", value_render_option="UNFORMATTED_VALUE")

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

        # '생활비' 한 덩어리(≈395만)의 세부 내역 — 같은 행 F:N에 이름, 바로 아랫행 F:N에 금액.
        # 이걸 펼쳐야 현재 가계부 카테고리(외식·교통·쇼핑…)와 같은 해상도로 비교할 수 있다.
        living_detail: List[Dict] = []
        for i, row in enumerate(grid):
            if (str(row[2]).strip() if len(row) > 2 else "") != LIVING_LABEL:
                continue
            vals = grid[i + 1] if i + 1 < len(grid) else []
            for c0 in range(LIVING_COL_FIRST, LIVING_COL_LAST + 1):
                nm = str(row[c0]).strip() if len(row) > c0 else ""
                v = vals[c0] if len(vals) > c0 else None
                if nm and isinstance(v, (int, float)) and v:
                    living_detail.append({"name": nm, "amount": round(float(v))})
            break

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
        if living_detail:
            out["living_detail"] = living_detail       # '생활비' 덩어리를 펼친 세부 (비교용)
            out["living_label"] = LIVING_LABEL
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
