# -*- coding: utf-8 -*-
"""시각화 탭의 '연도별 소득·지출 요약' 표를 읽는다 (A56:E…).

왜 시트에 표를 따로 뒀나 — 연도별 가계부 원장은 시대마다 구조가 다르다.
  2026년      한 탭에 월별 7열 블록 (소득/고정비/변동비)
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


def fetch_annual_flow() -> List[Dict[str, Any]]:
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
        if not out:
            print("WARN: 시각화 연도별 소득·지출 표가 비어 있음")
        else:
            print(f"OK: 연도별 소득·지출 {len(out)}개년 "
                  f"({out[-1]['year']}~{out[0]['year']})")
        return out
    except Exception as e:  # noqa: BLE001 — 이 표가 없어도 나머지 대시보드는 살아야 한다
        print(f"WARN: 연도별 소득·지출 읽기 실패 ({type(e).__name__}: {e})")
        return []
