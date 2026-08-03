# -*- coding: utf-8 -*-
"""★주식계좌(현재) → ★월별자산(월별 기록) 자동 기록 + 이력 읽기.

GOOGLEFINANCE는 '지금' 시세만 안다 — 어제 값은 어디에도 남지 않는다.
월별 흐름을 그리려면 각 달의 값을 그 시점에 얼려 저장해야 하고,
그 저장소로 이미 존재하는 ★월별자산 탭(2021~2028.4 계좌별 기록)을 재사용한다.

  write_current_month()           이번 달 칸에 계좌별 합계 upsert (실행할 때마다 덮어씀 →
                                  달이 바뀌면 직전 달 마지막 값이 자연히 확정)
  write_current_month_realestate()  부동산 KB 실시세를 이번 달 칸에
  fetch_monthly()                 전체 이력 → 대시보드 monthly 블록
  fetch_asset_history()           전월 비교값 (현재값은 sheets_yearly가 담당)
  month_summary()                 그 달 소계 (총자산·부채·순자산)
  latest_complete_month()         '현재값'으로 삼을 달 — 자산·부채가 둘 다 채워진 최신 달
  sheet_grid()                    이 탭의 격자 (실행당 1회만 읽는 캐시)

현재값 읽기(부채·회사주식·전세보증금)는 sheets_yearly가 이 모듈의 상수·격자를 빌려
수행한다. 같은 일을 하는 함수를 양쪽에 두면 한쪽만 고쳐져 어긋나므로 여기선 지웠다.

안전장치: 3~15행(말단 계좌)의 '값' 칸만 쓴다. 소계·증감률·과거 월은 건드리지 않는다.
"""
import os
from datetime import date
from typing import Any, Dict, List, Optional

import sheets_fire  # 인증 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID

# 월별 원장 탭. 2026-08 '★월별자산(2026년)' → '★월별자산'으로 변경(연도 무관 이름).
# 이 탭은 코드가 값을 '쓰기'까지 하므로 이름이 어긋나면 조용히 실패하면 안 된다 —
# _ws()가 새 이름 → 옛 이름 순으로 찾고, 못 찾으면 예외를 그대로 올려 잡을 실패시킨다.
TAB = "★월별자산"
TAB_LEGACY = ("★월별자산(2026년)",)


def _ws(gc):
    """월별 원장 워크시트. 새 이름 → 옛 이름 순으로 찾는다 (이름 변경 전/후 모두 동작).

    워크시트 목록 한 번으로 해결하므로 worksheet(title)과 API 비용이 같다.
    둘 다 없으면 gspread 예외를 그대로 올린다 — 쓰기 대상 탭이라 조용히 넘기면 안 된다.
    """
    sh = gc.open_by_key(SPREADSHEET_ID)
    by_title = {w.title: w for w in sh.worksheets()}
    for t in (TAB, *TAB_LEGACY):
        if t in by_title:
            if t != TAB:
                print(f"INFO: 월별 원장 탭이 아직 옛 이름('{t}')입니다 — '{TAB}'로 바꿔도 그대로 동작합니다")
            return by_title[t]
    return sh.worksheet(TAB)   # 없으면 WorksheetNotFound를 그대로 올린다


# 계좌 행 탐색 범위 (3~15행이 말단 계좌, 16행부터 소계)
ACCT_ROW_FIRST, ACCT_ROW_LAST = 3, 15

# ⚠️ 행 번호를 하드코딩하지 않는다. 매번 시트의 라벨(C=종류, D=이름)을 읽어 행을 찾는다.
#   2026-07-17: 사용자가 5·6행의 과세/비과세 라벨을 맞바꿨는데 코드는 옛 행번호대로 써서
#   두 계좌 값이 뒤바뀌었다. 이름 변경·행 삽입에 조용히 깨지는 구조라 라벨 기준으로 전환.

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

# 시트가 스스로 계산하는 월별 소계 행 (전월 대비 KPI의 폴백 기준값)
SUMMARY_ROWS = {"gross": 25, "debt": 37, "net": 38}

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


