from datetime import date
from account_performance import calculate


def holding(**changes):
    return dict(owner="Example", account="ISA", ticker="DEMO", qty=10,
                value_krw=1200, currency="KRW", price_live=True, **changes)


def test_market_move_uses_current_quantity_not_deposits():
    history = {"DEMO": [(date(2026, 10, 23), 90), (date(2026, 10, 29), 100), (date(2026, 10, 30), 120)]}
    result = calculate({"holdings": [holding()]}, history)["accounts"][0]
    assert result["periods"]["d1"]["delta_krw"] == 200
    assert round(result["periods"]["d1"]["pct"], 5) == 20
    assert result["periods"]["y1"]["pct"] is None


def test_usd_fx_and_cash_are_combined_without_cash_interest():
    stock = holding()
    stock.update(currency="USD", value_krw=1560000)
    cash = dict(owner="Example", account="ISA", ticker="", qty=0, value_krw=10000)
    history = {"DEMO": [(date(2026, 10, 29), 100), (date(2026, 10, 30), 120)],
               "KRW=X": [(date(2026, 10, 29), 1200), (date(2026, 10, 30), 1300)]}
    period = calculate({"holdings": [stock, cash]}, history)["accounts"][0]["periods"]["d1"]
    assert period["base_krw"] == 1210000
    assert period["delta_krw"] == 360000


def test_one_missing_position_never_becomes_a_partial_account_return():
    missing = holding()
    missing.update(ticker="NEW", value_krw=800)
    history = {"DEMO": [(date(2026, 10, 29), 100), (date(2026, 10, 30), 120)]}
    account = calculate({"holdings": [holding(), missing]}, history)["accounts"][0]
    assert account["current_krw"] == 2000
    assert account["periods"]["d1"]["pct"] is None


def test_weekends_use_the_last_close_before_calendar_horizon():
    history = {"DEMO": [(date(2026, 10, 30), 100), (date(2026, 11, 2), 120)]}
    period = calculate({"holdings": [holding()]}, history)["accounts"][0]["periods"]["d1"]
    assert period["base_dates"] == ["2026-10-30"]


def test_accounts_are_partitioned_by_both_owner_and_account():
    other = holding()
    other["owner"] = "Second"
    assert len(calculate({"holdings": [holding(), other]}, {})["accounts"]) == 2


def test_intraday_anchor_uses_yesterday_when_today_daily_bar_is_missing():
    history = {"DEMO": [(date(2026, 10, 29), 90), (date(2026, 10, 30), 100)]}
    period = calculate({"holdings": [holding()]}, history, {"DEMO": date(2026, 11, 2)})["accounts"][0]["periods"]["d1"]
    assert period["base_dates"] == ["2026-10-30"]
    assert period["delta_krw"] == 200
