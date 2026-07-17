# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > ★주식계좌 탭의 계좌별 보유내역을 읽어온다.

시트가 원 소스(source of truth) — 평가액은 시트의 GOOGLEFINANCE 계산값을 그대로 쓴다.
배당금만 yfinance 실지급 이력(최근 12개월)으로 보강한다.

  연 배당(세전) = 수량 × TTM 주당배당 × (USD면 환율)
  연 배당(세후) = 세전 × (1 − 계좌별 세율)   ← 같은 종목도 계좌에 따라 세금이 다르다
  월별 배당      = TTM 실지급월에 배분 (분기 종목은 해당 분기월에만 계상)

실패는 파이프라인을 죽이지 않는다 — 예외 시 {} 반환, 대시보드는 금융자산 탭만 비운다.
"""
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sheets_fire  # 인증 재사용 (_authorize)

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "★주식계좌"
DATA_RANGE = "A4:K42"
FX_CELL = "H1"

# 연금성 계좌 판별 (인출 제약) — 그 외는 유동성
_PENSION_PAT = ("연저펀", "IRP", "퇴직연금", "연금저축")


def _group_of(account: str) -> str:
    return "연금성" if any(p in account for p in _PENSION_PAT) else "유동성"


def _tax_for(account: str, currency: str) -> Tuple[float, str]:
    """계좌 성격별 배당 원천징수율 (수령 시점 기준).

    연금계좌는 수령 시 과세하지 않고 인출 때 연금소득세(3.3~5.5%)를 낸다 — 과세이연.
    ISA는 순이익 200만원(서민형 400만원)까지 비과세, 초과분 9.9% 분리과세.
    일반계좌: 국내 상장 15.4%(배당소득세 14%+지방세 1.4%),
              미국 상장은 현지 15% 원천징수로 종결(외국납부세액공제로 국내 추가징수 없음).
    ※ 금융소득 2천만원 초과 시 종합과세 — 현재 합계는 그 아래.
    """
    if any(p in account for p in _PENSION_PAT):
        return 0.0, "연금계좌 과세이연 (인출 시 3.3~5.5%)"
    if "ISA" in account:
        return 0.0, "ISA 비과세 한도 내 (초과분 9.9%)"
    if (currency or "").upper() == "USD":
        return 0.15, "미국 원천징수 15%"
    return 0.154, "배당소득세 15.4%"


def _yf_symbol(ticker: str) -> str:
    """시트 티커 → yfinance 심볼. KRX:360750 → 360750.KS / SCHD → SCHD"""
    t = (ticker or "").strip()
    if t.upper().startswith("KRX:"):
        return t.split(":", 1)[1] + ".KS"
    return t


def _ttm_dividend(symbol: str, today: Optional[date] = None) -> Tuple[float, Dict[int, float]]:
    """최근 12개월 주당 배당 (합계, {월: 주당액}). 없으면 (0, {}).

    창은 '오늘 − 365일 초과'. 구버전은 '마지막 지급일 − 365일 이상'이라 경계 지급분이
    중복 포함돼 분기 종목이 연 5회로 잡혔다 (RISE200 +46%, S&P500 +33%, SCHD +25% 과장).
    """
    today = today or date.today()
    try:
        import pandas as pd
        import yfinance as yf
        d = yf.Ticker(symbol).dividends
        if d is None or len(d) == 0:
            return 0.0, {}
        cutoff = pd.Timestamp(today - timedelta(days=365))
        if d.index.tz is not None:
            cutoff = cutoff.tz_localize(d.index.tz)
        recent = d[d.index > cutoff]        # 초과 — 경계 중복 방지
        by_month: Dict[int, float] = {}
        for ts, v in recent.items():
            by_month[ts.month] = by_month.get(ts.month, 0.0) + float(v)
        return float(recent.sum()), by_month
    except Exception as e:  # noqa: BLE001
        print(f"WARN: {symbol} 배당 조회 실패 ({e})")
        return 0.0, {}


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v or ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_holdings() -> Dict[str, Any]:
    """★주식계좌 → {fx, holdings:[...]} . 실패 시 {}."""
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증정보 없음 — 금융자산 탭 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        fx = _num(ws.acell(FX_CELL, value_render_option="UNFORMATTED_VALUE").value)
        rows = ws.get(DATA_RANGE, value_render_option="UNFORMATTED_VALUE")

        holdings: List[Dict] = []
        last_account = ""
        div_cache: Dict[str, Tuple[float, Dict[int, float]]] = {}

        for r in rows:
            r = (list(r) + [""] * 11)[:11]
            account, owner, kind, ticker, name, qty, cur = (
                str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip(),
                str(r[3]).strip(), str(r[4]).strip(), r[5], str(r[6]).strip(),
            )
            # 계좌 셀 병합 → 빈 칸은 직전 계좌명 이어받기
            if account:
                last_account = account
            else:
                account = last_account
            if not owner:
                continue  # 빈 행
            value_krw = round(_num(r[9]))
            price = _num(r[7])
            qty_n = _num(qty)

            div_ps, by_month = 0.0, {}
            if ticker:
                sym = _yf_symbol(ticker)
                if sym not in div_cache:
                    div_cache[sym] = _ttm_dividend(sym)
                div_ps, by_month = div_cache[sym]
            rate = fx if cur.upper() == "USD" else 1.0
            # 월별 세전 배당 (1~12월) — TTM 실지급월에만 계상.
            # 연간은 월별 합으로 잡는다 → 월별 차트와 연간 카드가 항상 일치 (반올림 오차 제거)
            div_months = [round(qty_n * by_month.get(m, 0.0) * rate) for m in range(1, 13)]
            div_krw = sum(div_months)
            tax_rate, tax_note = _tax_for(account, cur)

            holdings.append({
                "account": account,
                "owner": owner,
                "kind": kind,                    # 투자 / 현금
                "group": _group_of(account),     # 연금성 / 유동성
                "ticker": ticker,
                "name": name or account,
                "qty": qty_n,
                "currency": cur or "KRW",
                "price": price,
                "value_krw": value_krw,
                "div_per_share": div_ps,
                "div_krw": div_krw,              # 연 세전
                "div_net_krw": round(div_krw * (1 - tax_rate)),
                "div_months": div_months,        # 월별 세전 (세후는 ×(1-tax_rate))
                "tax_rate": tax_rate,
                "tax_note": tax_note,
            })

        if not holdings:
            print("WARN: ★주식계좌 보유내역 없음")
            return {}
        total = sum(h["value_krw"] for h in holdings)
        div = sum(h["div_krw"] for h in holdings)
        div_net = sum(h["div_net_krw"] for h in holdings)
        print(f"OK: 금융자산 {len(holdings)}건 총 {total/1e8:.2f}억 · "
              f"연 배당 세전 {div/1e4:,.0f}만원 → 세후 {div_net/1e4:,.0f}만원")
        return {"fx": round(fx, 2), "holdings": holdings}
    except Exception as e:  # noqa: BLE001
        print(f"WARN: ★주식계좌 읽기 실패 ({type(e).__name__}: {e}) — 금융자산 탭 생략")
        return {}


if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")
    d = fetch_holdings()
    for h in d.get("holdings", []):
        print(f"{h['owner']} {h['group']:4} {h['account'][:18]:18} {h['name'][:22]:22} "
              f"{h['value_krw']:>12,} 배당 {h['div_krw']:>9,}")
