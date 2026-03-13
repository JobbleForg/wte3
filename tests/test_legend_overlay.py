from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from wte_trend_viewer.ui.widgets.trend_plot_widget import (
    _FloatingLegendEntry,
    _FloatingLegendOverlay,
)


def test_floating_legend_entry_elides_long_text_when_narrow(qapp) -> None:
    entry = _FloatingLegendEntry("Customer Data/FY1104", "#6CB6FF")
    entry.resize(120, entry.height())
    qapp.processEvents()

    assert entry._label.text() != "Customer Data/FY1104"
    assert "\u2026" in entry._label.text()


def test_legend_overlay_reflows_columns_when_narrowing_after_widening(qapp) -> None:
    parent = QWidget()
    parent.resize(900, 500)
    parent.show()

    overlay = _FloatingLegendOverlay(parent)
    overlay.set_entries(
        [("#6CB6FF", f"Customer Data/FY{i:04d}") for i in range(1102, 1108)]
    )
    overlay.show()
    qapp.processEvents()

    overlay.resize(700, 180)
    qapp.processEvents()
    overlay._sync_entries_layout()
    qapp.processEvents()
    assert overlay._entries_container._column_count == 3

    overlay.resize(260, 180)
    qapp.processEvents()
    overlay._sync_entries_layout()
    qapp.processEvents()
    assert overlay._entries_container._column_count == 1


def test_legend_resize_handles_match_reference_scale_and_edge_alignment(qapp) -> None:
    parent = QWidget()
    parent.resize(900, 500)
    parent.show()

    overlay = _FloatingLegendOverlay(parent)
    overlay.set_entries([("#6CB6FF", "Customer Data/FY1104")])
    overlay.resize(260, 180)
    overlay.show()
    qapp.processEvents()

    assert overlay._width_handle.size() == QSize(10, 10)
    assert overlay._height_handle.size() == QSize(10, 10)
    assert overlay._width_handle.x() >= overlay.width() - overlay._width_handle.width() - 1
    assert overlay._height_handle.y() >= overlay.height() - overlay._height_handle.height() - 1
