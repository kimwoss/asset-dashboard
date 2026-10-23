from datetime import datetime, timezone
from block_cache import read_block


def test_empty_success_replaces_previous_result():
    fetched, statuses = {}, {}
    result, changed = read_block("liabilities", lambda: [], (), {"liabilities": [1]}, fetched, statuses, datetime.now(timezone.utc), False)
    assert result == [] and changed
    assert statuses["liabilities"]["state"] == "ok"


def test_failure_retains_previous_value_and_time():
    fetched, statuses = {"liabilities": "old"}, {}
    def fail():
        raise TimeoutError("private details must not be published")
    result, changed = read_block("liabilities", fail, (), {"liabilities": [1]}, fetched, statuses, datetime.now(timezone.utc), False)
    assert result == [1] and not changed
    assert fetched["liabilities"] == "old"
    assert statuses["liabilities"]["reason"] == "TimeoutError"


def test_empty_cache_is_reused():
    result, changed = read_block("news", lambda: [1], (), {"news": []}, {}, {}, datetime.now(timezone.utc), True)
    assert result == [] and not changed