def latest_complete_month(grid: List[List], today: Optional[date] = None):
    """대시보드가 '현재값'으로 삼을 달 → (col0, year, month). 없으면 (None, None, None).

    '값이 있는 달'이 아니라 '완성된 달'을 고른다. 이 구분이 핵심이다 —
    월이 바뀌면 일별 잡이 계좌·부동산을 새 달 칸에 자동으로 쓰지만 대출·전세보증금은
    사용자가 손으로 넣는다. 그 사이에 새 달을 현재값으로 잡으면 부채가 0으로 읽혀
    순자산이 통째로 부풀어 보인다(2026-08 기준 14억). 총자산·순자산 행은 수식이라
    하위가 비어도 숫자가 찍히므로 판정 근거로 쓸 수 없다.

    그래서 자산(계좌)과 부채(대출)가 '둘 다' 채워진 가장 최근 달을 쓴다.
    사용자가 새 달 대출을 넣기 전까지는 직전 달 값이 그대로 유지된다 — 섞이지 않는다.
    """
    today = today or date.today()

    def val(r1: int, c0: int) -> float:
        r = grid[r1 - 1] if len(grid) >= r1 else []
        v = r[c0] if len(r) > c0 else 0
        return float(v) if isinstance(v, (int, float)) else 0.0

    y, m = today.year, today.month
    for _ in range(24):                      # 최대 2년 거슬러 올라간다
        c = month_col(y, m)
        if c is not None:
            has_asset = any(val(r, c) > 0 for r in range(ACCT_ROW_FIRST, ACCT_ROW_LAST + 1))
            has_debt = any(val(r, c) > 0 for r in LIAB_ROWS)
            if has_asset and has_debt:
                return c, y, m
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return None, None, None


def _col_a1(idx0: int) -> str:
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ── 격자 캐시 ────────────────────────────────────────────────────────────────
# 한 실행에서 이 탭을 여러 번 읽고 있었다. 월별 흐름·자산 이력·부채·회사주식이 저마다
# 자기 범위를 따로 불러 ★월별자산만 실행당 5회 왕복했다. 값은 실행 중에 바뀌지 않으니
# 넉넉한 범위(A1:BN40)로 한 번 읽어 모두가 나눠 쓴다 — 왕복 5회 → 1회.
# 쓰기 뒤에는 반드시 버린다(_invalidate). 안 그러면 방금 기록한 이번 달 값을 못 본다.
GRID_RANGE = "A1:BN40"
_grid_cache = {}


def sheet_grid(rng: str = GRID_RANGE):
    """★월별자산 격자(캐시). 실패 시 None — 호출자가 각자 폴백한다."""
    if rng in _grid_cache:
        return _grid_cache[rng]
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            return None
        ws = _ws(gc)
        _grid_cache[rng] = ws.get(rng, value_render_option="UNFORMATTED_VALUE")
        return _grid_cache[rng]
    except Exception as e:  # noqa: BLE001
        print(f"WARN: ★월별자산 읽기 실패 ({type(e).__name__}: {e})")
        return None


def _invalidate():
    """시트에 쓴 뒤 캐시를 버린다 — 이후 읽기가 방금 기록한 값을 보게."""
    _grid_cache.clear()


def _group_of(name: str) -> str:
    return "연금성" if any(p in name for p in ("연저펀", "IRP", "퇴직연금", "연금저축")) else "유동성"


def _totals_by_row(holdings: List[Dict], acct_rows: Dict[int, tuple]):
    """★주식계좌 보유내역 → (행별 합계, 매핑 실패한 계좌들). 행은 시트 라벨로 찾는다.

    두 탭의 계좌명은 _norm() 정규화 후 그대로 일치해야 한다. 별칭표를 두지 않는 이유:
    한쪽 이름이 바뀌면 별칭이 조용히 엉뚱한 행을 가리키게 되기 때문이다
    (2026-07-17 'CMA(스토리지)'→'현금' 별칭이 시트 이름 통일 후 오히려 매핑을 깨뜨렸다).
    이름이 어긋나면 숨기지 말고 호출자가 기록을 멈추게 한다.
    """
    index = {v: r for r, v in acct_rows.items()}  # (정규화 계좌명, 소유자) → 행
    totals: Dict[int, float] = {}
    unmapped = set()
    circular = set()
    for h in holdings:
        row = index.get((_norm(h["account"]), h["owner"]))
        if row is None:
            unmapped.add((h["account"], h["owner"]))
            continue
        # 이 보유내역이 ★월별자산을 되읽은 값이면, 그 행은 우리가 쓸 대상이 아니다.
        # 되쓰면 값이 자기 자신에서 나오게 되어(A→B→A) 한 번의 오기록이 영구히 굳는다.
        if h.get("circular"):
            circular.add(row)
        totals[row] = totals.get(row, 0) + h["value_krw"]
    for row in circular:
        totals.pop(row, None)
    return totals, unmapped, circular


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
        ws = _ws(gc)
        # 라벨을 먼저 읽어 행을 정한다 — 이름이 바뀌어도 따라간다
        acct_rows = _account_rows(ws.get(f"A1:D{ACCT_ROW_LAST}"))
        totals, unmapped, circular = _totals_by_row(holdings, acct_rows)
        if circular:
            names = ", ".join(f"{acct_rows[r][1]} {acct_rows[r][0]}({r}행)" for r in sorted(circular))
            print(f"WARN: ★주식계좌가 ★월별자산을 되읽는 계좌 [{names}] — 해당 행 기록 생략. "
                  f"★주식계좌의 해당 셀을 실제 잔액(하드값)으로 바꿔주세요.")
        if unmapped:
            # 부분 기록은 하지 않는다 — 매핑 못 한 계좌의 행에 0이 박혀 실제 잔액을
            # 지워버린다 (2026-07-17 W13이 실제로 이렇게 0이 됐다).
            print(f"ERROR: ★월별자산에 매핑 안 된 계좌 {unmapped} — 기록 전체 생략. "
                  f"두 탭의 계좌명(C열)·소유자(D열)를 맞춰주세요.")
            return False
        if not totals or sum(totals.values()) <= 0:
            print("WARN: 계좌 합계 0 — 기록 생략 (덮어쓰기 사고 방지)")
            return False
        a1 = _col_a1(col)
        # 말단 계좌 행만, 한 칸씩 (소계·증감률 절대 미접촉)
        cells = [{"range": f"{a1}{row}", "values": [[round(totals.get(row, 0))]]}
                 for row in acct_rows if row not in circular]
        ws.batch_update(cells, value_input_option="USER_ENTERED")
        print(f"OK: ★월별자산 {today:%Y-%m} ({a1}열) 기록 — 계좌 합계 "
              f"{sum(totals.values())/1e8:.2f}억")
        _invalidate()          # 방금 쓴 값을 이후 읽기가 보도록
        return True
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 월별 기록 실패 ({type(e).__name__}: {e})")
        return False


