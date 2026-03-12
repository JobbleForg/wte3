from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...workbook import WorkbookInspectionResult, WorkbookSheetSummary


class SheetSelectionDialog(QDialog):
    """Choose which data sheets from a workbook should populate Imported tags."""

    def __init__(
        self,
        inspection: WorkbookInspectionResult,
        *,
        selected_sheet_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._inspection = inspection
        self._selected_sheet_names = set(selected_sheet_names or [])

        self.setWindowTitle("Select Sheets")
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        description = QLabel(
            (
                f"Choose which worksheets from {inspection.source_path.name} should populate "
                "the Imported tags list."
            ),
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._sheet_list = QListWidget(self)
        self._sheet_list.setAlternatingRowColors(True)
        self._populate_sheet_list()
        layout.addWidget(self._sheet_list, stretch=1)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)

        select_detected_button = QPushButton("Select detected", button_row)
        select_detected_button.clicked.connect(self._select_detected)
        button_layout.addWidget(select_detected_button)

        clear_button = QPushButton("Clear", button_row)
        clear_button.clicked.connect(self._clear_selection)
        button_layout.addWidget(clear_button)
        button_layout.addStretch()

        layout.addWidget(button_row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def selected_sheet_names(self) -> list[str]:
        selected: list[str] = []
        for index in range(self._sheet_list.count()):
            item = self._sheet_list.item(index)
            if item.checkState() == Qt.Checked:
                sheet_name = item.data(Qt.UserRole)
                if isinstance(sheet_name, str):
                    selected.append(sheet_name)
        return selected

    def accept(self) -> None:
        if not self.selected_sheet_names():
            QMessageBox.warning(
                self,
                "No Sheets Selected",
                "Select at least one sheet to continue.",
            )
            return
        super().accept()

    def _populate_sheet_list(self) -> None:
        data_sheet_names = {sheet.name for sheet in self._inspection.data_sheets}
        default_selected = self._selected_sheet_names or data_sheet_names

        for sheet in self._inspection.sheets:
            label = self._describe_sheet(sheet)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, sheet.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if sheet.name in default_selected else Qt.Unchecked)
            self._sheet_list.addItem(item)

    def _describe_sheet(self, sheet: WorkbookSheetSummary) -> str:
        if sheet.is_data_sheet and sheet.timestamp_column:
            return (
                f"{sheet.name}  ({len(sheet.tag_names)} tags, {sheet.row_count} rows, "
                f"time column: {sheet.timestamp_column})"
            )
        return f"{sheet.name}  ({sheet.row_count} rows, no timestamp detected)"

    def _select_detected(self) -> None:
        data_sheet_names = {sheet.name for sheet in self._inspection.data_sheets}
        for index in range(self._sheet_list.count()):
            item = self._sheet_list.item(index)
            sheet_name = item.data(Qt.UserRole)
            item.setCheckState(Qt.Checked if sheet_name in data_sheet_names else Qt.Unchecked)

    def _clear_selection(self) -> None:
        for index in range(self._sheet_list.count()):
            self._sheet_list.item(index).setCheckState(Qt.Unchecked)
