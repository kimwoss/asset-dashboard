"""Timestamped regular-session quotes, shared by briefing and holding valuation."""
from datetime import datetime, timedelta
from math import isfinite
import json
import re
import urllib.request
from zoneinfo import ZoneInfo


def positive(value):
    try:
        value = float(str(value).replace(",", ""))
        return value if isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def session_day(symbol, now):
    from quotes import _market
    market = _market(symbol)
    zone = "America/New_York" if market == "US" else "UTC" if market == "FX" else "Asia/Seoul"
    return now.astimezone(ZoneInfo(zone)).date()


def valid_tick(symbol, at, now, opened):
    from quotes import _market
    if at is None or at > now + timedelta(seconds=30):
        return False
    market = _market(symbol)
    zone = ZoneInfo("America/New_York" if market == "US" else "UTC" if market == "FX" else "Asia/Seoul")
    local = at.astimezone(zone)
    minute = local.hour * 60 + local.minute
    if market in ("KRX", "US"):
        if local.weekday() >= 5:
            return False
        lo, hi = (540, 930) if market == "KRX" else (570, 960)
        if not lo <= minute <= hi:
            return False
    if opened and (local.date() != session_day(symbol, now) or now - at > timedelta(minutes=30)):
        return False
    return True


def naver_points(symbols, now, is_open):
    """One primary Naver Finance request for all Korean holdings; no account data sent."""
    codes = {s.split(".")[0]: s for s in symbols if re.fullmatch(r"\d{6}\.(KS|KQ)", s)}
    if not codes:
        return {}
    url = "https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(sorted(codes))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
    with urllib.request.urlopen(request, timeout=8) as response:
        rows = json.load(response).get("datas") or []
    out = {}
    for row in rows:
        symbol = codes.get(row.get("itemCode"))
        price, at = positive(row.get("closePrice")), stamp(row.get("localTradedAt"))
        if not symbol or not price or row.get("marketSessionType") != "regularMarket":
            continue
        opened = is_open("KRX", now)
        if not valid_tick(symbol, at, now, opened) or (opened and row.get("marketStatus") != "OPEN"):
            continue
        out[symbol] = {"price": price, "asof": at.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat(),
                       "price_at": at.isoformat(), "price_kind": "intraday" if opened else "close",
                       "source": "Naver Finance", "quote_state": "delayed" if opened and now-at > timedelta(minutes=3) else "ok"}
    return out


def yahoo_points(symbols, now, is_open):
    """Reject premarket and previous-session bars at the opening boundary."""
    import pandas as pd
    import yfinance as yf
    from quotes import _market
    active = [s for s in symbols if is_open(_market(s), now)]
    if not active:
        return {}
    frame = yf.download(active, period="2d", interval="1m", progress=False, threads=False, auto_adjust=False)
    if frame is None or frame.empty or "Close" not in frame:
        return {}
    close, out = frame["Close"], {}
    for symbol in active:
        values = close[symbol] if isinstance(close, pd.DataFrame) and symbol in close else close if isinstance(close, pd.Series) and len(active) == 1 else None
        if values is None:
            continue
        for index, price in reversed(list(values.dropna().items())):
            at = index.to_pydatetime()
            if positive(price) and valid_tick(symbol, at, now, True):
                out[symbol] = {"price": float(price), "asof": session_day(symbol, at).isoformat(),
                               "price_at": at.isoformat(), "price_kind": "intraday", "source": "Yahoo Finance",
                               "quote_state": "delayed" if now-at > timedelta(minutes=3) else "ok"}
                break
    return out


def fetch_points(symbols, daily=None, now=None):
    import quotes
    now = now or datetime.now(quotes.KST)
    daily = quotes._daily_closes(symbols) if daily is None else daily
    out = {s: {"price": p, "asof": quotes._DAILY_DATES.get(s), "price_at": None,
               "price_kind": "close", "source": "Yahoo Finance",
               "quote_state": "awaiting" if quotes._is_open(quotes._market(s), now) else "ok"}
           for s, p in daily.items() if positive(p)}
    try:
        primary = naver_points(symbols, now, quotes._is_open)
    except Exception as error:
        print(f"WARN: 국내 시세 직접 조회 실패 ({type(error).__name__}) — Yahoo 폴백")
        primary = {}
    try:
        fallback = yahoo_points([s for s in symbols if s not in primary], now, quotes._is_open)
    except Exception as error:
        print(f"WARN: 장중 시세 조회 실패 ({type(error).__name__}) — 마지막 확인 가격 유지")
        fallback = {}
    for symbol, point in {**fallback, **primary}.items():
        previous = out.get(symbol)
        if previous and previous.get("asof") and point["asof"] < previous["asof"]:
            continue
        out[symbol] = point
    print(f"OK: 거래시각 확인 {len(out)}/{len(symbols)}종목 · 장중 {sum(p['price_kind']=='intraday' for p in out.values())} · 개장시세 대기 {sum(p['quote_state']=='awaiting' for p in out.values())}")
    return out
