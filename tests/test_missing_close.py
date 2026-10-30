# -*- coding: utf-8 -*-
"""야후 일봉의 '거래는 있었는데 종가만 빈' 날 채우기 (2026-10-29 SCHD 사례)."""
import sys
import types
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_live as U  # noqa: E402


def _fake_yf(monkeypatch, last_bar_by_day):
    idx = pd.DatetimeIndex([pd.Timestamp(f"{d} 15:55", tz="America/New_York") for d in last_bar_by_day])
    bars = pd.DataFrame({"Close": list(last_bar_by_day.values())}, index=idx)
    fake = types.SimpleNamespace(Ticker=lambda s: types.SimpleNamespace(history=lambda **k: bars))
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_fills_close_when_day_traded(monkeypatch):
    days = pd.DatetimeIndex(["2026-10-27", "2026-10-28", "2026-10-29"])
    close = pd.Series([35.12, 35.09, float("nan")], index=days)
    traded = pd.Series([True, True, True], index=days)          # 10/29 거래량 2,395만
    _fake_yf(monkeypatch, {"2026-10-29": 35.62})
    out, filled = U._fill_missing_closes("SCHD", close, traded)
    assert filled == ["2026-10-29"] and out.iloc[-1] == 35.62
    assert close.isna().iloc[-1], "원본을 바꾸면 안 된다"


def test_does_not_invent_a_close_on_a_holiday(monkeypatch):
    """거래 흔적이 없는 날(휴장)은 장중 봉이 있어 보여도 채우지 않는다."""
    days = pd.DatetimeIndex(["2026-11-25", "2026-11-26"])
    close = pd.Series([35.0, float("nan")], index=days)
    traded = pd.Series([True, False], index=days)              # 추수감사절
    _fake_yf(monkeypatch, {"2026-11-26": 99.0})
    out, filled = U._fill_missing_closes("SCHD", close, traded)
    assert filled == [] and pd.isna(out.iloc[-1])


def test_no_gap_means_no_network_call(monkeypatch):
    days = pd.DatetimeIndex(["2026-10-28", "2026-10-29"])
    close = pd.Series([35.09, 35.61], index=days)
    traded = pd.Series([True, True], index=days)

    def boom(*a, **k):
        raise AssertionError("빈 종가가 없는데 장중 봉을 조회했다")
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=boom))
    out, filled = U._fill_missing_closes("SCHD", close, traded)
    assert filled == [] and out.equals(close)
