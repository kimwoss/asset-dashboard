# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > 시뮬레이션 → '은퇴 100세 지도' 웹 탭.

시트에 39세→108세 연도별 순자산 궤적이 이미 계산돼 있다(적립→인출 단계 전환,
투자수익·연지출·의료비·연금·저축, 그리고 실질가치=오늘 돈 기준). 증권앱·가계부엔
없는 장기 자산 궤적 — 웹은 이 결과를 읽어 라인차트로 보여준다(계산은 시트가 원본).

주의: 순자산이 소진나이(≈97세)에 0을 지난 뒤 모델은 부채나선(투자수익이 음수로
치닫는 비현실적 구간)이 된다. 그 뒤 데이터도 넘기되, 실제 표시 절단은 웹이 판단한다.
"""
import re
from typing import Any, Dict, List, Optional

import sheets_fire

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "시뮬레이션"
BLOCK = "A1:N90"
HEADER_LABEL = "나이"          # 이 행부터 연도별 데이터
# 데이터 열 (0-indexed): A나이 B연도 C단계 D순자산 E투자수익 F연지출 G의료 H연금 I은퇴후소득 J저축 M실질순자산
COL = {"age": 0, "year": 1, "phase": 2, "net": 3, "invest": 4, "spend": 5,
       "medical": 6, "pension": 7, "retire_income": 8, "saving": 9, "real_net": 12}


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v or ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _find(grid: List[List], label: str) -> Optional[tuple]:
    """라벨 셀 위치 (row, col) 0-indexed. 없으면 None."""
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            if str(v).strip() == label:
                return (r, c)
    return None


def _right(grid: List[List], label: str) -> Any:
    """라벨 오른쪽 첫 비어있지 않은 셀 값."""
    pos = _find(grid, label)
    if not pos:
        return ""
    r, c = pos
    for cc in range(c + 1, len(grid[r])):
        if str(grid[r][cc]).strip():
            return grid[r][cc]
    return ""


def fetch_simulation() -> Dict[str, Any]:
    """시뮬레이션 → {summary, retire_age, depletion_age, series}. 실패 시 {}."""
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증 없음 — 은퇴 지도 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        grid = ws.get(BLOCK, value_render_option="UNFORMATTED_VALUE")

        hdr = _find(grid, HEADER_LABEL)
        if not hdr:
            print("WARN: 시뮬레이션 헤더('나이') 못 찾음")
            return {}
        hr = hdr[0]

        series: List[Dict] = []
        for r in range(hr + 1, len(grid)):
            row = grid[r]
            age = _num(row[COL["age"]] if len(row) > COL["age"] else 0)
            if age < 20 or age > 120:
                continue
            def g(k):
                i = COL[k]
                return round(_num(row[i])) if len(row) > i else 0
            series.append({
                "age": int(age),
                "year": str(row[COL["year"]]).strip() if len(row) > COL["year"] else "",
                "phase": str(row[COL["phase"]]).strip() if len(row) > COL["phase"] else "",
                "net": g("net"), "real_net": g("real_net"),
                "invest": g("invest"), "spend": g("spend"),
                "medical": g("medical"), "pension": g("pension"), "saving": g("saving"),
            })
        if not series:
            print("WARN: 시뮬레이션 데이터 없음")
            return {}

        # 은퇴 나이 = 처음 '인출' 단계, 소진 나이 = 순자산이 처음 0 미만이 되는 나이
        retire_age = next((s["age"] for s in series if "인출" in s["phase"]), None)
        depletion_age = next((s["age"] for s in series if s["net"] < 0), None)
        # 시트 요약 텍스트의 소진나이도 파싱 (우선)
        dep_txt = str(_right(grid, "자산소진 예상나이"))
        m = re.search(r"(\d+)\s*세", dep_txt)
        if m:
            depletion_age = int(m.group(1))

        summary = {
            "retire_asset": round(_num(_right(grid, "은퇴시점 자산"))),
            "target_basic": round(_num(_right(grid, "은퇴필요 기본자금"))),
            "target_rich": round(_num(_right(grid, "은퇴 부자자금"))),
            "real_net_now": series[0]["real_net"],
            "end_age": series[-1]["age"],
            "real_net_end": series[-1]["real_net"],
        }
        print(f"OK: 은퇴 지도 {len(series)}개년({series[0]['age']}~{series[-1]['age']}세) · "
              f"은퇴 {retire_age}세 · 소진 {depletion_age}세")
        return {"summary": summary, "retire_age": retire_age,
                "depletion_age": depletion_age, "series": series}
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 은퇴 지도 읽기 실패 ({type(e).__name__}: {e})")
        return {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_simulation()
    if d:
        s = d["summary"]
        print(f"\n은퇴시점 자산 {s['retire_asset']/1e8:.1f}억 · 소진 {d['depletion_age']}세")
        for x in d["series"][::5]:
            print(f"  {x['age']}세 {x['phase']:4} 순자산 {x['net']/1e8:7.2f}억 · 실질 {x['real_net']/1e8:7.2f}억")
