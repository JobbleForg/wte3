from __future__ import annotations

from contextlib import contextmanager
import html
import re
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QDateTime, QEvent, QSignalBlocker, QTimer, Qt, Signal, QTimeZone
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QToolButton,
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
    "#56B4E9",
    "#009E73",
    "#D55E00",
    "#CC79A7",
    "#8DD3C7",
    "#FDB462",
    "#B3DE69",
    "#FCCDE5",
    "#80B1D3",
    "#FB8072",
    "#BC80BD",
    "#FFED6F",
    "#00C2FF",
    "#7AE582",
)
MIN_VISIBLE_SAMPLES = 800
DISPLAY_Y_MIN = 0.0
DISPLAY_Y_MAX = 100.0
SCALE_PANEL_COLUMN_PADDING = 10
SCALE_PANEL_COLUMN_SPACING = 6
SCALE_PANEL_MIN_WIDTH = 92
SCALE_PANEL_TAGS_PER_COLUMN = 5
SCALE_PANEL_STRETCH_RESET_COLUMNS = 12
HIGHLIGHT_DIM_ALPHA = 68
TIME_MODE_DURATION = "duration"
TIME_MODE_END = "end"
DEFAULT_DURATION_PRESETS = (
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "8h",
    "12h",
    "1d",
    "2d",
)


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
    interpolated_value: float | None
    interpolation_mode: str
    interpolation_start_timestamp: float | None
    interpolation_end_timestamp: float | None
    previous_timestamp: float | None
    previous_value: float | None
    next_timestamp: float | None
    next_value: float | None


@dataclass(frozen=True)
class TrendCursorStats:
    cursor_timestamp: float
    series_stats: tuple[TrendCursorSeriesStats, ...]


@dataclass
class _PreparedTrendPlotSeries:
    plotted: TrendPlotSeries
    display_label: str
    color: str
    display_low_range: float
    display_high_range: float
    x_values: np.ndarray
    y_values: np.ndarray
    curve: object


