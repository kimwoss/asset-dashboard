# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > 🌍이주 대시보드 → '살고싶은 도시' 웹 탭.

시트의 자동화(도시명 입력 → Numbeo 실시간 IMPORTHTML → 배율 → 도시별 생활비)는
Google Sheets 위에서만 돈다. 정적 호스팅인 웹은 브라우저에서 Numbeo를 직접 못 긁는다
(CORS·API키). 그래서 다른 탭들과 같은 원칙 — 시트가 원본, 웹은 그 결과를 미러링한다.
도시를 더하거나 바꾸려면 시트 4행에 도시명을 입력하면 되고, 다음 동기화 때 웹에 반영된다.

읽는 것: 도시별 월간 카테고리 생활비 · 월/연 합계 · 도시 FIRE 필요자금.
웹에서 재계산: 서울 대비 비율, 실시간 순자산 기준 달성률 (메인 FIRE 섹션과 일관되게).

파싱은 A열 라벨을 기준으로 한다 — 행이 밀리거나 항목이 늘어도 따라가도록.
"""
from datetime import date
from typing import Any, Dict, List, Optional

import sheets_fire  # 인증·스프레드시트 ID 재사용

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "🌍이주 대시보드"
BLOCK = "A1:N55"

HEADER_LABEL = "항목"          # 이 행 E~N에 도시명
STATUS_LABEL = "[데이터 상태]"
SEOUL_COL = 3                  # D열 (0-indexed) = 서울(기준)
CITY_COL_FIRST = 4            # E열부터 도시

# 월간 생활비 블록 경계 (A열 라벨)
MONTHLY_START = "[월간 생활비]"
MONTHLY_TOTAL = "월간 합계"
ANNUAL_TOTAL = "연간 합계"
AVG_MONTHLY = "평균 월 생활비"
ANNUAL_BUDGET = "연간 사용예산"
FIRE_TARGET_PREFIX = "FIRE 기본 필요자금"


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("₩", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def fetch_cities(today: Optional[date] = None) -> Dict[str, Any]:
    """🌍이주 대시보드 → {cities, seoul, categories, ...}. 실패 시 {} (탭만 숨김)."""
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 살고싶은 도시 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK, value_render_option="UNFORMATTED_VALUE")

        def cell(r0: int, c0: int) -> Any:
            row = grid[r0] if r0 < len(grid) else []
            return row[c0] if c0 < len(row) else ""

        def label(r0: int) -> str:
            return str(cell(r0, 0)).strip()

        # 1) 헤더 행 — 도시명. 서울(D) + 도시(E~N) 중 값이 있는 열만.
        hdr = next((r for r in range(len(grid)) if label(r) == HEADER_LABEL), None)
        if hdr is None:
            print("WARN: 이주 대시보드 헤더('항목') 못 찾음")
            return {}
        status_row = next((r for r in range(len(grid)) if label(r) == STATUS_LABEL), None)

        def col_name(c0: int) -> str:
            return str(cell(hdr, c0)).strip()

        city_cols = [c for c in range(CITY_COL_FIRST, len(grid[hdr]) if hdr < len(grid) else 0)
                     if col_name(c)]

        # 2) 월간 카테고리 행 (블록 시작 ~ '월간 합계' 사이, 라벨 있는 행)
        m_start = next((r for r in range(len(grid)) if label(r).startswith(MONTHLY_START)), None)
        m_total = next((r for r in range(len(grid)) if label(r) == MONTHLY_TOTAL), None)
        cat_rows: List[int] = []
        if m_start is not None and m_total is not None:
            for r in range(m_start + 1, m_total):
                lab = label(r)
                if lab and not lab.startswith("["):
                    cat_rows.append(r)

        # 결과 행들
        row_of = lambda pred: next((r for r in range(len(grid)) if pred(label(r))), None)
        r_avg = row_of(lambda l: l == AVG_MONTHLY)
        r_budget = row_of(lambda l: l == ANNUAL_BUDGET)
        r_annual = row_of(lambda l: l == ANNUAL_TOTAL)
        r_fire = row_of(lambda l: l.startswith(FIRE_TARGET_PREFIX))

        categories_meta = [{"name": label(r), "group": str(cell(r, 1)).strip()} for r in cat_rows]

        def build(c0: int, name: str, status: str = "") -> Dict[str, Any]:
            return {
                "name": name,
                "status": status,
                "categories": [round(_num(cell(r, c0))) for r in cat_rows],
                "monthly_total": round(_num(cell(m_total, c0))) if m_total is not None else 0,
                "annual_fixed": round(_num(cell(r_annual, c0))) if r_annual is not None else 0,
                "avg_monthly": round(_num(cell(r_avg, c0))) if r_avg is not None else 0,
                "annual_budget": round(_num(cell(r_budget, c0))) if r_budget is not None else 0,
                "fire_target": round(_num(cell(r_fire, c0))) if r_fire is not None else 0,
            }

        seoul = build(SEOUL_COL, str(cell(hdr, SEOUL_COL)).strip() or "서울")
        cities = []
        for c in city_cols:
            st = str(cell(status_row, c)).strip() if status_row is not None else ""
            cities.append(build(c, col_name(c), st))

        if not cities or seoul["avg_monthly"] <= 0:
            print("WARN: 이주 대시보드 도시/서울 값 없음 — 생략")
            return {}

        out = {
            "seoul": seoul,
            "cities": cities,
            "categories": categories_meta,
        }
        print(f"OK: 살고싶은 도시 {len(cities)}곳 · 서울 월 {seoul['avg_monthly']/1e4:,.0f}만원 기준")
        return out
    except Exception as e:  # noqa: BLE001 — 자산추적을 죽이지 않는다
        print(f"WARN: 살고싶은 도시 읽기 실패 ({type(e).__name__}: {e})")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_cities()
    if d:
        s = d["seoul"]
        print(f"\n서울: 월 {s['avg_monthly']:,} · FIRE {s['fire_target']/1e8:.2f}억")
        print(f"\n{'도시':<26}{'상태':<8}{'월생활비':>12}{'서울대비':>9}{'FIRE필요':>10}")
        for c in sorted(d["cities"], key=lambda x: x["avg_monthly"]):
            vs = c["avg_monthly"] / s["avg_monthly"] * 100
            print(f"{c['name'][:25]:<26}{c['status']:<8}{c['avg_monthly']:>12,}{vs:>8.0f}%{c['fire_target']/1e8:>9.2f}억")
        print(f"\n카테고리: {[m['name'] for m in d['categories']]}")
