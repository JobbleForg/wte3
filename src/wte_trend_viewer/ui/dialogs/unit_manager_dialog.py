from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...tag_units import normalize_unit_list, normalize_unit_text


class UnitManagerDialog(QDialog):
    """Manage the reusable unit library for tag assignment."""

    def __init__(self, units: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial_units = normalize_unit_list(units)

        self.setWindowTitle("Edit Units")
        self.resize(420, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        description = QLabel(
            (
                "Units added here appear in the tag right-click Assign unit menu. "
                "Deleting a unit clears it from any assigned tags when you apply changes."
            ),
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._unit_list = QListWidget(self)
        self._unit_list.setAlternatingRowColors(True)
        layout.addWidget(self._unit_list, stretch=1)
        self._populate_units(self._initial_units)

        button_row = QWidget(self)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)

        add_button = QPushButton("Add", button_row)
        add_button.clicked.connect(self._add_unit)
        button_layout.addWidget(add_button)

        edit_button = QPushButton("Edit", button_row)
        edit_button.clicked.connect(self._edit_selected_unit)
        button_layout.addWidget(edit_button)

        delete_button = QPushButton("Delete", button_row)
        delete_button.clicked.connect(self._delete_selected_unit)
        button_layout.addWidget(delete_button)

        button_layout.addStretch(1)
        layout.addWidget(button_row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def units(self) -> list[str]:
        return [
            self._unit_list.item(index).text().strip()
            for index in range(self._unit_list.count())
            if self._unit_list.item(index).text().strip()
        ]

    def renamed_units(self) -> dict[str, str]:
        renamed: dict[str, str] = {}
        for index in range(self._unit_list.count()):
            item = self._unit_list.item(index)
            original_value = item.data(Qt.UserRole)
            current_value = item.text().strip()
            if (
                isinstance(original_value, str)
                and original_value.strip()
                and current_value
                and current_value != original_value.strip()
            ):
                renamed[original_value.strip()] = current_value
        return renamed

    def removed_units(self) -> list[str]:
        remaining_originals = {
            item.data(Qt.UserRole).strip()
            for index in range(self._unit_list.count())
            for item in [self._unit_list.item(index)]
            if isinstance(item.data(Qt.UserRole), str) and item.data(Qt.UserRole).strip()
        }
        return [
            unit
            for unit in self._initial_units
            if unit not in remaining_originals and unit not in self.renamed_units()
        ]

    def accept(self) -> None:
        units = normalize_unit_list(self.units())
        if len(units) != self._unit_list.count():
            QMessageBox.warning(
                self,
                "Invalid Units",
                "Unit names must be non-empty and unique.",
            )
            return
        super().accept()

    def _populate_units(self, units: list[str]) -> None:
        self._unit_list.clear()
        for unit in units:
            item = QListWidgetItem(unit)
            item.setData(Qt.UserRole, unit)
            self._unit_list.addItem(item)

    def _add_unit(self) -> None:
        value, accepted = QInputDialog.getText(
            self,
            "Add Unit",
            "Unit (for example [m3/hr] or [C]):",
        )
        if not accepted:
            return

        unit = normalize_unit_text(value)
        if unit is None:
            QMessageBox.warning(self, "Invalid Unit", "Enter a non-empty unit.")
            return
        if self._has_unit(unit):
            QMessageBox.warning(self, "Duplicate Unit", f"{unit} already exists.")
            return

        item = QListWidgetItem(unit)
        item.setData(Qt.UserRole, None)
        self._unit_list.addItem(item)
        self._unit_list.setCurrentItem(item)

    def _edit_selected_unit(self) -> None:
        current_item = self._unit_list.currentItem()
        if current_item is None:
            QMessageBox.warning(self, "No Unit Selected", "Select a unit to edit.")
            return

        current_text = current_item.text().strip()
        value, accepted = QInputDialog.getText(
            self,
            "Edit Unit",
            "Unit:",
            text=current_text,
        )
        if not accepted:
            return

        unit = normalize_unit_text(value)
        if unit is None:
            QMessageBox.warning(self, "Invalid Unit", "Enter a non-empty unit.")
            return
        if unit.casefold() != current_text.casefold() and self._has_unit(unit):
            QMessageBox.warning(self, "Duplicate Unit", f"{unit} already exists.")
            return

        current_item.setText(unit)

    def _delete_selected_unit(self) -> None:
        current_row = self._unit_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Unit Selected", "Select a unit to delete.")
            return
        self._unit_list.takeItem(current_row)

    def _has_unit(self, unit: str) -> bool:
        target = unit.casefold()
        for index in range(self._unit_list.count()):
            item = self._unit_list.item(index)
            if item.text().strip().casefold() == target:
                return True
        return False
