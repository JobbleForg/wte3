from __future__ import annotations

from PySide6.QtWidgets import QWidget

from wte_trend_viewer.ui.widgets.trend_plot_widget import _FloatingLegendOverlay


def _make_overlay(qapp, entries: int = 6) -> tuple[QWidget, _FloatingLegendOverlay]:
    parent = QWidget()
    parent.resize(900, 500)
    parent.show()

    overlay = _FloatingLegendOverlay(parent)
    overlay.set_entries(
        [
            (
                "#6CB6FF",
                f"Customer Data/VeryLongLegendTagNameFY{1000 + index}",
            )
            for index in range(entries)
        ]
    )
    overlay.show()
    qapp.processEvents()
    return parent, overlay


def test_legend_entries_scale_down_with_short_height(qapp) -> None:
    _, overlay = _make_overlay(qapp)

    overlay.resize(260, 180)
    qapp.processEvents()
    overlay._sync_entries_layout()
    qapp.processEvents()
    full_height_font = overlay._entries_container._entries[0]._label.font().pointSizeF()

    overlay.resize(260, 120)
    qapp.processEvents()
    overlay._sync_entries_layout()
    qapp.processEvents()

    entry = overlay._entries_container._entries[0]
    margins = entry._layout.contentsMargins()
    content_height = entry.height() - margins.top() - margins.bottom()

    assert entry._label.font().pointSizeF() < full_height_font
    assert entry._label.sizeHint().height() <= content_height


def test_legend_entries_reflow_when_narrowing_after_expanding(qapp) -> None:
    _, overlay = _make_overlay(qapp)

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


def test_legend_resize_handles_match_reference_size_and_placement(qapp) -> None:
    _, overlay = _make_overlay(qapp)
    overlay.resize(320, 180)
    qapp.processEvents()

    assert overlay._width_handle.size().width() == 10
    assert overlay._height_handle.size().height() == 10
    assert overlay._width_handle.x() == overlay.width() - (overlay._width_handle.width() // 2)
    assert overlay._height_handle.y() == overlay.height() - (overlay._height_handle.height() // 2)


def test_legend_entry_text_is_elided_instead_of_raw_clipping(qapp) -> None:
    _, overlay = _make_overlay(qapp, entries=2)
    overlay.resize(220, 120)
    qapp.processEvents()
    overlay._sync_entries_layout()
    qapp.processEvents()

    label = overlay._entries_container._entries[0]._label

    assert label.text() != label.toolTip()
