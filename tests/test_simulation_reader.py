import sys
import types
import sheets_sim


def test_income_column_and_zero_values_are_preserved(monkeypatch):
    grid = [["", "은퇴시점 자산", 100], ["", "은퇴필요 기본자금", 100],
            ["나이", "연도", "단계", "순자산"],
            [40, 2026, "현재", 100, 1, 2, 3, 4, 5, 6, 0, 0, 90, "평상", .03, 1],
            [41, 2027, "인출", 90, 0, 0, 0, 0, 0, 0, 0, 0, 80, "평상", .03, 1]]
    class Worksheet:
        id = 123
        def get(self, block, **kwargs):
            assert block == "A1:P90"
            return grid
    sheet = types.SimpleNamespace(worksheet=lambda name: Worksheet())
    client = types.SimpleNamespace(open_by_key=lambda key: sheet)
    monkeypatch.setitem(sys.modules, "gspread", types.ModuleType("gspread"))
    monkeypatch.setattr(sheets_sim.sheets_fire, "_authorize", lambda module: client)
    monkeypatch.setattr(sheets_sim, "SPREADSHEET_ID", "synthetic-master")
    data = sheets_sim.fetch_simulation()
    assert data["series"][0]["retire_income"] == 5
    assert data["series"][0]["pension"] == 4
    assert data["series"][1]["retire_income"] == 0
    assert data["retire_age"] == 41

    assert data["source_url"] == "https://docs.google.com/spreadsheets/d/synthetic-master/edit#gid=123"
