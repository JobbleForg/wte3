from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QAbstractItemView

from wte_trend_viewer.ui.main_window import TrendViewerMainWindow
from wte_trend_viewer.ui.widgets.hierarchy_tree import SearchableHierarchyTree


def test_hierarchy_tree_uses_extended_selection(qapp) -> None:
    tree = SearchableHierarchyTree()

    assert tree.selectionMode() == QAbstractItemView.ExtendedSelection


def test_hierarchy_tree_reports_selected_tags_in_tree_order(qapp) -> None:
    tree = SearchableHierarchyTree()
    group = tree.add_category("Group", emit_change=False)
    first_tag = tree.add_tag("TagA", parent=group, emit_change=False)
    second_tag = tree.add_tag("TagB", parent=group, emit_change=False)

    group.setSelected(True)
    first_tag.setSelected(True)
    second_tag.setSelected(True)

    assert tree.selected_tag_names() == ["TagA", "TagB"]


def test_hierarchy_tree_expands_selected_group_to_all_descendant_tags(qapp) -> None:
    tree = SearchableHierarchyTree()
    group = tree.add_category("Group", emit_change=False)
    sub_group = tree.add_category("Sub", parent=group, emit_change=False)
    tree.add_tag("TagA", parent=group, emit_change=False)
    tree.add_tag("TagB", parent=sub_group, emit_change=False)
    tree.add_tag("TagC", parent=sub_group, emit_change=False)

    group.setSelected(True)

    assert tree.selected_tag_names() == ["TagB", "TagC", "TagA"]


def test_hierarchy_tree_expands_selected_subgroup_to_its_descendant_tags_only(qapp) -> None:
    tree = SearchableHierarchyTree()
    group = tree.add_category("Group", emit_change=False)
    sub_group = tree.add_category("Sub", parent=group, emit_change=False)
    tree.add_tag("TagA", parent=group, emit_change=False)
    tree.add_tag("TagB", parent=sub_group, emit_change=False)
    tree.add_tag("TagC", parent=sub_group, emit_change=False)

    sub_group.setSelected(True)

    assert tree.selected_tag_names() == ["TagB", "TagC"]


def test_main_window_previews_all_selected_hierarchy_tags(qapp, monkeypatch) -> None:
    window = TrendViewerMainWindow(restore_last_session=False)
    group = window._hierarchy_tree.add_category("Group", emit_change=False)
    first_tag = window._hierarchy_tree.add_tag("TagA", parent=group, emit_change=False)
    second_tag = window._hierarchy_tree.add_tag("TagB", parent=group, emit_change=False)

    captured: dict[str, object] = {}

    def fake_preview(tag_names: list[str], *, persist_selection: bool) -> bool:
        captured["tag_names"] = list(tag_names)
        captured["persist_selection"] = persist_selection
        return True

    monkeypatch.setattr(window, "_preview_tags", fake_preview)

    selection_model = window._hierarchy_tree.selectionModel()
    first_index = window._hierarchy_tree.indexFromItem(first_tag)
    second_index = window._hierarchy_tree.indexFromItem(second_tag)
    selection_model.select(first_index, QItemSelectionModel.SelectionFlag.Select)
    selection_model.select(second_index, QItemSelectionModel.SelectionFlag.Select)
    selection_model.setCurrentIndex(
        second_index,
        QItemSelectionModel.SelectionFlag.NoUpdate,
    )

    window._handle_hierarchy_selection_changed()

    assert captured == {
        "tag_names": ["TagA", "TagB"],
        "persist_selection": True,
    }


def test_main_window_previews_descendant_tags_when_group_selected(qapp, monkeypatch) -> None:
    window = TrendViewerMainWindow(restore_last_session=False)
    group = window._hierarchy_tree.add_category("Group", emit_change=False)
    sub_group = window._hierarchy_tree.add_category("Sub", parent=group, emit_change=False)
    window._hierarchy_tree.add_tag("TagA", parent=group, emit_change=False)
    window._hierarchy_tree.add_tag("TagB", parent=sub_group, emit_change=False)
    window._hierarchy_tree.add_tag("TagC", parent=sub_group, emit_change=False)

    captured: dict[str, object] = {}

    def fake_preview(tag_names: list[str], *, persist_selection: bool) -> bool:
        captured["tag_names"] = list(tag_names)
        captured["persist_selection"] = persist_selection
        return True

    monkeypatch.setattr(window, "_preview_tags", fake_preview)

    selection_model = window._hierarchy_tree.selectionModel()
    group_index = window._hierarchy_tree.indexFromItem(group)
    selection_model.select(group_index, QItemSelectionModel.SelectionFlag.Select)
    selection_model.setCurrentIndex(
        group_index,
        QItemSelectionModel.SelectionFlag.NoUpdate,
    )

    window._handle_hierarchy_selection_changed()

    assert captured == {
        "tag_names": ["TagB", "TagC", "TagA"],
        "persist_selection": True,
    }
