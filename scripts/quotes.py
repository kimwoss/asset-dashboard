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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

KST = timezone(timedelta(hours=9))


def _market(sym: str) -> str:
    """심볼이 속한 시장. 열려 있는지 판단하는 기준이 시장마다 다르다."""
    s = sym.upper()
    if s.endswith("=X"):
        return "FX"
    if s.endswith(".KS") or s.endswith(".KQ"):
        return "KRX"
    return "US"


def _is_open(market: str, now: Optional[datetime] = None) -> bool:
    """지금 그 시장이 열려 있나 — 시계만 본다(휴장일은 '봉이 신선한가'로 따로 거른다)."""
    now = now or datetime.now(KST)
    wd = now.weekday()
    if market == "KRX":
        if wd >= 5:
            return False
        t = now.hour * 60 + now.minute
        return 9 * 60 <= t <= 15 * 60 + 30
    if market == "US":
        from zoneinfo import ZoneInfo
        ny = now.astimezone(ZoneInfo("America/New_York"))
        if ny.weekday() >= 5:
            return False
        t = ny.hour * 60 + ny.minute
        return 9 * 60 + 30 <= t <= 16 * 60
    # 외환 — 월 06:00 KST 개장 ~ 토 06:00 KST 폐장 (뉴욕 일요일 17:00 ET 기준)
    if wd == 5:
        return now.hour < 6
    if wd == 6:
        return False
    if wd == 0:
        return now.hour >= 6
    return True


def _daily_closes(symbols: List[str]) -> Dict[str, float]:
    """{심볼: 마지막 '정식 종가'}. 주말 행은 버린다.

    야후는 환율(KRW=X)에 토·일 행을 만든다. 실제로 거래된 날이 아니고 값도 흔들려,
    주말마다 평가액이 움직이는 원인이 된다(2026-09 실측: 금 1,367.36 → 일 1,354.40).
    """
    import pandas as pd
    import yfinance as yf
    try:
        df = yf.download(symbols, period="10d", interval="1d", progress=False,
                         threads=False, auto_adjust=False)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 일봉 종가 실패 ({type(e).__name__}: {str(e)[:60]})")
        return {}
    if df is None or df.empty or "Close" not in df:
        return {}
    cl = df["Close"]
    if isinstance(cl, pd.Series):
        cl = cl.to_frame(symbols[0])
    idx = pd.DatetimeIndex(cl.index)
    cl = cl[[d.weekday() < 5 for d in idx]]
    out: Dict[str, float] = {}
    for s in symbols:
        if s not in cl:
            continue
        v = cl[s].dropna()
        if len(v):
            out[s] = float(v.iloc[-1])
    return out


def settled_fx(sheet_fx: Optional[float]) -> Optional[float]:
    """외환이 닫혀 있으면 마지막 평일 종가로 고정한다.

    시트의 환율은 GOOGLEFINANCE라 주말에도 값이 바뀐다. USD 보유분이 금융자산의 3분의 1이라
    그것만으로 순자산이 주말 내내 움직였다.
    """
    if _is_open("FX"):
        return sheet_fx
    v = _daily_closes(["KRW=X"]).get("KRW=X")
    return v or sheet_fx

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

    # 기준은 '정식 종가'다. 장중에만 1분봉으로 갈아끼운다.
    #
    # 종전엔 언제나 1분봉의 마지막 값을 썼다. 두 가지가 잘못됐다.
    #   ① 국내 ETF는 1분봉이 14:59에서 끊겨 종가 단일가(15:30)를 통째로 놓친다.
    #      2026-09 실측: 보유 6종목이 정식 종가보다 0.18~0.44% 낮게 잡혔다. 상시 저평가였다.
    #   ② 배치가 레이트리밋 등으로 실패하면 종목별 폴백(fast_info=정식 종가)으로 넘어가는데,
    #      두 값이 0.2~0.4% 달라서 실행마다 평가액이 점프했다. 장이 닫힌 주말에도 숫자가
    #      계속 바뀌어 보인 주된 원인이다.
    # 이제 닫혀 있으면 어느 실행에서 받아도 같은 값이 나온다.
    daily = _daily_closes(symbols)
    intraday: Dict[str, float] = {}

    # 1분봉은 한 번에 받는다. 종목마다 Ticker().fast_info를 부르면 22종목 × 하루 144회 =
    # 3,168 요청이 되어 Yahoo 레이트리밋에 걸린다. download는 실행당 1요청이다.
    try:
        df = yf.download(symbols, period="1d", interval="1m", progress=False,
                         threads=False, auto_adjust=False)
        cl = df["Close"] if "Close" in df else None
        if cl is not None:
            if len(symbols) == 1:                 # 단일 종목은 컬럼이 평평하게 온다
                v = cl.dropna()
                if len(v):
                    intraday[symbols[0]] = float(v.iloc[-1])
            else:
                for s in symbols:
                    if s in cl:
                        v = cl[s].dropna()
                        if len(v):
                            intraday[s] = float(v.iloc[-1])
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 1분봉 실패 ({type(e).__name__}: {str(e)[:60]}) — 종가로 진행")

    live = 0
    for s in symbols:
        if _is_open(_market(s)) and s in intraday:
            out[s] = intraday[s]; live += 1
        elif s in daily:
            out[s] = daily[s]
        elif s in intraday:                        # 일봉을 못 받았으면 있는 것이라도
            out[s] = intraday[s]

    # 둘 다 못 받은 것만 개별로 — 보통 0~2종목이라 요청이 늘지 않는다.
    # (장이 닫혀 있는데 여기로 내려오면 fast_info의 lastPrice는 정식 종가라 결과가 같다)
    for s in [x for x in symbols if x not in out]:
        try:
            v = yf.Ticker(s).fast_info["lastPrice"]
            if v and v > 0:
                out[s] = float(v)
        except Exception as e:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않는다
            print(f"WARN: {s} 시세 실패 ({type(e).__name__})")
    asof = datetime.now(KST).isoformat()
    print(f"OK: 시세 {len(out)}/{len(symbols)}종목 (장중 {live} · 종가 {len(out)-live}) "
          f"({time.time()-t0:.1f}s)")
    return out, asof


def apply_live_prices(fin: Dict[str, Any], fx: Optional[float] = None) -> Dict[str, Any]:
    """fetch_holdings() 결과의 평가액을 현재가로 다시 계산해 덮어쓴다.

    fin을 제자리에서 고치고 그대로 돌려준다. 시세를 못 받았으면 아무것도 바꾸지 않는다.
    """
    holdings = (fin or {}).get("holdings") or []
    if not holdings:
        return fin
    # 환율도 같은 규칙 — 닫혀 있으면 마지막 평일 종가로 고정한다.
    # 시트 환율(GOOGLEFINANCE)은 주말에도 움직여서, USD 보유분(금융자산의 1/3)을 통해
    # 순자산이 주말 내내 흔들렸다. 표시용 fin["fx"]도 같은 값으로 맞춰 환산과 어긋나지 않게 한다.
    rate = fx or settled_fx(fin.get("fx")) or 0
    if rate:
        fin["fx"] = rate
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
