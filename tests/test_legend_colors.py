from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from PySide6.QtWidgets import QComboBox

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import LEGEND_COLOR_COLUMN, TrendViewerMainWindow
from wte_trend_viewer.ui.widgets.trend_plot_widget import TrendPlotSeries


class _LoadedWorkbookStub:
    def __init__(self, plotted_series: list[TrendPlotSeries]) -> None:
        self.source_path = Path("Workbook.xlsx")
        self._series_by_tag = {
            plotted.series.tag_name: plotted.series for plotted in plotted_series
        }
        self._sheet_by_tag = {
            plotted.series.tag_name: plotted.sheet for plotted in plotted_series
        }

    def series_for_tag(self, tag_name: str):
        return self._series_by_tag.get(tag_name)

    def sheet_for_tag(self, tag_name: str):
        return self._sheet_by_tag.get(tag_name)


def _make_plot_series(tag_name: str, values: list[float]) -> TrendPlotSeries:
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
        values=pl.Series(tag_name, values),
    )
    sheet = TrendSheetData(
        name="Process Data",
        timestamp_column="Timestamp",
        timestamps=timestamps,
        tag_series=(series,),
        row_count=3,
        column_count=2,
    )
    return TrendPlotSeries(sheet=sheet, series=series)


def test_legend_color_combo_swaps_plot_colors(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    plotted_series = [
        _make_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]
    window._loaded_workbook = _LoadedWorkbookStub(plotted_series)

    assert window._preview_tags(["TagA", "TagB"], persist_selection=False) is True

    first_color = window._current_plot_colors_by_tag["TagA"]
    second_color = window._current_plot_colors_by_tag["TagB"]

    assert window._legend_table is not None
    color_combo = window._legend_table.cellWidget(0, LEGEND_COLOR_COLUMN)
    assert isinstance(color_combo, QComboBox)

    color_combo.setCurrentIndex(color_combo.findData(second_color))

    assert window._stored_color_for_tag("TagA") == second_color
    assert window._stored_color_for_tag("TagB") == first_color
    assert window._current_plot_colors_by_tag["TagA"] == second_color
    assert window._current_plot_colors_by_tag["TagB"] == first_color


def test_tag_colors_persist_in_session(qapp, tmp_path) -> None:
    session_store = SessionStore(tmp_path)
    window = TrendViewerMainWindow(
        session_store=session_store,
        restore_last_session=False,
    )
    plotted_series = [
        _make_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]
    window._loaded_workbook = _LoadedWorkbookStub(plotted_series)
    assert window._preview_tags(["TagA", "TagB"], persist_selection=False) is True

    window._set_plot_color_for_tag("TagA", "#F28F3B", persist=False)
    session = window._capture_session()

    restored_window = TrendViewerMainWindow(
        session_store=session_store,
        restore_last_session=False,
    )
    restored_window._apply_session(session)

    assert restored_window._stored_color_for_tag("TagA") == "#F28F3B"
