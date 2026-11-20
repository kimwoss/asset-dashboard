from datetime import datetime
import json
import sys
from types import SimpleNamespace
import pandas as pd
import pytest
import market_quotes as M
import quotes
from update_live import _quotes, _rows


def at(text):
    return datetime.fromisoformat(text)


@pytest.mark.parametrize("symbol,point,now,valid", [
    ("SCHD", "2026-11-19T16:00:00-05:00", "2026-11-20T09:30:10-05:00", False),
    ("SCHD", "2026-11-20T09:29:00-05:00", "2026-11-20T09:30:10-05:00", False),
    ("SCHD", "2026-11-20T09:30:00-05:00", "2026-11-20T09:30:10-05:00", True),
    ("360750.KS", "2026-11-19T15:30:00+09:00", "2026-11-20T09:00:10+09:00", False),
    ("360750.KS", "2026-11-20T09:00:00+09:00", "2026-11-20T09:00:10+09:00", True),
    ("360750.KS", "2026-11-20T09:02:00+09:00", "2026-11-20T09:00:10+09:00", False),
    ("KRW=X", "2026-11-20T15:01:00Z", "2026-11-21T00:02:00+09:00", True),
])
def test_opening_requires_a_current_regular_session_tick(symbol, point, now, valid):
    assert M.valid_tick(symbol, at(point), at(now), True) is valid


def test_naver_batches_prices_and_uses_trade_time_not_response_clock(monkeypatch):
    rows = [{"itemCode":"360750","closePrice":"25,000","localTradedAt":"2026-11-20T09:00:01+09:00","marketStatus":"OPEN","marketSessionType":"regularMarket"}]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return json.dumps({"datas":rows,"time":"20991231120000"}).encode()
    monkeypatch.setattr(M.urllib.request,"urlopen",lambda *a,**k:Response())
    point=M.naver_points(["360750.KS"],at("2026-11-20T09:00:10+09:00"),quotes._is_open)["360750.KS"]
    assert point["price"] == 25000
    assert point["price_at"] == rows[0]["localTradedAt"]
    assert point["quote_state"] == "ok"
    rows[0]["marketStatus"]="CLOSE"
    assert M.naver_points(["360750.KS"],at("2026-11-20T09:00:10+09:00"),quotes._is_open)=={}


def test_single_symbol_multiindex_intraday_is_supported(monkeypatch):
    frame=pd.DataFrame({("Close","SCHD"):[35.5]},index=pd.DatetimeIndex(["2026-11-20T14:30:00Z"]))
    monkeypatch.setitem(sys.modules,"yfinance",SimpleNamespace(download=lambda *a,**k:frame))
    point=M.yahoo_points(["SCHD"],at("2026-11-20T14:31:00+00:00"),quotes._is_open)["SCHD"]
    assert point["price"]==35.5
    assert point["asof"]=="2026-11-20"


def test_opening_without_a_tick_is_explicitly_pending(monkeypatch):
    monkeypatch.setattr(M,"naver_points",lambda *a:{})
    monkeypatch.setattr(M,"yahoo_points",lambda *a:{})
    monkeypatch.setitem(quotes._DAILY_DATES,"SCHD","2026-11-19")
    point=M.fetch_points(["SCHD"],daily={"SCHD":35},now=at("2026-11-20T14:30:10Z"))["SCHD"]
    assert point["quote_state"]=="awaiting"
    assert point["price_at"] is None
    assert point["asof"]=="2026-11-19"


def test_briefing_uses_intraday_price_even_before_today_daily_row_exists(monkeypatch):
    idx=pd.DatetimeIndex(["2025-11-19","2026-11-13","2026-11-19"])
    frame=pd.DataFrame({("Close","SCHD"):[25,30,35],("Open","SCHD"):[25,30,35],("Volume","SCHD"):[1,1,1]},index=idx)
    monkeypatch.setitem(sys.modules,"yfinance",SimpleNamespace(download=lambda *a,**k:frame))
    point={"price":36,"asof":"2026-11-20","price_at":"2026-11-20T09:31:00-05:00","price_kind":"intraday","source":"Yahoo Finance","quote_state":"ok"}
    result=_quotes(["SCHD"],{"SCHD":point})["SCHD"]
    assert result["price"]==36
    assert result["d1"]==pytest.approx(2.86)
    assert result["w1"]==20
    assert result["price_kind"]=="intraday"
    row=_rows([("SCHD","SCHD","$",1)],{"SCHD":result})[0]
    assert row["price_at"]==point["price_at"]


def test_holdings_share_the_exact_briefing_quote():
    holding={"ticker":"KRX:360750","qty":2,"price":24000,"value_krw":48000,"currency":"KRW"}
    point={"price":25000,"asof":"2026-11-20","price_at":"2026-11-20T09:00:01+09:00","price_kind":"intraday","source":"Naver Finance","quote_state":"ok"}
    result=quotes.apply_live_prices({"fx":1400,"holdings":[holding]},fx=1400,price_points={"360750.KS":point})
    assert result["holdings"][0]["value_krw"]==50000
    assert result["holdings"][0]["price_at"]==point["price_at"]
