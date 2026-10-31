import sys
from types import SimpleNamespace
from unittest.mock import patch
import sheets_annual

def test_annual_failure_is_unavailable_so_cache_keeps_last_success():
    with patch.object(sheets_annual.sheets_fire, "_authorize", return_value=None), patch.dict(sys.modules, {"gspread": SimpleNamespace()}):
        assert sheets_annual.fetch_annual_flow() is None

def test_corrected_source_rows_are_read_without_legacy_fixed_values(capsys):
    grid = [["year","months","income","expense","note"],[2024,12,1000,531,"보정 추정"],[2023,12,800,555,"보정 추정"]]
    ws = SimpleNamespace(get=lambda *a, **kw: grid)
    gc = SimpleNamespace(open_by_key=lambda key: SimpleNamespace(worksheet=lambda name: ws))
    with patch.object(sheets_annual.sheets_fire, "_authorize", return_value=gc), patch.dict(sys.modules, {"gspread": SimpleNamespace()}):
        result=sheets_annual.fetch_annual_flow()
    assert result[0]["expense"] == 531
    assert result[1]["expense"] == 555
    assert "annual_flow source signature" in capsys.readouterr().out
