from __future__ import annotations

from pathlib import Path

import polars as pl

from wte_trend_viewer.workbook import WorkbookInspector


def test_inspector_prefixes_tag_names_when_multiple_data_sheets(monkeypatch) -> None:
    frames = {
        "BoilerA": pl.DataFrame(
            {
                "Timestamp": ["2026-01-01T00:00:00", "2026-01-01T00:01:00"],
                "Pressure": [1.0, 1.1],
            }
        ),
        "BoilerB": pl.DataFrame(
            {
                "Timestamp": ["2026-01-01T00:00:00", "2026-01-01T00:01:00"],
                "Pressure": [2.0, 2.1],
            }
        ),
        "Meta": pl.DataFrame({"Title": ["Example"]}),
    }
    monkeypatch.setattr(
        "wte_trend_viewer.workbook.read_workbook_frames",
        lambda _source: frames,
    )

    result = WorkbookInspector().inspect(Path("dummy.xlsx"))

    assert result.available_tags == ("BoilerA/Pressure", "BoilerB/Pressure")


def test_inspector_keeps_plain_tag_names_for_single_data_sheet(monkeypatch) -> None:
    frames = {
        "Meta": pl.DataFrame({"Title": ["Example"]}),
        "BoilerA": pl.DataFrame(
            {
                "Timestamp": ["2026-01-01T00:00:00", "2026-01-01T00:01:00"],
                "Pressure": [1.0, 1.1],
                "Flow": [4.0, 4.1],
            }
        ),
    }
    monkeypatch.setattr(
        "wte_trend_viewer.workbook.read_workbook_frames",
        lambda _source: frames,
    )

    result = WorkbookInspector().inspect(Path("dummy.xlsx"))

    assert result.available_tags == ("Pressure", "Flow")
