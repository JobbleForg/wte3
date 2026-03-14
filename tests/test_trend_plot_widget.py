from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl
import pytest

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.ui.widgets.trend_plot_widget import (
    DISPLAY_Y_MAX,
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
    return _make_named_plot_series_with_minutes(tag_name, [0, 5, 10], values)


def _make_named_plot_series_with_minutes(
    tag_name: str,
    minutes: list[int],
    values: list[float],
) -> TrendPlotSeries:
    timestamps = pl.Series(
        "Timestamp",
        [datetime(2026, 1, 1, 0, minute, 0) for minute in minutes],
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


def test_time_controls_can_collapse_and_roundtrip_state(qapp) -> None:
    widget = TrendPlotWidget()

    assert widget._navigation_controls_container.isHidden() is False
    assert widget.time_selection_state()["time_controls_collapsed"] is False


def test_plot_context_menu_reflects_floating_legend_state(qapp) -> None:
    widget = TrendPlotWidget()

    menu = widget._build_plot_context_menu()
    actions = menu.actions()

    assert [action.text() for action in actions] == [
        "Floating legend",
        "Show data at cursor time",
    ]
    assert actions[0].isCheckable() is True
    assert actions[0].isChecked() is False
    assert actions[1].isCheckable() is True
    assert actions[1].isChecked() is False


def test_shared_scale_context_menu_reflects_decimal_setting(qapp) -> None:
    widget = TrendPlotWidget()

    menu = widget._build_shared_scale_context_menu()
    actions = menu.actions()

    assert [action.text() for action in actions] == ["Auto", "0", "1", "2", "3", "4", "5", "6"]
    assert actions[0].isChecked() is True

    widget._set_shared_scale_decimal_places(2, emit_state_change=False)
    menu = widget._build_shared_scale_context_menu()
    actions = menu.actions()

    assert actions[0].isChecked() is False
    assert actions[3].text() == "2"
    assert actions[3].isChecked() is True


def test_floating_legend_shows_cursor_time_values(qapp) -> None:
    widget = TrendPlotWidget()
    plotted_series = [
        _make_named_plot_series("TagA", [10.0, 15.0, 13.0]),
        _make_named_plot_series("TagB", [4.0, 5.0, 6.0]),
    ]
    widget.plot_series_group(workbook_name="Workbook", plotted_series=plotted_series)

    widget._set_floating_legend_enabled(True, emit_state_change=False)
    widget._set_floating_legend_show_cursor_data(True, emit_state_change=False)
    widget._set_cursor_position(datetime(2026, 1, 1, 0, 6, 0).timestamp())

    assert widget._floating_legend_item.isVisible() is True
    assert "TagA" in widget._floating_legend_html
    assert "TagB" in widget._floating_legend_html
    assert "14.600" in widget._floating_legend_html
    assert "5.200" in widget._floating_legend_html
    assert widget._floating_legend_item.pos().y() == pytest.approx(DISPLAY_Y_MAX - 2.0)
    assert widget.time_selection_state()["floating_legend_enabled"] is True
    assert widget.time_selection_state()["floating_legend_show_cursor_data"] is True

    widget._toggle_time_controls_collapsed()

    assert widget._navigation_controls_container.isHidden() is True
    assert widget.time_selection_state()["time_controls_collapsed"] is True

    widget.set_time_selection_state({"time_controls_collapsed": False})

    assert widget._navigation_controls_container.isHidden() is False
    assert widget.time_selection_state()["time_controls_collapsed"] is False


def test_shared_scale_decimal_places_updates_labels_and_roundtrips_state(qapp) -> None:
    widget = TrendPlotWidget()
    plotted = _make_plot_series()
    widget.plot_series_group(
        workbook_name="Workbook",
        plotted_series=[plotted],
        display_ranges_by_tag={"Pressure": (10.0, 15.0)},
    )

    assert widget._shared_scale_top_layout.itemAtPosition(0, 0).widget().text() == "15.000"
    assert widget._shared_scale_mid_layout.itemAtPosition(0, 0).widget().text() == "12.500"
    assert widget._shared_scale_bottom_layout.itemAtPosition(0, 0).widget().text() == "10.000"

    widget._set_shared_scale_decimal_places(1, emit_state_change=False)

    assert widget._shared_scale_top_layout.itemAtPosition(0, 0).widget().text() == "15.0"
    assert widget._shared_scale_mid_layout.itemAtPosition(0, 0).widget().text() == "12.5"
    assert widget._shared_scale_bottom_layout.itemAtPosition(0, 0).widget().text() == "10.0"
    assert widget.time_selection_state()["shared_scale_decimal_places"] == 1

    widget.set_time_selection_state({"shared_scale_decimal_places": 4})

    assert widget._shared_scale_top_layout.itemAtPosition(0, 0).widget().text() == "15.0000"
    assert widget._shared_scale_mid_layout.itemAtPosition(0, 0).widget().text() == "12.5000"
    assert widget._shared_scale_bottom_layout.itemAtPosition(0, 0).widget().text() == "10.0000"
    assert widget.time_selection_state()["shared_scale_decimal_places"] == 4


def test_visible_stats_ignore_padded_draw_samples(qapp) -> None:
    widget = TrendPlotWidget()
    plotted = _make_named_plot_series_with_minutes("Pressure", [0, 5, 10, 15], [100.0, 1.0, 2.0, 3.0])
    captured_stats: list[list[TrendVisibleSeriesStats]] = []
    widget.visibleStatsChanged.connect(lambda stats: captured_stats.append(list(stats)))
    widget.plot_series_group(workbook_name="Workbook", plotted_series=[plotted])

    start = datetime(2026, 1, 1, 0, 5, 0).timestamp()
    end = datetime(2026, 1, 1, 0, 15, 0).timestamp()
    widget._set_visible_range(start, end, preserved_y_range=widget.current_y_range())

    stats = captured_stats[-1][0]
    assert stats.sample_count == 3
    assert stats.latest_value == 3.0
    assert stats.minimum_value == 1.0
    assert stats.maximum_value == 3.0
    assert stats.average_value == pytest.approx(2.0)


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