# 부동산 KB 실시세를 기록할 후보 행 범위 (계좌 소계 16행 ~ 총자산소계 25행 사이).
# 이 안에서 C라벨이 KB 자산 이름과 겹치는 행만 골라 쓴다 — 전세·회사주식 등은 자동으로 제외된다.
RE_ROW_FIRST, RE_ROW_LAST = 17, 24


def write_current_month_realestate(re_assets: List[Dict], today: Optional[date] = None) -> bool:
    """KB 실시세 부동산을 이번 달 칸에 기록. re_assets=[{name, value_krw}] (category=='부동산').

    ★월별자산 부동산 행(인덕원삼호·송천센트레빌 등)을 C라벨↔KB자산명 겹침으로 찾아 그 달 칸에
    하드값으로 upsert한다. 기존엔 시트 추정 수식(=U*1.009)이라 KB 실시세와 드리프트했다.
    전세·회사주식 등 KB와 무관한 행은 이름이 안 겹쳐 자동 제외 → 절대 건드리지 않는다.
    """
    if not re_assets:
        return False
    today = today or date.today()
    col = month_col(today.year, today.month)
    if col is None:
        print(f"WARN: {today:%Y-%m}은 ★월별자산 범위 밖 — 부동산 기록 생략")
        return False
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            return False
        ws = _ws(gc)
        labels = ws.get(f"C{RE_ROW_FIRST}:C{RE_ROW_LAST}")
        a1 = _col_a1(col)
        cells, matched = [], []
        for i, row in enumerate(labels):
            r = RE_ROW_FIRST + i
            label = (row[0].strip() if row else "").replace(" ", "")
            if not label:
                continue
            for a in re_assets:
                if label in str(a.get("name", "")).replace(" ", "") and a.get("value_krw", 0) > 0:
                    cells.append({"range": f"{a1}{r}", "values": [[round(a["value_krw"])]]})
                    matched.append(f"{label}={a['value_krw']/1e8:.2f}억")
                    break
        if not cells:
            print("WARN: ★월별자산 부동산 행 매칭 실패 — KB 기록 생략")
            return False
        ws.batch_update(cells, value_input_option="USER_ENTERED")
        print(f"OK: ★월별자산 {today:%Y-%m} ({a1}열) 부동산 KB 기록 — {' · '.join(matched)}")
        _invalidate()          # 방금 쓴 값을 이후 읽기가 보도록
        return True
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 부동산 월별 기록 실패 ({type(e).__name__}: {e})")
        return False


