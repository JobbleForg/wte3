from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import TrendViewerMainWindow
from wte_trend_viewer.ui.widgets.trend_plot_widget import (
    TrendCursorSeriesStats,
    TrendCursorStats,
    TrendPlotSeries,
    TrendVisibleSeriesStats,
)


def _cursor_stats(cursor_timestamp: float, sample_timestamp: float, value: float) -> TrendCursorStats:
    return TrendCursorStats(
        cursor_timestamp=cursor_timestamp,
        series_stats=(
            TrendCursorSeriesStats(
                tag_name="Pressure",
                sheet_name="BoilerA",
                color="#6CB6FF",
                sample_timestamp=sample_timestamp,
                cursor_value=value,
            ),
        ),
    )


def _visible_stats() -> list[TrendVisibleSeriesStats]:
    return [
        TrendVisibleSeriesStats(
            tag_name="Pressure",
            sheet_name="BoilerA",
            color="#6CB6FF",
            sample_count=3,
            latest_value=13.0,
            minimum_value=10.0,
            maximum_value=15.0,
            average_value=12.6666666667,
        )
    ]


def _make_plot_series() -> TrendPlotSeries:
    timestamps = pl.Series(
        "Timestamp",
        [
            datetime(2026, 1, 1, 0, 0, 0),
            datetime(2026, 1, 1, 0, 5, 0),
            datetime(2026, 1, 1, 0, 10, 0),
        ],
    )
    series = TrendSeriesData(
        tag_name="Pressure",
        sheet_name="BoilerA",
        source_column="Pressure",
        values=pl.Series("Pressure", [10.0, 15.0, 13.0]),
    )
    sheet = TrendSheetData(
        name="BoilerA",
        timestamp_column="Timestamp",
        timestamps=timestamps,
        tag_series=(series,),
        row_count=3,
        column_count=2,
    )
    return TrendPlotSeries(sheet=sheet, series=series)


def test_cursor_label_currently_uses_raw_pointer_time_instead_of_sample_time(qapp) -> None:
    window = TrendViewerMainWindow(restore_last_session=False)
    widget = window._trend_plot_widget
    assert widget is not None
    widget.resize(800, 600)
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    raw_cursor_timestamp = datetime(2026, 1, 1, 0, 6, 0).timestamp()
    nearest_sample_timestamp = datetime(2026, 1, 1, 0, 5, 0).timestamp()

    widget._set_cursor_position(raw_cursor_timestamp)
    stats = widget._build_cursor_stats(raw_cursor_timestamp)

    assert widget._cursor_label.text() == "Cursor: 2026-01-01 00:06:00"
    assert stats.series_stats[0].sample_timestamp == nearest_sample_timestamp


@pytest.mark.xfail(
    reason="Known issue: cursor label shows raw pointer time instead of the sampled timestamp behind the displayed value.",
    strict=False,
)
def test_cursor_label_should_match_sample_timestamp_for_single_series(qapp) -> None:
    window = TrendViewerMainWindow(restore_last_session=False)
    widget = window._trend_plot_widget
    assert widget is not None
    widget.resize(800, 600)
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    raw_cursor_timestamp = datetime(2026, 1, 1, 0, 6, 0).timestamp()
    widget._set_cursor_position(raw_cursor_timestamp)

    assert widget._cursor_label.text() == "Cursor: 2026-01-01 00:05:00"


def test_cursor_stats_signal_re_emits_for_same_nearest_sample_region(qapp) -> None:
    window = TrendViewerMainWindow(restore_last_session=False)
    widget = window._trend_plot_widget
    assert widget is not None
    widget.resize(800, 600)
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    emissions: list[float] = []
    widget.cursorStatsChanged.connect(
        lambda stats: emissions.append(None if stats is None else stats.cursor_timestamp)
    )

    widget._set_cursor_position(datetime(2026, 1, 1, 0, 5, 1).timestamp())
    widget._set_cursor_position(datetime(2026, 1, 1, 0, 5, 2).timestamp())
    widget._set_cursor_position(datetime(2026, 1, 1, 0, 5, 3).timestamp())

    assert len(emissions) == 3


def test_main_window_resizes_analytics_columns_on_every_cursor_update(qapp, tmp_path, monkeypatch) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path / "sessions"),
        restore_last_session=False,
    )
    window._current_visible_stats = _visible_stats()
    assert window._analytics_table is not None

    resize_call_count = 0
    original_resize = window._analytics_table.resizeColumnsToContents

    def counted_resize() -> None:
        nonlocal resize_call_count
        resize_call_count += 1
        original_resize()

    monkeypatch.setattr(window._analytics_table, "resizeColumnsToContents", counted_resize)

    sample_timestamp = datetime(2026, 1, 1, 0, 5, 0).timestamp()
    window._handle_plot_cursor_stats_changed(_cursor_stats(sample_timestamp + 1, sample_timestamp, 15.0))
    window._handle_plot_cursor_stats_changed(_cursor_stats(sample_timestamp + 2, sample_timestamp, 15.0))
    window._handle_plot_cursor_stats_changed(_cursor_stats(sample_timestamp + 3, sample_timestamp, 15.0))

    assert resize_call_count == 3


@pytest.mark.xfail(
    reason="Known issue: analytics table fully refreshes and auto-sizes on every cursor move, even when the nearest sample is unchanged.",
    strict=False,
)
def test_main_window_should_coalesce_redundant_cursor_updates(qapp, tmp_path, monkeypatch) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path / "sessions"),
        restore_last_session=False,
    )
    window._current_visible_stats = _visible_stats()
    assert window._analytics_table is not None

    resize_call_count = 0

    def counted_resize() -> None:
        nonlocal resize_call_count
        resize_call_count += 1

    monkeypatch.setattr(window._analytics_table, "resizeColumnsToContents", counted_resize)

    sample_timestamp = datetime(2026, 1, 1, 0, 5, 0).timestamp()
    for offset in (1, 2, 3):
        window._handle_plot_cursor_stats_changed(
            _cursor_stats(sample_timestamp + offset, sample_timestamp, 15.0)
        )

    assert resize_call_count <= 1
