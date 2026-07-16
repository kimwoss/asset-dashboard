# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > ★주식계좌 탭의 계좌별 보유내역을 읽어온다.

시트가 원 소스(source of truth) — 평가액은 시트의 GOOGLEFINANCE 계산값을 그대로 쓴다.
배당금만 yfinance 실지급 이력(최근 12개월)으로 보강한다.

  연 예상 배당금 = 수량 × TTM 주당배당 × (USD면 환율)

실패는 파이프라인을 죽이지 않는다 — 예외 시 {} 반환, 대시보드는 금융자산 탭만 비운다.
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import sheets_fire  # 인증 재사용 (_authorize)

SPREADSHEET_ID = sheets_fire.SPREADSHEET_ID
TAB = "★주식계좌"
DATA_RANGE = "A4:K42"
FX_CELL = "H1"

# 연금성 계좌 판별 (인출 제약) — 그 외는 유동성
_PENSION_PAT = ("연저펀", "IRP", "퇴직연금", "연금저축")


def _group_of(account: str) -> str:
    return "연금성" if any(p in account for p in _PENSION_PAT) else "유동성"


def _yf_symbol(ticker: str) -> str:
    """시트 티커 → yfinance 심볼. KRX:360750 → 360750.KS / SCHD → SCHD"""
    t = (ticker or "").strip()
    if t.upper().startswith("KRX:"):
        return t.split(":", 1)[1] + ".KS"
    return t


def _ttm_dividend(symbol: str) -> float:
    """최근 12개월 주당 배당 합계 (실지급 이력). 없으면 0."""
    try:
        import pandas as pd
        import yfinance as yf
        d = yf.Ticker(symbol).dividends
        if d is None or len(d) == 0:
            return 0.0
        cutoff = d.index.max() - pd.Timedelta(days=365)
        return float(d[d.index >= cutoff].sum())
    except Exception as e:  # noqa: BLE001
        print(f"WARN: {symbol} 배당 조회 실패 ({e})")
        return 0.0


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
        div_cache: Dict[str, float] = {}

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

            div_ps = 0.0
            if ticker:
                sym = _yf_symbol(ticker)
                if sym not in div_cache:
                    div_cache[sym] = _ttm_dividend(sym)
                div_ps = div_cache[sym]
            rate = fx if cur.upper() == "USD" else 1.0
            div_krw = round(qty_n * div_ps * rate)

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
                "div_krw": div_krw,
            })

        if not holdings:
            print("WARN: ★주식계좌 보유내역 없음")
            return {}
        total = sum(h["value_krw"] for h in holdings)
        div = sum(h["div_krw"] for h in holdings)
        print(f"OK: 금융자산 {len(holdings)}건 총 {total/1e8:.2f}억 · 연 예상배당 {div/1e4:,.0f}만원")
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
