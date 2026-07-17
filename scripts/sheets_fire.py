# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > ★종합 탭의 'FIRE 결과 요약'을 읽어온다.

대시보드에 은퇴 목표(FIRE) 트래킹을 이식하기 위한 읽기 전용 모듈.
자산 평가(KB/yfinance)는 대시보드가 실시간으로 계산하고, 이 모듈은
'목표·가정치'(목표금액, 목표연도, 은퇴 후 생활비, 소진 나이 등)만 가져온다.

인증 (우선순위):
  1. GOOGLE_SHEETS_CREDENTIALS       환경변수에 서비스계정 JSON 문자열 (GitHub Actions)
  2. GOOGLE_SHEETS_CREDENTIALS_FILE  환경변수에 JSON 파일 경로 (로컬 테스트)
  3. config/credentials.json         (gitignore — 로컬 폴백)

실패는 절대 파이프라인을 죽이지 않는다 — 예외 시 {} 반환, 대시보드는 FIRE 섹션만 숨긴다.
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

SPREADSHEET_ID = "13xGH_kjWZbkNW_Me03pdVPkMjtmtDRcRZ8T2_Bz5SDc"
SHEET_NAME = "★종합"
ROOT = Path(__file__).resolve().parent.parent

# 규리는 우현보다 8살 아래 (2026-07 사용자 확인). ★종합의 나이는 전부 우현 기준이라
# 대시보드에 두 사람 나이를 병기하려면 이 차이가 필요하다.
SPOUSE_AGE_GAP = 8

# 레이블 → (결과키, 열 인덱스). 값은 레이블 오른쪽 n번째 비어있지 않은 셀.
_LABEL_MAP: Dict[str, List[Union[str, Tuple[str, int]]]] = {
    "net_worth":        ["현재 순자산"],
    "retire_asset":     ["은퇴 시점 예상 자산"],
    "target_basic":     [("은퇴 필요 총자금(기본/부자)", 0)],
    "target_rich":      [("은퇴 필요 총자금(기본/부자)", 1)],
    "pct_basic":        [("목표 달성률", 0)],
    "pct_rich":         [("목표 달성률", 1)],
    "depletion_raw":    ["자산 소진 예상 나이"],
    "real_return":      ["세후 실질수익률"],
    "monthly_expense":  ["은퇴시점 월생활비 (물가반영)"],
    "monthly_net_spend":["은퇴 후 월 순지출 (고정지출 포함)"],
    "current_age":      ["현재 나이"],
    "current_year":     ["현재 연도"],
    "retire_age":       ["은퇴 목표 나이"],
    "accum_years":      ["적립 기간"],
    "life_expectancy":  ["기대 수명"],
}
_PCT_KEYS = {"pct_basic", "pct_rich", "real_return"}
_STR_KEYS = {"depletion_raw"}


def fetch_fire_summary() -> Dict[str, Any]:
    """★종합 결과 요약 dict. 실패 시 {} (파이프라인 비중단)."""
    try:
        import gspread  # 지연 import — 미설치 환경에서도 나머지 파이프라인 동작
        gc = _authorize(gspread)
        if gc is None:
            print("WARN: FIRE 시트 인증정보 없음 — FIRE 섹션 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        rows = ws.get_all_values()
        data = _parse_rows(rows)
        if not data.get("net_worth"):
            print("WARN: FIRE 시트 파싱 실패(net_worth 없음) — FIRE 섹션 생략")
            return {}
        return _derive(data)
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 대시보드 자산추적은 지켜야 한다
        print(f"WARN: FIRE 시트 읽기 실패 ({type(e).__name__}: {e}) — FIRE 섹션 생략")
        return {}


def _authorize(gspread):
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "").strip()
    if raw:
        return gspread.service_account_from_dict(json.loads(raw))
    path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "").strip()
    if path and Path(path).exists():
        return gspread.service_account(filename=path)
    local = ROOT / "config" / "credentials.json"
    if local.exists():
        return gspread.service_account(filename=str(local))
    return None


def _parse_rows(rows: List[List[str]]) -> Dict[str, Any]:
    """레이블 오른쪽 첫 2개 비어있지 않은 값 수집 (first-wins)."""
    row_data: Dict[str, List[str]] = {}
    for row in rows:
        for c, cell in enumerate(row):
            label = cell.strip()
            if not label or label in row_data:
                continue
            right: List[str] = []
            for c2 in range(c + 1, len(row)):
                v = row[c2].strip()
                if v:
                    right.append(v)
                    if len(right) == 2:
                        break
            if right:
                row_data[label] = right

    out: Dict[str, Any] = {}
    for key, specs in _LABEL_MAP.items():
        for spec in specs:
            if isinstance(spec, tuple):
                lname, idx = spec
                vals = row_data.get(lname, [])
                if len(vals) > idx:
                    out[key] = _coerce(key, vals[idx])
                    break
            else:
                vals = row_data.get(spec, [])
                if vals:
                    out[key] = _coerce(key, vals[0])
                    break
    return out


def _coerce(key: str, raw: str) -> Any:
    if key in _STR_KEYS:
        return raw
    if key in _PCT_KEYS:
        m = re.search(r"[\d.]+", raw.replace(",", ""))
        if not m:
            return 0.0
        v = float(m.group())
        return v if v > 1 else v * 100  # 0.77 → 77
    cleaned = raw.replace(",", "").replace("원", "").replace(" ", "")
    m = re.search(r"\d+", cleaned)
    return int(m.group()) if m else 0


def _derive(d: Dict[str, Any]) -> Dict[str, Any]:
    """파생값 추가 — 목표연도, 소진 나이 숫자, 배우자 나이 기준."""
    year, accum = d.get("current_year") or 0, d.get("accum_years")
    if 2000 <= year <= 2100 and accum is not None and 0 <= accum <= 60:
        d["target_year"] = year + accum
    m = re.search(r"\d+", d.get("depletion_raw", ""))
    if m:
        d["depletion_age"] = int(m.group())
    # 시트의 나이는 전부 우현 기준 한 사람 것뿐이다. 대시보드가 규리 나이를 함께
    # 적으려면 나이차가 필요한데 시트엔 없어 여기서 넘긴다 (2026-07 사용자 확인).
    d["age_self"], d["age_spouse"], d["age_gap"] = "우현", "규리", SPOUSE_AGE_GAP
    return d


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from pprint import pprint
    pprint(fetch_fire_summary())
