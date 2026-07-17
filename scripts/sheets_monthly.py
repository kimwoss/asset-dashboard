# -*- coding: utf-8 -*-
"""★주식계좌(현재) → ★월별자산(월별 기록) 자동 기록 + 이력 읽기.

GOOGLEFINANCE는 '지금' 시세만 안다 — 어제 값은 어디에도 남지 않는다.
월별 흐름을 그리려면 각 달의 값을 그 시점에 얼려 저장해야 하고,
그 저장소로 이미 존재하는 ★월별자산 탭(2021~2028.4 계좌별 기록)을 재사용한다.

  write_current_month()  이번 달 칸에 계좌별 합계 upsert (실행할 때마다 덮어씀 →
                         달이 바뀌면 직전 달 마지막 값이 자연히 확정)
  fetch_monthly()        전체 이력 → 대시보드 monthly 블록
  fetch_liabilities()    대출·전세보증금(26~35행) 최신 월 잔액 — 사용자가 매월초 수기
                         갱신하는 영역을 읽기만 한다 (target 매핑은 코드가 유지)

안전장치: 3~15행(말단 계좌)의 '값' 칸만 쓴다. 소계·증감률·과거 월은 건드리지 않는다.
"""
import os
from datetime import date
from typing import Any, Dict, List, Optional

import sheets_fire  # 인증 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "★월별자산(2026년)"

# 계좌 행 탐색 범위 (3~15행이 말단 계좌, 16행부터 소계)
ACCT_ROW_FIRST, ACCT_ROW_LAST = 3, 15

# ⚠️ 행 번호를 하드코딩하지 않는다. 매번 시트의 라벨(C=종류, D=이름)을 읽어 행을 찾는다.
#   2026-07-17: 사용자가 5·6행의 과세/비과세 라벨을 맞바꿨는데 코드는 옛 행번호대로 써서
#   두 계좌 값이 뒤바뀌었다. 이름 변경·행 삽입에 조용히 깨지는 구조라 라벨 기준으로 전환.

# ★주식계좌 ↔ ★월별자산 이름이 다른 것만 별칭으로 잇는다 (그 외는 정규화 후 그대로 매칭)
_ALIAS: Dict[tuple, tuple] = {
    ("CMA(스토리지)", "규리"): ("현금", "규리"),  # 사용자 확인 — 월별자산 '현금'과 동일
}
_OWNER_KR = {"김우현": "우현", "문규리": "규리"}


def _norm(name: str) -> str:
    """'미래에셋 연저펀(과세)' → '연저펀(과세)' — 두 탭의 표기 차이를 흡수."""
    n = str(name or "").strip()
    for prefix in ("미래에셋 ", "미래에셋"):
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    return n.replace(" ", "")


def _account_rows(grid: List[List]) -> Dict[int, tuple]:
    """★월별자산 3~15행 → {행: (정규화 계좌명, 소유자)}. 시트 라벨이 유일한 근거."""
    out: Dict[int, tuple] = {}
    for r in range(ACCT_ROW_FIRST, ACCT_ROW_LAST + 1):
        row = grid[r - 1] if len(grid) >= r else []
        name = _norm(row[2] if len(row) > 2 else "")
        owner_raw = str(row[3] if len(row) > 3 else "").strip()
        owner = _OWNER_KR.get(owner_raw, owner_raw)
        if name and owner:
            out[r] = (name, owner)
    return out

# 부채 행 (26~35) → (kind, target). 이름·소유자는 시트에서 읽는다.
# target = 이 부채가 조달한 자산군 (순자산 배분 상계용) — 시트에 없는 정보라 코드가 유지.
#   회사 대출(1.50%) → 전세보증금: 파크하비오 보증금 조달에 사용 (2026-07-17 사용자 확인)
LIAB_ROWS: Dict[int, tuple] = {
    26: ("loan", "무담보"),        # 우리은행 예금담보(4.18%)
    27: ("loan", "무담보"),        # 회사 대출(2.50%)
    28: ("loan", "부동산"),        # 디딤돌 주택담보(2.75%)
    29: ("loan", "전세보증금"),    # 파크하비오 전세대출(4.08%)
    30: ("loan", "전세보증금"),    # 회사 대출(1.50%)
    31: ("loan", "무담보"),        # 부모님 대출(0%)
    32: ("loan", "무담보"),        # 부모님 대출(5%)
    34: ("rental_deposit", "부동산"),  # 인덕원삼호 전세보증금
    35: ("rental_deposit", "부동산"),  # 송천센트레빌 전세보증금
}
_OWNER_NORM = {"김우현": "우현", "문규리": "규리"}

