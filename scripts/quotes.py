# -*- coding: utf-8 -*-
"""보유종목 평가액을 우리가 직접 계산한다 — GOOGLEFINANCE 지연을 우회하려고.

왜 필요한가. 시트의 평가액은 GOOGLEFINANCE가 계산한 값인데 그게 15~20분 지연이고,
게다가 시트가 언제 재계산되는지는 우리가 못 정한다. 30분 주기로 읽어도 화면에는
최대 50분 전 값이 앉았다. 시트에는 티커와 수량이 있으니 가격만 우리가 받아
곱하면 그 지연 사슬이 끊긴다.

  평가액 = 수량 × 현재가 × (USD면 환율)

정직하게 남기는 한계 — 무료로 실시간 시세를 주는 곳은 없다.
  · 미국 ETF/주식 : Yahoo가 사실상 실시간 (지연 1분 안팎)
  · 국내 ETF(.KS) : Yahoo도 15~20분 지연. GOOGLEFINANCE와 다르지 않다
  · 환율          : 거의 실시간
그래서 10분 주기로 돌리면 미국 비중은 10분 안쪽, 국내 비중은 25~30분이 된다.
이 부부의 목표 포트폴리오는 90%가 미국이라 대부분이 앞쪽에 든다.

가격을 못 받은 종목은 **시트 값을 그대로 둔다.** 0으로 떨어뜨리면 순자산이 통째로
흔들려 조용한 오류보다 시끄러운 오류가 낫다는 원칙에도 어긋난다.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

# 시세를 믿지 않는 선 — 시트 값 대비 이 비율을 넘게 벗어나면 무시한다.
# 액면분할·티커 재사용 같은 사고에서 yfinance가 엉뚱한 값을 주는 일이 있다.
SANITY_LO, SANITY_HI = 0.5, 2.0


def _symbols(holdings: List[Dict]) -> Dict[str, List[Dict]]:
    """yfinance 심볼 → 그 심볼을 쓰는 보유 행들."""
    from sheets_holdings import _yf_symbol
    out: Dict[str, List[Dict]] = {}
    for h in holdings:
        t = (h.get("ticker") or "").strip()
        if not t or not h.get("qty"):
            continue                      # 현금·예금은 시세가 없다
        out.setdefault(_yf_symbol(t), []).append(h)
    return out


def fetch_prices(symbols: List[str]) -> Tuple[Dict[str, float], Optional[str]]:
    """{심볼: 현재가}. 실패한 심볼은 빠진다. 두 번째 값은 조회 시각(ISO)."""
    if not symbols:
        return {}, None
    try:
        import yfinance as yf
    except ImportError:
        print("WARN: yfinance 없음 — 시세 직접 계산 생략")
        return {}, None

    out: Dict[str, float] = {}
    t0 = time.time()
    # 한 번에 받는다. 종목마다 Ticker().fast_info를 부르면 22종목 × 하루 144회 =
    # 3,168 요청이 되어 Yahoo 레이트리밋에 걸린다. download는 실행당 1요청이다.
    try:
        df = yf.download(symbols, period="1d", interval="1m", progress=False,
                         threads=False, auto_adjust=False)
        cl = df["Close"] if "Close" in df else None
        if cl is not None:
            if len(symbols) == 1:                 # 단일 종목은 컬럼이 평평하게 온다
                v = cl.dropna()
                if len(v):
                    out[symbols[0]] = float(v.iloc[-1])
            else:
                for s in symbols:
                    if s in cl:
                        v = cl[s].dropna()
                        if len(v):
                            out[s] = float(v.iloc[-1])
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 일괄 시세 실패 ({type(e).__name__}: {str(e)[:60]})")

    # 일괄에서 빠진 것만 개별로 — 보통 0~2종목이라 요청이 늘지 않는다
    for s in [x for x in symbols if x not in out]:
        try:
            v = yf.Ticker(s).fast_info["lastPrice"]
            if v and v > 0:
                out[s] = float(v)
        except Exception as e:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않는다
            print(f"WARN: {s} 시세 실패 ({type(e).__name__})")
    from datetime import datetime, timedelta, timezone
    asof = datetime.now(timezone(timedelta(hours=9))).isoformat()
    print(f"OK: 시세 {len(out)}/{len(symbols)}종목 ({time.time()-t0:.1f}s)")
    return out, asof


def apply_live_prices(fin: Dict[str, Any], fx: Optional[float] = None) -> Dict[str, Any]:
    """fetch_holdings() 결과의 평가액을 현재가로 다시 계산해 덮어쓴다.

    fin을 제자리에서 고치고 그대로 돌려준다. 시세를 못 받았으면 아무것도 바꾸지 않는다.
    """
    holdings = (fin or {}).get("holdings") or []
    if not holdings:
        return fin
    rate = fx or fin.get("fx") or 0
    by_sym = _symbols(holdings)
    prices, asof = fetch_prices(sorted(by_sym))
    if not prices:
        return fin

    moved = kept = 0
    for sym, rows in by_sym.items():
        p = prices.get(sym)
        if not p:
            kept += len(rows); continue
        for h in rows:
            usd = (h.get("currency") or "KRW").upper() == "USD"
            if usd and not rate:
                kept += 1; continue
            new_val = round(h["qty"] * p * (rate if usd else 1.0))
            old_val = h.get("value_krw") or 0
            # 시트 값과 지나치게 어긋나면 우리 쪽을 의심한다
            if old_val and not (SANITY_LO <= new_val / old_val <= SANITY_HI):
                print(f"WARN: {sym} 평가액이 시트 대비 {new_val/old_val:.2f}배 — 시트 값 유지")
                kept += 1; continue
            h["price"], h["value_krw"], h["price_live"] = p, new_val, True
            moved += 1

    total = sum(h.get("value_krw") or 0 for h in holdings)
    fin["quotes_asof"] = asof
    fin["quotes_live"] = moved
    print(f"OK: 평가액 재계산 {moved}건 (시트 유지 {kept}건) · 합계 {total/1e8:.2f}억")
    return fin
