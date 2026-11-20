from datetime import datetime
from real_estate import collect, expected_date, refresh_due


def at(text): return datetime.fromisoformat(text)


def test_friday_8am_invalidates_a_just_collected_weekly_cache():
    previous={"assets":[{"name":"A","asof":"2026-11-13"}]}
    assert expected_date(at("2026-11-20T07:59:00+09:00"))=="2026-11-13"
    assert expected_date(at("2026-11-20T08:00:00+09:00"))=="2026-11-20"
    assert refresh_due(previous,"2026-11-20T07:59:00+09:00",at("2026-11-20T08:00:10+09:00"))


def test_retry_each_five_minutes_until_every_property_is_current():
    previous={"assets":[{"name":"A","asof":"2026-11-20"},{"name":"B","asof":"2026-11-13"}]}
    assert refresh_due(previous,"2026-11-20T08:00:00+09:00",at("2026-11-20T08:05:00+09:00"))
    previous["assets"][1]["asof"]="2026-11-20"
    assert not refresh_due(previous,"2026-11-20T08:00:00+09:00",at("2026-11-20T08:05:00+09:00"))


def test_one_failed_property_is_preserved_without_blocking_the_other():
    known={"A":{"name":"A","asof":"2026-11-13","value_krw":100000000},"B":{"name":"B","asof":"2026-11-13","value_krw":200000000}}
    properties=[{"name":"A","complex_id":1,"area_id":1},{"name":"B","complex_id":2,"area_id":1}]
    def lookup(complex_id,*args,**kwargs):
        assert kwargs["window_s"]==0
        if complex_id==2: raise TimeoutError()
        return 11000,"2026-11-20"
    result=collect(properties,known,at("2026-11-20T08:01:00+09:00"),lookup)
    assert [a["value_krw"] for a in result["assets"]]==[110000000,200000000]
    assert result["pending"]==["B"]
    assert result["errors"][0]["name"]=="B"


def test_kb_dates_cannot_regress_or_come_from_the_future():
    prop={"name":"A","complex_id":1,"area_id":1}
    old={"name":"A","asof":"2026-11-20","value_krw":100000000}
    for bad in ["2026-11-13","2026-11-27"]:
        result=collect([prop],{"A":old},at("2026-11-20T08:01:00+09:00"),lambda *a,**k:(10000,bad))
        assert result["assets"]==[old]
        assert result["errors"]


def test_kb_selects_the_newest_source_date_instead_of_response_order(monkeypatch):
    import kb_api
    monkeypatch.setattr(kb_api,"price_info",lambda *a,**k:{"시세":[
        {"매매기준가":10000,"기준일자":"20261113","매매일반거래가":10000},
        {"매매기준가":11000,"기준일자":"20261120","매매일반거래가":11000}]})
    assert kb_api.latest_price(1,1)==(11000,"2026-11-20")


def test_kb_never_renames_an_undated_quote_as_today(monkeypatch):
    import pytest, kb_api
    monkeypatch.setattr(kb_api,"price_info",lambda *a,**k:{"시세":[{"매매일반거래가":10000}]})
    with pytest.raises(ValueError,match="source date"):
        kb_api.latest_price(1,1)


def test_real_kb_schema_uses_quote_date_not_earlier_contract_or_reference_date(monkeypatch):
    import kb_api
    row={"전세계약시작년월일":"20261107","전세계약종료년월일":"20261107",
         "시세기준년월일":"20261120","기준년월일":"20261116",
         "매매계약종료년월일":"20261007","매매일반거래가":116000}
    monkeypatch.setattr(kb_api,"price_info",lambda *a,**k:{"시세":[row]})
    assert kb_api.latest_price(4389,4247)==(116000,"2026-11-20")


def test_contract_dates_alone_cannot_make_a_price_fresh(monkeypatch):
    import pytest, kb_api
    monkeypatch.setattr(kb_api,"price_info",lambda *a,**k:{"시세":[{"전세계약시작년월일":"20261120","매매일반거래가":116000}]})
    with pytest.raises(ValueError,match="source date"):
        kb_api.latest_price(1,1)


def test_current_but_failed_kb_reads_are_retried_during_friday():
    previous={"assets":[{"name":"A","asof":"2026-11-20"}],"errors":[{"name":"A"}]}
    assert refresh_due(previous,"2026-11-20T08:00:00+09:00",at("2026-11-20T08:05:00+09:00"))
