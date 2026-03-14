from __future__ import annotations

from datetime import datetime

import polars as pl
from PySide6.QtCore import Qt

from wte_trend_viewer.data_manager import TrendSeriesData, TrendSheetData
from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import (
    LEGEND_HIGH_RANGE_COLUMN,
    LEGEND_SHEET_COLUMN,
    LEGEND_TAG_COLUMN,
    LEGEND_UNIT_COLUMN,
    LEGEND_LOW_RANGE_COLUMN,
    TrendViewerMainWindow,
)
from wte_trend_viewer.ui.widgets.hierarchy_tree import SearchableHierarchyTree
from wte_trend_viewer.ui.widgets.trend_plot_widget import (
    TrendCursorSeriesStats,
    TrendCursorStats,
    TrendPlotSeries,
    TrendVisibleSeriesStats,
)


def _make_plot_series(tag_name: str) -> TrendPlotSeries:
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
    return TrendPlotSeries(sheet=sheet, series=series)


def test_hierarchy_tree_selected_tag_names_keep_original_name(qapp) -> None:
    tree = SearchableHierarchyTree()
    tag_item = tree.add_tag("Process Data/TAG001", emit_change=False)

    tag_item.setText(0, "TAG001 - Example temperature [C]")
    tag_item.setSelected(True)

    assert tree.selected_tag_names() == ["Process Data/TAG001"]


def test_custom_name_updates_imported_and_hierarchy_labels(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    original_name = "Process Data/TAG001"
    custom_name = "TAG001 - Example temperature"
    unit = "C"

    window.set_imported_tags([original_name], persist=False)
    group = window._hierarchy_tree.add_category("Group", emit_change=False)
    hierarchy_tag = window._hierarchy_tree.add_tag(original_name, parent=group, emit_change=False)

    window._set_custom_name_for_tag(original_name, custom_name, persist=False)
    window._assign_unit_to_tags([original_name], unit, persist=False)

    imported_item = window._imported_tags_list.find_item_by_tag_name(original_name)

    assert imported_item is not None
    assert imported_item.text() == f"{custom_name} | {original_name} | [C]"
    assert hierarchy_tag.text(0) == f"{custom_name} [C]"
    assert imported_item.toolTip() == (
        f"Custom: {custom_name}\nOriginal: {original_name}\nUnit: [C]"
    )


def test_custom_name_does_not_replace_original_name_in_hierarchy_session(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    original_name = "Process Data/TAG001"
    custom_name = "TAG001 - Example temperature"

    group = window._hierarchy_tree.add_category("Group", emit_change=False)
    window._hierarchy_tree.add_tag(original_name, parent=group, emit_change=False)
    window._set_custom_name_for_tag(original_name, custom_name, persist=False)

    session = window._capture_session()

    assert session.hierarchy[0].children[0].name == original_name


def test_clearing_custom_name_restores_default_labels(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    original_name = "Process Data/TAG001"

    window.set_imported_tags([original_name], persist=False)
    hierarchy_tag = window._hierarchy_tree.add_tag(original_name, emit_change=False)
    window._set_custom_name_for_tag(
        original_name,
        "TAG001 - Example temperature",
        persist=False,
    )

    assert window._clear_custom_name_for_tag(original_name, persist=False) is True

    imported_item = window._imported_tags_list.find_item_by_tag_name(original_name)
    assert imported_item is not None
    assert imported_item.text() == original_name
    assert hierarchy_tag.text(0) == original_name


def test_legend_and_analytics_use_custom_label_with_unit(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    original_name = "Process Data/TAG001"
    custom_name = "TAG001 - Example temperature"
    unit = "C"
    plotted = _make_plot_series(original_name)

    window._set_custom_name_for_tag(original_name, custom_name, persist=False)
    window._assign_unit_to_tags([original_name], unit, persist=False)
    window._update_legend_table([plotted])
    window._current_visible_stats = [
        TrendVisibleSeriesStats(
            tag_name=original_name,
            sheet_name="Process Data",
            color="#6CB6FF",
            sample_count=3,
            latest_value=13.0,
            minimum_value=10.0,
            maximum_value=15.0,
            average_value=12.67,
        )
    ]
    window._current_cursor_stats = None
    window._update_analytics_table()

    assert window._legend_table is not None
    assert window._legend_table.item(0, LEGEND_TAG_COLUMN).text() == f"{custom_name} [C]"
    assert (
        window._legend_table.item(0, LEGEND_TAG_COLUMN).foreground().style()
        == Qt.BrushStyle.SolidPattern
    )
    assert (
        window._legend_table.item(0, LEGEND_SHEET_COLUMN).foreground().style()
        == Qt.BrushStyle.NoBrush
    )
    assert (
        window._legend_table.item(0, LEGEND_UNIT_COLUMN).foreground().style()
        == Qt.BrushStyle.NoBrush
    )
    assert (
        window._legend_table.item(0, LEGEND_LOW_RANGE_COLUMN).foreground().style()
        == Qt.BrushStyle.NoBrush
    )
    assert (
        window._legend_table.item(0, LEGEND_HIGH_RANGE_COLUMN).foreground().style()
        == Qt.BrushStyle.NoBrush
    )
    assert window._analytics_table is not None
    assert window._analytics_table.item(0, 0).text() == f"{custom_name} [C]"
    assert window._analytics_table.item(0, 0).foreground().style() == Qt.BrushStyle.SolidPattern
    assert window._analytics_table.item(0, 1).foreground().style() == Qt.BrushStyle.NoBrush


def test_bottom_tabs_are_legend_analytics_settings(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )

    assert window._bottom_tabs is not None
    assert [window._bottom_tabs.tabText(index) for index in range(window._bottom_tabs.count())] == [
        "Legend",
        "Analytics",
        "Settings",
    ]


def test_analytics_cursor_value_prefers_cursor_time_value(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    tag_name = "Process Data/TAG001"
    window._current_visible_stats = [
        TrendVisibleSeriesStats(
            tag_name=tag_name,
            sheet_name="Process Data",
            color="#6CB6FF",
            sample_count=3,
            latest_value=6.2,
            minimum_value=5.0,
            maximum_value=6.2,
            average_value=5.6,
        )
    ]
    window._current_cursor_stats = TrendCursorStats(
        cursor_timestamp=datetime(2026, 1, 1, 0, 6, 0).timestamp(),
        series_stats=(
            TrendCursorSeriesStats(
                tag_name=tag_name,
                sheet_name="Process Data",
                color="#6CB6FF",
                sample_timestamp=datetime(2026, 1, 1, 0, 5, 0).timestamp(),
                cursor_value=7.918,
                interpolated_value=5.255,
                interpolation_mode="linear",
                interpolation_start_timestamp=datetime(2026, 1, 1, 0, 5, 0).timestamp(),
                interpolation_end_timestamp=datetime(2026, 1, 1, 0, 10, 0).timestamp(),
                previous_timestamp=datetime(2026, 1, 1, 0, 5, 0).timestamp(),
                previous_value=5.2,
                next_timestamp=datetime(2026, 1, 1, 0, 10, 0).timestamp(),
                next_value=5.3,
            ),
        ),
    )

    window._update_analytics_table()

    assert window._analytics_table is not None
    assert window._analytics_table.item(0, 1).text() == "5.255"
    assert "Interpolation: linear" in window._analytics_table.item(0, 1).toolTip()
