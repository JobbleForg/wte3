from __future__ import annotations

from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import TrendViewerMainWindow


def test_assign_unit_to_tags_updates_library_and_assignments(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )

    window._assign_unit_to_tags(["TagA", "TagB"], "[C]", persist=False)

    assert window._unit_for_tag("TagA") == "[C]"
    assert window._unit_for_tag("TagB") == "[C]"
    assert window._stored_available_units() == ["[C]"]


def test_rename_available_unit_updates_existing_assignments(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    window._assign_unit_to_tags(["TagA", "TagB"], "[C]", persist=False)

    window._rename_available_unit("[C]", "[degC]", persist=False)

    assert window._unit_for_tag("TagA") == "[degC]"
    assert window._unit_for_tag("TagB") == "[degC]"
    assert window._stored_available_units() == ["[degC]"]


def test_remove_available_unit_clears_existing_assignments(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    window._assign_unit_to_tags(["TagA", "TagB"], "[C]", persist=False)

    removed_count = window._remove_available_unit("[C]", persist=False)

    assert removed_count == 2
    assert window._unit_for_tag("TagA") is None
    assert window._unit_for_tag("TagB") is None
    assert window._stored_available_units() == []


def test_refresh_tag_unit_presentations_updates_tooltips(qapp, tmp_path) -> None:
    window = TrendViewerMainWindow(
        session_store=SessionStore(tmp_path),
        restore_last_session=False,
    )
    window.set_imported_tags(["TagA"], persist=False)
    group = window._hierarchy_tree.add_category("Group", emit_change=False)
    hierarchy_tag = window._hierarchy_tree.add_tag("TagA", parent=group, emit_change=False)

    window._assign_unit_to_tags(["TagA"], "[m3/hr]", persist=False)

    imported_item = window._imported_tags_list.item(0)

    assert imported_item is not None
    assert imported_item.toolTip() == "Original: TagA\nUnit: [m3/hr]"
    assert hierarchy_tag.toolTip(0) == "Original: TagA\nUnit: [m3/hr]"
