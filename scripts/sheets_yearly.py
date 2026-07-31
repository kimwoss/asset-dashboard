# -*- coding: utf-8 -*-
"""★연도별자산(자동수식) — 대시보드의 '현재값' 단일 참조점.

★월별자산은 매월 새 열이 생겨(7월→8월…) '이번 달 열'을 계산해 참조해야 하고, 탭 이름에
연도가 박혀 있어(★월별자산(2026년)) 해가 바뀌면 깨진다. 반면 ★연도별자산은 영구 탭에
연도 열(F=2021 … K=2026 … M=2028)이 있고, 사용자가 각 연도 열을 그 해의 '최신값'으로
유지한다(월별 최신 열을 자동수식으로 미러). 그래서 '지금 값'은 이 탭의 '올해 열'에서 읽는다.

행 구조는 ★월별자산과 동일하므로 sheets_monthly의 행 상수·정규화를 그대로 재사용한다.
  계좌 3~15 · 회사주식 17 · 외화 18 · 부동산 20~23 · 대출 26~32 · 전세보증금 34~35 · 소계 25/37/38

담당: 부채·회사주식/외화(순자산 구성)·자산 증감(전년=연도별, 전월=월별 위임).
월별 흐름 차트·시트 기록(월별 열에 저장)은 여전히 ★월별자산이 원본이다.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

import sheets_fire
import sheets_monthly as sm  # 행 상수·정규화·prev-month 위임 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "★연도별자산(자동수식)"

YEAR_COL_FIRST = 5   # F열 = 2021 (0-indexed)
YEAR_BASE = 2021
YEAR_COL_LAST = 12   # M열 = 2028
_BLOCK = "A1:M40"


def year_col(year: int) -> Optional[int]:
    """연도 → 0-indexed 열. 범위 밖이면 None. (2021=F … 2026=K … 2028=M)"""
    c = YEAR_COL_FIRST + (year - YEAR_BASE)
    return c if YEAR_COL_FIRST <= c <= YEAR_COL_LAST else None


def _grid(today: date):
    """★연도별자산 격자 — 이제 '전년 비교'에만 쓴다 (현재값은 아래 _current 로 옮겼다)."""
    import gspread
    gc = sheets_fire._authorize(gspread)
    if gc is None:
        return None
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
    return ws.get(_BLOCK, value_render_option="UNFORMATTED_VALUE")


def _current(today: date):
    """현재값의 원천 → (★월별자산 격자, 그 달 열, 'YYYY-MM' 라벨).

    종전엔 ★연도별자산 올해 열(K)을 현재값으로 읽었다. 그런데 그 열은 자동이 아니라
    사용자가 매월 36개 수식을 손으로 W→Y처럼 옮겨 붙이는 수동 미러였다. 옮기는 걸
    잊으면 지난달 숫자가 새 달 내내 조용히 표시된다(2026-08에 실제로 그럴 뻔했다).

    그래서 원본인 ★월별자산에서 '완성된 최신 달'을 직접 찾아 쓴다 — 수식을 손볼 일이
    사라지고, 자산·부채가 같은 달에서 나와 섞이지 않는다.
    """
    import gspread
    gc = sheets_fire._authorize(gspread)
    if gc is None:
        return None, None, ""
    ws = gc.open_by_key(sm.SPREADSHEET_ID).worksheet(sm.TAB)
    grid = ws.get("A1:BN40", value_render_option="UNFORMATTED_VALUE")
    col, y, m = sm.latest_complete_month(grid, today)
    if col is None:
        print("WARN: ★월별자산에 자산·부채가 모두 채워진 달이 없음")
        return grid, None, ""
    return grid, col, f"{y}-{m:02d}"


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v or ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _cell(grid, r1: int, c0: Optional[int]) -> float:
    if c0 is None:
        return 0.0
    r = grid[r1 - 1] if len(grid) >= r1 else []
    v = r[c0] if len(r) > c0 else 0
    return float(v) if isinstance(v, (int, float)) else 0.0


def _label(grid, r1: int) -> str:
    r = grid[r1 - 1] if len(grid) >= r1 else []
    return str(r[2]).strip() if len(r) > 2 else ""


def fetch_liabilities(today: Optional[date] = None) -> List[Dict]:
    """★연도별자산 올해 열에서 대출·전세보증금 잔액을 읽는다. 실패/빈 결과 시 [] → yaml 폴백."""
    today = today or date.today()
    try:
        grid, col, asof = _current(today)
        if grid is None or col is None:
            return []
        out: List[Dict] = []
        for r, (kind, target) in sm.LIAB_ROWS.items():
            name = _label(grid, r)
            amount = _cell(grid, r, col)
            if not name or amount <= 0:
                continue
            owner_raw = str(grid[r-1][3]).strip() if len(grid) >= r and len(grid[r-1]) > 3 else ""
            owner = sm._OWNER_KR.get(owner_raw, owner_raw or "공동")
            out.append({
                "name": name, "owner": owner, "kind": kind, "target": target,
                "amount_krw": round(amount),
                "note": f"★월별자산 {asof}" + (" · 파크하비오 보증금 조달" if r == 30 else ""),
            })
        total = sum(l["amount_krw"] for l in out)
        print(f"OK: 부채 {len(out)}건 {total/1e8:.2f}억 (★월별자산 {asof})")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 부채 읽기 실패 ({type(e).__name__}: {e}) — yaml 폴백")
        return []


def fetch_other_assets(today: Optional[date] = None) -> int:
    """★연도별자산 올해 열의 회사주식·원달러/엔화 합. 없으면 0."""
    today = today or date.today()
    try:
        grid, col, _asof = _current(today)
        if grid is None or col is None:
            return 0
        total = 0.0
        for r in range(sm.RE_ROW_FIRST, sm.RE_ROW_LAST + 1):
            label = _label(grid, r).replace(" ", "")
            if any(k in label for k in ("회사주식", "원달러", "엔화", "외화")):
                total += _cell(grid, r, col)
        return round(total)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 회사주식·외화 읽기 실패 ({type(e).__name__}: {e})")
        return 0


def fetch_residence_deposits(today: Optional[date] = None) -> List[Dict]:
    """★연도별자산 올해 열의 거주 전세보증금(파크하비오·인텔리지 전세, 받을 돈).

    부동산 영역(20~23행) 중 라벨에 '전세'가 든 행 = 거주용으로 맡긴 전세보증금(자산).
    소유 아파트(인덕원삼호·송천센트레빌)는 '전세'가 없어 자동 제외.
    반환 [{name, owner, value_krw, note}], 실패/빈 결과 시 [] → 호출자가 yaml 폴백.
    """
    today = today or date.today()
    try:
        grid, col, asof = _current(today)
        if grid is None or col is None:
            return []
        out: List[Dict] = []
        for r in range(sm.RE_ROW_FIRST, sm.RE_ROW_LAST + 1):
            label = _label(grid, r)
            if "전세" not in label.replace(" ", ""):
                continue
            amount = _cell(grid, r, col)
            if amount <= 0:
                continue
            owner_raw = str(grid[r - 1][3]).strip() if len(grid) >= r and len(grid[r - 1]) > 3 else ""
            owner = sm._OWNER_KR.get(owner_raw, owner_raw or "공동")
            out.append({"name": label, "owner": owner, "value_krw": round(amount),
                        "note": f"★월별자산 {asof} 기준"})
        if out:
            total = sum(d["value_krw"] for d in out)
            print(f"OK: 거주 전세보증금 {len(out)}건 {total/1e8:.2f}억 (★월별자산 {asof})")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 거주 전세보증금 읽기 실패 ({type(e).__name__}: {e}) — yaml 폴백")
        return []


def fetch_asset_history(today: Optional[date] = None) -> Dict[str, Any]:
    """자산 상세 증감용 — 현재·전월은 ★월별자산, 전년은 ★연도별자산(작년 열).

    현재값은 ★월별자산의 '완성된 최신 달'에서 읽는다(자산·부채가 둘 다 채워진 달).
    전년 비교만 ★연도별자산에 남는다 — 그 탭은 연 1회만 손대면 되므로 수동 미러의
    위험이 없다.

    반환 구조는 sheets_monthly.fetch_asset_history와 동일: {prev_month, prev_year,
    assets:{key:{cur,m1,y1}}, liabilities:{...}, totals:{k:{m1,y1}}}.
    """
    today = today or date.today()
    try:
        grid, cur_c, asof = _current(today)          # 현재 = ★월별자산 최신 완성 달
        ygrid = _grid(today)                          # 전년 = ★연도별자산
        y1_c = year_col(today.year - 1)
        if grid is None or cur_c is None:
            return {}
        # 전년 격자를 못 읽으면 y1만 0으로 두고 현재·전월은 그대로 낸다
        yc = (lambda r: round(_cell(ygrid, r, y1_c))) if (ygrid is not None and y1_c is not None) else (lambda r: 0)

        # 전월 값은 ★월별자산이 원본 — 월별 리더에서 그대로 가져온다.
        m_hist = sm.fetch_asset_history(today) or {}
        m_assets = m_hist.get("assets", {})
        m_liab = m_hist.get("liabilities", {})
        m_tot = m_hist.get("totals", {})

        assets: Dict[str, Dict] = {}
        acct_rows = sm._account_rows(grid)
        for owner in ("우현", "규리"):
            rows = [r for r, (n, o) in acct_rows.items() if o == owner]
            if rows:
                key = f"계좌:{owner}"
                assets[key] = {
                    "cur": round(sum(_cell(grid, r, cur_c) for r in rows)),
                    "m1": (m_assets.get(key) or {}).get("m1", 0),
                    "y1": sum(yc(r) for r in rows),
                }
        for r in range(sm.RE_ROW_FIRST, sm.RE_ROW_LAST + 1):
            lab = _label(grid, r)
            if not lab or "주식" in lab or "원달러" in lab:
                continue
            if _cell(grid, r, cur_c) or yc(r):
                assets[lab] = {"cur": round(_cell(grid, r, cur_c)),
                               "m1": (m_assets.get(lab) or {}).get("m1", 0),
                               "y1": yc(r)}
        liabilities: Dict[str, Dict] = {}
        for r in sm.LIAB_ROWS:
            lab = _label(grid, r)
            if lab and (_cell(grid, r, cur_c) or yc(r)):
                liabilities[lab] = {"cur": round(_cell(grid, r, cur_c)),
                                    "m1": (m_liab.get(lab) or {}).get("m1", 0),
                                    "y1": yc(r)}
        totals = {k: {"m1": (m_tot.get(k) or {}).get("m1", 0), "y1": yc(r)}
                  for k, r in sm.SUMMARY_ROWS.items()}

        print(f"OK: 자산 이력 — 자산 {len(assets)}종 · 부채 {len(liabilities)}종 "
              f"(현재 ★월별자산 {asof} · 전월 ★월별자산 · 전년 ★연도별자산 {today.year-1})")
        return {"prev_month": m_hist.get("prev_month", ""), "prev_year": str(today.year - 1),
                "assets": assets, "liabilities": liabilities, "totals": totals}
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 자산 이력 읽기 실패 ({type(e).__name__}: {e})")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("year_col(2026) =", year_col(2026))
    for l in fetch_liabilities():
        print(f"  {l['name']:<22} {l['owner']:<4} {l['amount_krw']:>14,}")
    print("회사주식·외화:", f"{fetch_other_assets():,}")