# 연간 열 (0-indexed): F~J = 2021~2025
ANNUAL_COLS = {5: "2021", 6: "2022", 7: "2023", 8: "2024", 9: "2025"}
MONTH_START_COL = 10   # K = 2026년 1월
MONTH_START = (2026, 1)
MONTH_STEP = 2         # 월마다 [값, 증감률] 2칸
LAST_MONTH = (2028, 4) # 시트가 뚫려 있는 마지막 달


def month_col(y: int, m: int) -> Optional[int]:
    """(년, 월) → 값 칸 0-indexed 열. 시트 범위 밖이면 None."""
    idx = (y - MONTH_START[0]) * 12 + (m - MONTH_START[1])
    last = (LAST_MONTH[0] - MONTH_START[0]) * 12 + (LAST_MONTH[1] - MONTH_START[1])
    if idx < 0 or idx > last:
        return None
    return MONTH_START_COL + MONTH_STEP * idx


def _col_a1(idx0: int) -> str:
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _group_of(name: str) -> str:
    return "연금성" if any(p in name for p in ("연저펀", "IRP", "퇴직연금", "연금저축")) else "유동성"


def _totals_by_row(holdings: List[Dict], acct_rows: Dict[int, tuple]) -> Dict[int, float]:
    """★주식계좌 보유내역 → ★월별자산 행별 합계. 행은 시트 라벨로 찾는다."""
    # (정규화 계좌명, 소유자) → 행
    index = {v: r for r, v in acct_rows.items()}
    totals: Dict[int, float] = {}
    unmapped = set()
    for h in holdings:
        key = (h["account"], h["owner"])
        key = _ALIAS.get(key, key)
        row = index.get((_norm(key[0]), key[1]))
        if row is None:
            unmapped.add(key)
            continue
        totals[row] = totals.get(row, 0) + h["value_krw"]
    if unmapped:
        print(f"WARN: ★월별자산에 매핑 안 된 계좌 {unmapped} — 기록에서 제외됨")
    return totals


def write_current_month(holdings: List[Dict], today: Optional[date] = None) -> bool:
    """이번 달 칸에 계좌별 합계 upsert. 성공 시 True."""
    if not holdings:
        return False
    today = today or date.today()
    col = month_col(today.year, today.month)
    if col is None:
        print(f"WARN: {today:%Y-%m}은 ★월별자산 범위 밖 — 기록 생략 (열 확장 필요)")
        return False
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 월별 기록 생략")
            return False
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        # 라벨을 먼저 읽어 행을 정한다 — 이름이 바뀌어도 따라간다
        acct_rows = _account_rows(ws.get(f"A1:D{ACCT_ROW_LAST}"))
        totals = _totals_by_row(holdings, acct_rows)
        if not totals or sum(totals.values()) <= 0:
            print("WARN: 계좌 합계 0 — 기록 생략 (덮어쓰기 사고 방지)")
            return False
        a1 = _col_a1(col)
        # 말단 계좌 행만, 한 칸씩 (소계·증감률 절대 미접촉)
        cells = [{"range": f"{a1}{row}", "values": [[round(totals.get(row, 0))]]}
                 for row in acct_rows]
        ws.batch_update(cells, value_input_option="USER_ENTERED")
        print(f"OK: ★월별자산 {today:%Y-%m} ({a1}열) 기록 — 계좌 합계 "
              f"{sum(totals.values())/1e8:.2f}억")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 월별 기록 실패 ({type(e).__name__}: {e})")
        return False


