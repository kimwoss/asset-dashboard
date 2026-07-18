# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > 연간리뷰 → '우리 부부 연간 리뷰' 웹 탭.

돈만이 아닌 삶의 기록 — 연도별 베스트 여행지·카페·술·책·영화·음악·모먼트·프로젝트와
월별 추억. 두 사람만의 유일무이한 탭.

시트 구조: 1행에 연도 헤더가 두 칸 간격으로(2026=C, 2025=E, …, 2021=M). 각 연도는
'열 쌍' 하나를 차지한다(2026=C·D, 2025=E·F, …). 두 칸에 서로 다른 항목이 들어가기도
하고(취향 둘) 같은 값이 중복되기도 해서, 두 칸의 고유한 값만 모아 합친다.
  2~18행  베스트 OO (17개 카테고리, B열 라벨)
  19~30행 1월~12월 추억 (B열 라벨)
"""
from typing import Any, Dict, List

import sheets_fire

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "연간리뷰"
BLOCK = "A1:N32"
YEAR_ROW = 0                 # 0-indexed
BEST_ROWS = range(1, 18)     # 2~18행 (베스트 카테고리)
MONTH_ROWS = range(18, 30)   # 19~30행 (1~12월)
# 연도 → 열 쌍 (0-indexed). 헤더는 첫 칸에만 있고 데이터는 두 칸에 걸친다.
YEAR_COLS = {2026: (2, 3), 2025: (4, 5), 2024: (6, 7),
             2023: (8, 9), 2022: (10, 11), 2021: (12, 13)}


def _merge(grid: List[List], row: int, cols) -> str:
    """열 쌍의 고유한 비어있지 않은 값을 합친다 (중복·공백 제거)."""
    seen: List[str] = []
    for c in cols:
        v = str(grid[row][c]).strip() if row < len(grid) and c < len(grid[row]) else ""
        if v and v != "-" and v not in seen:
            seen.append(v)
    return " · ".join(seen)


def fetch_review() -> Dict[str, Any]:
    """연간리뷰 → {years, byYear:{year:{best:[{label,text}], months:[{label,text}]}}}. 실패 시 {}."""
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 연간 리뷰 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK)

        def label(r: int) -> str:
            return str(grid[r][1]).strip() if r < len(grid) and len(grid[r]) > 1 else ""

        years: List[int] = []
        by_year: Dict[str, Any] = {}
        for year, cols in sorted(YEAR_COLS.items(), reverse=True):
            best = [{"label": label(r), "text": _merge(grid, r, cols)} for r in BEST_ROWS]
            best = [b for b in best if b["label"] and b["text"]]
            months = [{"label": label(r), "text": _merge(grid, r, cols)} for r in MONTH_ROWS]
            months = [m for m in months if m["label"] and m["text"]]
            if not best and not months:
                continue  # 아직 안 채운 연도 (진행 중이거나 빈 슬롯)
            years.append(year)
            by_year[str(year)] = {"best": best, "months": months}

        if not years:
            print("WARN: 연간 리뷰 데이터 없음")
            return {}
        print(f"OK: 연간 리뷰 {len(years)}개년 ({years[-1]}~{years[0]})")
        return {"years": years, "byYear": by_year}
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 연간 리뷰 읽기 실패 ({type(e).__name__}: {e})")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_review()
    if d:
        for y in d["years"]:
            yr = d["byYear"][str(y)]
            print(f"\n=== {y} · 베스트 {len(yr['best'])}종 · 월 {len(yr['months'])}개 ===")
            for b in yr["best"][:4]:
                print(f"  {b['label']}: {b['text'][:50]}")
