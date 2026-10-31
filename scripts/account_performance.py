"""Current-position market moves, not deposit-adjusted account investment returns."""
from datetime import date, datetime, timedelta, timezone
from math import isfinite

HORIZONS = {"d1": 1, "w1": 7, "m1": 30, "y1": 365}


def _positive(value):
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def _before(series, target):
    points = [(day, price) for day, price in series if day <= target and _positive(price)]
    return max(points, default=None, key=lambda point: point[0])


def calculate(fin, history, anchors=None):
    """All positions must have a baseline; never report a partial account as complete."""
    from sheets_holdings import _yf_symbol
    grouped = {}
    for holding in fin.get("holdings") or []:
        key = (holding.get("owner", ""), holding.get("account", ""))
        grouped.setdefault(key, []).append(holding)
    accounts = []
    for (owner, account), holdings in grouped.items():
        current = sum(h.get("value_krw") or 0 for h in holdings)
        periods = {}
        for horizon, days in HORIZONS.items():
            base = 0.0
            dates, missing = set(), []
            for h in holdings:
                value = h.get("value_krw") or 0
                if not value:
                    continue
                ticker, qty = h.get("ticker"), h.get("qty") or 0
                if not ticker or not qty:
                    base += value  # Non-priced cash/deposits: no assumed interest income.
                    continue
                symbol = _yf_symbol(ticker)
                series = history.get(symbol) or []
                if not series or not h.get("price_live"):
                    missing.append(h.get("name") or ticker)
                    continue
                anchor = (anchors or {}).get(symbol) or max(day for day, _ in series)
                point = _before(series, anchor - timedelta(days=days))
                if not point or (anchor - timedelta(days=days) - point[0]).days > 10:
                    missing.append(h.get("name") or ticker)
                    continue
                price = point[1]
                if (h.get("currency") or "KRW").upper() == "USD":
                    fx = _before(history.get("KRW=X") or [], point[0])
                    if not fx or (point[0] - fx[0]).days > 10:
                        missing.append(h.get("name") or ticker)
                        continue
                    price *= fx[1]
                base += qty * price
                dates.add(point[0].isoformat())
            if missing or base <= 0:
                periods[horizon] = {"delta_krw": None, "pct": None, "missing": sorted(set(missing))}
            else:
                # Calculate from unrounded baseline; round only the displayed amount.
                periods[horizon] = {"base_krw": round(base), "delta_krw": round(current - base),
                                    "pct": (current / base - 1) * 100, "base_dates": sorted(dates)}
        accounts.append({"owner": owner, "account": account, "current_krw": current, "periods": periods})
    return {"method": "current_positions_price_only", "accounts": accounts,
            "asof": fin.get("quotes_asof"), "includes_fx": True}


def fetch_account_performance(fin):
    """One batch for all holdings + FX; raw closes exclude reinvested cash dividends."""
    from sheets_holdings import _yf_symbol
    symbols = {_yf_symbol(h["ticker"]) for h in fin.get("holdings", []) if h.get("ticker") and h.get("qty")}
    if any((h.get("currency") or "").upper() == "USD" for h in fin.get("holdings", [])):
        symbols.add("KRW=X")
    history, anchors = {}, {}
    if symbols:
        try:
            import yfinance as yf
            from quotes import fill_missing_closes, _market, _is_open
            from zoneinfo import ZoneInfo
            frame = yf.download(sorted(symbols), period="2y", interval="1d", auto_adjust=False,
                                progress=False, threads=False, group_by="column")
            close = frame["Close"]
            for symbol in symbols:
                if symbol not in close:
                    continue
                values = close[symbol]
                traded = (frame["Volume"][symbol].fillna(0) > 0) | frame["Open"][symbol].notna()
                if not symbol.endswith("=X"):
                    values, _ = fill_missing_closes(symbol, values, traded)
                history[symbol] = [(stamp.date(), float(value)) for stamp, value in values.dropna().items()
                                   if stamp.weekday() < 5 and _positive(float(value))]
                # During trading, compare to yesterday even if Yahoo's daily row
                # for today is not present yet. US and KR dates can differ.
                market = _market(symbol)
                if _is_open(market):
                    zone = "America/New_York" if market == "US" else "Asia/Seoul"
                    anchors[symbol] = datetime.now(ZoneInfo(zone)).date()
        except Exception as error:
            print(f"WARN: account comparison history unavailable ({type(error).__name__})")
    result = calculate(fin, history, anchors)
    print(f"OK: account market moves {len(result['accounts'])} accounts")
    return result
