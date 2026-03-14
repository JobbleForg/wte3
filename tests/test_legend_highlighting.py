from __future__ import annotations

from datetime import datetime

import polars as pl
from PySide6.QtCore import Qt

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import (
    LEGEND_HIGHLIGHT_COLUMN,
    TrendViewerMainWindow,
)
from wte_trend_viewer.ui.widgets.trend_plot_widget import TrendPlotSeries


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


def test_legend_highlight_checkbox_dims_other_series(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    plotted_series = [
        _make_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]

    window._current_plotted_series = list(plotted_series)
    window._current_preview_tag_names = [plotted.series.tag_name for plotted in plotted_series]
    window._trend_plot_widget.plot_series_group(
        workbook_name="Workbook",
        plotted_series=plotted_series,
    )
    window._update_plot_support_panels(plotted_series)

    assert window._legend_table is not None
    assert (
        window._legend_table.horizontalHeader().contextMenuPolicy()
        == Qt.CustomContextMenu
    )

    highlight_item = window._legend_table.item(0, LEGEND_HIGHLIGHT_COLUMN)
    assert highlight_item is not None

    highlight_item.setCheckState(Qt.Checked)

    assert window._stored_highlighted_tag_names() == ["TagA"]
    assert window._trend_plot_widget._prepared_series[0].curve.opts["pen"].color().alpha() == 255
    assert window._trend_plot_widget._prepared_series[1].curve.opts["pen"].color().alpha() < 255

    window._clear_all_legend_highlights(persist=False)

    assert window._stored_highlighted_tag_names() == []
    assert window._legend_table.item(0, LEGEND_HIGHLIGHT_COLUMN).checkState() == Qt.Unchecked
    assert window._legend_table.item(1, LEGEND_HIGHLIGHT_COLUMN).checkState() == Qt.Unchecked


def test_highlighted_tags_persist_in_session(qapp, tmp_path) -> None:
    session_store = SessionStore(tmp_path)
    window = TrendViewerMainWindow(
        session_store=session_store,
        restore_last_session=False,
    )

    window._current_preview_tag_names = ["TagA", "TagB"]
    window._set_highlighted_tag_names(["TagA"], persist=False)
    session = window._capture_session()

    restored_window = TrendViewerMainWindow(
        session_store=session_store,
        restore_last_session=False,
    )
    restored_window._apply_session(session)

    assert restored_window._stored_highlighted_tag_names() == ["TagA"]

