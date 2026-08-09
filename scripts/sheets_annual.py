# -*- coding: utf-8 -*-
"""시각화 탭의 '연도별 소득·지출 요약' 표를 읽는다 (A56:E…).

왜 시트에 표를 따로 뒀나 — 연도별 가계부 원장은 시대마다 구조가 다르다.
  ★가계부     한 탭에 월별 7열 블록 (소득/고정비/변동비) — 구 '2026년', 연도 무관 이름으로 변경
  2025년 N월  탭마다 유형·금액 요약블록 (라벨 열이 H/I/J로 이동)
  2024년 이하 요약블록이 없거나 지출 부호가 뒤섞여 있음
매번 이 이질적인 원장을 파싱하면 조용히 틀린 숫자가 나온다. 그래서 집계는 시트에서
한 번만 하고(2026은 수식으로 자동, 과거는 확정값), 대시보드는 그 표만 읽는다.
연도를 추가하고 싶으면 시트에 행을 더하면 된다 — 코드는 손대지 않는다.

'총지출(투자 제외)'의 정의 — 소비·고정비만. 투자와 '기타'(전세보증금 이동 같은
대형 자금이동)는 뺀다. 2025년 4월에 3억·3.88억·-3.6억이 기타로 잡혀 있어, 넣으면
그 해 지출이 2억 넘게 튄다.

실패는 파이프라인을 죽이지 않는다 — 예외 시 [] 반환.
"""
from typing import Any, Dict, List

import sheets_fire
import sheets_monthly

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "시각화"
BLOCK = "A57:E70"   # 57행 헤더, 58행부터 연도


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").replace(",", "").replace("₩", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def loan_expense_from_spending(spending: Dict[str, Any]) -> Dict[int, float]:
    """생활비 블록에서 '올해 지출에 대출로 잡힌 금액'을 뽑는다 — 원금 차감의 상한.

    sheets_spending이 '대출'을 excluded로 이미 분리해 두었으므로 그 값을 그대로 쓴다.
    두 곳에서 따로 세면 어긋나므로 출처를 하나로 묶는다.
    """
    if not spending:
        return {}
    year = spending.get("year")
    if not year:
        return {}
    for e in spending.get("excluded") or []:
        if e.get("name") == "대출":
            return {int(year): sum(e.get("values") or [])}
    return {}


# ── 대출 원금 상환액 ──────────────────────────────────────────────────────────
# 빚 갚는 돈은 이자(진짜 나간 돈)와 원금(순자산이 그만큼 는 것)이 섞여 있다. 원금을
# 지출로 세면 저축률이 실제보다 낮게 나온다. 2025년은 사용자가 원장에 조정 셀을 넣어
# 걷어냈고 2026년은 그대로 들어 있어, 두 해 저축률이 같은 잣대가 아니었다.
#
# 원금은 ★월별자산의 대출 잔액이 줄어든 만큼이다 — 가계부를 손대지 않아도 뽑힌다.
# ⚠️ 합계끼리 빼면 안 된다. 2025년은 파크하비오 전세대출 3억을 새로 빌려 잔액이 순증했고,
#    그대로 빼면 '원금 상환 −1.7억'이라는 헛소리가 나온다. 대출 '한 건씩' 감소분만 세고
#    늘어난 건(신규 차입)은 0으로 둔다. 대환(A 상환+B 신규)은 과대 추정될 수 있다.
def _attach_principal(rows: List[Dict[str, Any]], loan_expense: Dict[int, float]) -> None:
    """각 연도 행에 principal(원금 상환 추정)과 principal_applied(실제 차감액)를 붙인다.

    실제 차감은 '그 해 지출에 대출이 얼마나 잡혀 있는지' 아는 해에만 한다(loan_expense).
    모르는 해까지 빼면, 지출에 애초에 대출이 없던 해(2022~2024: 시트 비고에 '고정비
    미항목화'로 명시)나 사용자가 이미 시트에서 걷어낸 해에서 이중으로 빠진다.
    """
    try:
        bal = sheets_monthly.fetch_loan_balances()
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 대출 잔액 읽기 실패 ({type(e).__name__}: {e}) — 원금 상환 조정 생략")
        return
    if not bal:
        return
    for r in rows:
        y, prev = str(r["year"]), str(r["year"] - 1)
        if y not in bal or prev not in bal:
            continue
        paid = sum(max(0.0, bal[prev].get(k, 0.0) - bal[y].get(k, 0.0))
                   for k in set(bal[prev]) | set(bal[y]))
        r["principal"] = round(paid)
        cap = loan_expense.get(r["year"])
        if cap is None:
            continue
        # 원금 추정이 그 해 '대출' 지출보다 크면 초과분은 애초에 지출로 안 잡힌 상환이다
        # (예: 부모님 대출). 잡히지도 않은 걸 빼면 지출이 과소해지므로 잡힌 만큼만 뺀다.
        applied = round(min(paid, cap))
        if applied > 0:
            r["principal_applied"] = applied
            r["expense"] = r["expense"] - applied


def fetch_annual_flow(loan_expense: Dict[int, float] = None) -> List[Dict[str, Any]]:
    """[{year, months, income, expense}] — 연도 내림차순. 실패/미입력 시 [].

    소득과 지출이 모두 채워진 행만 낸다. 2024·2023처럼 자리만 잡아 둔 빈 행은
    건너뛴다 — 0원으로 그리면 그 해에 한 푼도 안 쓴 것처럼 보인다.
    """
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 연도별 소득·지출 생략")
            return []
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK, value_render_option="UNFORMATTED_VALUE")

        out: List[Dict[str, Any]] = []
        for row in grid[1:]:                      # 0번은 헤더
            row = (list(row) + [""] * 5)[:5]
            year = int(_num(row[0]))
            income, expense = _num(row[2]), _num(row[3])
            if not (1900 < year < 2200) or income <= 0 or expense <= 0:
                continue
            months = int(_num(row[1])) or 12
            out.append({
                "year": year,
                "months": max(1, min(12, months)),  # 월평균 계산의 분모
                "income": round(income),
                "expense": round(expense),
                "note": str(row[4] or "").strip(),
            })
        out.sort(key=lambda d: d["year"], reverse=True)
        _attach_principal(out, loan_expense or {})
        if not out:
            print("WARN: 시각화 연도별 소득·지출 표가 비어 있음")
        else:
            print(f"OK: 연도별 소득·지출 {len(out)}개년 "
                  f"({out[-1]['year']}~{out[0]['year']})")
        return out
    except Exception as e:  # noqa: BLE001 — 이 표가 없어도 나머지 대시보드는 살아야 한다
        print(f"WARN: 연도별 소득·지출 읽기 실패 ({type(e).__name__}: {e})")
        return []
