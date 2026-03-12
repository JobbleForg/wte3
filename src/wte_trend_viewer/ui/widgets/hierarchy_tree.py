from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QWidget,
)

from .imported_tag_list import SearchableImportedTagList


ITEM_KIND_ROLE = Qt.UserRole + 1
GROUP_ITEM_KIND = "group"
TAG_ITEM_KIND = "tag"


class SearchableHierarchyTree(QTreeWidget):
    """Hierarchy tree ready for manual grouping, copy-drops, and type-to-search."""

    structureChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setFocusPolicy(Qt.StrongFocus)

        self._search_buffer = ""
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(900)
        self._search_timer.timeout.connect(self._clear_search_buffer)

    def clear_hierarchy(self, *, emit_change: bool = True) -> None:
        self.clear()
        if emit_change:
            self.structureChanged.emit()

    def add_category(
        self,
        name: str,
        parent: QTreeWidgetItem | None = None,
        *,
        emit_change: bool = True,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, ITEM_KIND_ROLE, GROUP_ITEM_KIND)
        item.setFlags(
            item.flags()
            | Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )

        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)
            parent.setExpanded(True)

        self.setCurrentItem(item)
        if emit_change:
            self.structureChanged.emit()
        return item

    def add_tag(
        self,
        name: str,
        parent: QTreeWidgetItem | None = None,
        *,
        emit_change: bool = True,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, ITEM_KIND_ROLE, TAG_ITEM_KIND)
        item.setFlags(
            item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        )

        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)
            parent.setExpanded(True)

        if emit_change:
            self.structureChanged.emit()
        return item

    def group_target_for_subcategory(self) -> QTreeWidgetItem | None:
        current = self.currentItem()
        if current is None:
            return None
        if current.data(0, ITEM_KIND_ROLE) == GROUP_ITEM_KIND:
            return current
        return current.parent()

    def remove_selected_item(self) -> bool:
        item = self.currentItem()
        if item is None:
            return False

        parent = item.parent()
        if parent is None:
            index = self.indexOfTopLevelItem(item)
            if index >= 0:
                self.takeTopLevelItem(index)
            else:
                return False
        else:
            index = parent.indexOfChild(item)
            if index >= 0:
                parent.takeChild(index)
            else:
                return False

        self.structureChanged.emit()
        return True

    def dropEvent(self, event) -> None:
        if isinstance(event.source(), SearchableImportedTagList) and event.mimeData().hasText():
            target_parent = self._drop_target_group(event.position().toPoint())
            tag_names = [
                tag_name.strip()
                for tag_name in event.mimeData().text().splitlines()
                if tag_name.strip()
            ]
            for tag_name in tag_names:
                self.add_tag(tag_name, target_parent, emit_change=False)
            self.structureChanged.emit()
            event.acceptProposedAction()
            return

        super().dropEvent(event)
        self.structureChanged.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            if self.remove_selected_item():
                return
        if self._handle_type_search(event):
            return
        super().keyPressEvent(event)

    def _handle_type_search(self, event) -> bool:
        modifiers = event.modifiers()
        if modifiers not in (Qt.NoModifier, Qt.ShiftModifier):
            return False

        if event.key() == Qt.Key_Backspace and self._search_buffer:
            self._search_buffer = self._search_buffer[:-1]
            self._search_timer.start()
            self._select_first_match()
            return True

        if event.key() == Qt.Key_Escape:
            self._clear_search_buffer()
            return True

        text = event.text()
        if not text or not text.isprintable():
            return False

        self._search_buffer += text.casefold()
        self._search_timer.start()
        self._select_first_match()
        return True

    def _select_first_match(self) -> None:
        term = self._search_buffer.strip()
        if not term:
            return

        iterator = QTreeWidgetItemIterator(self)
        while iterator.value() is not None:
            item = iterator.value()
            if term in item.text(0).casefold():
                self.setCurrentItem(item)
                self.scrollToItem(item)
                self._expand_to_item(item)
                return
            iterator += 1

    def _expand_to_item(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def _drop_target_group(self, point) -> QTreeWidgetItem | None:
        target = self.itemAt(point)
        if target is None:
            return None
        if target.data(0, ITEM_KIND_ROLE) == GROUP_ITEM_KIND:
            return target
        return target.parent()

    def _clear_search_buffer(self) -> None:
        self._search_buffer = ""