def fetch_asset_history(today: Optional[date] = None) -> Dict[str, Any]:
    """자산 상세용 전월·전년 이력 → {prev_month, prev_year, assets:{key:{m1,y1}}, liabilities:{...}}.

    각 항목의 전월(직전 달)·전년(2025 연말) 값을 ★월별자산에서 읽는다. 대시보드가 현재값(라이브)
    과 비교해 증감을 표시한다. 키:
      계좌 → '계좌:우현' / '계좌:규리' (계좌 행 소유자별 합)
      부동산·전세 → 라벨 (인덕원삼호 / 송천센트레빌 / <전세 행 라벨>)
      부채 → 라벨 (회사 대출(2.50%) 등, ★월별자산 라벨과 자산 상세 이름이 동일)
    실패 시 {}.
    """
    today = today or date.today()
    try:
        grid = sheet_grid()               # 캐시된 격자 — 같은 실행에선 한 번만 읽는다
        if grid is None:
            return {}

        def cell(r1: int, c0: Optional[int]) -> float:
            if c0 is None:
                return 0.0
            r = grid[r1 - 1] if len(grid) >= r1 else []
            v = r[c0] if len(r) > c0 else 0
            return float(v) if isinstance(v, (int, float)) else 0.0

        def label(r1: int) -> str:
            r = grid[r1 - 1] if len(grid) >= r1 else []
            return str(r[2]).strip() if len(r) > 2 else ""

        cur_col = month_col(today.year, today.month)
        py, pm = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        prev_col = month_col(py, pm)
        year_col = max(ANNUAL_COLS)  # 2025 = J열 (index 9)

        assets: Dict[str, Dict] = {}
        # 계좌 소유자별 합 (3~15행)
        acct_rows = _account_rows(grid)
        for owner in ("우현", "규리"):
            rows = [r for r, (n, o) in acct_rows.items() if o == owner]
            if rows:
                assets[f"계좌:{owner}"] = {
                    "cur": round(sum(cell(r, cur_col) for r in rows)),
                    "m1": round(sum(cell(r, prev_col) for r in rows)),
                    "y1": round(sum(cell(r, year_col) for r in rows)),
                }
        # 부동산·전세 (17~24행): 라벨을 키로
        for r in range(RE_ROW_FIRST, RE_ROW_LAST + 1):
            lab = label(r)
            if not lab or "주식" in lab or "원달러" in lab:
                continue
            if cell(r, cur_col) or cell(r, prev_col):
                assets[lab] = {"cur": round(cell(r, cur_col)), "m1": round(cell(r, prev_col)),
                               "y1": round(cell(r, year_col))}
        # 부채 (26~35행): 라벨을 키로 (자산 상세 이름과 동일)
        liabilities: Dict[str, Dict] = {}
        for r in LIAB_ROWS:
            lab = label(r)
            if lab and (cell(r, cur_col) or cell(r, prev_col)):
                liabilities[lab] = {"cur": round(cell(r, cur_col)), "m1": round(cell(r, prev_col)),
                                    "y1": round(cell(r, year_col))}

        # 합계 행용 — 시트 소계(총자산 25·총부채 37·순자산 38)의 전월·전년 값.
        # 상단 KPI와 같은 기준: 현재값은 라이브(snap), 전월/전년 기준은 시트 소계.
        totals = {k: {"m1": round(cell(r, prev_col)), "y1": round(cell(r, year_col))}
                  for k, r in SUMMARY_ROWS.items()}

        print(f"OK: 자산 이력 — 자산 {len(assets)}종 · 부채 {len(liabilities)}종 "
              f"(전월 {py}-{pm:02d} · 전년 {ANNUAL_COLS[year_col]})")
        return {"prev_month": f"{py}-{pm:02d}", "prev_year": ANNUAL_COLS[year_col],
                "assets": assets, "liabilities": liabilities, "totals": totals}
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 자산 이력 읽기 실패 ({type(e).__name__}: {e})")
        return {}


def fetch_monthly(today: Optional[date] = None) -> Dict[str, Any]:
    """★월별자산 → {periods, accounts} (대시보드 월별 흐름용). 실패 시 {}."""
    today = today or date.today()
    try:
        grid = sheet_grid()               # 캐시된 격자 (A1:BN40이 16행 범위를 덮는다)
        if grid is None:
            return {}
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


def month_summary(y: int, m: int) -> Dict[str, float]:
    """특정 달의 시트 기준 총자산·부채·순자산 소계. 그 달이 비었으면 {}.

    전월 대비 KPI의 폴백 기준값 — 우리 history.csv에 그 달 실측이 없을 때만 쓴다.
    시트는 부동산을 KB시세 대신 월 +0.9% 추정으로 굴리므로 우리 평가액과 몇 천만원
    어긋난다 (2026-07: 시트 32.40억 vs 우리 32.63억). 부채는 우리도 이 시트에서
    읽으므로 일치한다.
    """
    col = month_col(y, m)
    if col is None:
        return {}
    try:
        grid = sheet_grid()               # 캐시된 격자 (소계 25·37·38행을 포함한다)
        if grid is None:
            return {}

        def cell(row1: int) -> float:
            r = grid[row1 - 1] if len(grid) >= row1 else []
            v = r[col] if len(r) > col else 0
            return float(v) if isinstance(v, (int, float)) else 0.0

        out = {k: cell(r) for k, r in SUMMARY_ROWS.items()}
        if out["net"] <= 0:
            return {}
        return out
    except Exception as e:  # noqa: BLE001
        print(f"WARN: {y}-{m:02d} 시트 소계 읽기 실패 ({type(e).__name__}: {e})")
        return {}