def fetch_monthly(today: Optional[date] = None) -> Dict[str, Any]:
    """★월별자산 → {periods, accounts} (대시보드 월별 흐름용). 실패 시 {}."""
    today = today or date.today()
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get("A1:BN16", value_render_option="UNFORMATTED_VALUE")
        acct_rows = _account_rows(grid)  # 라벨 기준 — 이름이 바뀌어도 따라간다

        def cell(row1: int, col0: int) -> float:
            r = grid[row1 - 1] if len(grid) >= row1 else []
            v = r[col0] if len(r) > col0 else 0
            return float(v) if isinstance(v, (int, float)) else 0.0

        # 표시할 기간: 연간(2021~2025) + 값이 있는 월 (미래 빈 칸 제외)
        periods: List[Dict] = [{"key": y, "label": y} for _, y in sorted(ANNUAL_COLS.items())]
        cols: List[int] = sorted(ANNUAL_COLS)
        y, m = MONTH_START
        while (y, m) <= (today.year, today.month):
            c = month_col(y, m)
            if c is None:
                break
            if any(cell(r, c) for r in acct_rows):  # 빈 달은 건너뜀
                periods.append({"key": f"{y}-{m:02d}", "label": f"{str(y)[2:]}.{m:02d}"})
                cols.append(c)
            m += 1
            if m > 12:
                y, m = y + 1, 1

        accounts = [{
            "name": name, "owner": owner, "group": _group_of(name),
            "values": [round(cell(row, c)) for c in cols],
        } for row, (name, owner) in acct_rows.items()]

        total = sum(a["values"][-1] for a in accounts) if periods else 0
        print(f"OK: 월별 이력 {len(periods)}기간 · 최신 {total/1e8:.2f}억")
        return {"periods": periods, "accounts": accounts}
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 월별 이력 읽기 실패 ({type(e).__name__}: {e})")
        return {}


def fetch_liabilities(today: Optional[date] = None) -> List[Dict]:
    """★월별자산 26~35행에서 최신 월의 대출·전세보증금 잔액을 읽는다.

    사용자가 매월초 수기 갱신하는 영역 — 이번 달이 비어 있으면(월초 갱신 전)
    값이 있는 직전 달로 폴백한다. 실패/빈 결과 시 [] → 호출자가 yaml 폴백.
    """
    today = today or date.today()
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            return []
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get("A26:BN35", value_render_option="UNFORMATTED_VALUE")

        def cell(row1: int, col0: int):
            r = grid[row1 - 26] if len(grid) > row1 - 26 else []
            return r[col0] if len(r) > col0 else ""

        # 값이 있는 최신 월 열 탐색 (이번 달 → 과거로, 최대 12개월)
        y, m = today.year, today.month
        col, used = None, ""
        for _ in range(12):
            c = month_col(y, m)
            if c is not None and any(
                isinstance(cell(r, c), (int, float)) and cell(r, c) > 0 for r in LIAB_ROWS
            ):
                col, used = c, f"{y}-{m:02d}"
                break
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        if col is None:
            print("WARN: ★월별자산 부채 영역에 최근 12개월 값 없음 — yaml 폴백")
            return []

        out: List[Dict] = []
        for r, (kind, target) in LIAB_ROWS.items():
            name = str(cell(r, 2)).strip()
            amount = cell(r, col)
            if not name or not isinstance(amount, (int, float)) or amount <= 0:
                continue  # 상환 완료·빈 행은 제외
            owner = _OWNER_NORM.get(str(cell(r, 3)).strip(), str(cell(r, 3)).strip() or "공동")
            out.append({
                "name": name, "owner": owner, "kind": kind, "target": target,
                "amount_krw": round(amount),
                "note": f"★월별자산 {used} 잔액" + (" · 파크하비오 보증금 조달" if r == 30 else ""),
            })
        total = sum(l["amount_krw"] for l in out)
        print(f"OK: 부채 {len(out)}건 {total/1e8:.2f}억 (★월별자산 {used})")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 부채 읽기 실패 ({type(e).__name__}: {e}) — yaml 폴백")
        return []


if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_monthly()
    for p, in zip(d.get("periods", [])):
        pass
    print(json.dumps(d.get("periods", []), ensure_ascii=False))
    for a in d.get("accounts", []):
        print(f"{a['owner']} {a['group']:4} {a['name'][:16]:16} {a['values'][-3:]}")
