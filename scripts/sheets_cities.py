# -*- coding: utf-8 -*-
"""Mirror the migration sheet. Missing costs must never become zero or stale success."""
from datetime import date, datetime, timezone
import math
from typing import Any, Dict, Optional

import sheets_fire

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "🌍이주 대시보드"
BLOCK = "A1:O60"
SEOUL_COL = 3
CITY_COL_FIRST = 4


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(str(value).replace(",", "").replace("₩", "").strip())
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_cities(grid) -> Dict[str, Any]:
    def cell(row, col):
        return grid[row][col] if row is not None and row < len(grid) and col < len(grid[row]) else ""

    def label(row):
        return str(cell(row, 0)).strip()

    def row_of(text, prefix=False):
        return next((r for r in range(len(grid))
                     if (label(r).startswith(text) if prefix else label(r) == text)), None)

    header = row_of("항목")
    monthly_start, monthly_end = row_of("[월간 생활비]", True), row_of("월간 합계")
    rows = {"monthly_total": monthly_end, "annual_fixed": row_of("연간 합계"),
            "avg_monthly": row_of("평균 월 생활비"), "annual_budget": row_of("연간 사용예산"),
            "fire_target": row_of("FIRE 기본 필요자금", True)}
    if header is None or monthly_start is None or any(r is None for r in rows.values()):
        raise ValueError("도시 시트 필수 행 누락")
    categories = [r for r in range(monthly_start + 1, monthly_end) if label(r) and not label(r).startswith("[")]
    if not categories:
        raise ValueError("도시 시트 월간 항목 누락")
    status_row = row_of("[데이터 상태]")

    def build(col):
        costs = [_number(cell(r, col)) for r in categories]
        totals = {key: _number(cell(row, col)) for key, row in rows.items()}
        missing = [label(r) for r, v in zip(categories, costs) if v is None]
        missing += [label(rows[key]) for key, v in totals.items() if v is None]
        if missing:
            return None, "자료 없음·계산 오류: " + ", ".join(missing)
        if any(totals[key] <= 0 for key in ("avg_monthly", "annual_budget", "fire_target")):
            return None, "생활비·FIRE 필요자금이 0 이하"
        if (abs(sum(costs) - totals["monthly_total"]) > 2
                or abs(totals["monthly_total"] * 12 + totals["annual_fixed"] - totals["annual_budget"]) > 2
                or abs(totals["avg_monthly"] * 12 - totals["annual_budget"]) > 2):
            return None, "월간 항목·연간 합계 불일치"
        return {"name": str(cell(header, col)).strip(), "status": str(cell(status_row, col)).strip(),
                "categories": [round(v) for v in costs], **{key: round(v) for key, v in totals.items()}}, None

    seoul, error = build(SEOUL_COL)
    if error:
        raise ValueError("서울 기준 계산 오류: " + error)
    cities, broken, details = [], [], []
    for col in range(CITY_COL_FIRST, len(grid[header])):
        name = str(cell(header, col)).strip()
        if not name:
            continue
        city, error = build(col)
        if error:
            broken.append(name)
            details.append({"name": name, "reason": error})
        else:
            cities.append(city)
    # Publish a successfully read source error, even when no city is valid.
    # Returning {} here would silently preserve obsolete values in the cache.
    return {"seoul": seoul, "cities": cities, "broken": broken, "broken_details": details,
            "categories": [{"name": label(r), "group": str(cell(r, 1)).strip()} for r in categories]}


def fetch_cities(today: Optional[date] = None) -> Dict[str, Any]:
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        result = parse_cities(ws.get(BLOCK, value_render_option="UNFORMATTED_VALUE"))
        result["fetched_at"] = datetime.now(timezone.utc).isoformat()
        print(f"OK: 후보 도시 {len(result['cities'])}곳 · 원본 오류 {len(result['broken'])}곳")
        return result
    except Exception as error:
        print(f"WARN: 후보 도시 읽기 실패 ({type(error).__name__}: {error})")
        return {}
