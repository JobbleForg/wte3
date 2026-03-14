from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from wte_trend_viewer.data_manager import (
    LoadedTrendWorkbook,
    TrendDataManager,
    TrendSeriesData,
    TrendSheetData,
)
from wte_trend_viewer.session import SessionStore, WorkspaceSession
from wte_trend_viewer.ui.main_window import TrendViewerMainWindow


def _build_loaded_workbook(source_path: Path, tag_name: str) -> LoadedTrendWorkbook:
    timestamps = pl.Series(
        "Timestamp",
        [
            datetime(2026, 1, 1, 0, 0, 0),
            datetime(2026, 1, 1, 0, 5, 0),
            datetime(2026, 1, 1, 0, 10, 0),
        ],
    )
    series = TrendSeriesData(
        tag_name=tag_name,
        sheet_name="Process Data",
        source_column=tag_name,
        values=pl.Series(tag_name, [10.0, 15.0, 13.0]),
    )
    sheet = TrendSheetData(
        name="Process Data",
        timestamp_column="Timestamp",
        timestamps=timestamps,
        tag_series=(series,),
        row_count=3,
        column_count=2,
    )
    return LoadedTrendWorkbook(
        source_path=source_path,
        selected_sheet_names=("Process Data",),
        sheets=(sheet,),
    )


def test_startup_restore_reopens_workbook_from_relative_path(qapp, tmp_path, monkeypatch) -> None:
    session_store = SessionStore(tmp_path / "sessions")
    workbook_path = tmp_path / "sample-data.xlsx"
    workbook_path.write_text("placeholder", encoding="utf-8")
    session_store.save_last_session(
        WorkspaceSession(
            imported_tags=["TagA"],
            trend_state={"preview_tag_names": ["TagA"]},
            settings_state={
                "last_workbook_path": str(tmp_path / "moved-away" / "sample-data.xlsx"),
                "last_workbook_name": "sample-data.xlsx",
                "last_workbook_relative_path": "sample-data.xlsx",
                "loaded_sheet_names": ["Process Data"],
            },
        )
    )

    load_calls: list[tuple[Path, list[str]]] = []

    def _fake_load_workbook(self, source, selected_sheet_names, *, inspection=None):
        resolved_source = Path(source).resolve()
        load_calls.append((resolved_source, list(selected_sheet_names)))
        return _build_loaded_workbook(resolved_source, "TagA")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TrendDataManager, "load_workbook", _fake_load_workbook)

    window = TrendViewerMainWindow(session_store=session_store)

    assert load_calls == [(workbook_path.resolve(), ["Process Data"])]
    assert window._loaded_workbook is not None
    assert window._current_preview_tag_names == ["TagA"]
    assert window._last_workbook_path() == workbook_path.resolve()
    assert window.statusBar().currentMessage() == "Restored last session."

    persisted_session = session_store.load_last_session()
    assert persisted_session.settings_state["last_workbook_path"] == str(workbook_path.resolve())
    assert persisted_session.settings_state["last_workbook_relative_path"] == "sample-data.xlsx"


def test_startup_restore_reports_when_workbook_cannot_be_reopened(qapp, tmp_path) -> None:
    session_store = SessionStore(tmp_path / "sessions")
    missing_workbook = tmp_path / "missing" / "Does Not Exist.xlsx"
    session_store.save_last_session(
        WorkspaceSession(
            imported_tags=["TagA"],
            trend_state={"preview_tag_names": ["TagA"]},
            settings_state={
                "last_workbook_path": str(missing_workbook),
                "last_workbook_name": missing_workbook.name,
                "loaded_sheet_names": ["Process Data"],
            },
        )
    )

    window = TrendViewerMainWindow(session_store=session_store)

    assert window._loaded_workbook is None
    assert window._imported_tags_list.tags() == ["TagA"]
    assert window.statusBar().currentMessage() == (
        "Restored last session layout, but the workbook could not be reopened automatically."
    )

