from __future__ import annotations

from wte_trend_viewer.session import SessionStore
from wte_trend_viewer.ui.main_window import TrendViewerMainWindow
from wte_trend_viewer.ui.widgets.hierarchy_tree import SearchableHierarchyTree


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
    unit = "[C]"

    window.set_imported_tags([original_name], persist=False)
    group = window._hierarchy_tree.add_category("Group", emit_change=False)
    hierarchy_tag = window._hierarchy_tree.add_tag(original_name, parent=group, emit_change=False)

    window._set_custom_name_for_tag(original_name, custom_name, persist=False)
    window._assign_unit_to_tags([original_name], unit, persist=False)

    imported_item = window._imported_tags_list.find_item_by_tag_name(original_name)

    assert imported_item is not None
    assert imported_item.text() == f"{custom_name} | {original_name} | {unit}"
    assert hierarchy_tag.text(0) == f"{custom_name} {unit}"
    assert imported_item.toolTip() == (
        f"Custom: {custom_name}\nOriginal: {original_name}\nUnit: {unit}"
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