class _TrendViewBox(pg.ViewBox):
    """ViewBox that keeps the trend plot vertically fixed while allowing X navigation."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._fixed_y_range: tuple[float, float] | None = None

    def set_fixed_y_range(self, y_min: float, y_max: float) -> None:
        if not np.isfinite(y_min) or not np.isfinite(y_max):
            return
        if y_min >= y_max:
            padding = abs(y_min) * 0.05 or 1.0
            y_min -= padding
            y_max += padding

        self._fixed_y_range = (float(y_min), float(y_max))
        fixed_height = float(y_max - y_min)
        self.setLimits(
            yMin=float(y_min),
            yMax=float(y_max),
            minYRange=fixed_height,
            maxYRange=fixed_height,
        )
        super().setYRange(float(y_min), float(y_max), padding=0)

    def scaleBy(self, s=None, center=None, x=None, y=None):
        if self._fixed_y_range is not None:
            if s is not None:
                x = s[0]
            super().scaleBy(center=center, x=x, y=None)
            self._enforce_fixed_y_range()
            return
        super().scaleBy(s=s, center=center, x=x, y=y)

    def translateBy(self, t=None, x=None, y=None):
        if self._fixed_y_range is not None:
            if t is not None:
                x = pg.Point(t).x()
            super().translateBy(x=x, y=None)
            self._enforce_fixed_y_range()
            return
        super().translateBy(t=t, x=x, y=y)

    def _enforce_fixed_y_range(self) -> None:
        if self._fixed_y_range is None:
            return
        super().setYRange(*self._fixed_y_range, padding=0)


class TrendPlotWidget(QWidget):
    """Phase-2 preview plot with visible-window slicing and downsampling."""

    visibleRangeChanged = Signal(float, float)
    visibleStatsChanged = Signal(object)
    cursorStatsChanged = Signal(object)
    panFractionChanged = Signal(int, int)
    timeSelectionStateChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._time_controls_collapsed = False
        self._shared_scale_decimal_places: int | None = None
        self._floating_legend_enabled = False
        self._floating_legend_show_cursor_data = False
        self._floating_legend_html = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._summary_label = QLabel(self)
        self._summary_label.setAlignment(Qt.AlignCenter)
        self._summary_label.setWordWrap(True)
        self._summary_label.hide()
        layout.addWidget(self._summary_label)

        plot_row = QWidget(self)
        plot_row_layout = QHBoxLayout(plot_row)
        plot_row_layout.setContentsMargins(0, 0, 0, 0)
        plot_row_layout.setSpacing(10)

        self._shared_scale_panel = QWidget(plot_row)
        self._shared_scale_panel.setFixedWidth(SCALE_PANEL_MIN_WIDTH)
        self._shared_scale_panel.hide()
        scale_layout = QVBoxLayout(self._shared_scale_panel)
        scale_layout.setContentsMargins(0, 4, 0, 4)
        scale_layout.setSpacing(0)

        self._shared_scale_top = QWidget(self._shared_scale_panel)
        self._shared_scale_top_layout = QGridLayout(self._shared_scale_top)
        self._shared_scale_top_layout.setContentsMargins(0, 0, 0, 0)
        self._shared_scale_top_layout.setSpacing(2)

        self._shared_scale_mid = QWidget(self._shared_scale_panel)
        self._shared_scale_mid_layout = QGridLayout(self._shared_scale_mid)
        self._shared_scale_mid_layout.setContentsMargins(0, 0, 0, 0)
        self._shared_scale_mid_layout.setSpacing(2)

        self._shared_scale_bottom = QWidget(self._shared_scale_panel)
        self._shared_scale_bottom_layout = QGridLayout(self._shared_scale_bottom)
        self._shared_scale_bottom_layout.setContentsMargins(0, 0, 0, 0)
        self._shared_scale_bottom_layout.setSpacing(2)

        self._bind_shared_scale_context_menu(self._shared_scale_panel)
        self._bind_shared_scale_context_menu(self._shared_scale_top)
        self._bind_shared_scale_context_menu(self._shared_scale_mid)
        self._bind_shared_scale_context_menu(self._shared_scale_bottom)

        scale_layout.addWidget(self._shared_scale_top)
        scale_layout.addStretch(1)
        scale_layout.addWidget(self._shared_scale_mid)
        scale_layout.addStretch(1)
        scale_layout.addWidget(self._shared_scale_bottom)
        plot_row_layout.addWidget(self._shared_scale_panel)

        axis_items = {"bottom": pg.DateAxisItem(orientation="bottom")}
        self._plot_view_box = _TrendViewBox(enableMenu=False)
        self._plot_widget = pg.PlotWidget(
            axisItems=axis_items,
            viewBox=self._plot_view_box,
            parent=self,
        )
        self._plot_widget.setBackground("#171D23")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setMenuEnabled(False)
        self._plot_widget.hideButtons()
        self._plot_view_box.setMouseMode(pg.ViewBox.PanMode)
        self._plot_view_box.setMouseEnabled(x=True, y=False)
        self._plot_view_box.set_fixed_y_range(DISPLAY_Y_MIN, DISPLAY_Y_MAX)
        self._plot_widget.setLabel("bottom", "Time")
        plot_row_layout.addWidget(self._plot_widget, stretch=1)
        layout.addWidget(plot_row, stretch=1)
        layout.addWidget(self._build_navigation_row())

        self._current_workbook_name = ""
        self._current_plotted_series: list[TrendPlotSeries] = []
        self._prepared_series: list[_PreparedTrendPlotSeries] = []
        self._data_x_range: tuple[float, float] | None = None
        self._current_visible_range: tuple[float, float] | None = None
        self._requested_time_range: tuple[float, float] | None = None
        self._pending_x_range: tuple[float, float] | None = None
        self._current_cursor_x: float | None = None
        self._highlighted_tag_names: set[str] = set()
        self._suspend_range_updates = False
        self._suspend_time_control_updates = False

        self._range_update_timer = QTimer(self)
        self._range_update_timer.setSingleShot(True)
        self._range_update_timer.setInterval(24)
        self._range_update_timer.timeout.connect(self._apply_pending_range_update)

        self._time_state_change_timer = QTimer(self)
        self._time_state_change_timer.setSingleShot(True)
        self._time_state_change_timer.setInterval(300)
        self._time_state_change_timer.timeout.connect(self._emit_time_selection_state_changed)

        self._cursor_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen("#D8DFE6", width=1, style=Qt.PenStyle.DashLine),
        )
        self._cursor_line.setZValue(1_000)
        self._cursor_line.hide()
        self._floating_legend_item = pg.TextItem(
            html="",
            anchor=(0.0, 0.0),
            fill=pg.mkBrush(18, 24, 31, 220),
            border=pg.mkPen("#46505A"),
        )
        self._floating_legend_item.setZValue(1_100)
        self._floating_legend_item.hide()

        self._plot_widget.installEventFilter(self)
        self._plot_widget.viewport().setMouseTracking(True)
        self._plot_widget.viewport().installEventFilter(self)
        self._plot_widget.scene().sigMouseMoved.connect(self._handle_scene_mouse_moved)
        self._plot_widget.sigXRangeChanged.connect(self._handle_x_range_changed)

        self.set_time_presets(list(DEFAULT_DURATION_PRESETS))
        self._time_mode_combo.setCurrentIndex(0)
        self._sync_time_control_enabled_state(False)

        self.show_empty(
            "No live trend data loaded.\nOpen a workbook to prepare sheets and tags for plotting."
        )

    def _build_navigation_row(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        status_row = QWidget(container)
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        self._visible_range_label = QLabel(status_row)
        self._visible_range_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._visible_range_label.hide()
        status_layout.addWidget(self._visible_range_label, stretch=1)

        self._cursor_label = QLabel(status_row)
        self._cursor_label.setAlignment(Qt.AlignCenter)
        self._cursor_label.hide()
        status_layout.addWidget(self._cursor_label, stretch=1)

        self._time_controls_toggle_button = QToolButton(status_row)
        self._time_controls_toggle_button.setAutoRaise(True)
        self._time_controls_toggle_button.clicked.connect(self._toggle_time_controls_collapsed)
        status_layout.addWidget(self._time_controls_toggle_button, alignment=Qt.AlignRight)

        layout.addWidget(status_row)

        self._navigation_controls_container = QWidget(container)
        navigation_controls_layout = QVBoxLayout(self._navigation_controls_container)
        navigation_controls_layout.setContentsMargins(0, 0, 0, 0)
        navigation_controls_layout.setSpacing(6)

        time_controls_row = QWidget(self._navigation_controls_container)
        time_controls_layout = QHBoxLayout(time_controls_row)
        time_controls_layout.setContentsMargins(0, 0, 0, 0)
        time_controls_layout.setSpacing(8)

        self._time_start_edit = QDateTimeEdit(time_controls_row)
        self._configure_datetime_edit(self._time_start_edit)
        self._time_start_edit.setMinimumWidth(140)
        self._time_start_edit.setMaximumWidth(172)
        time_controls_layout.addWidget(self._time_start_edit)

        self._time_mode_combo = QComboBox(time_controls_row)
        self._time_mode_combo.addItem("Duration", TIME_MODE_DURATION)
        self._time_mode_combo.addItem("End", TIME_MODE_END)
        self._time_mode_combo.setMinimumWidth(86)
        self._time_mode_combo.setMaximumWidth(108)
        self._time_mode_combo.currentIndexChanged.connect(self._handle_time_mode_changed)
        time_controls_layout.addWidget(self._time_mode_combo)

        self._time_value_stack = QStackedWidget(time_controls_row)
        self._time_value_stack.setMinimumWidth(150)
        self._time_value_stack.setMaximumWidth(196)

        self._time_duration_input = QLineEdit(time_controls_row)
        self._time_duration_input.setPlaceholderText("1h 30m")
        self._time_duration_input.setClearButtonEnabled(True)
        self._time_duration_input.returnPressed.connect(self._apply_time_selection_from_controls)
        self._time_value_stack.addWidget(self._time_duration_input)

        self._time_end_edit = QDateTimeEdit(time_controls_row)
        self._configure_datetime_edit(self._time_end_edit)
        self._time_value_stack.addWidget(self._time_end_edit)
        time_controls_layout.addWidget(self._time_value_stack)

        self._time_preset_combo = QComboBox(time_controls_row)
        self._time_preset_combo.setPlaceholderText("Preset")
        self._time_preset_combo.setCurrentIndex(-1)
        self._time_preset_combo.setMinimumWidth(90)
        self._time_preset_combo.setMaximumWidth(120)
        self._time_preset_combo.currentIndexChanged.connect(self._handle_time_preset_changed)
        time_controls_layout.addWidget(self._time_preset_combo)

        self._apply_time_selection_button = QPushButton("Apply", time_controls_row)
        self._apply_time_selection_button.setMinimumWidth(68)
        self._apply_time_selection_button.setMaximumWidth(78)
        self._apply_time_selection_button.clicked.connect(self._apply_time_selection_from_controls)
        time_controls_layout.addWidget(self._apply_time_selection_button)
        time_controls_layout.addStretch(1)
        navigation_controls_layout.addWidget(time_controls_row)

        pan_controls_row = QWidget(self._navigation_controls_container)
        pan_controls_layout = QHBoxLayout(pan_controls_row)
        pan_controls_layout.setContentsMargins(0, 0, 0, 0)
        pan_controls_layout.setSpacing(8)
        pan_controls_layout.addStretch(1)

        self._pan_numerator_spin = QSpinBox(pan_controls_row)
        self._pan_numerator_spin.setRange(1, 100)
        self._pan_numerator_spin.setValue(1)
        self._pan_numerator_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._pan_numerator_spin.setAlignment(Qt.AlignCenter)
        self._pan_numerator_spin.setFixedWidth(44)
        self._pan_numerator_spin.valueChanged.connect(self._handle_pan_fraction_changed)
        pan_controls_layout.addWidget(self._pan_numerator_spin)

        slash_label = QLabel("/", pan_controls_row)
        slash_label.setAlignment(Qt.AlignCenter)
        slash_label.setFixedWidth(10)
        pan_controls_layout.addWidget(slash_label)

        self._pan_denominator_spin = QSpinBox(pan_controls_row)
        self._pan_denominator_spin.setRange(1, 100)
        self._pan_denominator_spin.setValue(4)
        self._pan_denominator_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._pan_denominator_spin.setAlignment(Qt.AlignCenter)
        self._pan_denominator_spin.setFixedWidth(44)
        self._pan_denominator_spin.valueChanged.connect(self._handle_pan_fraction_changed)
        pan_controls_layout.addWidget(self._pan_denominator_spin)

        self._pan_left_button = QPushButton("<", pan_controls_row)
        self._pan_left_button.setFixedWidth(36)
        self._pan_left_button.clicked.connect(self._pan_left_by_fraction)
        pan_controls_layout.addWidget(self._pan_left_button)

        self._pan_right_button = QPushButton(">", pan_controls_row)
        self._pan_right_button.setFixedWidth(36)
        self._pan_right_button.clicked.connect(self._pan_right_by_fraction)
        pan_controls_layout.addWidget(self._pan_right_button)

        navigation_controls_layout.addWidget(pan_controls_row)
        layout.addWidget(self._navigation_controls_container)
        self._apply_time_controls_collapsed_state()

        return container

    def _configure_datetime_edit(self, control: QDateTimeEdit) -> None:
        control.setCalendarPopup(True)
        control.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        control.setTimeZone(QTimeZone.systemTimeZone())

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

    def set_time_presets(self, presets: list[str]) -> None:
        normalized_presets = normalize_duration_presets(presets)
        current_text = self._time_preset_combo.currentText().strip()
        current_index = -1
        with (
            QSignalBlocker(self._time_preset_combo),
            _suspend_time_control_updates(self),
        ):
            self._time_preset_combo.clear()
            self._time_preset_combo.addItems(normalized_presets)
            if current_text:
                current_index = self._time_preset_combo.findText(current_text)
            self._time_preset_combo.setCurrentIndex(current_index)
        self._sync_time_control_enabled_state(bool(self._prepared_series))

    def time_presets(self) -> list[str]:
        return [
            self._time_preset_combo.itemText(index).strip()
            for index in range(self._time_preset_combo.count())
            if self._time_preset_combo.itemText(index).strip()
        ]

    def set_time_selection_state(self, state: dict[str, object]) -> None:
        mode = str(state.get("time_selection_mode", TIME_MODE_DURATION)).strip().lower()
        if mode not in {TIME_MODE_DURATION, TIME_MODE_END}:
            mode = TIME_MODE_DURATION
        controls_collapsed = bool(state.get("time_controls_collapsed", False))
        shared_scale_decimal_places = _coerce_scale_decimal_places(
            state.get("shared_scale_decimal_places")
        )
        floating_legend_enabled = bool(state.get("floating_legend_enabled", False))
        floating_legend_show_cursor_data = bool(
            state.get("floating_legend_show_cursor_data", False)
        )

        start_epoch = _coerce_epoch(state.get("time_window_start_epoch"))
        end_epoch = _coerce_epoch(state.get("time_window_end_epoch"))
        duration_text = ""
        if start_epoch is not None and end_epoch is not None and end_epoch > start_epoch:
            duration_text = format_duration_seconds(int(round(end_epoch - start_epoch)))

        with _suspend_time_control_updates(self):
            self._time_mode_combo.setCurrentIndex(
                1 if mode == TIME_MODE_END else 0
            )
            if start_epoch is not None:
                self._time_start_edit.setDateTime(_qdatetime_from_epoch(start_epoch))
            if end_epoch is not None:
                self._time_end_edit.setDateTime(_qdatetime_from_epoch(end_epoch))
            self._time_duration_input.setText(duration_text)
            matching_preset = _matching_duration_preset(
                parse_duration_text(duration_text),
                self.time_presets(),
            )
            if matching_preset is None:
                self._time_preset_combo.setCurrentIndex(-1)
            else:
                self._time_preset_combo.setCurrentIndex(
                    self._time_preset_combo.findText(matching_preset)
                )
            self._sync_time_mode_controls()

        if start_epoch is not None and end_epoch is not None and end_epoch > start_epoch:
            self._requested_time_range = (start_epoch, end_epoch)
        else:
            self._requested_time_range = None
        self._set_time_controls_collapsed(controls_collapsed, emit_state_change=False)
        self._set_shared_scale_decimal_places(
            shared_scale_decimal_places,
            emit_state_change=False,
        )
        self._set_floating_legend_enabled(
            floating_legend_enabled,
            emit_state_change=False,
        )
        self._set_floating_legend_show_cursor_data(
            floating_legend_show_cursor_data,
            emit_state_change=False,
        )

    def time_selection_state(self) -> dict[str, object]:
        state: dict[str, object] = {
            "time_selection_mode": self._current_time_mode(),
            "time_controls_collapsed": self._time_controls_collapsed,
            "shared_scale_decimal_places": self._shared_scale_decimal_places,
            "floating_legend_enabled": self._floating_legend_enabled,
            "floating_legend_show_cursor_data": self._floating_legend_show_cursor_data,
        }

        x_range = self._current_visible_range
        if x_range is None:
            start_epoch = float(self._time_start_edit.dateTime().toSecsSinceEpoch())
            end_epoch = float(self._time_end_edit.dateTime().toSecsSinceEpoch())
        else:
            start_epoch, end_epoch = x_range

        if end_epoch > start_epoch:
            state["time_window_start_epoch"] = float(start_epoch)
            state["time_window_end_epoch"] = float(end_epoch)
        return state

    def show_empty(self, message: str) -> None:
        self._current_workbook_name = ""
        self._current_plotted_series = []
        self._prepared_series = []
        self._data_x_range = None
        self._current_visible_range = None
        self._pending_x_range = None
        self._summary_label.setText(message)
        self._summary_label.show()
        self._clear_cursor_state()
        self._clear_visible_range_state()
        self._hide_floating_legend()

        self._reset_plot_item()
        self._set_shared_scale_labels([])

        self._set_navigation_enabled(False)
        self.visibleStatsChanged.emit([])

    def set_highlighted_tags(self, tag_names: list[str]) -> None:
        self._highlighted_tag_names = {
            str(tag_name).strip() for tag_name in tag_names if str(tag_name).strip()
        }
        self._apply_highlight_state()

    def plot_series_group(
        self,
        *,
        workbook_name: str,
        plotted_series: list[TrendPlotSeries],
        display_ranges_by_tag: dict[str, tuple[float, float]] | None = None,
        display_labels_by_tag: dict[str, str] | None = None,
        series_colors_by_tag: dict[str, str] | None = None,
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
            color = _resolved_series_color(
                plotted.series.tag_name,
                series_colors_by_tag,
                fallback=PLOT_COLORS[index % len(PLOT_COLORS)],
            )
            low_range, high_range = _resolved_series_display_range(
                plotted.series.tag_name,
                display_ranges_by_tag,
            )
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
                    display_label=_display_label_for_tag(
                        plotted.series.tag_name,
                        display_labels_by_tag,
                    ),
                    color=color,
                    display_low_range=low_range,
                    display_high_range=high_range,
                    x_values=x_array,
                    y_values=y_array,
                    curve=curve,
                )
            )
            x_min_values.append(float(x_array[0]))
            x_max_values.append(float(x_array[-1]))

        if not prepared_series:
            tag_names = ", ".join(
                _display_label_for_tag(
                    plotted.series.tag_name,
                    display_labels_by_tag,
                )
                for plotted in plotted_series
            )
            self.show_empty(
                f"{workbook_name}\n{tag_names or 'Selected tags'}\n"
                "No plottable numeric values were found."
            )
            return

        title = (
            prepared_series[0].display_label
            if len(prepared_series) == 1
            else f"{len(prepared_series)} selected tags"
        )
        plot_item.setTitle(title)
        plot_item.setLabel("left", "")
        plot_item.setLabel("bottom", "Time")

        self._current_workbook_name = workbook_name
        self._current_plotted_series = [prepared.plotted for prepared in prepared_series]
        self._prepared_series = prepared_series
        self._summary_label.hide()
        self._apply_highlight_state()
        x_min = min(x_min_values)
        x_max = max(x_max_values)
        self._data_x_range = (x_min, x_max)
        self._set_navigation_enabled(True)
        requested_range = _clamp_requested_time_range(
            self._requested_time_range,
            data_min=x_min,
            data_max=x_max,
        )
        if requested_range is None:
            self._set_visible_range(x_min, x_max)
        else:
            self._set_visible_range(*requested_range)

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
        target_points = max(MIN_VISIBLE_SAMPLES, int(self._plot_widget.width() * 1.5))

        for prepared in self._prepared_series:
            draw_start_index, draw_end_index = _visible_index_bounds(
                prepared.x_values,
                x_min,
                x_max,
            )
            stats_start_index, stats_end_index = _visible_stats_index_bounds(
                prepared.x_values,
                x_min,
                x_max,
            )
            visible_x = prepared.x_values[draw_start_index:draw_end_index]
            visible_y = prepared.y_values[draw_start_index:draw_end_index]
            stats_y = prepared.y_values[stats_start_index:stats_end_index]

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
            prepared.curve.setData(
                downsampled_x,
                _normalize_display_values(
                    downsampled_y,
                    low_range=prepared.display_low_range,
                    high_range=prepared.display_high_range,
                ),
            )

            if stats_y.size == 0:
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
            else:
                visible_stats.append(
                    TrendVisibleSeriesStats(
                        tag_name=prepared.plotted.series.tag_name,
                        sheet_name=prepared.plotted.sheet.name,
                        color=prepared.color,
                        sample_count=int(stats_y.size),
                        latest_value=float(stats_y[-1]),
                        minimum_value=float(np.min(stats_y)),
                        maximum_value=float(np.max(stats_y)),
                        average_value=float(np.mean(stats_y)),
                    )
                )

        if preserved_y_range is None:
            self._apply_visible_y_range()
        else:
            self._set_y_range(*preserved_y_range)

        self._sync_time_controls_to_visible_range(x_min, x_max)
        self._set_visible_range_text(x_min, x_max)
        self.visibleRangeChanged.emit(x_min, x_max)
        self.visibleStatsChanged.emit(visible_stats)

        if self._current_cursor_x is not None and x_min <= self._current_cursor_x <= x_max:
            self._set_cursor_position(self._current_cursor_x)
        else:
            self._clear_cursor_state()

    def _apply_visible_y_range(self) -> None:
        self._set_y_range(DISPLAY_Y_MIN, DISPLAY_Y_MAX)

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
        self._suspend_range_updates = True
        self._plot_view_box.set_fixed_y_range(y_min, y_max)
        self._suspend_range_updates = False

    def _set_navigation_enabled(self, enabled: bool) -> None:
        self._sync_time_control_enabled_state(enabled)
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

    def _sync_time_control_enabled_state(self, enabled: bool) -> None:
        self._time_start_edit.setEnabled(enabled)
        self._time_mode_combo.setEnabled(enabled)
        self._apply_time_selection_button.setEnabled(enabled)
        self._sync_time_mode_controls(enabled=enabled)

    def _current_time_mode(self) -> str:
        mode = self._time_mode_combo.currentData()
        if isinstance(mode, str) and mode in {TIME_MODE_DURATION, TIME_MODE_END}:
            return mode
        return TIME_MODE_DURATION

    def _sync_time_mode_controls(self, *, enabled: bool | None = None) -> None:
        control_enabled = bool(self._prepared_series) if enabled is None else enabled
        mode = self._current_time_mode()
        self._time_value_stack.setCurrentIndex(1 if mode == TIME_MODE_END else 0)
        self._time_duration_input.setEnabled(control_enabled and mode == TIME_MODE_DURATION)
        self._time_end_edit.setEnabled(control_enabled and mode == TIME_MODE_END)
        self._time_preset_combo.setEnabled(
            control_enabled
            and mode == TIME_MODE_DURATION
            and self._time_preset_combo.count() > 0
        )

    def _handle_time_mode_changed(self, _index: int) -> None:
        if self._suspend_time_control_updates:
            return
        self._sync_time_mode_controls()
        self._schedule_time_selection_state_changed()

    def _handle_time_preset_changed(self, index: int) -> None:
        if self._suspend_time_control_updates or index < 0:
            return
        preset_text = self._time_preset_combo.itemText(index).strip()
        if preset_text:
            self._time_duration_input.setText(preset_text)

    def _apply_time_selection_from_controls(self) -> None:
        requested_range = self._requested_range_from_controls()
        if requested_range is None:
            return

        self._requested_time_range = requested_range
        if not self._prepared_series or self._data_x_range is None:
            return

        clamped_range = _clamp_requested_time_range(
            requested_range,
            data_min=self._data_x_range[0],
            data_max=self._data_x_range[1],
        )
        if clamped_range is None:
            return

        self._set_visible_range(
            clamped_range[0],
            clamped_range[1],
            preserved_y_range=self.current_y_range(),
        )
        self._schedule_time_selection_state_changed()

    def _requested_range_from_controls(self) -> tuple[float, float] | None:
        start_epoch = float(self._time_start_edit.dateTime().toSecsSinceEpoch())
        if self._current_time_mode() == TIME_MODE_END:
            end_epoch = float(self._time_end_edit.dateTime().toSecsSinceEpoch())
        else:
            duration_seconds = parse_duration_text(self._time_duration_input.text())
            if duration_seconds is None:
                return None
            end_epoch = start_epoch + duration_seconds

        if end_epoch <= start_epoch:
            return None
        return start_epoch, end_epoch

    def _sync_time_controls_to_visible_range(self, x_min: float, x_max: float) -> None:
        self._current_visible_range = (x_min, x_max)
        self._requested_time_range = (x_min, x_max)
        duration_seconds = max(0, int(round(x_max - x_min)))
        duration_text = format_duration_seconds(duration_seconds)
        matching_preset = _matching_duration_preset(duration_seconds, self.time_presets())

        with _suspend_time_control_updates(self):
            self._time_start_edit.setDateTime(_qdatetime_from_epoch(x_min))
            self._time_end_edit.setDateTime(_qdatetime_from_epoch(x_max))
            self._time_duration_input.setText(duration_text)
            if matching_preset is None:
                self._time_preset_combo.setCurrentIndex(-1)
            else:
                self._time_preset_combo.setCurrentIndex(
                    self._time_preset_combo.findText(matching_preset)
                )

        self._schedule_time_selection_state_changed()

    def _schedule_time_selection_state_changed(self) -> None:
        if self._suspend_time_control_updates:
            return
        self._time_state_change_timer.start()

    def _emit_time_selection_state_changed(self) -> None:
        self.timeSelectionStateChanged.emit()

    def _toggle_time_controls_collapsed(self) -> None:
        self._set_time_controls_collapsed(
            not self._time_controls_collapsed,
            emit_state_change=True,
        )

    def _set_time_controls_collapsed(self, collapsed: bool, *, emit_state_change: bool) -> None:
        normalized_collapsed = bool(collapsed)
        if normalized_collapsed == self._time_controls_collapsed:
            return
        self._time_controls_collapsed = normalized_collapsed
        self._apply_time_controls_collapsed_state()
        if emit_state_change:
            self._schedule_time_selection_state_changed()

    def _apply_time_controls_collapsed_state(self) -> None:
        if hasattr(self, "_navigation_controls_container"):
            self._navigation_controls_container.setVisible(not self._time_controls_collapsed)
        if hasattr(self, "_time_controls_toggle_button"):
            self._time_controls_toggle_button.setArrowType(
                Qt.DownArrow if self._time_controls_collapsed else Qt.UpArrow
            )

    def _reset_plot_item(self) -> None:
        plot_item = self._plot_widget.getPlotItem()
        plot_item.clear()
        plot_item.setTitle("")
        left_axis = plot_item.getAxis("left")
        left_axis.setStyle(
            showValues=False,
            tickLength=0,
            autoExpandTextSpace=False,
            autoReduceTextSpace=True,
        )
        left_axis.setWidth(0)
        left_axis.setFixedWidth(0)
        left_axis.setMinimumWidth(0)
        left_axis.setMaximumWidth(0)
        plot_item.showAxis("left", False)
        plot_item.hideAxis("left")
        plot_item.layout.setColumnFixedWidth(0, 0)
        plot_item.setLabel("left", "")
        plot_item.setLabel("bottom", "Time")
        self._cursor_line.hide()
        plot_item.addItem(self._cursor_line, ignoreBounds=True)
        self._floating_legend_item.hide()
        plot_item.addItem(self._floating_legend_item, ignoreBounds=True)

    def _apply_highlight_state(self) -> None:
        active_highlighted_tags = self._active_highlighted_tag_names()
        highlight_is_active = bool(active_highlighted_tags)

        for prepared in self._prepared_series:
            is_dimmed = (
                highlight_is_active
                and prepared.plotted.series.tag_name not in active_highlighted_tags
            )
            prepared.curve.setPen(pg.mkPen(_series_qcolor(prepared.color, dimmed=is_dimmed), width=2))

        self._set_shared_scale_labels(self._prepared_series)
        if self._current_cursor_x is not None:
            self._update_floating_legend(self._build_cursor_stats(self._current_cursor_x))

    def _active_highlighted_tag_names(self) -> set[str]:
        prepared_tag_names = {
            prepared.plotted.series.tag_name for prepared in self._prepared_series
        }
        return {
            tag_name
            for tag_name in self._highlighted_tag_names
            if tag_name in prepared_tag_names
        }

    def _set_shared_scale_labels(
        self,
        prepared_series: list[_PreparedTrendPlotSeries],
    ) -> None:
        _clear_layout(self._shared_scale_top_layout)
        _clear_layout(self._shared_scale_mid_layout)
        _clear_layout(self._shared_scale_bottom_layout)

        if not prepared_series:
            self._shared_scale_panel.setFixedWidth(SCALE_PANEL_MIN_WIDTH)
            self._shared_scale_panel.hide()
            return

        column_count = _shared_scale_column_count(len(prepared_series))
        column_widths = _shared_scale_column_widths(
            prepared_series,
            self._shared_scale_panel.fontMetrics(),
            self._shared_scale_decimal_places,
        )
        self._shared_scale_panel.setFixedWidth(_shared_scale_panel_width(column_widths))
        _configure_scale_grid(self._shared_scale_top_layout, column_widths)
        _configure_scale_grid(self._shared_scale_mid_layout, column_widths)
        _configure_scale_grid(self._shared_scale_bottom_layout, column_widths)

        active_highlighted_tags = self._active_highlighted_tag_names()
        highlight_is_active = bool(active_highlighted_tags)
        for index, prepared in enumerate(prepared_series):
            row_index = index % SCALE_PANEL_TAGS_PER_COLUMN
            column_index = index // SCALE_PANEL_TAGS_PER_COLUMN
            midpoint = (prepared.display_low_range + prepared.display_high_range) / 2.0
            is_dimmed = (
                highlight_is_active
                and prepared.plotted.series.tag_name not in active_highlighted_tags
            )
            self._shared_scale_top_layout.addWidget(
                self._build_scale_label(
                    value=prepared.display_high_range,
                    color=prepared.color,
                    tooltip=f"{prepared.display_label} high range",
                    dimmed=is_dimmed,
                ),
                row_index,
                column_index,
            )
            self._shared_scale_mid_layout.addWidget(
                self._build_scale_label(
                    value=midpoint,
                    color=prepared.color,
                    tooltip=f"{prepared.display_label} midpoint",
                    dimmed=is_dimmed,
                ),
                row_index,
                column_index,
            )
            self._shared_scale_bottom_layout.addWidget(
                self._build_scale_label(
                    value=prepared.display_low_range,
                    color=prepared.color,
                    tooltip=f"{prepared.display_label} low range",
                    dimmed=is_dimmed,
                ),
                row_index,
                column_index,
            )

        self._shared_scale_panel.show()

    def _build_scale_label(
        self,
        *,
        value: float,
        color: str,
        tooltip: str,
        dimmed: bool = False,
    ) -> QLabel:
        label = QLabel(
            _format_scale_value(value, self._shared_scale_decimal_places),
            self._shared_scale_panel,
        )
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(f"color: {_qcolor_to_css(_series_qcolor(color, dimmed=dimmed))};")
        label.setToolTip(tooltip)
        label.setFrameStyle(QFrame.NoFrame)
        self._bind_shared_scale_context_menu(label)
        return label

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
        cursor_stats = self._build_cursor_stats(cursor_x)
        self._update_floating_legend(cursor_stats)
        self.cursorStatsChanged.emit(cursor_stats)

    def _clear_cursor_state(self) -> None:
        self._current_cursor_x = None
        self._cursor_line.hide()
        self._cursor_label.clear()
        self._cursor_label.hide()
        self._hide_floating_legend()
        self.cursorStatsChanged.emit(None)

    def _set_visible_range_text(self, x_min: float, x_max: float) -> None:
        self._visible_range_label.setText(_format_compact_time_range(x_min, x_max))
        self._visible_range_label.setToolTip(_format_time_range(x_min, x_max))
        self._visible_range_label.show()

    def _clear_visible_range_state(self) -> None:
        self._current_visible_range = None
        self._visible_range_label.clear()
        self._visible_range_label.setToolTip("")
        self._visible_range_label.hide()

    def _build_cursor_stats(self, cursor_x: float) -> TrendCursorStats:
        series_stats: list[TrendCursorSeriesStats] = []
        for prepared in self._prepared_series:
            previous_index, nearest_index, next_index = _cursor_sample_indices(
                prepared.x_values,
                cursor_x,
            )
            previous_timestamp: float | None = None
            previous_value: float | None = None
            sample_timestamp: float | None = None
            cursor_value: float | None = None
            interpolated_value: float | None = None
            interpolation_mode = "unavailable"
            interpolation_start_timestamp: float | None = None
            interpolation_end_timestamp: float | None = None
            next_timestamp: float | None = None
            next_value: float | None = None
            if previous_index is not None:
                previous_timestamp = float(prepared.x_values[previous_index])
                value = float(prepared.y_values[previous_index])
                if np.isfinite(value):
                    previous_value = value
            if nearest_index is not None:
                sample_timestamp = float(prepared.x_values[nearest_index])
                value = float(prepared.y_values[nearest_index])
                if np.isfinite(value):
                    cursor_value = value
            if next_index is not None:
                next_timestamp = float(prepared.x_values[next_index])
                value = float(prepared.y_values[next_index])
                if np.isfinite(value):
                    next_value = value
            (
                interpolated_value,
                interpolation_mode,
                interpolation_start_timestamp,
                interpolation_end_timestamp,
            ) = _interpolated_cursor_value(
                prepared.x_values,
                prepared.y_values,
                cursor_x,
                previous_index=previous_index,
                nearest_index=nearest_index,
                next_index=next_index,
            )

            series_stats.append(
                TrendCursorSeriesStats(
                    tag_name=prepared.plotted.series.tag_name,
                    sheet_name=prepared.plotted.sheet.name,
                    color=prepared.color,
                    sample_timestamp=sample_timestamp,
                    cursor_value=cursor_value,
                    interpolated_value=interpolated_value,
                    interpolation_mode=interpolation_mode,
                    interpolation_start_timestamp=interpolation_start_timestamp,
                    interpolation_end_timestamp=interpolation_end_timestamp,
                    previous_timestamp=previous_timestamp,
                    previous_value=previous_value,
                    next_timestamp=next_timestamp,
                    next_value=next_value,
                )
            )

        return TrendCursorStats(
            cursor_timestamp=cursor_x,
            series_stats=tuple(series_stats),
        )

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._plot_widget.viewport():
            if event.type() == QEvent.Leave:
                self._clear_cursor_state()
            elif event.type() == QEvent.ContextMenu:
                global_position = (
                    event.globalPos()
                    if hasattr(event, "globalPos")
                    else self._plot_widget.viewport().mapToGlobal(event.pos())
                )
                self._build_plot_context_menu().exec(global_position)
                return True
        return super().eventFilter(watched, event)

    def _build_plot_context_menu(self) -> QMenu:
        menu = QMenu(self)
        floating_legend_action = menu.addAction("Floating legend")
        floating_legend_action.setCheckable(True)
        floating_legend_action.setChecked(self._floating_legend_enabled)
        floating_legend_action.toggled.connect(
            lambda checked: self._set_floating_legend_enabled(checked, emit_state_change=True)
        )

        cursor_data_action = menu.addAction("Show data at cursor time")
        cursor_data_action.setCheckable(True)
        cursor_data_action.setChecked(self._floating_legend_show_cursor_data)
        cursor_data_action.toggled.connect(
            lambda checked: self._set_floating_legend_show_cursor_data(
                checked,
                emit_state_change=True,
            )
        )
        return menu

    def _bind_shared_scale_context_menu(self, widget: QWidget) -> None:
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda position, source=widget: self._show_shared_scale_context_menu(
                source.mapToGlobal(position)
            )
        )

    def _show_shared_scale_context_menu(self, global_position) -> None:
        self._build_shared_scale_context_menu().exec(global_position)

    def _build_shared_scale_context_menu(self) -> QMenu:
        menu = QMenu(self)
        for label, decimal_places in (
            ("Auto", None),
            ("0", 0),
            ("1", 1),
            ("2", 2),
            ("3", 3),
            ("4", 4),
            ("5", 5),
            ("6", 6),
        ):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._shared_scale_decimal_places == decimal_places)
            action.triggered.connect(
                lambda _checked=False, places=decimal_places: self._set_shared_scale_decimal_places(
                    places,
                    emit_state_change=True,
                )
            )
        return menu

    def _set_shared_scale_decimal_places(
        self,
        decimal_places: int | None,
        *,
        emit_state_change: bool,
    ) -> None:
        normalized_places = _coerce_scale_decimal_places(decimal_places)
        if normalized_places == self._shared_scale_decimal_places:
            return
        self._shared_scale_decimal_places = normalized_places
        self._set_shared_scale_labels(self._prepared_series)
        if emit_state_change:
            self._schedule_time_selection_state_changed()

    def _set_floating_legend_enabled(self, enabled: bool, *, emit_state_change: bool) -> None:
        normalized_enabled = bool(enabled)
        if normalized_enabled == self._floating_legend_enabled:
            if normalized_enabled:
                self._refresh_floating_legend_from_current_cursor()
            return
        self._floating_legend_enabled = normalized_enabled
        self._refresh_floating_legend_from_current_cursor()
        if emit_state_change:
            self._schedule_time_selection_state_changed()

    def _set_floating_legend_show_cursor_data(
        self,
        enabled: bool,
        *,
        emit_state_change: bool,
    ) -> None:
        normalized_enabled = bool(enabled)
        if normalized_enabled == self._floating_legend_show_cursor_data:
            if self._floating_legend_enabled:
                self._refresh_floating_legend_from_current_cursor()
            return
        self._floating_legend_show_cursor_data = normalized_enabled
        if normalized_enabled:
            self._floating_legend_enabled = True
        self._refresh_floating_legend_from_current_cursor()
        if emit_state_change:
            self._schedule_time_selection_state_changed()

    def _refresh_floating_legend_from_current_cursor(self) -> None:
        if self._current_cursor_x is None:
            self._hide_floating_legend()
            return
        self._update_floating_legend(self._build_cursor_stats(self._current_cursor_x))

    def _update_floating_legend(self, cursor_stats: TrendCursorStats) -> None:
        if not self._floating_legend_enabled or not self._prepared_series:
            self._hide_floating_legend()
            return

        stats_by_tag = {
            stats.tag_name: stats
            for stats in cursor_stats.series_stats
        }
        lines: list[str] = []
        active_highlighted_tags = self._active_highlighted_tag_names()
        highlight_is_active = bool(active_highlighted_tags)
        for prepared in self._prepared_series:
            tag_name = prepared.plotted.series.tag_name
            color_css = _qcolor_to_css(
                _series_qcolor(
                    prepared.color,
                    dimmed=highlight_is_active and tag_name not in active_highlighted_tags,
                )
            )
            label_text = html.escape(prepared.display_label)
            if self._floating_legend_show_cursor_data:
                value_text = _format_floating_legend_value(stats_by_tag.get(tag_name))
                lines.append(
                    f"<span style='color:{color_css};'><b>{label_text}</b>: {html.escape(value_text)}</span>"
                )
            else:
                lines.append(
                    f"<span style='color:{color_css};'><b>{label_text}</b></span>"
                )

        if not lines:
            self._hide_floating_legend()
            return

        self._floating_legend_html = (
            "<div style='font-size:11px; line-height:1.35;'>"
            + "<br/>".join(lines)
            + "</div>"
        )
        self._floating_legend_item.setHtml(self._floating_legend_html)
        self._floating_legend_item.setAnchor(
            (1.0, 0.0)
            if self._should_anchor_floating_legend_right(cursor_stats.cursor_timestamp)
            else (0.0, 0.0)
        )
        self._floating_legend_item.setPos(
            cursor_stats.cursor_timestamp,
            DISPLAY_Y_MAX - 2.0,
        )
        self._floating_legend_item.show()

    def _hide_floating_legend(self) -> None:
        self._floating_legend_html = ""
        self._floating_legend_item.hide()

    def _should_anchor_floating_legend_right(self, cursor_x: float) -> bool:
        if self._current_visible_range is None:
            return False
        x_min, x_max = self._current_visible_range
        return cursor_x >= (x_min + x_max) / 2.0


def _build_summary_text(
    *,
    workbook_name: str,
    visible_stats: list[TrendVisibleSeriesStats],
    x_min: float,
    x_max: float,
    display_labels_by_tag: dict[str, str] | None = None,
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
            "Sheet: "
            f"{stats.sheet_name} | Tag: {_display_label_for_tag(stats.tag_name, display_labels_by_tag)}\n"
            f"Visible samples: {stats.sample_count:,}\n"
            f"Visible range: {time_range}"
        )

    sheet_names = sorted({stats.sheet_name for stats in visible_stats}, key=str.casefold)
    tag_names = [
        _display_label_for_tag(stats.tag_name, display_labels_by_tag)
        for stats in visible_stats
    ]
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


def _display_label_for_tag(
    tag_name: str,
    display_labels_by_tag: dict[str, str] | None,
) -> str:
    if display_labels_by_tag is not None:
        display_label = display_labels_by_tag.get(tag_name)
        if isinstance(display_label, str) and display_label.strip():
            return display_label.strip()
    return tag_name


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


def _configure_scale_grid(layout: QGridLayout, column_widths: list[int]) -> None:
    column_count = len(column_widths)
    layout.setHorizontalSpacing(SCALE_PANEL_COLUMN_SPACING if column_count > 1 else 2)
    layout.setVerticalSpacing(2)
    for column_index in range(SCALE_PANEL_STRETCH_RESET_COLUMNS):
        layout.setColumnStretch(column_index, 0)
        layout.setColumnMinimumWidth(column_index, 0)
    for column_index in range(column_count):
        layout.setColumnMinimumWidth(column_index, column_widths[column_index])


def _shared_scale_column_widths(
    prepared_series: list[_PreparedTrendPlotSeries],
    font_metrics,
    decimal_places: int | None,
) -> list[int]:
    column_count = _shared_scale_column_count(len(prepared_series))
    widths: list[int] = [0] * column_count

    for index, prepared in enumerate(prepared_series):
        column_index = index // SCALE_PANEL_TAGS_PER_COLUMN
        midpoint = (prepared.display_low_range + prepared.display_high_range) / 2.0
        column_values = (
            _format_scale_value(prepared.display_high_range, decimal_places),
            _format_scale_value(midpoint, decimal_places),
            _format_scale_value(prepared.display_low_range, decimal_places),
        )
        widest_value = max(font_metrics.horizontalAdvance(text) for text in column_values)
        widths[column_index] = max(widths[column_index], widest_value + SCALE_PANEL_COLUMN_PADDING)

    return [max(SCALE_PANEL_MIN_WIDTH if column_count == 1 else 0, width) for width in widths]


def _shared_scale_column_count(series_count: int) -> int:
    if series_count <= 0:
        return 1
    return max(1, (series_count + SCALE_PANEL_TAGS_PER_COLUMN - 1) // SCALE_PANEL_TAGS_PER_COLUMN)


def _shared_scale_panel_width(column_widths: list[int]) -> int:
    column_count = len(column_widths)
    return max(
        SCALE_PANEL_MIN_WIDTH,
        sum(column_widths)
        + (max(0, column_count - 1) * SCALE_PANEL_COLUMN_SPACING),
    )


def _series_qcolor(color: str, *, dimmed: bool) -> QColor:
    qcolor = QColor(color)
    if dimmed:
        qcolor.setAlpha(HIGHLIGHT_DIM_ALPHA)
    return qcolor


def _qcolor_to_css(color: QColor) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def _format_time_range(start_epoch: float, end_epoch: float) -> str:
    start = _format_timestamp(start_epoch)
    end = _format_timestamp(end_epoch)
    return f"{start} to {end}"


def _format_compact_time_range(start_epoch: float, end_epoch: float) -> str:
    start = datetime.fromtimestamp(start_epoch)
    end = datetime.fromtimestamp(end_epoch)
    if start.date() == end.date():
        start_text = start.strftime("%m-%d %H:%M")
        end_text = end.strftime("%H:%M")
    elif start.year == end.year:
        start_text = start.strftime("%m-%d")
        end_text = end.strftime("%m-%d")
    else:
        start_text = start.strftime("%Y-%m-%d")
        end_text = end.strftime("%Y-%m-%d")
    return f"{start_text} -> {end_text}"


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _format_scale_value(value: float, decimal_places: int | None = None) -> str:
    if decimal_places is not None:
        return f"{value:,.{decimal_places}f}"
    if abs(value) >= 100:
        return f"{value:,.2f}"
    if abs(value) >= 1:
        return f"{value:,.3f}"
    return f"{value:,.4f}"


def _format_floating_legend_value(cursor_stats: TrendCursorSeriesStats | None) -> str:
    if cursor_stats is None:
        return "-"
    for value in (
        cursor_stats.interpolated_value,
        cursor_stats.cursor_value,
        cursor_stats.previous_value,
        cursor_stats.next_value,
    ):
        if value is not None:
            return _format_scale_value(value)
    return "-"


def _coerce_scale_decimal_places(value: object) -> int | None:
    if value is None:
        return None
    try:
        decimal_places = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= decimal_places <= 6:
        return decimal_places
    return None


def _visible_index_bounds(
    x_values: np.ndarray,
    x_min: float,
    x_max: float,
) -> tuple[int, int]:
    start_index = max(0, int(np.searchsorted(x_values, x_min, side="left")) - 1)
    end_index = min(x_values.size, int(np.searchsorted(x_values, x_max, side="right")) + 1)
    return start_index, end_index


def _visible_stats_index_bounds(
    x_values: np.ndarray,
    x_min: float,
    x_max: float,
) -> tuple[int, int]:
    start_index = int(np.searchsorted(x_values, x_min, side="left"))
    end_index = int(np.searchsorted(x_values, x_max, side="right"))
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


def _resolved_series_display_range(
    tag_name: str,
    display_ranges_by_tag: dict[str, tuple[float, float]] | None,
) -> tuple[float, float]:
    if display_ranges_by_tag is not None:
        stored = display_ranges_by_tag.get(tag_name)
        if stored is not None:
            low_range, high_range = stored
            if np.isfinite(low_range) and np.isfinite(high_range) and low_range < high_range:
                return float(low_range), float(high_range)
    return 0.0, 1.0


def _resolved_series_color(
    tag_name: str,
    series_colors_by_tag: dict[str, str] | None,
    *,
    fallback: str,
) -> str:
    if series_colors_by_tag is not None:
        color = series_colors_by_tag.get(tag_name)
        if isinstance(color, str) and color.strip():
            return color.strip().upper()
    return fallback


def _normalize_display_values(
    y_values: np.ndarray,
    *,
    low_range: float,
    high_range: float,
) -> np.ndarray:
    if y_values.size == 0:
        return y_values

    span = high_range - low_range
    if not np.isfinite(span) or span <= 0:
        return np.full(y_values.shape, np.nan, dtype=np.float64)

    normalized = ((y_values.astype(np.float64) - low_range) / span) * DISPLAY_Y_MAX
    normalized = np.clip(normalized, DISPLAY_Y_MIN, DISPLAY_Y_MAX)
    normalized[~np.isfinite(y_values)] = np.nan
    return normalized


def _cursor_sample_indices(
    x_values: np.ndarray,
    target_x: float,
) -> tuple[int | None, int | None, int | None]:
    if x_values.size == 0:
        return None, None, None

    left_insert_index = int(np.searchsorted(x_values, target_x, side="left"))
    right_insert_index = int(np.searchsorted(x_values, target_x, side="right"))

    previous_index = left_insert_index - 1 if left_insert_index > 0 else None
    next_index = right_insert_index if right_insert_index < x_values.size else None

    if left_insert_index <= 0:
        return previous_index, 0, next_index
    if left_insert_index >= x_values.size:
        return previous_index, int(x_values.size - 1), next_index

    right_index = left_insert_index
    left_index = left_insert_index - 1
    left_distance = abs(float(x_values[left_index]) - target_x)
    right_distance = abs(float(x_values[right_index]) - target_x)
    if right_distance < left_distance:
        return previous_index, right_index, next_index
    return previous_index, left_index, next_index


def _interpolated_cursor_value(
    x_values: np.ndarray,
    y_values: np.ndarray,
    target_x: float,
    *,
    previous_index: int | None,
    nearest_index: int | None,
    next_index: int | None,
) -> tuple[float | None, str, float | None, float | None]:
    if nearest_index is not None:
        nearest_x = float(x_values[nearest_index])
        nearest_y = float(y_values[nearest_index])
        if nearest_x == target_x and np.isfinite(nearest_y):
            return nearest_y, "exact", nearest_x, nearest_x

    if previous_index is not None and next_index is not None:
        start_x = float(x_values[previous_index])
        end_x = float(x_values[next_index])
        start_y = float(y_values[previous_index])
        end_y = float(y_values[next_index])
        if (
            np.isfinite(start_y)
            and np.isfinite(end_y)
            and end_x != start_x
            and start_x <= target_x <= end_x
        ):
            fraction = (target_x - start_x) / (end_x - start_x)
            value = start_y + ((end_y - start_y) * fraction)
            return float(value), "linear", start_x, end_x

    if nearest_index is not None:
        nearest_x = float(x_values[nearest_index])
        nearest_y = float(y_values[nearest_index])
        if np.isfinite(nearest_y):
            return nearest_y, "nearest", nearest_x, nearest_x

    return None, "unavailable", None, None


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


def _clamp_requested_time_range(
    requested_range: tuple[float, float] | None,
    *,
    data_min: float,
    data_max: float,
) -> tuple[float, float] | None:
    if requested_range is None:
        return None

    x_min, x_max = requested_range
    if not np.isfinite(x_min) or not np.isfinite(x_max) or x_max <= x_min:
        return None
    return _clamp_x_range(float(x_min), float(x_max), data_min, data_max)


def parse_duration_text(value: str) -> int | None:
    normalized = value.strip().lower()
    if not normalized:
        return None

    time_match = re.fullmatch(r"(\d{1,3}):(\d{2})(?::(\d{2}))?", normalized)
    if time_match is not None:
        hours = int(time_match.group(1))
        minutes = int(time_match.group(2))
        seconds = int(time_match.group(3) or "0")
        total_seconds = (hours * 3600) + (minutes * 60) + seconds
        return total_seconds if total_seconds > 0 else None

    token_matches = list(re.finditer(r"(\d+)\s*([wdhms])", normalized))
    compact_text = normalized.replace(" ", "")
    if not token_matches or "".join(match.group(0).replace(" ", "") for match in token_matches) != compact_text:
        return None

    multipliers = {
        "w": 7 * 24 * 3600,
        "d": 24 * 3600,
        "h": 3600,
        "m": 60,
        "s": 1,
    }
    total_seconds = 0
    for match in token_matches:
        total_seconds += int(match.group(1)) * multipliers[match.group(2)]
    return total_seconds if total_seconds > 0 else None


def format_duration_seconds(total_seconds: int) -> str:
    safe_seconds = max(0, int(total_seconds))
    if safe_seconds == 0:
        return "0s"

    parts: list[str] = []
    remaining = safe_seconds
    units = (
        ("w", 7 * 24 * 3600),
        ("d", 24 * 3600),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    )
    for suffix, unit_seconds in units:
        value, remaining = divmod(remaining, unit_seconds)
        if value > 0:
            parts.append(f"{value}{suffix}")
    return " ".join(parts[:3])


def normalize_duration_presets(values: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        text = str(raw_value).strip()
        duration_seconds = parse_duration_text(text)
        if duration_seconds is None:
            continue
        normalized_text = format_duration_seconds(duration_seconds)
        key = normalized_text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(normalized_text)
    return normalized or list(DEFAULT_DURATION_PRESETS)


def _matching_duration_preset(duration_seconds: int | None, presets: list[str]) -> str | None:
    if duration_seconds is None:
        return None
    for preset in presets:
        if parse_duration_text(preset) == duration_seconds:
            return preset
    return None


def _qdatetime_from_epoch(timestamp: float) -> QDateTime:
    return QDateTime.fromSecsSinceEpoch(
        int(round(timestamp)),
        QTimeZone.systemTimeZone(),
    )


def _coerce_epoch(value: object) -> float | None:
    if isinstance(value, (int, float)) and np.isfinite(value):
        return float(value)
    return None


@contextmanager
def _suspend_time_control_updates(widget: TrendPlotWidget):
    previous_value = widget._suspend_time_control_updates
    widget._suspend_time_control_updates = True
    try:
        yield
    finally:
        widget._suspend_time_control_updates = previous_value
