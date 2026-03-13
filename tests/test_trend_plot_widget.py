from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl
import pytest

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.ui.widgets.trend_plot_widget import (
    PLOT_COLORS,
    TrendPlotSeries,
    TrendVisibleSeriesStats,
    TrendPlotWidget,
    _build_summary_text,
    _clamp_x_range,
    _cursor_sample_indices,
    _downsample_visible_slice,
)


def _make_plot_series() -> TrendPlotSeries:
    return _make_named_plot_series("Pressure", [10.0, 15.0, 13.0])


def _make_named_plot_series(tag_name: str, values: list[float]) -> TrendPlotSeries:
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
        sheet_name="BoilerA",
        source_column=tag_name,
        values=pl.Series(tag_name, values),
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


def test_widget_emits_cursor_stats_for_nearest_sample_and_interpolation(qapp) -> None:
    widget = TrendPlotWidget()
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    cursor_timestamp = datetime(2026, 1, 1, 0, 6, 0).timestamp()
    stats = widget._build_cursor_stats(cursor_timestamp)

    assert stats.cursor_timestamp == cursor_timestamp
    assert len(stats.series_stats) == 1
    series_stats = stats.series_stats[0]
    assert series_stats.sample_timestamp == datetime(2026, 1, 1, 0, 5, 0).timestamp()
    assert series_stats.cursor_value == 15.0
    assert series_stats.previous_timestamp == datetime(2026, 1, 1, 0, 5, 0).timestamp()
    assert series_stats.previous_value == 15.0
    assert series_stats.next_timestamp == datetime(2026, 1, 1, 0, 10, 0).timestamp()
    assert series_stats.next_value == 13.0
    assert series_stats.interpolation_mode == "linear"
    assert series_stats.interpolated_value == pytest.approx(14.6)


def test_widget_keeps_y_range_fixed_during_scale_and_translate(qapp) -> None:
    widget = TrendPlotWidget()
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    initial_y_range = widget.current_y_range()
    view_box = widget._plot_widget.getViewBox()
    view_box.scaleBy(x=0.5, y=0.25)
    assert widget.current_y_range() == initial_y_range

    view_box.translateBy(x=120.0, y=50.0)
    assert widget.current_y_range() == initial_y_range


def test_cursor_label_is_in_navigation_row(qapp) -> None:
    widget = TrendPlotWidget()

    assert widget._cursor_label.parent() is widget._visible_range_label.parent()
    assert widget._cursor_label.parent() is not widget


def test_plot_color_palette_is_large_and_unique() -> None:
    assert len(PLOT_COLORS) >= 20
    assert len(set(PLOT_COLORS)) == len(PLOT_COLORS)


def test_highlighted_tags_dim_other_series(qapp) -> None:
    widget = TrendPlotWidget()
    plotted_series = [
        _make_named_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_named_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]
    widget.plot_series_group(workbook_name="Workbook", plotted_series=plotted_series)

    widget.set_highlighted_tags(["TagA"])

    tag_a_pen = widget._prepared_series[0].curve.opts["pen"]
    tag_b_pen = widget._prepared_series[1].curve.opts["pen"]
    assert tag_a_pen.color().alpha() == 255
    assert tag_b_pen.color().alpha() < 255


def test_widget_uses_provided_series_colors(qapp) -> None:
    widget = TrendPlotWidget()
    plotted_series = [
        _make_named_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_named_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]
    series_colors_by_tag = {
        "TagA": "#FFED6F",
        "TagB": "#00C2FF",
    }
    widget.plot_series_group(
        workbook_name="Workbook",
        plotted_series=plotted_series,
        series_colors_by_tag=series_colors_by_tag,
    )

    assert widget._prepared_series[0].color == "#FFED6F"
    assert widget._prepared_series[1].color == "#00C2FF"
    assert widget._prepared_series[0].curve.opts["pen"].color().name().upper() == "#FFED6F"
    assert widget._prepared_series[1].curve.opts["pen"].color().name().upper() == "#00C2FF"


def test_left_axis_label_is_hidden(qapp) -> None:
    widget = TrendPlotWidget()
    plotted = _make_plot_series()
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    left_axis = widget._plot_widget.getPlotItem().getAxis("left")

    assert left_axis.labelText == ""
    assert left_axis.style["showValues"] is False


def test_summary_text_includes_empty_state_message() -> None:
    text = _build_summary_text(
        workbook_name="Workbook",
        visible_stats=[],
        x_min=0.0,
        x_max=10.0,
    )

    assert "No live trend data loaded." in text


def test_summary_text_prefers_display_labels_when_provided() -> None:
    text = _build_summary_text(
        workbook_name="Workbook",
        visible_stats=[
            TrendVisibleSeriesStats(
                tag_name="Process Data/TAG001",
                sheet_name="Process Data",
                color="#6CB6FF",
                sample_count=3,
                latest_value=12.0,
                minimum_value=10.0,
                maximum_value=14.0,
                average_value=12.0,
            )
        ],
        x_min=0.0,
        x_max=10.0,
        display_labels_by_tag={
            "Process Data/TAG001": "TAG001 - Example temperature [C]"
        },
    )

    assert "TAG001 - Example temperature [C]" in text
    assert "Process Data/TAG001" not in text


def test_downsample_visible_slice_keeps_endpoints() -> None:
    x_values = np.arange(10, dtype=np.float64)
    y_values = np.array([5, 4, 3, 9, 2, 8, 1, 7, 0, 6], dtype=np.float64)

    sampled_x, sampled_y = _downsample_visible_slice(x_values, y_values, max_points=4)

    assert sampled_x[0] == 0
    assert sampled_x[-1] == 9
    assert sampled_y.shape == sampled_x.shape


def test_cursor_sample_indices_prefers_left_value_on_tie() -> None:
    x_values = np.asarray([10.0, 20.0, 30.0], dtype=np.float64)

    assert _cursor_sample_indices(x_values, 25.0) == (1, 1, 2)


def test_clamp_x_range_limits_window_to_data_extent() -> None:
    assert _clamp_x_range(-5.0, 5.0, 0.0, 20.0) == (0.0, 10.0)
