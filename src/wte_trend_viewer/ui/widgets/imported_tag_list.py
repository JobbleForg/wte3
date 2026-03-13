from __future__ import annotations

from PySide6.QtCore import QMimeData, QTimer, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget


TAG_MIME_TYPE = "application/x-wte-imported-tags"
TAG_NAME_ROLE = Qt.UserRole + 2


class SearchableImportedTagList(QListWidget):
    """Imported-tag list with copy-drag and type-to-search behavior."""

    tagsChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setFocusPolicy(Qt.StrongFocus)

        self._search_buffer = ""
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(900)
        self._search_timer.timeout.connect(self._clear_search_buffer)

    def set_tags(self, tags: list[str], *, emit_change: bool = True) -> None:
        self.clear()
        for tag_name in sorted(set(tags), key=str.casefold):
            item = QListWidgetItem(tag_name)
            item.setData(TAG_NAME_ROLE, tag_name)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.addItem(item)
        if emit_change:
            self.tagsChanged.emit()

    def tags(self) -> list[str]:
        tags: list[str] = []
        for index in range(self.count()):
            item = self.item(index)
            tag_name = self.tag_name_for_item(item)
            if tag_name is not None:
                tags.append(tag_name)
        return tags

    def tag_name_for_item(self, item: QListWidgetItem | None) -> str | None:
        if item is None:
            return None
        value = item.data(TAG_NAME_ROLE)
        if isinstance(value, str) and value.strip():
            return value.strip()
        text = item.text().strip()
        return text or None

    def find_item_by_tag_name(self, tag_name: str) -> QListWidgetItem | None:
        target = tag_name.strip()
        if not target:
            return None

        for index in range(self.count()):
            item = self.item(index)
            if self.tag_name_for_item(item) == target:
                return item
        return None

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:
        tag_names = [
            tag_name
            for item in items
            for tag_name in [self.tag_name_for_item(item)]
            if tag_name is not None
        ]
        mime_data = QMimeData()
        mime_data.setText("\n".join(tag_names))
        mime_data.setData(TAG_MIME_TYPE, "\n".join(tag_names).encode("utf-8"))
        return mime_data

    def supportedDragActions(self) -> Qt.DropActions:
        return Qt.CopyAction

    def keyPressEvent(self, event) -> None:
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

        for index in range(self.count()):
            item = self.item(index)
            if item is not None and term in item.text().casefold():
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return

    def _clear_search_buffer(self) -> None:
        self._search_buffer = ""
