from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.ui.widgets.trend_plot_widget import (
    TrendPlotSeries,
    TrendPlotWidget,
    _build_summary_text,
    _clamp_x_range,
    _downsample_visible_slice,
    _nearest_index,
)


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


def test_widget_emits_cursor_stats_for_nearest_sample(qapp) -> None:
    widget = TrendPlotWidget()
    widget.resize(800, 600)
    widget.show()
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    mid_timestamp = datetime(2026, 1, 1, 0, 6, 0).timestamp()
    stats = widget._build_cursor_stats(mid_timestamp)

    assert stats.cursor_timestamp == mid_timestamp
    assert stats.series_stats[0].sample_timestamp == datetime(2026, 1, 1, 0, 5, 0).timestamp()
    assert stats.series_stats[0].cursor_value == 15.0


def test_summary_text_includes_sheet_and_tag() -> None:
    text = _build_summary_text(
        workbook_name="Workbook",
        visible_stats=[],
        x_min=0.0,
        x_max=10.0,
    )

    assert "No live trend data loaded." in text


def test_downsample_visible_slice_keeps_endpoints() -> None:
    x_values = np.arange(10, dtype=np.float64)
    y_values = np.array([5, 4, 3, 9, 2, 8, 1, 7, 0, 6], dtype=np.float64)

    sampled_x, sampled_y = _downsample_visible_slice(x_values, y_values, max_points=4)

    assert sampled_x[0] == 0
    assert sampled_x[-1] == 9
    assert sampled_y.shape == sampled_x.shape


def test_nearest_index_prefers_left_value_on_tie() -> None:
    x_values = np.asarray([10.0, 20.0, 30.0], dtype=np.float64)

    assert _nearest_index(x_values, 25.0) == 1


def test_clamp_x_range_limits_window_to_data_extent() -> None:
    assert _clamp_x_range(-5.0, 5.0, 0.0, 20.0) == (0.0, 10.0)
