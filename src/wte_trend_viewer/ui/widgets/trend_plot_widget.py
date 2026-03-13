from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QPoint, QRect, QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...data_manager import TrendSeriesData, TrendSheetData


PLOT_COLORS = (
    "#6CB6FF",
    "#F28F3B",
    "#61D095",
    "#E06C75",
    "#C678DD",
    "#E5C07B",
)
MIN_VISIBLE_SAMPLES = 800


@dataclass(frozen=True)
class TrendPlotSeries:
    sheet: TrendSheetData
    series: TrendSeriesData


@dataclass(frozen=True)
class TrendVisibleSeriesStats:
    tag_name: str
    sheet_name: str
    color: str
    sample_count: int
    latest_value: float | None
    minimum_value: float | None
    maximum_value: float | None
    average_value: float | None


@dataclass(frozen=True)
class TrendCursorSeriesStats:
    tag_name: str
    sheet_name: str
    color: str
    sample_timestamp: float | None
    cursor_value: float | None


@dataclass(frozen=True)
class TrendCursorStats:
    cursor_timestamp: float
    series_stats: tuple[TrendCursorSeriesStats, ...]


@dataclass
class _PreparedTrendPlotSeries:
    plotted: TrendPlotSeries
    color: str
    x_values: np.ndarray
    y_values: np.ndarray
    curve: object


