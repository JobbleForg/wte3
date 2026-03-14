from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
from PySide6.QtCore import Qt

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import (
    DETACHED_LEGEND_HIGHLIGHT_COLUMN,
    TrendViewerMainWindow,
)
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


def test_pop_out_trend_creates_independent_detached_windows(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    plotted_series = [
        _make_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]
    window._loaded_workbook = _LoadedWorkbookStub(plotted_series)

    assert window._preview_tags(["TagA"], persist_selection=False) is True
    assert window._pop_out_trend_action.isEnabled() is True

    window._pop_out_current_trend_window()
    assert len(window._detached_trend_windows) == 1
    first_window = window._detached_trend_windows[0]
    assert [prepared.plotted.series.tag_name for prepared in first_window._trend_plot_widget._prepared_series] == [
        "TagA"
    ]

    assert window._preview_tags(["TagB"], persist_selection=False) is True
    window._pop_out_current_trend_window()

    assert len(window._detached_trend_windows) == 2
    second_window = window._detached_trend_windows[1]
    assert [prepared.plotted.series.tag_name for prepared in second_window._trend_plot_widget._prepared_series] == [
        "TagB"
    ]
    assert [prepared.plotted.series.tag_name for prepared in first_window._trend_plot_widget._prepared_series] == [
        "TagA"
    ]


def test_detached_trend_window_can_shrink_to_compact_width(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    plotted_series = [
        _make_plot_series("TagA", [10.0, 15.0, 13.0]),
    ]
    window._loaded_workbook = _LoadedWorkbookStub(plotted_series)

    assert window._preview_tags(["TagA"], persist_selection=False) is True

    window._pop_out_current_trend_window()
    assert len(window._detached_trend_windows) == 1
    detached_window = window._detached_trend_windows[0]
    detached_window.show()
    qapp.processEvents()

    assert detached_window.minimumSizeHint().width() <= 620

    detached_window.resize(640, 420)
    qapp.processEvents()

    assert detached_window.width() <= 640


def test_detached_trend_window_has_collapsible_details_tabs(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    plotted_series = [
        _make_plot_series("TagA", [10.0, 15.0, 13.0]),
    ]
    window._loaded_workbook = _LoadedWorkbookStub(plotted_series)

    assert window._preview_tags(["TagA"], persist_selection=False) is True

    window._pop_out_current_trend_window()
    detached_window = window._detached_trend_windows[0]

    assert detached_window._details_section.is_expanded() is False
    assert detached_window._analytics_table.columnCount() == 5
    assert detached_window._legend_table.columnCount() == 6

    detached_window._details_section.set_expanded(True)
    qapp.processEvents()

    assert detached_window._details_section.is_expanded() is True


def test_detached_trend_window_highlight_checkbox_updates_plot(qapp, tmp_path) -> None:
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

    window._pop_out_current_trend_window()
    detached_window = window._detached_trend_windows[0]
    assert detached_window._legend_table is not None

    highlight_item = detached_window._legend_table.item(0, DETACHED_LEGEND_HIGHLIGHT_COLUMN)
    assert highlight_item is not None

    highlight_item.setCheckState(Qt.Checked)
    qapp.processEvents()

    assert detached_window._trend_plot_widget._active_highlighted_tag_names() == {"TagA"}

