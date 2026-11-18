import pytest
from sheets_cities import parse_cities, _number


def grid():
    return [
        ["항목", "", "", "서울", "Test City"],
        ["[데이터 상태]", "", "", "기준", "✓ live"],
        ["[월간 생활비]"],
        ["식비", "", "", 100, 50],
        ["쇼핑", "", "", 200, 100],
        ["월간 합계", "", "", 300, 150],
        ["연간 합계", "", "", 120, 120],
        ["연간 사용예산", "", "", 3720, 1920],
        ["평균 월 생활비", "", "", 310, 160],
        ["FIRE 기본 필요자금 (근사)", "", "", 10000, 5161],
    ]


def test_valid_source_and_free_local_cost():
    source = grid()
    assert parse_cities(source)["cities"][0]["avg_monthly"] == 160
    source[4][4] = 0
    source[5][4], source[7][4], source[8][4] = 50, 720, 60
    assert parse_cities(source)["cities"][0]["categories"] == [50, 0]


@pytest.mark.parametrize("missing", ["", None, "#N/A", "?", float("nan"), True])
def test_missing_cost_cannot_be_zero_or_cached_success(missing):
    source = grid()
    source[4][4] = missing
    result = parse_cities(source)
    assert result and result["cities"] == []
    assert result["broken"] == ["Test City"]
    assert "쇼핑" in result["broken_details"][0]["reason"]


def test_complete_but_inconsistent_totals_are_rejected():
    source = grid()
    source[8][4] = 100
    assert parse_cities(source)["broken"] == ["Test City"]


def test_invalid_seoul_does_not_publish_comparisons():
    source = grid()
    source[4][3] = "#VALUE!"
    with pytest.raises(ValueError, match="서울 기준"):
        parse_cities(source)


def test_numeric_parser_rejects_nonfinite_and_boolean():
    assert _number("1,234") == 1234
    for value in ["?", "", False, "NaN", "Infinity", -1]:
        assert _number(value) is None


def test_null_labels_do_not_appear_as_none_or_create_a_phantom_city():
    source = grid()
    source[0].append(None)
    source[3][1] = None
    result = parse_cities(source)
    assert len(result["cities"]) == 1
    assert result["broken"] == []
    assert result["categories"][0]["group"] == ""