class _FloatingLegendEntry(QFrame):
    MINIMUM_COLUMN_WIDTH = 190
    _BASE_HEIGHT = 28
    _MIN_HEIGHT = 16
    _MIN_SCALE = 0.58
    _MIN_FONT_POINT_SIZE = 6.0
    _BASE_HORIZONTAL_MARGIN = 8
    _BASE_VERTICAL_MARGIN = 4
    _BASE_SPACING = 8
    _BASE_SWATCH_WIDTH = 18
    _BASE_SWATCH_HEIGHT = 4

    def __init__(self, text: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("floatingLegendEntry")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(8)

        self._swatch = QFrame(self)
        self._swatch.setStyleSheet(f"background-color: {color}; border: none;")
        self._layout.addWidget(self._swatch, alignment=Qt.AlignVCenter)

        self._label = _LegendEntryLabel(text, self)
        self._label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._layout.addWidget(self._label, stretch=1)

        label_font = self._label.font()
        self._base_font_point_size = label_font.pointSizeF()
        if self._base_font_point_size <= 0:
            self._base_font_point_size = float(label_font.pointSize() or 10)

        self.set_scale(1.0)

    def set_scale(self, scale: float) -> None:
        scale = max(self._MIN_SCALE, min(scale, 1.0))
        horizontal_margin = max(5, int(round(self._BASE_HORIZONTAL_MARGIN * scale)))
        vertical_margin = max(2, int(round(self._BASE_VERTICAL_MARGIN * scale)))
        spacing = max(4, int(round(self._BASE_SPACING * scale)))
        swatch_width = max(10, int(round(self._BASE_SWATCH_WIDTH * scale)))
        swatch_height = max(2, int(round(self._BASE_SWATCH_HEIGHT * scale)))

        self._layout.setContentsMargins(
            horizontal_margin,
            vertical_margin,
            horizontal_margin,
            vertical_margin,
        )
        self._layout.setSpacing(spacing)
        self._swatch.setFixedSize(swatch_width, swatch_height)

        label_font = self._label.font()
        label_font.setPointSizeF(
            max(self._MIN_FONT_POINT_SIZE, self._base_font_point_size * scale)
        )
        self._label.setFont(label_font)
        self._label.refresh_text()

        font_metrics = QFontMetrics(label_font)
        row_height = max(
            self._MIN_HEIGHT,
            max(font_metrics.height(), swatch_height) + (vertical_margin * 2),
        )
        self.setFixedHeight(row_height)


class _LegendEntryLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setToolTip(text)

    def refresh_text(self) -> None:
        available_width = max(0, self.contentsRect().width())
        if available_width <= 0:
            super().setText(self._full_text)
            return
        elided = self.fontMetrics().elidedText(
            self._full_text,
            Qt.ElideRight,
            available_width,
        )
        super().setText(elided)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_text()


class _WrappingLegendEntries(QWidget):
    MINIMUM_COLUMN_WIDTH = _FloatingLegendEntry.MINIMUM_COLUMN_WIDTH

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[_FloatingLegendEntry] = []
        self._column_count = 0
        self._row_count = 0
        self._available_width = 0
        self._available_height = 0
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setHorizontalSpacing(6)
        self._layout.setVerticalSpacing(4)

    def set_entries(self, entries: list[tuple[str, str]]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._entries = [
            _FloatingLegendEntry(text, color, self)
            for color, text in entries
        ]
        self._column_count = 0
        self._row_count = 0
        self._rebuild_layout()

    def update_available_size(self, width: int, height: int) -> None:
        self._available_width = max(1, int(width))
        self._available_height = max(1, int(height))
        self._rebuild_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._available_width <= 0:
            self._available_width = max(1, self.contentsRect().width())
        if self._available_height <= 0:
            self._available_height = max(1, self.contentsRect().height())
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        if not self._entries:
            self._column_count = 0
            self._row_count = 0
            self.setMinimumHeight(0)
            return

        contents_margins = self._layout.contentsMargins()
        available_width = max(1, self._available_width or self.contentsRect().width())
        available_height = max(1, self._available_height or self.contentsRect().height())
        horizontal_spacing = max(0, self._layout.horizontalSpacing())
        vertical_spacing = max(0, self._layout.verticalSpacing())
        content_width = max(
            1,
            available_width - contents_margins.left() - contents_margins.right(),
        )
        target_column_width = self.MINIMUM_COLUMN_WIDTH + horizontal_spacing
        column_count = max(1, (content_width + horizontal_spacing) // target_column_width)
        row_count = max(1, (len(self._entries) + column_count - 1) // column_count)
        content_height = max(
            1,
            available_height - contents_margins.top() - contents_margins.bottom(),
        )
        available_row_height = (
            content_height - (max(0, row_count - 1) * vertical_spacing)
        ) / row_count
        scale = min(1.0, available_row_height / _FloatingLegendEntry._BASE_HEIGHT)

        for entry in self._entries:
            entry.set_scale(scale)

        previous_column_count = self._column_count
        self._column_count = column_count
        self._row_count = row_count
        while self._layout.count():
            self._layout.takeAt(0)

        reset_count = max(previous_column_count, column_count) + 2
        for column_index in range(reset_count):
            self._layout.setColumnStretch(column_index, 0)

        for column_index in range(column_count):
            self._layout.setColumnStretch(column_index, 1)

        for index, entry in enumerate(self._entries):
            row_index = index // column_count
            column_index = index % column_count
            self._layout.addWidget(entry, row_index, column_index)

        self.setMinimumHeight(self.sizeHint().height())
        self.updateGeometry()


class _LegendResizeHandle(QWidget):
    dragged = Signal(int)
    dragFinished = Signal()
    _IDLE_DIAMETER = 5
    _ACTIVE_DIAMETER = 7

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._orientation = orientation
        self._hovered = False
        self._pressed = False
        self._last_global_pos: QPoint | None = None

        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFixedSize(10, 10)
        self.setCursor(
            Qt.SizeHorCursor if orientation == Qt.Horizontal else Qt.SizeVerCursor
        )

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        if not self._pressed:
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._pressed = True
        self._last_global_pos = event.globalPosition().toPoint()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._pressed or self._last_global_pos is None:
            super().mouseMoveEvent(event)
            return

        current_global_pos = event.globalPosition().toPoint()
        delta = current_global_pos - self._last_global_pos
        primary_delta = delta.x() if self._orientation == Qt.Horizontal else delta.y()
        if primary_delta:
            self.dragged.emit(primary_delta)
            self._last_global_pos = current_global_pos
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self._pressed:
            super().mouseReleaseEvent(event)
            return
        self._pressed = False
        self._last_global_pos = None
        self.update()
        self.dragFinished.emit()
        event.accept()

    def paintEvent(self, event) -> None:
        del event
        diameter = self._ACTIVE_DIAMETER if self._hovered or self._pressed else self._IDLE_DIAMETER

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        fill_color = QColor("#8BA7C2" if self._hovered or self._pressed else "#576C80")
        border_color = QColor("#C7D4DE" if self._pressed else "#91A5B7")
        painter.setPen(border_color)
        painter.setBrush(fill_color)
        x_pos = (self.width() - diameter) / 2
        y_pos = (self.height() - diameter) / 2
        painter.drawEllipse(int(x_pos), int(y_pos), diameter, diameter)


class _FloatingLegendOverlay(QFrame):
    stateChanged = Signal()

    _DEFAULT_SIZE = (260, 180)
    _MIN_WIDTH = 240
    _MIN_HEIGHT = 120
    _COLLAPSED_HEIGHT = 34
    _EDGE_PADDING = 12

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("floatingLegendOverlay")
        self.setMouseTracking(True)

        self._drag_offset: QPoint | None = None
        self._expanded_size = None
        self._minimized = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QWidget(self)
        self._header.setObjectName("floatingLegendHeader")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 6, 6, 6)
        header_layout.setSpacing(6)

        self._title_label = QLabel("Trend legend", self._header)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._toggle_button = QPushButton("-", self._header)
        self._toggle_button.setObjectName("floatingLegendToggle")
        self._toggle_button.setFixedSize(22, 20)
        self._toggle_button.clicked.connect(self.toggle_minimized)
        header_layout.addWidget(self._toggle_button)

        layout.addWidget(self._header)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setObjectName("floatingLegendScrollArea")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self._scroll_area, stretch=1)

        self._entries_container = _WrappingLegendEntries(self)
        self._scroll_area.setWidget(self._entries_container)

        self._width_handle = _LegendResizeHandle(Qt.Horizontal, self)
        self._width_handle.dragged.connect(self._resize_width_by)
        self._width_handle.dragFinished.connect(self.stateChanged.emit)

        self._height_handle = _LegendResizeHandle(Qt.Vertical, self)
        self._height_handle.dragged.connect(self._resize_height_by)
        self._height_handle.dragFinished.connect(self.stateChanged.emit)

        self.resize(*self._DEFAULT_SIZE)
        self.hide()

    def set_entries(self, entries: list[tuple[str, str]]) -> None:
        self._entries_container.set_entries(entries)
        if entries:
            self.show()
            self.raise_()
            self._sync_entries_layout()
            self._update_resize_handles()
            self.clamp_to_parent()
        else:
            self.hide()

    def legend_state(self) -> dict[str, object]:
        expanded_size = self._expanded_size if self._expanded_size is not None else self.size()
        return {
            "floating_overlay_geometry": [
                int(self.x()),
                int(self.y()),
                int(self.width()),
                int(self.height()),
            ],
            "floating_overlay_expanded_size": [
                int(expanded_size.width()),
                int(expanded_size.height()),
            ],
            "floating_overlay_minimized": self._minimized,
        }

    def apply_state(self, state: dict[str, object]) -> None:
        expanded_size = state.get("floating_overlay_expanded_size")
        if (
            isinstance(expanded_size, list)
            and len(expanded_size) == 2
            and all(isinstance(value, int) for value in expanded_size)
        ):
            self._expanded_size = self._clamp_size(expanded_size[0], expanded_size[1])

        geometry = state.get("floating_overlay_geometry")
        if (
            isinstance(geometry, list)
            and len(geometry) == 4
            and all(isinstance(value, int) for value in geometry)
        ):
            x_pos, y_pos, width, height = geometry
            self.setGeometry(self._clamp_geometry(QRect(x_pos, y_pos, width, height)))
            if self._expanded_size is None:
                self._expanded_size = self.size()

        self.set_minimized(
            bool(state.get("floating_overlay_minimized", False)),
            preserve_expanded_size=True,
        )
        self.clamp_to_parent()

    def set_minimized(
        self,
        minimized: bool,
        *,
        preserve_expanded_size: bool = False,
    ) -> None:
        if minimized == self._minimized:
            return

        self._minimized = minimized
        if minimized:
            if not preserve_expanded_size:
                self._expanded_size = self._clamp_size(self.width(), self.height())
            self._scroll_area.hide()
            self._toggle_button.setText("+")
            self.setMinimumHeight(self._COLLAPSED_HEIGHT)
            self.setMaximumHeight(self._COLLAPSED_HEIGHT)
            self.resize(max(self.width(), self._MIN_WIDTH), self._COLLAPSED_HEIGHT)
        else:
            expanded_size = self._expanded_size or self._clamp_size(*self._DEFAULT_SIZE)
            self._scroll_area.show()
            self._toggle_button.setText("-")
            self.setMinimumSize(self._MIN_WIDTH, self._MIN_HEIGHT)
            self.setMaximumHeight(16_777_215)
            self.resize(expanded_size)

        self._update_resize_handles()
        self.clamp_to_parent()
        self._sync_entries_layout()

    def toggle_minimized(self) -> None:
        self.set_minimized(not self._minimized)
        self.stateChanged.emit()

    def clamp_to_parent(self) -> None:
        self.setGeometry(self._clamp_geometry(self.geometry()))
        self._update_resize_handles()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._minimized:
            self._expanded_size = self._clamp_size(self.width(), self.height())
            self._sync_entries_layout()
        self._update_resize_handles()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if self._header.geometry().contains(event.position().toPoint()):
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None:
            super().mouseMoveEvent(event)
            return

        parent = self.parentWidget()
        if parent is None:
            return
        target_top_left = parent.mapFromGlobal(
            event.globalPosition().toPoint() - self._drag_offset
        )
        self.setGeometry(self._clamp_geometry(QRect(target_top_left, self.size())))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is None or event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self._drag_offset = None
        self.unsetCursor()
        self.stateChanged.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._header.geometry().contains(event.position().toPoint()):
            self.toggle_minimized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _resize_width_by(self, delta: int) -> None:
        if self._minimized:
            return
        geometry = self.geometry()
        geometry.setWidth(geometry.width() + delta)
        self.setGeometry(self._clamp_geometry(geometry))

    def _resize_height_by(self, delta: int) -> None:
        if self._minimized:
            return
        geometry = self.geometry()
        geometry.setHeight(geometry.height() + delta)
        self.setGeometry(self._clamp_geometry(geometry))

    def _update_resize_handles(self) -> None:
        handle_visible = not self._minimized
        self._width_handle.setVisible(handle_visible)
        self._height_handle.setVisible(handle_visible)
        if not handle_visible:
            return

        self._width_handle.raise_()
        self._height_handle.raise_()
        body_top = self._header.height()
        body_height = max(0, self.height() - body_top)
        self._width_handle.move(
            self.width() - (self._width_handle.width() // 2),
            body_top + max(0, (body_height - self._width_handle.height()) // 2),
        )
        self._height_handle.move(
            max(6, (self.width() - self._height_handle.width()) // 2),
            self.height() - (self._height_handle.height() // 2),
        )

    def _sync_entries_layout(self) -> None:
        if self._minimized:
            return
        self._entries_container.update_available_size(
            self._scroll_area.viewport().width(),
            self._scroll_area.viewport().height(),
        )

    def _clamp_size(self, width: int, height: int):
        parent = self.parentWidget()
        size_class = self.size().__class__
        if parent is None:
            return size_class(width, height)

        available = parent.rect().adjusted(
            self._EDGE_PADDING,
            self._EDGE_PADDING,
            -self._EDGE_PADDING,
            -self._EDGE_PADDING,
        )
        min_height = self._COLLAPSED_HEIGHT if self._minimized else self._MIN_HEIGHT
        width = max(self._MIN_WIDTH, min(width, available.width()))
        height = max(min_height, min(height, available.height()))
        return size_class(width, height)

    def _clamp_geometry(self, geometry: QRect) -> QRect:
        parent = self.parentWidget()
        if parent is None:
            return geometry

        available = parent.rect().adjusted(
            self._EDGE_PADDING,
            self._EDGE_PADDING,
            -self._EDGE_PADDING,
            -self._EDGE_PADDING,
        )
        if available.width() <= 0 or available.height() <= 0:
            return geometry

        min_height = self._COLLAPSED_HEIGHT if self._minimized else self._MIN_HEIGHT
        width = max(self._MIN_WIDTH, min(geometry.width(), available.width()))
        height = max(min_height, min(geometry.height(), available.height()))

        x_pos = min(max(geometry.x(), available.left()), available.right() - width + 1)
        y_pos = min(max(geometry.y(), available.top()), available.bottom() - height + 1)
        return QRect(x_pos, y_pos, width, height)


class TrendPlotWidget(QWidget):
    """Phase-2 preview plot with visible-window slicing and downsampling."""

    visibleRangeChanged = Signal(float, float)
    visibleStatsChanged = Signal(object)
    cursorStatsChanged = Signal(object)
    panFractionChanged = Signal(int, int)
    legendStateChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._summary_label = QLabel(self)
        self._summary_label.setAlignment(Qt.AlignCenter)
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        self._cursor_label = QLabel(self)
        self._cursor_label.setAlignment(Qt.AlignCenter)
        self._cursor_label.hide()
        layout.addWidget(self._cursor_label)

        axis_items = {"bottom": pg.DateAxisItem(orientation="bottom")}
        self._plot_widget = pg.PlotWidget(axisItems=axis_items, parent=self)
        self._plot_widget.setBackground("#171D23")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setMenuEnabled(False)
        self._plot_widget.hideButtons()
        self._plot_widget.setLabel("bottom", "Time")
        self._plot_widget.setLabel("left", "Value")
        layout.addWidget(self._plot_widget, stretch=1)
        layout.addWidget(self._build_navigation_row())

        self._current_workbook_name = ""
        self._current_plotted_series: list[TrendPlotSeries] = []
        self._prepared_series: list[_PreparedTrendPlotSeries] = []
        self._data_x_range: tuple[float, float] | None = None
        self._pending_x_range: tuple[float, float] | None = None
        self._current_cursor_x: float | None = None
        self._suspend_range_updates = False

        self._range_update_timer = QTimer(self)
        self._range_update_timer.setSingleShot(True)
        self._range_update_timer.setInterval(24)
        self._range_update_timer.timeout.connect(self._apply_pending_range_update)

        self._cursor_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen("#D8DFE6", width=1, style=Qt.PenStyle.DashLine),
        )
        self._cursor_line.setZValue(1_000)
        self._cursor_line.hide()

        self._floating_legend_overlay = _FloatingLegendOverlay(self._plot_widget)
        self._floating_legend_overlay.move(16, 16)
        self._floating_legend_overlay.stateChanged.connect(self.legendStateChanged.emit)

        self._plot_widget.installEventFilter(self)
        self._plot_widget.viewport().setMouseTracking(True)
        self._plot_widget.viewport().installEventFilter(self)
        self._plot_widget.scene().sigMouseMoved.connect(self._handle_scene_mouse_moved)
        self._plot_widget.sigXRangeChanged.connect(self._handle_x_range_changed)

        self.show_empty(
            "No live trend data loaded.\nOpen a workbook to prepare sheets and tags for plotting."
        )

    def _build_navigation_row(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch()

        self._pan_numerator_spin = QSpinBox(container)
        self._pan_numerator_spin.setRange(1, 100)
        self._pan_numerator_spin.setValue(1)
        self._pan_numerator_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._pan_numerator_spin.setAlignment(Qt.AlignCenter)
        self._pan_numerator_spin.setFixedWidth(52)
        self._pan_numerator_spin.valueChanged.connect(self._handle_pan_fraction_changed)
        layout.addWidget(self._pan_numerator_spin)

        slash_label = QLabel("/", container)
        slash_label.setAlignment(Qt.AlignCenter)
        slash_label.setFixedWidth(10)
        layout.addWidget(slash_label)

        self._pan_denominator_spin = QSpinBox(container)
        self._pan_denominator_spin.setRange(1, 100)
        self._pan_denominator_spin.setValue(4)
        self._pan_denominator_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._pan_denominator_spin.setAlignment(Qt.AlignCenter)
        self._pan_denominator_spin.setFixedWidth(52)
        self._pan_denominator_spin.valueChanged.connect(self._handle_pan_fraction_changed)
        layout.addWidget(self._pan_denominator_spin)

        self._pan_left_button = QPushButton("<", container)
        self._pan_left_button.setFixedWidth(40)
        self._pan_left_button.clicked.connect(self._pan_left_by_fraction)
        layout.addWidget(self._pan_left_button)

        self._pan_right_button = QPushButton(">", container)
        self._pan_right_button.setFixedWidth(40)
        self._pan_right_button.clicked.connect(self._pan_right_by_fraction)
        layout.addWidget(self._pan_right_button)

        return container

    def pan_fraction(self) -> tuple[int, int]:
        return self._pan_numerator_spin.value(), self._pan_denominator_spin.value()

    def set_pan_fraction(self, numerator: int, denominator: int) -> None:
        safe_numerator = max(1, min(100, int(numerator)))
        safe_denominator = max(1, min(100, int(denominator)))
        with (
            QSignalBlocker(self._pan_numerator_spin),
            QSignalBlocker(self._pan_denominator_spin),
        ):
            self._pan_numerator_spin.setValue(safe_numerator)
            self._pan_denominator_spin.setValue(safe_denominator)

    def legend_state(self) -> dict[str, object]:
        return self._floating_legend_overlay.legend_state()

    def apply_legend_state(self, state: dict[str, object]) -> None:
        self._floating_legend_overlay.apply_state(state)

    def show_empty(self, message: str) -> None:
        self._current_workbook_name = ""
        self._current_plotted_series = []
        self._prepared_series = []
        self._data_x_range = None
        self._pending_x_range = None
        self._summary_label.setText(message)
        self._clear_cursor_state()

        self._reset_plot_item()
        self._floating_legend_overlay.set_entries([])

        self._set_navigation_enabled(False)
        self.visibleStatsChanged.emit([])

    def plot_series_group(
        self,
        *,
        workbook_name: str,
        plotted_series: list[TrendPlotSeries],
    ) -> None:
        plot_item = self._plot_widget.getPlotItem()
        self._reset_plot_item()
        self._clear_cursor_state()

        prepared_series: list[_PreparedTrendPlotSeries] = []
        x_min_values: list[float] = []
        x_max_values: list[float] = []

        for index, plotted in enumerate(plotted_series):
            x_values, y_values = plotted.series.plot_points(plotted.sheet.timestamps)
            if not x_values:
                continue

            x_array = np.asarray(x_values, dtype=np.float64)
            y_array = np.asarray(y_values, dtype=np.float64)
            color = PLOT_COLORS[index % len(PLOT_COLORS)]
            curve = self._plot_widget.plot(
                [],
                [],
                pen=pg.mkPen(color, width=2),
                connect="finite",
            )
            curve.setSkipFiniteCheck(True)

            prepared_series.append(
                _PreparedTrendPlotSeries(
                    plotted=plotted,
                    color=color,
                    x_values=x_array,
                    y_values=y_array,
                    curve=curve,
                )
            )
            x_min_values.append(float(x_array[0]))
            x_max_values.append(float(x_array[-1]))

        if not prepared_series:
            tag_names = ", ".join(plotted.series.tag_name for plotted in plotted_series)
            self.show_empty(
                f"{workbook_name}\n{tag_names or 'Selected tags'}\n"
                "No plottable numeric values were found."
            )
            return

        title = (
            prepared_series[0].plotted.series.tag_name
            if len(prepared_series) == 1
            else f"{len(prepared_series)} selected tags"
        )
        plot_item.setTitle(title)
        plot_item.setLabel("left", "Value")
        plot_item.setLabel("bottom", "Time")

        self._current_workbook_name = workbook_name
        self._current_plotted_series = [prepared.plotted for prepared in prepared_series]
        self._prepared_series = prepared_series
        x_min = min(x_min_values)
        x_max = max(x_max_values)
        self._data_x_range = (x_min, x_max)
        self._floating_legend_overlay.set_entries(
            [
                (prepared.color, prepared.plotted.series.tag_name)
                for prepared in prepared_series
            ]
        )
        self._set_navigation_enabled(True)

        self._set_visible_range(x_min, x_max)

    def current_x_range(self) -> tuple[float, float]:
        x_range = self._plot_widget.getPlotItem().viewRange()[0]
        return float(x_range[0]), float(x_range[1])

    def current_y_range(self) -> tuple[float, float]:
        y_range = self._plot_widget.getPlotItem().viewRange()[1]
        return float(y_range[0]), float(y_range[1])

    def _handle_x_range_changed(self, _plot_widget, x_range) -> None:
        if self._suspend_range_updates:
            return

        try:
            x_min, x_max = float(x_range[0]), float(x_range[1])
        except (TypeError, ValueError, IndexError):
            return

        if not self._prepared_series:
            return

        self._pending_x_range = (x_min, x_max)
        self._range_update_timer.start()

    def _apply_pending_range_update(self) -> None:
        if self._pending_x_range is None:
            return
        x_min, x_max = self._pending_x_range
        self._pending_x_range = None
        self._update_visible_window(x_min, x_max)

    def _update_visible_window(
        self,
        x_min: float,
        x_max: float,
        *,
        preserved_y_range: tuple[float, float] | None = None,
    ) -> None:
        if not self._prepared_series:
            return

        visible_stats: list[TrendVisibleSeriesStats] = []
        y_min_values: list[float] = []
        y_max_values: list[float] = []
        target_points = max(MIN_VISIBLE_SAMPLES, int(self._plot_widget.width() * 1.5))

        for prepared in self._prepared_series:
            start_index, end_index = _visible_index_bounds(prepared.x_values, x_min, x_max)
            visible_x = prepared.x_values[start_index:end_index]
            visible_y = prepared.y_values[start_index:end_index]

            if visible_x.size == 0:
                prepared.curve.setData([], [])
                visible_stats.append(
                    TrendVisibleSeriesStats(
                        tag_name=prepared.plotted.series.tag_name,
                        sheet_name=prepared.plotted.sheet.name,
                        color=prepared.color,
                        sample_count=0,
                        latest_value=None,
                        minimum_value=None,
                        maximum_value=None,
                        average_value=None,
                    )
                )
                continue

            downsampled_x, downsampled_y = _downsample_visible_slice(
                visible_x,
                visible_y,
                target_points,
            )
            prepared.curve.setData(downsampled_x, downsampled_y)

            y_min_values.append(float(np.min(visible_y)))
            y_max_values.append(float(np.max(visible_y)))
            visible_stats.append(
                TrendVisibleSeriesStats(
                    tag_name=prepared.plotted.series.tag_name,
                    sheet_name=prepared.plotted.sheet.name,
                    color=prepared.color,
                    sample_count=int(visible_y.size),
                    latest_value=float(visible_y[-1]),
                    minimum_value=float(np.min(visible_y)),
                    maximum_value=float(np.max(visible_y)),
                    average_value=float(np.mean(visible_y)),
                )
            )

        if preserved_y_range is None:
            self._apply_visible_y_range(y_min_values, y_max_values)
        else:
            self._set_y_range(*preserved_y_range)

        self._summary_label.setText(
            _build_summary_text(
                workbook_name=self._current_workbook_name,
                visible_stats=visible_stats,
                x_min=x_min,
                x_max=x_max,
            )
        )
        self.visibleRangeChanged.emit(x_min, x_max)
        self.visibleStatsChanged.emit(visible_stats)

        if self._current_cursor_x is not None and x_min <= self._current_cursor_x <= x_max:
            self._set_cursor_position(self._current_cursor_x)
        else:
            self._clear_cursor_state()

    def _apply_visible_y_range(
        self,
        y_min_values: list[float],
        y_max_values: list[float],
    ) -> None:
        if not y_min_values or not y_max_values:
            return

        y_min = min(y_min_values)
        y_max = max(y_max_values)
        if y_min == y_max:
            padding = abs(y_min) * 0.05 or 1.0
        else:
            padding = (y_max - y_min) * 0.08

        self._set_y_range(y_min - padding, y_max + padding)

    def _set_visible_range(
        self,
        x_min: float,
        x_max: float,
        *,
        preserved_y_range: tuple[float, float] | None = None,
    ) -> None:
        plot_item = self._plot_widget.getPlotItem()
        self._pending_x_range = None
        self._range_update_timer.stop()
        self._suspend_range_updates = True
        plot_item.setXRange(x_min, x_max, padding=0)
        self._suspend_range_updates = False
        self._update_visible_window(x_min, x_max, preserved_y_range=preserved_y_range)

    def _set_y_range(self, y_min: float, y_max: float) -> None:
        if not np.isfinite(y_min) or not np.isfinite(y_max):
            return
        if y_min >= y_max:
            padding = abs(y_min) * 0.05 or 1.0
            y_min -= padding
            y_max += padding

        self._suspend_range_updates = True
        self._plot_widget.getPlotItem().setYRange(y_min, y_max, padding=0)
        self._suspend_range_updates = False

    def _set_navigation_enabled(self, enabled: bool) -> None:
        self._pan_numerator_spin.setEnabled(enabled)
        self._pan_denominator_spin.setEnabled(enabled)
        self._pan_left_button.setEnabled(enabled)
        self._pan_right_button.setEnabled(enabled)

    def _handle_pan_fraction_changed(self, _value: int) -> None:
        numerator, denominator = self.pan_fraction()
        self.panFractionChanged.emit(numerator, denominator)

    def _pan_left_by_fraction(self) -> None:
        self._pan_by_fraction(-1.0)

    def _pan_right_by_fraction(self) -> None:
        self._pan_by_fraction(1.0)

    def _pan_by_fraction(self, direction: float) -> None:
        if not self._prepared_series:
            return

        x_min, x_max = self.current_x_range()
        window_width = x_max - x_min
        if window_width <= 0:
            return

        numerator, denominator = self.pan_fraction()
        step = window_width * (numerator / denominator)
        if step <= 0:
            return

        target_x_min = x_min + (step * direction)
        target_x_max = x_max + (step * direction)
        if self._data_x_range is not None:
            target_x_min, target_x_max = _clamp_x_range(
                target_x_min,
                target_x_max,
                self._data_x_range[0],
                self._data_x_range[1],
            )

        current_y_range = self.current_y_range()
        self._set_visible_range(
            target_x_min,
            target_x_max,
            preserved_y_range=current_y_range,
        )

    def _reset_plot_item(self) -> None:
        plot_item = self._plot_widget.getPlotItem()
        plot_item.clear()
        plot_item.setTitle("")
        plot_item.setLabel("left", "Value")
        plot_item.setLabel("bottom", "Time")
        self._cursor_line.hide()
        plot_item.addItem(self._cursor_line, ignoreBounds=True)

    def _handle_scene_mouse_moved(self, scene_position: object) -> None:
        if not self._prepared_series:
            return

        plot_item = self._plot_widget.getPlotItem()
        view_box = plot_item.getViewBox()
        if view_box is None or not view_box.sceneBoundingRect().contains(scene_position):
            self._clear_cursor_state()
            return

        cursor_point = view_box.mapSceneToView(scene_position)
        cursor_x = float(cursor_point.x())
        if not np.isfinite(cursor_x):
            self._clear_cursor_state()
            return

        self._set_cursor_position(cursor_x)

    def _set_cursor_position(self, cursor_x: float) -> None:
        self._current_cursor_x = cursor_x
        self._cursor_line.setPos(cursor_x)
        self._cursor_line.show()
        self._cursor_label.setText(f"Cursor: {_format_timestamp(cursor_x)}")
        self._cursor_label.show()
        self.cursorStatsChanged.emit(self._build_cursor_stats(cursor_x))

    def _clear_cursor_state(self) -> None:
        self._current_cursor_x = None
        self._cursor_line.hide()
        self._cursor_label.clear()
        self._cursor_label.hide()
        self.cursorStatsChanged.emit(None)

    def _build_cursor_stats(self, cursor_x: float) -> TrendCursorStats:
        series_stats: list[TrendCursorSeriesStats] = []
        for prepared in self._prepared_series:
            nearest_index = _nearest_index(prepared.x_values, cursor_x)
            sample_timestamp: float | None = None
            cursor_value: float | None = None
            if nearest_index is not None:
                sample_timestamp = float(prepared.x_values[nearest_index])
                value = float(prepared.y_values[nearest_index])
                if np.isfinite(value):
                    cursor_value = value

            series_stats.append(
                TrendCursorSeriesStats(
                    tag_name=prepared.plotted.series.tag_name,
                    sheet_name=prepared.plotted.sheet.name,
                    color=prepared.color,
                    sample_timestamp=sample_timestamp,
                    cursor_value=cursor_value,
                )
            )

        return TrendCursorStats(
            cursor_timestamp=cursor_x,
            series_stats=tuple(series_stats),
        )

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._plot_widget and event.type() == QEvent.Resize:
            self._floating_legend_overlay.clamp_to_parent()
        elif watched is self._plot_widget.viewport() and event.type() == QEvent.Leave:
            self._clear_cursor_state()
        return super().eventFilter(watched, event)


def _build_summary_text(
    *,
    workbook_name: str,
    visible_stats: list[TrendVisibleSeriesStats],
    x_min: float,
    x_max: float,
) -> str:
    if not visible_stats:
        return (
            "No live trend data loaded.\n"
            "Open a workbook to prepare sheets and tags for plotting."
        )

    sample_count = sum(stats.sample_count for stats in visible_stats)
    time_range = _format_time_range(x_min, x_max)

    if len(visible_stats) == 1:
        stats = visible_stats[0]
        return (
            f"{workbook_name}\n"
            f"Sheet: {stats.sheet_name} | Tag: {stats.tag_name}\n"
            f"Visible samples: {stats.sample_count:,}\n"
            f"Visible range: {time_range}"
        )

    sheet_names = sorted({stats.sheet_name for stats in visible_stats}, key=str.casefold)
    tag_names = [stats.tag_name for stats in visible_stats]
    return (
        f"{workbook_name}\n"
        f"Sheets: {', '.join(sheet_names)}\n"
        f"Tags ({len(tag_names)}): {_summarize_tag_names(tag_names)}\n"
        f"Visible samples: {sample_count:,}\n"
        f"Visible range: {time_range}"
    )


def _summarize_tag_names(tag_names: list[str]) -> str:
    if len(tag_names) <= 4:
        return ", ".join(tag_names)
    visible = ", ".join(tag_names[:4])
    return f"{visible}, +{len(tag_names) - 4} more"


def _format_time_range(start_epoch: float, end_epoch: float) -> str:
    start = _format_timestamp(start_epoch)
    end = _format_timestamp(end_epoch)
    return f"{start} to {end}"


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _visible_index_bounds(
    x_values: np.ndarray,
    x_min: float,
    x_max: float,
) -> tuple[int, int]:
    start_index = max(0, int(np.searchsorted(x_values, x_min, side="left")) - 1)
    end_index = min(x_values.size, int(np.searchsorted(x_values, x_max, side="right")) + 1)
    return start_index, end_index


def _downsample_visible_slice(
    x_values: np.ndarray,
    y_values: np.ndarray,
    max_points: int,
) -> tuple[np.ndarray, np.ndarray]:
    if x_values.size <= max_points:
        return x_values, y_values

    bucket_count = max(1, max_points // 2)
    bucket_edges = np.linspace(0, x_values.size, bucket_count + 1, dtype=np.int64)
    sampled_indices: list[int] = [0]

    for bucket_index in range(bucket_count):
        start_index = int(bucket_edges[bucket_index])
        end_index = int(bucket_edges[bucket_index + 1])
        if end_index - start_index <= 0:
            continue

        segment = y_values[start_index:end_index]
        local_min_index = start_index + int(np.argmin(segment))
        local_max_index = start_index + int(np.argmax(segment))

        if local_min_index <= local_max_index:
            sampled_indices.extend((local_min_index, local_max_index))
        else:
            sampled_indices.extend((local_max_index, local_min_index))

    sampled_indices.append(x_values.size - 1)
    unique_indices = np.unique(np.asarray(sampled_indices, dtype=np.int64))
    return x_values[unique_indices], y_values[unique_indices]


def _nearest_index(x_values: np.ndarray, target_x: float) -> int | None:
    if x_values.size == 0:
        return None

    right_index = int(np.searchsorted(x_values, target_x, side="left"))
    if right_index <= 0:
        return 0
    if right_index >= x_values.size:
        return int(x_values.size - 1)

    left_index = right_index - 1
    left_distance = abs(float(x_values[left_index]) - target_x)
    right_distance = abs(float(x_values[right_index]) - target_x)
    if right_distance < left_distance:
        return right_index
    return left_index


def _clamp_x_range(
    x_min: float,
    x_max: float,
    data_min: float,
    data_max: float,
) -> tuple[float, float]:
    if data_min >= data_max:
        return data_min, data_max

    window_width = x_max - x_min
    data_width = data_max - data_min
    if window_width >= data_width:
        return data_min, data_max

    if x_min < data_min:
        shift = data_min - x_min
        x_min += shift
        x_max += shift
    if x_max > data_max:
        shift = x_max - data_max
        x_min -= shift
        x_max -= shift

    return x_min, x_max
