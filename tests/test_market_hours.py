"""장이 닫혀 있으면 값이 고정되어야 한다 — 주말 변동 사고(2026-09) 회귀 테스트.

증상: 장이 열리지 않은 일요일에도 접속할 때마다 순자산이 ±0.03~0.07% 움직였다.
원인 둘 —
  ① 가격을 언제나 '마지막 1분봉'에서 뽑았다. 국내 ETF는 1분봉이 14:59에서 끊겨
     종가 단일가(15:30)를 놓친다. 보유 6종목이 정식 종가보다 0.18~0.44% 낮았다.
     게다가 배치가 실패해 종목별 폴백(fast_info=정식 종가)으로 넘어가면 그만큼 점프했다.
  ② 야후는 환율(KRW=X)에 토·일 행을 만든다. 금 1,367.36 → 일 1,354.40(-0.95%).
     USD가 금융자산의 1/3이라 그것만으로 순자산이 주말 내내 흔들렸다.
"""
from datetime import datetime

import pytest

quotes = pytest.importorskip("quotes")
KST = quotes.KST


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=KST)


@pytest.mark.parametrize("sym,expect", [
    ("360750.KS", "KRX"), ("148020.KQ", "KRX"),
    ("SCHD", "US"), ("^GSPC", "US"),
    ("KRW=X", "FX"), ("JPYKRW=X", "FX"),
])
def test_시장_분류(sym, expect):
    assert quotes._market(sym) == expect


@pytest.mark.parametrize("when,market,open_", [
    ("2026-09-25T10:00", "KRX", True),    # 금 장중
    ("2026-09-25T15:31", "KRX", False),   # 금 마감 직후
    ("2026-09-26T10:00", "KRX", False),   # 토
    ("2026-09-27T10:00", "KRX", False),   # 일
    ("2026-09-25T23:00", "US", True),     # 금 22:30~ = 뉴욕 장중
    ("2026-09-26T06:00", "US", False),    # 토 새벽 = 뉴욕 금요일 마감 후
    ("2026-09-27T12:00", "US", False),    # 일
    ("2026-09-26T03:00", "FX", True),     # 토 06시 전 = 아직 열림
    ("2026-09-26T09:00", "FX", False),    # 토 06시 후 = 주말 폐장
    ("2026-09-27T12:00", "FX", False),    # 일
    ("2026-09-28T05:00", "FX", False),    # 월 06시 전
    ("2026-09-28T07:00", "FX", True),     # 월 06시 후 = 개장
])
def test_개장_판정(when, market, open_):
    assert quotes._is_open(market, at(when)) is open_


def test_주말엔_모든_시장이_닫혀_있다():
    """하나라도 열려 있다고 판단하면 '장 마감' 배지가 뜨지 않는다."""
    sun = at("2026-09-27T12:00")
    assert not any(quotes._is_open(m, sun) for m in ("KRX", "US", "FX"))


def test_환율은_시트값이_아니라_평일_종가로_고정된다(monkeypatch):
    """시트 환율(GOOGLEFINANCE)은 주말에도 움직인다. 닫혀 있으면 무시해야 한다."""
    monkeypatch.setattr(quotes, "_is_open", lambda m, now=None: False)
    monkeypatch.setattr(quotes, "_daily_closes", lambda syms: {"KRW=X": 1367.36})
    assert quotes.settled_fx(9999.0) == 1367.36


def test_장중에는_시트_환율을_그대로_쓴다(monkeypatch):
    monkeypatch.setattr(quotes, "_is_open", lambda m, now=None: True)
    assert quotes.settled_fx(1400.0) == 1400.0


def test_닫혀_있으면_1분봉이_아니라_종가를_쓴다(monkeypatch):
    """핵심 회귀 — 1분봉(14:59)과 종가(15:30)가 다를 때 종가를 택해야 한다."""
    monkeypatch.setattr(quotes, "_is_open", lambda m, now=None: False)
    monkeypatch.setattr(quotes, "_daily_closes", lambda syms: {"360750.KS": 26200.0})

    class _FakeYF:
        @staticmethod
        def download(*a, **k):
            raise RuntimeError("1분봉 안 씀")
    import sys
    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF)
    got, _ = quotes.fetch_prices(["360750.KS"])
    assert got["360750.KS"] == 26200.0
