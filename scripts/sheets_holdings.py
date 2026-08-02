# -*- coding: utf-8 -*-
"""⭐️분당부부_MASTER > ★주식계좌 탭의 계좌별 보유내역을 읽어온다.

시트가 원 소스(source of truth) — 평가액은 시트의 GOOGLEFINANCE 계산값을 그대로 쓴다.
배당금만 yfinance 배당 이력으로 보강한다.

  올해 배당(세전) = 현재 수량 × 올해 지급월별 주당배당 × (USD면 환율)
  올해 배당(세후) = 세전 × (1 − 계좌별 세율)   ← 같은 종목도 계좌에 따라 세금이 다르다
  월별 배당        = 실제 '지급월'에 계상. 기준일 지난 달은 확정, 남은 달은 작년 실적으로 추정
                     (증권앱의 '2026년 배당금(예상)'과 같은 방식)

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
# 일별 잡이 값을 써 넣는 탭. 이 탭을 참조하는 셀은 원 소스가 아니다 (아래 순환참조 탐지).
_WRITEBACK_TAB = "★월별자산"

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


def _pay_month(ex_date: date, is_krx: bool) -> Tuple[int, int]:
    """배당락일(분배금 기준일) → 실제 지급이 찍히는 (년, 월).

    yfinance가 주는 날짜는 '지급일'이 아니라 '배당락일'이다. 증권앱은 지급월에 꽂아
    보여주므로 그대로 쓰면 어긋난다.
      국내 ETF: 기준일이 매월 말 영업일(1/29·4/29·6/29…), 지급은 기준일로부터
                수 영업일 뒤 → 거의 항상 익월 초. +6일이면 월말 기준일이 다음 달로 넘어가고,
                (드물지만) 월 중순 기준일이면 같은 달에 남는다.
      미국 ETF: 배당락 며칠 뒤 같은 달 지급 (SCHD 3/25→3월, 12/10→12월). +3일.
    지급일 자체는 yfinance에 없어 근사한다 — 2026-07 실측으로 증권앱 월별과 맞춤 확인.
    """
    d = ex_date + timedelta(days=6 if is_krx else 3)
    return d.year, d.month


def _year_dividends(symbol: str, year: int, today: date) -> Dict[int, Tuple[float, str]]:
    """올해 지급월 기준 주당 배당 {월: (주당액, 'actual'|'est')}.

    증권앱의 '2026년 배당금(예상)'과 같은 방식 — 최근 12개월(TTM) 합계가 아니라
    올해 달력에 맞춘다:
      이미 기준일이 지난 달 → 실제 확정 금액 (actual)
      아직 남은 달        → 작년 같은 지급월의 실적으로 추정 (est)
    수량은 항상 현재 보유수량을 쓴다 — '지금 이대로 두면 올해 얼마'라는 뜻이다.
    """
    try:
        import yfinance as yf
        d = yf.Ticker(symbol).dividends
        if d is None or len(d) == 0:
            return {}
        is_krx = symbol.upper().endswith(".KS")
        paid: Dict[Tuple[int, int], float] = {}
        for ts, v in d.items():
            ym = _pay_month(ts.date(), is_krx)
            paid[ym] = paid.get(ym, 0.0) + float(v)

        out: Dict[int, Tuple[float, str]] = {}
        for m in range(1, 13):
            if m <= today.month:      # 기준일이 지난 달 = 금액 확정
                amt, kind = paid.get((year, m), 0.0), "actual"
            else:                     # 남은 달 = 작년 같은 달로 추정
                amt, kind = paid.get((year - 1, m), 0.0), "est"
            if amt:
                out[m] = (amt, kind)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"WARN: {symbol} 배당 조회 실패 ({e})")
        return {}


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v or ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_holdings(with_dividends: bool = True, today: Optional[date] = None) -> Dict[str, Any]:
    """★주식계좌 → {fx, year, holdings:[...]} . 실패 시 {}.

    with_dividends=False — 배당(yfinance 이력 조회)을 건너뛴다. 30분마다 도는
    실시간 시세 잡용: 배당은 분기 단위로 바뀌므로 매번 조회할 이유가 없다.
    """
    today = today or date.today()
    year = today.year
    try:
        import gspread
        gc = sheets_fire._authorize(gspread)
        if gc is None:
            print("WARN: 시트 인증정보 없음 — 금융자산 탭 생략")
            return {}
        ws = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB)
        fx = _num(ws.acell(FX_CELL, value_render_option="UNFORMATTED_VALUE").value)
        rows = ws.get(DATA_RANGE, value_render_option="UNFORMATTED_VALUE")
        # 순환참조 탐지 — 아래 write_current_month()가 쓰는 탭을 이 셀이 되읽고 있으면
        # 값이 자기 자신에서 나온다(A→B→A). 한 번 잘못 쓰이면 시트가 그 값을 사실로
        # 굳혀버린다 (2026-08-01 우현 주택청약 10,098,550이 실제로 이렇게 박혔다).
        formulas = ws.get(DATA_RANGE, value_render_option="FORMULA")

        holdings: List[Dict] = []
        last_account = ""
        div_cache: Dict[str, Dict[int, Tuple[float, str]]] = {}

        for i, r in enumerate(rows):
            fr = (list(formulas[i]) + [""] * 11)[:11] if i < len(formulas) else [""] * 11
            circular = any(_WRITEBACK_TAB in str(c) for c in fr)
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

            cal: Dict[int, Tuple[float, str]] = {}
            if ticker and with_dividends:
                sym = _yf_symbol(ticker)
                if sym not in div_cache:
                    div_cache[sym] = _year_dividends(sym, year, today)
                cal = div_cache[sym]
            rate = fx if cur.upper() == "USD" else 1.0
            # 올해 월별 세전 배당 (1~12월, 지급월 기준).
            # 연간은 월별 합으로 잡는다 → 월별 차트와 연간 카드가 항상 일치 (반올림 오차 제거)
            div_months = [round(qty_n * cal.get(m, (0.0, ""))[0] * rate) for m in range(1, 13)]
            # 확정/추정 표시 — 증권앱처럼 지나간 달은 실적, 남은 달은 예상으로 구분해 보여준다
            div_kinds = [cal.get(m, (0.0, ""))[1] for m in range(1, 13)]
            div_krw = sum(div_months)
            div_ps = sum(v for v, _ in cal.values())
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
                "div_months": div_months,        # 올해 월별 세전 (세후는 ×(1-tax_rate))
                "div_kinds": div_kinds,          # 월별 'actual'(확정) / 'est'(추정) / ''(없음)
                "tax_rate": tax_rate,
                "tax_note": tax_note,
                "circular": circular,            # 이 값은 ★월별자산에서 되읽은 것 → 되쓰기 금지
            })

        if not holdings:
            print("WARN: ★주식계좌 보유내역 없음")
            return {}
        total = sum(h["value_krw"] for h in holdings)
        msg = f"OK: 금융자산 {len(holdings)}건 총 {total/1e8:.2f}억"
        if with_dividends:  # 배당을 스킵했으면 0원이라 적지 않는다 (오해 방지)
            div = sum(h["div_krw"] for h in holdings)
            div_net = sum(h["div_net_krw"] for h in holdings)
            done = sum(v for h in holdings for v, k in zip(h["div_months"], h["div_kinds"]) if k == "actual")
            msg += (f" · {year}년 배당 세전 {div/1e4:,.0f}만원 → 세후 {div_net/1e4:,.0f}만원"
                    f" (확정 {done/1e4:,.0f}만 + 추정 {(div-done)/1e4:,.0f}만)")
        print(msg)
        return {"fx": round(fx, 2), "year": year, "holdings": holdings}
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
