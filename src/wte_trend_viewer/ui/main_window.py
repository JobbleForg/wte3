from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolBar,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from ..data_manager import LoadedTrendWorkbook, TrendDataManager
from ..session import SessionStore, SessionTreeNode, WorkspaceSession
from ..tag_units import display_unit_text, normalize_unit_list, normalize_unit_text
from ..workbook import WorkbookInspector
from .dialogs.sheet_selection_dialog import SheetSelectionDialog
from .dialogs.unit_manager_dialog import UnitManagerDialog
from .widgets.hierarchy_tree import (
    GROUP_ITEM_KIND,
    ITEM_KIND_ROLE,
    TAG_ITEM_KIND,
    SearchableHierarchyTree,
)
from .widgets.imported_tag_list import SearchableImportedTagList
from .widgets.trend_plot_widget import (
    DEFAULT_DURATION_PRESETS,
    PLOT_COLORS,
    TrendCursorSeriesStats,
    TrendCursorStats,
    TrendPlotSeries,
    TrendPlotWidget,
    TrendVisibleSeriesStats,
    normalize_duration_presets,
    parse_duration_text,
)

LEGEND_TAG_COLUMN = 0
LEGEND_SHEET_COLUMN = 1
LEGEND_UNIT_COLUMN = 2
LEGEND_LOW_RANGE_COLUMN = 3
LEGEND_HIGH_RANGE_COLUMN = 4
LEGEND_COLOR_COLUMN = 5
LEGEND_HIGHLIGHT_COLUMN = 6
DETACHED_LEGEND_HIGHLIGHT_COLUMN = 5


class _CollapsibleSection(QWidget):
    def __init__(
        self,
        title_text: str,
        *,
        expanded: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._expanded = expanded
        self._content_widget: QWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        header_label = QLabel(title_text, header)
        header_layout.addWidget(header_label)
        header_layout.addStretch(1)

        self._toggle_button = QToolButton(header)
        self._toggle_button.setAutoRaise(True)
        self._toggle_button.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self._toggle_button, alignment=Qt.AlignRight)

        layout.addWidget(header)

        self._content_container = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        layout.addWidget(self._content_container)

        self.set_expanded(expanded)

    def set_content_widget(self, widget: QWidget) -> None:
        if self._content_widget is not None:
            self._content_layout.removeWidget(self._content_widget)
            self._content_widget.setParent(None)
        self._content_widget = widget
        self._content_layout.addWidget(widget)
        self._content_container.setVisible(self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._content_container.setVisible(self._expanded)
        self._toggle_button.setArrowType(
            Qt.UpArrow if self._expanded else Qt.DownArrow
        )

    def is_expanded(self) -> bool:
        return self._expanded

    def _toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)


class _DetachedTrendWindow(QWidget):
    def __init__(
        self,
        *,
        title_text: str,
        workbook_name: str,
        plotted_series: list[TrendPlotSeries],
        display_ranges_by_tag: dict[str, tuple[float, float]],
        display_labels_by_tag: dict[str, str],
        display_units_by_tag: dict[str, str],
        series_colors_by_tag: dict[str, str],
        highlighted_tag_names: list[str],
        time_presets: list[str],
        time_selection_state: dict[str, object],
        pan_fraction: tuple[int, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title_text)
        self.resize(1200, 720)
        self._display_labels_by_tag = dict(display_labels_by_tag)
        self._display_units_by_tag = dict(display_units_by_tag)
        self._series_colors_by_tag = dict(series_colors_by_tag)
        self._current_visible_stats: list[TrendVisibleSeriesStats] = []
        self._current_cursor_stats: TrendCursorStats | None = None
        self._legend_table: QTableWidget | None = None
        self._analytics_table: QTableWidget | None = None
        self._suspend_detached_legend_updates = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Trend window", self)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self._trend_plot_widget = TrendPlotWidget(self)
        self._trend_plot_widget.visibleStatsChanged.connect(
            self._handle_plot_visible_stats_changed
        )
        self._trend_plot_widget.cursorStatsChanged.connect(
            self._handle_plot_cursor_stats_changed
        )
        self._trend_plot_widget.set_time_presets(time_presets)
        self._trend_plot_widget.set_pan_fraction(*pan_fraction)
        self._trend_plot_widget.set_time_selection_state(time_selection_state)
        self._trend_plot_widget.plot_series_group(
            workbook_name=workbook_name,
            plotted_series=plotted_series,
            display_ranges_by_tag=display_ranges_by_tag,
            display_labels_by_tag=display_labels_by_tag,
            series_colors_by_tag=series_colors_by_tag,
        )
        self._trend_plot_widget.set_highlighted_tags(highlighted_tag_names)
        layout.addWidget(self._trend_plot_widget, stretch=1)

        details_tabs = QTabWidget(self)
        details_tabs.addTab(
            self._build_detached_legend_tab(
                plotted_series,
                display_ranges_by_tag,
                highlighted_tag_names,
            ),
            "Legend",
        )
        details_tabs.addTab(self._build_detached_analytics_tab(), "Analytics")
        details_tabs.addTab(self._build_detached_settings_tab(time_presets), "Settings")

        self._details_section = _CollapsibleSection(
            "Legend / Analytics / Settings",
            expanded=False,
            parent=self,
        )
        self._details_section.set_content_widget(details_tabs)
        layout.addWidget(self._details_section)
        self._update_detached_analytics_table()

    def _build_detached_legend_tab(
        self,
        plotted_series: list[TrendPlotSeries],
        display_ranges_by_tag: dict[str, tuple[float, float]],
        highlighted_tag_names: list[str],
    ) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._legend_table = QTableWidget(0, 6, container)
        self._legend_table.setHorizontalHeaderLabels(
            ["Tag", "Sheet", "Unit", "Low Range", "High Range", "Highlight"]
        )
        self._legend_table.verticalHeader().setVisible(False)
        self._legend_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._legend_table.setAlternatingRowColors(True)
        self._legend_table.itemChanged.connect(self._handle_detached_legend_item_changed)
        header = self._legend_table.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(
            self._show_detached_legend_header_context_menu
        )
        layout.addWidget(self._legend_table)

        active_highlights = set(highlighted_tag_names)
        self._suspend_detached_legend_updates = True
        try:
            for row_index, plotted in enumerate(plotted_series):
                self._legend_table.insertRow(row_index)
                tag_name = plotted.series.tag_name
                tag_item = QTableWidgetItem(self._display_labels_by_tag.get(tag_name, tag_name))
                tag_item.setForeground(
                    QColor(
                        self._series_colors_by_tag.get(
                            tag_name,
                            PLOT_COLORS[row_index % len(PLOT_COLORS)],
                        )
                    )
                )
                tag_item.setToolTip(tag_name)
                tag_item.setFlags(tag_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, 0, tag_item)

                sheet_item = QTableWidgetItem(plotted.sheet.name)
                sheet_item.setFlags(sheet_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, 1, sheet_item)

                unit_item = QTableWidgetItem(self._display_units_by_tag.get(tag_name, "-"))
                unit_item.setFlags(unit_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, 2, unit_item)

                low_range, high_range = display_ranges_by_tag.get(tag_name, (0.0, 0.0))
                low_item = QTableWidgetItem(_format_range_value(low_range))
                low_item.setFlags(low_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, 3, low_item)

                high_item = QTableWidgetItem(_format_range_value(high_range))
                high_item.setFlags(high_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, 4, high_item)

                highlight_item = QTableWidgetItem("")
                highlight_item.setData(Qt.UserRole, tag_name)
                highlight_item.setFlags(
                    (highlight_item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable
                )
                highlight_item.setCheckState(
                    Qt.Checked if tag_name in active_highlights else Qt.Unchecked
                )
                highlight_item.setTextAlignment(Qt.AlignCenter)
                self._legend_table.setItem(row_index, 5, highlight_item)
        finally:
            self._suspend_detached_legend_updates = False

        self._legend_table.resizeColumnsToContents()
        return container

    def _build_detached_analytics_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._analytics_table = QTableWidget(0, 5, container)
        self._analytics_table.setHorizontalHeaderLabels(
            [
                "Tag",
                "Cursor Value",
                "Window Min",
                "Window Max",
                "Window Avg",
            ]
        )
        self._analytics_table.verticalHeader().setVisible(False)
        self._analytics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._analytics_table.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._analytics_table)
        return container

    def _build_detached_settings_tab(self, time_presets: list[str]) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        helper = QLabel(
            "Detached views keep their own cursor, time window, and pan state. "
            "These presets remain available in the bottom time controls.",
            container,
        )
        helper.setWordWrap(True)
        layout.addWidget(helper)

        preset_list = QListWidget(container)
        preset_list.setSelectionMode(QAbstractItemView.NoSelection)
        for preset in time_presets:
            preset_list.addItem(preset)
        layout.addWidget(preset_list, stretch=1)
        return container

    def _handle_plot_visible_stats_changed(self, visible_stats: object) -> None:
        if isinstance(visible_stats, list):
            self._current_visible_stats = [
                stats for stats in visible_stats if isinstance(stats, TrendVisibleSeriesStats)
            ]
        else:
            self._current_visible_stats = []
        self._update_detached_analytics_table()

    def _handle_plot_cursor_stats_changed(self, cursor_stats: object) -> None:
        if isinstance(cursor_stats, TrendCursorStats):
            self._current_cursor_stats = cursor_stats
        else:
            self._current_cursor_stats = None
        self._update_detached_analytics_table()

    def _update_detached_analytics_table(self) -> None:
        if self._analytics_table is None:
            return

        cursor_stats_by_tag: dict[str, TrendCursorSeriesStats] = {}
        if self._current_cursor_stats is not None:
            cursor_stats_by_tag = {
                stats.tag_name: stats for stats in self._current_cursor_stats.series_stats
            }

        self._analytics_table.setRowCount(0)
        for row_index, stats in enumerate(self._current_visible_stats):
            self._analytics_table.insertRow(row_index)
            cursor_stats = cursor_stats_by_tag.get(stats.tag_name)
            tag_item = QTableWidgetItem(
                self._display_labels_by_tag.get(stats.tag_name, stats.tag_name)
            )
            tag_item.setForeground(QColor(stats.color))
            tag_item.setToolTip(stats.tag_name)
            self._analytics_table.setItem(row_index, 0, tag_item)
            self._analytics_table.setItem(
                row_index,
                1,
                _build_cursor_value_item(cursor_stats),
            )
            self._analytics_table.setItem(
                row_index,
                2,
                _build_numeric_item(stats.minimum_value),
            )
            self._analytics_table.setItem(row_index, 3, _build_numeric_item(stats.maximum_value))
            self._analytics_table.setItem(row_index, 4, _build_numeric_item(stats.average_value))

        self._analytics_table.resizeColumnsToContents()

    def _handle_detached_legend_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_detached_legend_updates:
            return
        if item.column() != DETACHED_LEGEND_HIGHLIGHT_COLUMN:
            return
        if self._legend_table is None:
            return

        highlighted_tag_names: list[str] = []
        for row_index in range(self._legend_table.rowCount()):
            highlight_item = self._legend_table.item(row_index, DETACHED_LEGEND_HIGHLIGHT_COLUMN)
            if highlight_item is None or highlight_item.checkState() != Qt.Checked:
                continue
            tag_name = str(highlight_item.data(Qt.UserRole) or "").strip()
            if tag_name:
                highlighted_tag_names.append(tag_name)

        self._trend_plot_widget.set_highlighted_tags(highlighted_tag_names)

    def _show_detached_legend_header_context_menu(self, position) -> None:
        if self._legend_table is None:
            return

        header = self._legend_table.horizontalHeader()
        if header.logicalIndexAt(position) != DETACHED_LEGEND_HIGHLIGHT_COLUMN:
            return

        menu = QMenu(header)
        clear_action = menu.addAction("Clear all")
        clear_action.setEnabled(any(self._detached_highlight_states()))
        selected_action = menu.exec(header.mapToGlobal(position))
        if selected_action is clear_action:
            self._clear_detached_highlights()

    def _clear_detached_highlights(self) -> None:
        if self._legend_table is None:
            return

        self._suspend_detached_legend_updates = True
        try:
            for row_index in range(self._legend_table.rowCount()):
                highlight_item = self._legend_table.item(row_index, DETACHED_LEGEND_HIGHLIGHT_COLUMN)
                if highlight_item is not None:
                    highlight_item.setCheckState(Qt.Unchecked)
        finally:
            self._suspend_detached_legend_updates = False

        self._trend_plot_widget.set_highlighted_tags([])

    def _detached_highlight_states(self) -> list[bool]:
        if self._legend_table is None:
            return []
        return [
            (self._legend_table.item(row_index, DETACHED_LEGEND_HIGHLIGHT_COLUMN) is not None)
            and self._legend_table.item(row_index, DETACHED_LEGEND_HIGHLIGHT_COLUMN).checkState() == Qt.Checked
            for row_index in range(self._legend_table.rowCount())
        ]


class TrendViewerMainWindow(QMainWindow):
    """Phase-1 shell with a configurable, persistent workspace."""

    def __init__(
        self,
        session_store: SessionStore | None = None,
        *,
        restore_last_session: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle("WTE Trend Viewer")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)
        self.setDockOptions(
            QMainWindow.AnimatedDocks
            | QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
        )

        self._session_store = session_store or SessionStore()
        self._workbook_inspector = WorkbookInspector()
        self._trend_data_manager = TrendDataManager(self._workbook_inspector)
        self._session = WorkspaceSession()
        self._suspend_session_updates = False
        self._loaded_workbook: LoadedTrendWorkbook | None = None

        self._hierarchy_tree = SearchableHierarchyTree(self)
        self._hierarchy_tree.itemSelectionChanged.connect(self._handle_hierarchy_selection_changed)
        self._hierarchy_tree.structureChanged.connect(self._handle_workspace_changed)
        self._hierarchy_tree.structureChanged.connect(self._refresh_tag_unit_presentations)
        self._hierarchy_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._hierarchy_tree.customContextMenuRequested.connect(self._show_hierarchy_tag_context_menu)

        self._imported_tags_list = SearchableImportedTagList(self)
        self._imported_tags_list.tagsChanged.connect(self._handle_workspace_changed)
        self._imported_tags_list.tagsChanged.connect(self._refresh_tag_unit_presentations)
        self._imported_tags_list.itemSelectionChanged.connect(
            self._handle_imported_tag_selection_changed
        )
        self._imported_tags_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._imported_tags_list.customContextMenuRequested.connect(
            self._show_imported_tag_context_menu
        )

        self._imported_count_label: QLabel | None = None
        self._add_subcategory_button: QPushButton | None = None
        self._delete_selected_button: QPushButton | None = None
        self._select_sheets_button: QPushButton | None = None
        self._left_workspace_splitter: QSplitter | None = None
        self._main_workspace_splitter: QSplitter | None = None
        self._bottom_tabs: QTabWidget | None = None
        self._trend_plot_widget: TrendPlotWidget | None = None
        self._legend_table: QTableWidget | None = None
        self._suspend_legend_table_updates = False
        self._time_preset_list: QListWidget | None = None
        self._analytics_table: QTableWidget | None = None
        self._current_plotted_series: list[TrendPlotSeries] = []
        self._current_plot_colors_by_tag: dict[str, str] = {}
        self._current_visible_stats: list[TrendVisibleSeriesStats] = []
        self._current_cursor_stats: TrendCursorStats | None = None
        self._current_preview_tag_names: list[str] = []
        self._detached_trend_windows: list[_DetachedTrendWindow] = []

        self._build_toolbar()
        self.addDockWidget(Qt.LeftDockWidgetArea, self._build_left_workspace_dock())
        self.setCentralWidget(self._build_main_workspace())

        if restore_last_session:
            self._restore_last_session()
        else:
            self._apply_session(WorkspaceSession())
            self._persist_last_session(show_errors=False)

        self._sync_workbook_actions()
        self._sync_trend_window_actions()
        self._sync_subcategory_button_state()
        self._update_trend_summary()

    def set_imported_tags(self, tags: list[str], *, persist: bool = True) -> None:
        self._imported_tags_list.set_tags(tags, emit_change=False)
        if self._imported_count_label is not None:
            self._imported_count_label.setText(f"{len(tags)} tags loaded")
        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Primary Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._open_workbook_action = QAction("Open Workbook", self)
        self._open_workbook_action.triggered.connect(self._prompt_open_workbook)
        toolbar.addAction(self._open_workbook_action)

        self._select_sheets_action = QAction("Select Sheets", self)
        self._select_sheets_action.triggered.connect(self._prompt_select_sheets)
        toolbar.addAction(self._select_sheets_action)

        self._load_session_action = QAction("Load Session", self)
        self._load_session_action.triggered.connect(self._prompt_load_session)
        toolbar.addAction(self._load_session_action)

        self._save_session_action = QAction("Save Session", self)
        self._save_session_action.triggered.connect(self._prompt_save_session)
        toolbar.addAction(self._save_session_action)

        self._clear_imported_tags_action = QAction("Clear Imported Tags", self)
        self._clear_imported_tags_action.triggered.connect(self._clear_imported_tags)
        toolbar.addAction(self._clear_imported_tags_action)

        self._pop_out_trend_action = QAction("Pop Out Trend", self)
        self._pop_out_trend_action.setEnabled(False)
        self._pop_out_trend_action.triggered.connect(self._pop_out_current_trend_window)
        toolbar.addAction(self._pop_out_trend_action)

        toolbar.addSeparator()

        for label in ("Reset View", "Inspection", "Export"):
            action = QAction(label, self)
            action.setEnabled(False)
            toolbar.addAction(action)

    def _build_left_workspace_dock(self) -> QDockWidget:
        dock = QDockWidget("Workspace", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMinimumWidth(300)
        dock.setWidget(self._build_left_workspace())
        return dock

    def _build_left_workspace(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._left_workspace_splitter = QSplitter(Qt.Vertical, container)
        self._left_workspace_splitter.addWidget(self._build_hierarchy_panel())
        self._left_workspace_splitter.addWidget(self._build_imported_tags_panel())
        self._left_workspace_splitter.setSizes([360, 320])
        self._left_workspace_splitter.splitterMoved.connect(self._handle_workspace_changed)

        layout.addWidget(self._left_workspace_splitter)
        return container

    def _build_hierarchy_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("panelCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        header = QWidget(panel)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Hierarchy list", header)
        header_layout.addWidget(title)
        header_layout.addStretch()

        add_category_button = QPushButton("Add category", header)
        add_category_button.clicked.connect(self._prompt_add_category)
        header_layout.addWidget(add_category_button)

        self._add_subcategory_button = QPushButton("Add sub category", header)
        self._add_subcategory_button.clicked.connect(self._prompt_add_subcategory)
        header_layout.addWidget(self._add_subcategory_button)

        self._delete_selected_button = QPushButton("Delete selected", header)
        self._delete_selected_button.clicked.connect(self._delete_selected_hierarchy_item)
        header_layout.addWidget(self._delete_selected_button)

        layout.addWidget(header)
        layout.addWidget(self._hierarchy_tree, stretch=1)
        return panel

    def _build_imported_tags_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("panelCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        header = QWidget(panel)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Imported tags", header)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._imported_count_label = QLabel("0 tags loaded", header)
        header_layout.addWidget(self._imported_count_label)

        self._select_sheets_button = QPushButton("Select sheets", header)
        self._select_sheets_button.clicked.connect(self._prompt_select_sheets)
        header_layout.addWidget(self._select_sheets_button)

        clear_tags_button = QPushButton("Clear", header)
        clear_tags_button.clicked.connect(self._clear_imported_tags)
        header_layout.addWidget(clear_tags_button)

        layout.addWidget(header)
        layout.addWidget(self._imported_tags_list, stretch=1)

        footer = QWidget(panel)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch(1)

        edit_units_button = QPushButton("Edit units", footer)
        edit_units_button.clicked.connect(self._prompt_edit_units)
        footer_layout.addWidget(edit_units_button)

        layout.addWidget(footer)
        return panel

    def _build_main_workspace(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._main_workspace_splitter = QSplitter(Qt.Vertical, container)
        self._main_workspace_splitter.addWidget(self._build_trend_view())
        self._main_workspace_splitter.addWidget(self._build_bottom_workspace())
        self._main_workspace_splitter.setSizes([620, 250])
        self._main_workspace_splitter.splitterMoved.connect(self._handle_workspace_changed)

        layout.addWidget(self._main_workspace_splitter)
        return container

    def _build_trend_view(self) -> QWidget:
        viewport = QFrame(self)
        viewport.setObjectName("trendViewport")

        layout = QVBoxLayout(viewport)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Trend window", viewport)
        title.setAlignment(Qt.AlignCenter)
        self._trend_plot_widget = TrendPlotWidget(viewport)
        self._trend_plot_widget.visibleStatsChanged.connect(self._handle_plot_visible_stats_changed)
        self._trend_plot_widget.cursorStatsChanged.connect(self._handle_plot_cursor_stats_changed)
        self._trend_plot_widget.panFractionChanged.connect(self._handle_workspace_changed)
        self._trend_plot_widget.timeSelectionStateChanged.connect(self._handle_workspace_changed)

        layout.addWidget(title)
        layout.addWidget(self._trend_plot_widget, stretch=1)
        return viewport

    def _build_bottom_workspace(self) -> QWidget:
        self._bottom_tabs = QTabWidget(self)
        self._bottom_tabs.addTab(self._build_legend_tab(), "Legend")
        self._bottom_tabs.addTab(self._build_analytics_tab(), "Analytics")
        self._bottom_tabs.addTab(self._build_settings_tab(), "Settings")
        self._bottom_tabs.currentChanged.connect(self._handle_workspace_changed)
        return self._bottom_tabs

    def _build_legend_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._legend_table = QTableWidget(0, 7, container)
        self._legend_table.setHorizontalHeaderLabels(
            ["Tag", "Sheet", "Unit", "Low Range", "High Range", "Color", "Highlight"]
        )
        self._legend_table.verticalHeader().setVisible(False)
        self._legend_table.setAlternatingRowColors(True)
        self._legend_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._legend_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._legend_table.itemChanged.connect(self._handle_legend_table_item_changed)
        header = self._legend_table.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_legend_header_context_menu)

        layout.addWidget(self._legend_table)
        return container

    def _build_settings_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Time Duration Presets", container)
        layout.addWidget(title)

        helper = QLabel(
            "These presets feed the trend time-selection dropdown. Enter values like 15m, 1h, 2d, or 01:30:00.",
            container,
        )
        helper.setWordWrap(True)
        layout.addWidget(helper)

        self._time_preset_list = QListWidget(container)
        self._time_preset_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._time_preset_list, stretch=1)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add", container)
        add_button.clicked.connect(self._add_time_preset)
        button_row.addWidget(add_button)

        edit_button = QPushButton("Edit", container)
        edit_button.clicked.connect(self._edit_selected_time_preset)
        button_row.addWidget(edit_button)

        remove_button = QPushButton("Remove", container)
        remove_button.clicked.connect(self._remove_selected_time_preset)
        button_row.addWidget(remove_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)
        return container

    def _stored_time_presets(self) -> list[str]:
        raw_presets = self._session.settings_state.get("time_duration_presets")
        if isinstance(raw_presets, list):
            return normalize_duration_presets([str(value) for value in raw_presets])
        return list(DEFAULT_DURATION_PRESETS)

    def _apply_time_presets(self, presets: list[str]) -> None:
        normalized_presets = normalize_duration_presets(presets)
        if self._time_preset_list is not None:
            selected_text = ""
            current_item = self._time_preset_list.currentItem()
            if current_item is not None:
                selected_text = current_item.text().strip()
            self._time_preset_list.clear()
            for preset in normalized_presets:
                self._time_preset_list.addItem(QListWidgetItem(preset))
            if selected_text:
                matching_items = self._time_preset_list.findItems(selected_text, Qt.MatchExactly)
                if matching_items:
                    self._time_preset_list.setCurrentItem(matching_items[0])

        if self._trend_plot_widget is not None:
            self._trend_plot_widget.set_time_presets(normalized_presets)

    def _set_time_presets(self, presets: list[str], *, persist: bool) -> None:
        normalized_presets = normalize_duration_presets(presets)
        self._session.settings_state["time_duration_presets"] = list(normalized_presets)
        self._apply_time_presets(normalized_presets)
        if persist:
            self._handle_workspace_changed()

    def _stored_available_units(self) -> list[str]:
        raw_units = self._session.settings_state.get("available_units")
        units: list[str] = []
        if isinstance(raw_units, list):
            units = normalize_unit_list(raw_units)

        tag_units = self._tag_units_state()
        for assigned_unit in tag_units.values():
            normalized_unit = normalize_unit_text(assigned_unit)
            if normalized_unit is not None and normalized_unit.casefold() not in {
                unit.casefold() for unit in units
            }:
                units.append(normalized_unit)
        return units

    def _set_available_units(self, units: list[str], *, persist: bool) -> None:
        self._session.settings_state["available_units"] = normalize_unit_list(units)
        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()

    def _tag_units_state(self) -> dict[str, object]:
        state = self._session.settings_state.get("tag_units")
        if isinstance(state, dict):
            return state
        state = {}
        self._session.settings_state["tag_units"] = state
        return state

    def _tag_custom_names_state(self) -> dict[str, object]:
        state = self._session.settings_state.get("tag_custom_names")
        if isinstance(state, dict):
            return state
        state = {}
        self._session.settings_state["tag_custom_names"] = state
        return state

    def _unit_for_tag(self, tag_name: str) -> str | None:
        value = self._tag_units_state().get(tag_name)
        return normalize_unit_text(value)

    def _custom_name_for_tag(self, tag_name: str) -> str | None:
        value = self._tag_custom_names_state().get(tag_name)
        return _normalize_custom_name_text(value)

    def _set_custom_name_for_tag(
        self,
        tag_name: str,
        custom_name: str,
        *,
        persist: bool,
    ) -> None:
        normalized_tag_name = tag_name.strip()
        normalized_custom_name = _normalize_custom_name_text(custom_name)
        if not normalized_tag_name or normalized_custom_name is None:
            return

        if normalized_custom_name.casefold() == normalized_tag_name.casefold():
            self._clear_custom_name_for_tag(normalized_tag_name, persist=persist)
            return

        self._tag_custom_names_state()[normalized_tag_name] = normalized_custom_name
        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()

    def _clear_custom_name_for_tag(self, tag_name: str, *, persist: bool) -> bool:
        normalized_tag_name = tag_name.strip()
        if not normalized_tag_name:
            return False

        removed = self._tag_custom_names_state().pop(normalized_tag_name, None)
        if removed is None:
            return False

        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()
        return True

    def _assign_unit_to_tags(
        self,
        tag_names: list[str],
        unit: str,
        *,
        persist: bool,
    ) -> None:
        normalized_unit = normalize_unit_text(unit)
        if normalized_unit is None:
            return

        tag_units = self._tag_units_state()
        normalized_tag_names = [
            tag_name.strip()
            for tag_name in tag_names
            if tag_name.strip()
        ]
        for tag_name in normalized_tag_names:
            tag_units[tag_name] = normalized_unit

        available_units = self._stored_available_units()
        if normalized_unit.casefold() not in {value.casefold() for value in available_units}:
            available_units.append(normalized_unit)
            self._session.settings_state["available_units"] = available_units

        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()

    def _clear_unit_from_tags(self, tag_names: list[str], *, persist: bool) -> None:
        tag_units = self._tag_units_state()
        changed = False
        for tag_name in tag_names:
            normalized_tag_name = tag_name.strip()
            if normalized_tag_name and normalized_tag_name in tag_units:
                tag_units.pop(normalized_tag_name, None)
                changed = True
        if not changed:
            return

        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()

    def _rename_available_unit(self, previous_unit: str, new_unit: str, *, persist: bool) -> None:
        old_unit = normalize_unit_text(previous_unit)
        renamed_unit = normalize_unit_text(new_unit)
        if old_unit is None or renamed_unit is None:
            return

        available_units = [
            renamed_unit if unit.casefold() == old_unit.casefold() else unit
            for unit in self._stored_available_units()
        ]
        self._session.settings_state["available_units"] = normalize_unit_list(available_units)

        tag_units = self._tag_units_state()
        for tag_name, assigned_unit in list(tag_units.items()):
            normalized_assigned_unit = normalize_unit_text(assigned_unit)
            if normalized_assigned_unit is not None and normalized_assigned_unit.casefold() == old_unit.casefold():
                tag_units[tag_name] = renamed_unit

        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()

    def _remove_available_unit(self, unit: str, *, persist: bool) -> int:
        normalized_unit = normalize_unit_text(unit)
        if normalized_unit is None:
            return 0

        self._session.settings_state["available_units"] = [
            value
            for value in self._stored_available_units()
            if value.casefold() != normalized_unit.casefold()
        ]

        tag_units = self._tag_units_state()
        removed_assignments = 0
        for tag_name, assigned_unit in list(tag_units.items()):
            normalized_assigned_unit = normalize_unit_text(assigned_unit)
            if normalized_assigned_unit is not None and normalized_assigned_unit.casefold() == normalized_unit.casefold():
                tag_units.pop(tag_name, None)
                removed_assignments += 1

        self._refresh_tag_unit_presentations()
        if persist:
            self._handle_workspace_changed()
        return removed_assignments

    def _add_time_preset(self) -> None:
        value, accepted = QInputDialog.getText(
            self,
            "Add Time Preset",
            "Duration preset (for example 15m, 1h, 2d, or 01:30:00):",
        )
        if not accepted:
            return

        normalized = _normalize_time_preset_input(value)
        if normalized is None:
            self.statusBar().showMessage("Enter a valid duration preset.", 4000)
            return

        presets = self._stored_time_presets()
        presets.append(normalized)
        self._set_time_presets(presets, persist=True)
        self.statusBar().showMessage(f"Added time preset: {normalized}", 3000)

    def _edit_selected_time_preset(self) -> None:
        if self._time_preset_list is None or self._time_preset_list.currentItem() is None:
            self.statusBar().showMessage("Select a time preset to edit.", 3000)
            return

        current_item = self._time_preset_list.currentItem()
        current_text = current_item.text().strip()
        value, accepted = QInputDialog.getText(
            self,
            "Edit Time Preset",
            "Duration preset:",
            text=current_text,
        )
        if not accepted:
            return

        normalized = _normalize_time_preset_input(value)
        if normalized is None:
            self.statusBar().showMessage("Enter a valid duration preset.", 4000)
            return

        presets = self._stored_time_presets()
        try:
            item_index = presets.index(current_text)
        except ValueError:
            item_index = -1
        if item_index >= 0:
            presets[item_index] = normalized
        else:
            presets.append(normalized)
        self._set_time_presets(presets, persist=True)
        self.statusBar().showMessage(f"Updated time preset: {normalized}", 3000)

    def _remove_selected_time_preset(self) -> None:
        if self._time_preset_list is None or self._time_preset_list.currentItem() is None:
            self.statusBar().showMessage("Select a time preset to remove.", 3000)
            return

        selected_text = self._time_preset_list.currentItem().text().strip()
        presets = [preset for preset in self._stored_time_presets() if preset != selected_text]
        self._set_time_presets(presets, persist=True)
        self.statusBar().showMessage(f"Removed time preset: {selected_text}", 3000)

    def _prompt_edit_units(self) -> None:
        dialog = UnitManagerDialog(self._stored_available_units(), parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        renamed_units = dialog.renamed_units()
        removed_units = dialog.removed_units()
        self._session.settings_state["available_units"] = dialog.units()

        for previous_unit, new_unit in renamed_units.items():
            self._rename_available_unit(previous_unit, new_unit, persist=False)
        for unit in removed_units:
            self._remove_available_unit(unit, persist=False)

        self._session.settings_state["available_units"] = normalize_unit_list(dialog.units())
        self._refresh_tag_unit_presentations()
        self._handle_workspace_changed()
        self.statusBar().showMessage("Updated unit library.", 3000)

    def _show_imported_tag_context_menu(self, position) -> None:
        item = self._imported_tags_list.itemAt(position)
        if item is None:
            item = self._imported_tags_list.currentItem()
            if item is None:
                return

        clicked_tag_name = self._imported_tags_list.tag_name_for_item(item)
        if clicked_tag_name is None:
            return

        unit_target_tag_names = (
            self._selected_imported_tag_names()
            if item.isSelected()
            else [clicked_tag_name]
        )
        self._show_tag_context_menu(
            clicked_tag_name=clicked_tag_name,
            unit_target_tag_names=unit_target_tag_names,
            global_pos=self._imported_tags_list.viewport().mapToGlobal(position),
        )

    def _show_hierarchy_tag_context_menu(self, position) -> None:
        item = self._hierarchy_tree.itemAt(position)
        if item is None:
            item = self._hierarchy_tree.currentItem()
            if item is None:
                return
        if item.data(0, ITEM_KIND_ROLE) != TAG_ITEM_KIND:
            return

        clicked_tag_name = self._hierarchy_tree.tag_name(item)
        if clicked_tag_name is None:
            return

        unit_target_tag_names = (
            self._selected_direct_hierarchy_tag_names()
            if item.isSelected()
            else [clicked_tag_name]
        )
        self._show_tag_context_menu(
            clicked_tag_name=clicked_tag_name,
            unit_target_tag_names=unit_target_tag_names,
            global_pos=self._hierarchy_tree.viewport().mapToGlobal(position),
        )

    def _show_tag_context_menu(
        self,
        *,
        clicked_tag_name: str,
        unit_target_tag_names: list[str],
        global_pos,
    ) -> None:
        normalized_tag_name = clicked_tag_name.strip()
        normalized_unit_target_tag_names = _normalize_tag_names(unit_target_tag_names)
        if not normalized_tag_name or not normalized_unit_target_tag_names:
            return

        menu = QMenu(self)
        custom_name = self._custom_name_for_tag(normalized_tag_name)
        if custom_name is None:
            add_custom_name_action = menu.addAction("Add custom name...")
            edit_custom_name_action = None
            remove_custom_name_action = None
        else:
            add_custom_name_action = None
            edit_custom_name_action = menu.addAction("Edit custom name...")
            remove_custom_name_action = menu.addAction("Remove custom name")
        menu.addSeparator()

        assign_unit_menu = menu.addMenu("Assign unit")
        add_unit_action, clear_unit_action, unit_actions = self._populate_assign_unit_menu(
            assign_unit_menu,
            normalized_unit_target_tag_names,
        )

        chosen_action = menu.exec(global_pos)
        if chosen_action is None:
            return
        if chosen_action is add_custom_name_action or chosen_action is edit_custom_name_action:
            self._prompt_custom_name_for_tag(normalized_tag_name)
            return
        if chosen_action is remove_custom_name_action:
            if self._clear_custom_name_for_tag(normalized_tag_name, persist=True):
                self.statusBar().showMessage(
                    f"Removed custom name for {normalized_tag_name}.",
                    3000,
                )
            return
        if chosen_action is add_unit_action:
            self._prompt_add_unit_for_tags(normalized_unit_target_tag_names)
            return
        if chosen_action is clear_unit_action:
            self._clear_unit_from_tags(normalized_unit_target_tag_names, persist=True)
            self.statusBar().showMessage(
                f"Cleared unit for {len(normalized_unit_target_tag_names)} tag(s).",
                3000,
            )
            return
        if chosen_action in unit_actions:
            selected_unit = unit_actions[chosen_action]
            self._assign_unit_to_tags(
                normalized_unit_target_tag_names,
                selected_unit,
                persist=True,
            )
            self.statusBar().showMessage(
                "Assigned "
                f"{display_unit_text(selected_unit) or selected_unit} "
                f"to {len(normalized_unit_target_tag_names)} tag(s).",
                3000,
            )

    def _populate_assign_unit_menu(
        self,
        menu: QMenu,
        tag_names: list[str],
    ) -> tuple[object, object, dict[object, str]]:
        normalized_tag_names = _normalize_tag_names(tag_names)

        available_units = self._stored_available_units()
        add_unit_action = menu.addAction("Add unit...")
        clear_unit_action = menu.addAction("Clear unit")
        if available_units:
            menu.addSeparator()

        current_units = {
            self._unit_for_tag(tag_name)
            for tag_name in normalized_tag_names
            if self._unit_for_tag(tag_name) is not None
        }
        common_unit = next(iter(current_units)) if len(current_units) == 1 else None

        unit_actions: dict[object, str] = {}
        for unit in available_units:
            action = menu.addAction(display_unit_text(unit) or unit)
            action.setCheckable(True)
            action.setChecked(unit == common_unit)
            unit_actions[action] = unit
        return add_unit_action, clear_unit_action, unit_actions

    def _prompt_custom_name_for_tag(self, tag_name: str) -> None:
        current_custom_name = self._custom_name_for_tag(tag_name) or ""
        value, accepted = QInputDialog.getText(
            self,
            "Custom Tag Name",
            f"Custom name for {tag_name}:",
            text=current_custom_name,
        )
        if not accepted:
            return

        custom_name = _normalize_custom_name_text(value)
        if custom_name is None:
            self.statusBar().showMessage("Enter a non-empty custom name.", 4000)
            return

        self._set_custom_name_for_tag(tag_name, custom_name, persist=True)
        self.statusBar().showMessage(
            f"Saved custom name for {tag_name}.",
            3000,
        )

    def _prompt_add_unit_for_tags(self, tag_names: list[str]) -> None:
        value, accepted = QInputDialog.getText(
            self,
            "Add Unit",
            "Unit (for example m^3/hr or C):",
        )
        if not accepted:
            return

        unit = normalize_unit_text(value)
        if unit is None:
            self.statusBar().showMessage("Enter a non-empty unit.", 4000)
            return

        self._assign_unit_to_tags(tag_names, unit, persist=True)
        self.statusBar().showMessage(
            f"Assigned {display_unit_text(unit) or unit} to {len(tag_names)} tag(s).",
            3000,
        )

    def _build_analytics_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._analytics_table = QTableWidget(0, 5, container)
        self._analytics_table.setHorizontalHeaderLabels(
            [
                "Tag",
                "Cursor Value",
                "Window Min",
                "Window Max",
                "Window Avg",
            ]
        )
        self._analytics_table.verticalHeader().setVisible(False)
        self._analytics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._analytics_table.setSelectionMode(QAbstractItemView.SingleSelection)

        layout.addWidget(self._analytics_table)
        return container

    def _prompt_add_category(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add Category", "Category name:")
        if not accepted or not name.strip():
            return

        self._hierarchy_tree.add_category(name.strip())
        self.statusBar().showMessage(f"Added category: {name.strip()}", 3000)

    def _prompt_add_subcategory(self) -> None:
        parent = self._hierarchy_tree.group_target_for_subcategory()
        if parent is None:
            self.statusBar().showMessage(
                "Select a category first to add a sub category.",
                4000,
            )
            return

        name, accepted = QInputDialog.getText(self, "Add Sub Category", "Sub category name:")
        if not accepted or not name.strip():
            return

        self._hierarchy_tree.add_category(name.strip(), parent=parent)
        self.statusBar().showMessage(f"Added sub category: {name.strip()}", 3000)

    def _prompt_open_workbook(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Workbook",
            "",
            "Excel Files (*.xlsx *.xlsb)",
        )
        if not file_path:
            return

        self._load_workbook_tags(file_path, prompt_for_sheets=True)

    def _prompt_select_sheets(self) -> None:
        workbook_path = self._last_workbook_path()
        if workbook_path is None:
            self.statusBar().showMessage("Open a workbook first.", 4000)
            return

        if not workbook_path.exists():
            QMessageBox.warning(
                self,
                "Workbook Not Found",
                f"The last workbook could not be found:\n{workbook_path}",
            )
            return

        self._load_workbook_tags(
            str(workbook_path),
            prompt_for_sheets=True,
            preferred_sheet_names=self._selected_sheet_names(),
        )

    def _load_workbook_tags(
        self,
        file_path: str,
        *,
        prompt_for_sheets: bool,
        preferred_sheet_names: list[str] | None = None,
    ) -> bool:
        try:
            result = self._workbook_inspector.inspect(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Workbook Load Failed", str(exc))
            return False

        data_sheets = [sheet for sheet in result.sheets if sheet.is_data_sheet]
        if not data_sheets:
            QMessageBox.warning(
                self,
                "No Trend Tags Found",
                "No worksheet with a recognizable timestamp column was found.",
            )
            return False

        selected_sheet_names = list(preferred_sheet_names or [sheet.name for sheet in data_sheets])
        if prompt_for_sheets:
            dialog = SheetSelectionDialog(
                result,
                selected_sheet_names=selected_sheet_names,
                parent=self,
            )
            if dialog.exec() != QDialog.Accepted:
                return False
            selected_sheet_names = dialog.selected_sheet_names()

        selected_data_sheet_names = [
            sheet.name for sheet in data_sheets if sheet.name in set(selected_sheet_names)
        ]
        if not selected_data_sheet_names:
            QMessageBox.warning(
                self,
                "No Data Sheets Selected",
                "Select at least one worksheet that contains trend data.",
            )
            return False

        try:
            self._loaded_workbook = self._trend_data_manager.load_workbook(
                file_path,
                selected_data_sheet_names,
                inspection=result,
            )
        except Exception as exc:
            self._clear_loaded_workbook_data()
            QMessageBox.critical(self, "Workbook Load Failed", str(exc))
            return False

        imported_tags = list(self._loaded_workbook.available_tags)
        self._store_last_workbook_location(result.source_path)
        self._session.settings_state["loaded_sheet_names"] = selected_data_sheet_names
        self.set_imported_tags(imported_tags)
        self._sync_workbook_actions()
        self._restore_preview_tag_selection()

        self.statusBar().showMessage(
            f"Loaded {len(imported_tags)} tags from {result.source_path.name} "
            f"({len(selected_data_sheet_names)} sheet(s)).",
            5000,
        )
        return True

    def _prompt_save_session(self) -> None:
        default_path = self._session_store.base_dir / "workspace-session.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            str(default_path),
            "WTE Session (*.json)",
        )
        if not file_path:
            return

        target = Path(file_path)
        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")

        try:
            session = self._capture_session()
            self._session_store.save(session, target)
            self._persist_last_session(show_errors=False)
        except Exception as exc:
            QMessageBox.critical(self, "Save Session Failed", str(exc))
            return

        self.statusBar().showMessage(f"Session saved to {target.name}.", 4000)

    def _prompt_load_session(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            str(self._session_store.base_dir),
            "WTE Session (*.json)",
        )
        if not file_path:
            return

        try:
            session = self._session_store.load(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Load Session Failed", str(exc))
            return

        self._apply_session(session)
        restored = self._restore_live_workbook_data(show_errors=True)
        self._persist_last_session(show_errors=False)
        if restored or not self._session.imported_tags:
            self.statusBar().showMessage(f"Loaded session from {Path(file_path).name}.", 4000)

    def _restore_last_session(self) -> None:
        try:
            session = self._session_store.load_last_session()
        except FileNotFoundError:
            session = WorkspaceSession()
            self._apply_session(session)
            self._persist_last_session(show_errors=False)
            self.statusBar().showMessage(
                "Started with a new empty session. Changes will be restored next launch."
            )
            return
        except Exception as exc:
            session = WorkspaceSession()
            self._apply_session(session)
            self.statusBar().showMessage(
                f"Last session could not be restored: {exc}",
                5000,
            )
            return

        self._apply_session(session)
        restored = self._restore_live_workbook_data(show_errors=False)
        self._persist_last_session(show_errors=False)
        if restored or not self._session.imported_tags:
            self.statusBar().showMessage("Restored last session.", 4000)
        else:
            self.statusBar().showMessage(
                "Restored last session layout, but the workbook could not be reopened automatically.",
                5000,
            )

    def _clear_imported_tags(self) -> None:
        self._clear_loaded_workbook_data()
        self.set_imported_tags([])
        self.statusBar().showMessage("Cleared imported tags.", 3000)

    def _delete_selected_hierarchy_item(self) -> None:
        if self._hierarchy_tree.remove_selected_item():
            self.statusBar().showMessage("Deleted selected hierarchy item.", 3000)
        else:
            self.statusBar().showMessage("Select a hierarchy item to delete.", 3000)

    def _apply_session(self, session: WorkspaceSession) -> None:
        self._suspend_session_updates = True
        try:
            self._session = session
            self._clear_loaded_workbook_data()
            self._hierarchy_tree.clear_hierarchy(emit_change=False)
            for node in session.hierarchy:
                self._populate_tree_from_node(node)

            self.set_imported_tags(session.imported_tags, persist=False)
            self._apply_time_presets(self._stored_time_presets())

            if self._trend_plot_widget is not None:
                self._trend_plot_widget.set_pan_fraction(
                    _coerce_positive_int(
                        session.trend_state.get("pan_step_numerator"),
                        default=1,
                    ),
                    _coerce_positive_int(
                        session.trend_state.get("pan_step_denominator"),
                        default=4,
                    ),
                )
                self._trend_plot_widget.set_time_selection_state(session.trend_state)

            ui_state = session.ui_state
            if self._left_workspace_splitter is not None:
                sizes = ui_state.get("left_splitter_sizes")
                if isinstance(sizes, list) and all(isinstance(value, int) for value in sizes):
                    self._left_workspace_splitter.setSizes(sizes)

            if self._main_workspace_splitter is not None:
                sizes = ui_state.get("main_splitter_sizes")
                if isinstance(sizes, list) and all(isinstance(value, int) for value in sizes):
                    self._main_workspace_splitter.setSizes(sizes)

            if self._bottom_tabs is not None:
                tab_index = ui_state.get("bottom_tab_index")
                if isinstance(tab_index, int) and 0 <= tab_index < self._bottom_tabs.count():
                    self._bottom_tabs.setCurrentIndex(tab_index)
        finally:
            self._suspend_session_updates = False

        self._refresh_tag_unit_presentations()
        self._sync_workbook_actions()
        self._sync_subcategory_button_state()

    def _restore_live_workbook_data(self, *, show_errors: bool) -> bool:
        workbook_path = self._last_workbook_path()
        selected_sheet_names = self._selected_sheet_names()
        if workbook_path is None or not selected_sheet_names or not self._session.imported_tags:
            self._clear_loaded_workbook_data()
            return False

        if not workbook_path.exists():
            self._clear_loaded_workbook_data()
            if show_errors:
                self.statusBar().showMessage(
                    f"The saved workbook could not be found: {workbook_path}",
                    5000,
                )
            return False

        try:
            loaded_workbook = self._trend_data_manager.load_workbook(
                workbook_path,
                selected_sheet_names,
            )
        except Exception as exc:
            self._clear_loaded_workbook_data()
            if show_errors:
                self.statusBar().showMessage(f"Workbook restore failed: {exc}", 5000)
            return False

        self._loaded_workbook = loaded_workbook
        self._store_last_workbook_location(loaded_workbook.source_path)
        live_tags = list(loaded_workbook.available_tags)
        tags_changed = live_tags != self._imported_tags_list.tags()
        self.set_imported_tags(live_tags, persist=False)
        self._restore_preview_tag_selection()
        if tags_changed:
            self._handle_workspace_changed()
        return True

    def _populate_tree_from_node(
        self,
        node: SessionTreeNode,
        parent: QTreeWidgetItem | None = None,
    ) -> None:
        if node.kind == TAG_ITEM_KIND:
            item = self._hierarchy_tree.add_tag(node.name, parent=parent, emit_change=False)
        else:
            item = self._hierarchy_tree.add_category(
                node.name,
                parent=parent,
                emit_change=False,
            )

        for child in node.children:
            self._populate_tree_from_node(child, item)

    def _handle_workspace_changed(self, *_args) -> None:
        if self._suspend_session_updates:
            return

        self._session = self._capture_session()
        self._persist_last_session(show_errors=True)
        self._sync_subcategory_button_state()

    def _capture_session(self) -> WorkspaceSession:
        ui_state: dict[str, object] = {}
        if self._left_workspace_splitter is not None:
            ui_state["left_splitter_sizes"] = self._left_workspace_splitter.sizes()
        if self._main_workspace_splitter is not None:
            ui_state["main_splitter_sizes"] = self._main_workspace_splitter.sizes()
        if self._bottom_tabs is not None:
            ui_state["bottom_tab_index"] = self._bottom_tabs.currentIndex()

        trend_state = dict(self._session.trend_state)
        if self._current_preview_tag_names:
            trend_state["preview_tag_names"] = list(self._current_preview_tag_names)
        else:
            trend_state.pop("preview_tag_names", None)
        trend_state.pop("preview_tag_name", None)
        if self._trend_plot_widget is not None:
            pan_numerator, pan_denominator = self._trend_plot_widget.pan_fraction()
            trend_state["pan_step_numerator"] = pan_numerator
            trend_state["pan_step_denominator"] = pan_denominator
            trend_state.update(self._trend_plot_widget.time_selection_state())

        settings_state = dict(self._session.settings_state)
        settings_state["time_duration_presets"] = self._stored_time_presets()
        return WorkspaceSession(
            version=self._session.version,
            hierarchy=self._snapshot_hierarchy(),
            imported_tags=self._imported_tags_list.tags(),
            trend_state=trend_state,
            legend_state={},
            analytics_state=dict(self._session.analytics_state),
            settings_state=settings_state,
            ui_state=ui_state,
        )

    def _snapshot_hierarchy(self) -> list[SessionTreeNode]:
        nodes: list[SessionTreeNode] = []
        for index in range(self._hierarchy_tree.topLevelItemCount()):
            nodes.append(self._snapshot_tree_item(self._hierarchy_tree.topLevelItem(index)))
        return nodes

    def _snapshot_tree_item(self, item: QTreeWidgetItem) -> SessionTreeNode:
        kind = item.data(0, ITEM_KIND_ROLE)
        if kind not in {GROUP_ITEM_KIND, TAG_ITEM_KIND}:
            kind = GROUP_ITEM_KIND

        if kind == TAG_ITEM_KIND:
            node_name = self._hierarchy_tree.tag_name(item) or item.text(0)
        else:
            node_name = item.text(0)
        children = [
            self._snapshot_tree_item(item.child(index))
            for index in range(item.childCount())
        ]
        return SessionTreeNode(name=node_name, kind=kind, children=children)

    def _persist_last_session(self, *, show_errors: bool) -> None:
        try:
            self._session_store.save_last_session(self._session)
        except Exception as exc:
            if show_errors:
                self.statusBar().showMessage(f"Auto-save failed: {exc}", 5000)

    def _clear_loaded_workbook_data(self) -> None:
        self._trend_data_manager.clear()
        self._loaded_workbook = None
        self._current_plotted_series = []
        self._current_plot_colors_by_tag = {}
        self._current_visible_stats = []
        self._current_cursor_stats = None
        self._current_preview_tag_names = []
        self._update_trend_summary()

    def _update_trend_summary(self) -> None:
        if self._trend_plot_widget is None:
            return

        if self._loaded_workbook is None:
            self._current_plot_colors_by_tag = {}
            self._trend_plot_widget.show_empty(
                "No live trend data loaded.\n"
                "Open a workbook to prepare sheets and tags for plotting."
            )
            self._update_plot_support_panels([])
            return

        self._current_plot_colors_by_tag = {}
        self._trend_plot_widget.show_empty(
            "Select one or more imported tags to preview the loaded trends."
        )
        self._update_plot_support_panels([])

    def _handle_imported_tag_selection_changed(self) -> None:
        selected_tag_names = self._selected_imported_tag_names()
        if not selected_tag_names:
            self._current_plotted_series = []
            self._current_plot_colors_by_tag = {}
            self._current_visible_stats = []
            self._current_cursor_stats = None
            self._current_preview_tag_names = []
            self._update_trend_summary()
            self._handle_workspace_changed()
            return

        self._preview_tags(selected_tag_names, persist_selection=True)

    def _handle_hierarchy_selection_changed(self) -> None:
        self._sync_subcategory_button_state()

        selected_tag_names = self._hierarchy_tree.selected_tag_names()
        if not selected_tag_names:
            return

        self._preview_tags(selected_tag_names, persist_selection=True)

    def _preview_tags(self, tag_names: list[str], *, persist_selection: bool) -> bool:
        if self._loaded_workbook is None or self._trend_plot_widget is None:
            self._current_plotted_series = []
            self._current_plot_colors_by_tag = {}
            self._current_visible_stats = []
            self._current_cursor_stats = None
            self._current_preview_tag_names = []
            self._update_trend_summary()
            return False

        plotted_series: list[TrendPlotSeries] = []
        seen_tag_names: set[str] = set()
        for tag_name in tag_names:
            normalized_tag_name = tag_name.strip()
            if not normalized_tag_name or normalized_tag_name in seen_tag_names:
                continue
            series = self._loaded_workbook.series_for_tag(normalized_tag_name)
            sheet = self._loaded_workbook.sheet_for_tag(normalized_tag_name)
            if series is None or sheet is None:
                continue
            plotted_series.append(TrendPlotSeries(sheet=sheet, series=series))
            seen_tag_names.add(normalized_tag_name)

        if not plotted_series:
            self._current_plotted_series = []
            self._current_plot_colors_by_tag = {}
            self._current_visible_stats = []
            self._current_cursor_stats = None
            self._current_preview_tag_names = []
            self._update_trend_summary()
            return False

        self._current_preview_tag_names = [
            plotted.series.tag_name for plotted in plotted_series
        ]
        self._current_plotted_series = list(plotted_series)
        self._current_plot_colors_by_tag = self._resolved_plot_colors(plotted_series)
        display_ranges_by_tag = {
            plotted.series.tag_name: self._resolved_display_range(plotted)
            for plotted in plotted_series
        }
        display_labels_by_tag = {
            plotted.series.tag_name: self._display_label_for_tag(
                plotted.series.tag_name,
                include_unit=True,
            )
            for plotted in plotted_series
        }
        self._trend_plot_widget.plot_series_group(
            workbook_name=self._loaded_workbook.source_path.name,
            plotted_series=plotted_series,
            display_ranges_by_tag=display_ranges_by_tag,
            display_labels_by_tag=display_labels_by_tag,
            series_colors_by_tag=self._current_plot_colors_by_tag,
        )
        self._trend_plot_widget.set_highlighted_tags(self._active_highlighted_tag_names())
        self._update_plot_support_panels(plotted_series)
        if persist_selection:
            self._handle_workspace_changed()
        return True

    def _pop_out_current_trend_window(self) -> None:
        if (
            self._trend_plot_widget is None
            or self._loaded_workbook is None
            or not self._current_plotted_series
        ):
            self.statusBar().showMessage("Select plotted tags before popping out a trend.", 3000)
            return

        display_ranges_by_tag = {
            plotted.series.tag_name: self._resolved_display_range(plotted)
            for plotted in self._current_plotted_series
        }
        display_labels_by_tag = {
            plotted.series.tag_name: self._display_label_for_tag(
                plotted.series.tag_name,
                include_unit=True,
            )
            for plotted in self._current_plotted_series
        }
        display_units_by_tag = {
            plotted.series.tag_name: display_unit_text(self._unit_for_tag(plotted.series.tag_name)) or "-"
            for plotted in self._current_plotted_series
        }
        detached_window = _DetachedTrendWindow(
            title_text=self._build_detached_trend_window_title(),
            workbook_name=self._loaded_workbook.source_path.name,
            plotted_series=list(self._current_plotted_series),
            display_ranges_by_tag=display_ranges_by_tag,
            display_labels_by_tag=display_labels_by_tag,
            display_units_by_tag=display_units_by_tag,
            series_colors_by_tag=dict(self._current_plot_colors_by_tag),
            highlighted_tag_names=self._active_highlighted_tag_names(),
            time_presets=self._stored_time_presets(),
            time_selection_state=self._trend_plot_widget.time_selection_state(),
            pan_fraction=self._trend_plot_widget.pan_fraction(),
            parent=None,
        )
        detached_window.destroyed.connect(
            lambda *_args, window=detached_window: self._forget_detached_trend_window(window)
        )
        self._detached_trend_windows.append(detached_window)
        detached_window.show()
        self.statusBar().showMessage("Opened detached trend window.", 3000)

    def _build_detached_trend_window_title(self) -> str:
        if self._loaded_workbook is None:
            return "Detached Trend"

        label = (
            self._display_label_for_tag(self._current_preview_tag_names[0], include_unit=True)
            if len(self._current_preview_tag_names) == 1
            else f"{len(self._current_preview_tag_names)} tags"
        )
        return f"Detached Trend - {self._loaded_workbook.source_path.name} - {label}"

    def _forget_detached_trend_window(self, window: _DetachedTrendWindow) -> None:
        self._detached_trend_windows = [
            existing_window
            for existing_window in self._detached_trend_windows
            if existing_window is not window
        ]

    def _restore_preview_tag_selection(self) -> None:
        preview_tag_names = self._saved_preview_tag_names()
        available_tags = self._imported_tags_list.tags()
        target_tag_names = [
            tag_name for tag_name in preview_tag_names if tag_name in available_tags
        ]
        if not target_tag_names and available_tags:
            target_tag_names = [available_tags[0]]

        if not target_tag_names:
            self._current_preview_tag_names = []
            self._update_trend_summary()
            return

        with QSignalBlocker(self._imported_tags_list):
            self._imported_tags_list.clearSelection()
            selection_model = self._imported_tags_list.selectionModel()
            first_selected_item = None
            for tag_name in target_tag_names:
                item = self._imported_tags_list.find_item_by_tag_name(tag_name)
                if item is None:
                    continue
                if first_selected_item is None:
                    first_selected_item = item
                index = self._imported_tags_list.indexFromItem(item)
                selection_model.select(index, QItemSelectionModel.SelectionFlag.Select)

            if first_selected_item is not None:
                current_index = self._imported_tags_list.indexFromItem(first_selected_item)
                selection_model.setCurrentIndex(
                    current_index,
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
                self._imported_tags_list.scrollToItem(first_selected_item)

        self._preview_tags(target_tag_names, persist_selection=False)

    def _saved_preview_tag_names(self) -> list[str]:
        value = self._session.trend_state.get("preview_tag_names")
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

        legacy_value = self._session.trend_state.get("preview_tag_name")
        if isinstance(legacy_value, str) and legacy_value.strip():
            return [legacy_value.strip()]
        return []

    def _stored_highlighted_tag_names(self) -> list[str]:
        value = self._session.trend_state.get("highlighted_tag_names")
        if isinstance(value, list):
            return _normalize_tag_names([str(item) for item in value])
        return []

    def _stored_tag_colors_state(self) -> dict[str, object]:
        colors = self._session.trend_state.get("tag_colors")
        if isinstance(colors, dict):
            return colors
        colors = {}
        self._session.trend_state["tag_colors"] = colors
        return colors

    def _stored_color_for_tag(self, tag_name: str) -> str | None:
        value = self._stored_tag_colors_state().get(tag_name)
        return _normalize_plot_color(value)

    def _resolved_plot_colors(self, plotted_series: list[TrendPlotSeries]) -> dict[str, str]:
        resolved_colors: dict[str, str] = {}
        used_colors: set[str] = set()

        for plotted in plotted_series:
            stored_color = self._stored_color_for_tag(plotted.series.tag_name)
            if stored_color is None or stored_color in used_colors:
                continue
            resolved_colors[plotted.series.tag_name] = stored_color
            used_colors.add(stored_color)

        for index, plotted in enumerate(plotted_series):
            tag_name = plotted.series.tag_name
            if tag_name in resolved_colors:
                continue

            available_color = next(
                (color for color in PLOT_COLORS if color not in used_colors),
                None,
            )
            if available_color is None:
                available_color = PLOT_COLORS[index % len(PLOT_COLORS)]
            resolved_colors[tag_name] = available_color
            used_colors.add(available_color)

        return resolved_colors

    def _set_plot_color_for_tag(self, tag_name: str, color: str, *, persist: bool) -> None:
        normalized_tag_name = tag_name.strip()
        normalized_color = _normalize_plot_color(color)
        if not normalized_tag_name or normalized_color is None:
            return

        current_colors = self._resolved_plot_colors(self._current_plotted_series)
        current_color = current_colors.get(normalized_tag_name)
        if current_color is None or current_color == normalized_color:
            return

        color_state = self._stored_tag_colors_state()
        color_state[normalized_tag_name] = normalized_color

        for other_tag_name, other_color in current_colors.items():
            if other_tag_name == normalized_tag_name or other_color != normalized_color:
                continue
            color_state[other_tag_name] = current_color
            break

        if self._current_preview_tag_names:
            self._preview_tags(self._current_preview_tag_names, persist_selection=False)
        if persist:
            self._handle_workspace_changed()

    def _active_highlighted_tag_names(self) -> list[str]:
        plotted_tag_names = {
            plotted.series.tag_name for plotted in self._current_plotted_series
        }
        return [
            tag_name
            for tag_name in self._stored_highlighted_tag_names()
            if tag_name in plotted_tag_names
        ]

    def _set_highlighted_tag_names(self, tag_names: list[str], *, persist: bool) -> None:
        normalized_tag_names = _normalize_tag_names(tag_names)
        if normalized_tag_names:
            self._session.trend_state["highlighted_tag_names"] = list(normalized_tag_names)
        else:
            self._session.trend_state.pop("highlighted_tag_names", None)

        if self._trend_plot_widget is not None:
            self._trend_plot_widget.set_highlighted_tags(self._active_highlighted_tag_names())
        self._update_plot_support_panels(self._current_plotted_series)
        if persist:
            self._handle_workspace_changed()

    def _clear_all_legend_highlights(self, *, persist: bool) -> None:
        self._set_highlighted_tag_names([], persist=persist)

    def _checked_highlight_tag_names_from_legend(self) -> list[str]:
        if self._legend_table is None:
            return []

        highlighted_tag_names: list[str] = []
        for row_index in range(self._legend_table.rowCount()):
            highlight_item = self._legend_table.item(row_index, LEGEND_HIGHLIGHT_COLUMN)
            if highlight_item is None or highlight_item.checkState() != Qt.Checked:
                continue
            tag_name = str(highlight_item.data(Qt.UserRole) or "").strip()
            if tag_name:
                highlighted_tag_names.append(tag_name)
        return highlighted_tag_names

    def _legacy_display_ranges_state(self) -> dict[str, object]:
        ranges = self._session.trend_state.get("display_ranges")
        if isinstance(ranges, dict):
            return ranges
        ranges = {}
        self._session.trend_state["display_ranges"] = ranges
        return ranges

    def _selection_display_ranges_state(self) -> dict[str, object]:
        ranges = self._session.trend_state.get("display_ranges_by_selection")
        if isinstance(ranges, dict):
            return ranges
        ranges = {}
        self._session.trend_state["display_ranges_by_selection"] = ranges
        return ranges

    def _display_range_selection_key(self, tag_names: list[str] | None = None) -> str | None:
        normalized_tag_names = _normalize_tag_names(tag_names or self._current_preview_tag_names)
        if not normalized_tag_names:
            return None
        sorted_tag_names = sorted(normalized_tag_names, key=str.casefold)
        return json.dumps(sorted_tag_names, ensure_ascii=True, separators=(",", ":"))

    def _resolved_display_range(self, plotted: TrendPlotSeries) -> tuple[float, float]:
        stored = self._stored_display_range(plotted.series.tag_name)
        if stored is not None:
            return stored

        minimum_value = plotted.series.minimum_value()
        maximum_value = plotted.series.maximum_value()
        return _normalize_display_range(minimum_value, maximum_value)

    def _resolved_display_range_for_tag_name(self, tag_name: str) -> tuple[float, float]:
        for plotted in self._current_plotted_series:
            if plotted.series.tag_name == tag_name:
                return self._resolved_display_range(plotted)
        return 0.0, 1.0

    def _stored_display_range(self, tag_name: str) -> tuple[float, float] | None:
        selection_key = self._display_range_selection_key()
        if selection_key is not None:
            selection_ranges = self._selection_display_ranges_state().get(selection_key)
            if isinstance(selection_ranges, dict):
                stored = _coerce_display_range_entry(selection_ranges.get(tag_name))
                if stored is not None:
                    return stored

        return _coerce_display_range_entry(self._legacy_display_ranges_state().get(tag_name))

    def _set_display_range(self, tag_name: str, low_range: float, high_range: float) -> None:
        display_range_entry = {
            "low": float(low_range),
            "high": float(high_range),
        }
        self._legacy_display_ranges_state()[tag_name] = dict(display_range_entry)

        selection_key = self._display_range_selection_key()
        if selection_key is None:
            return

        selection_ranges = self._selection_display_ranges_state().get(selection_key)
        if not isinstance(selection_ranges, dict):
            selection_ranges = {}
            self._selection_display_ranges_state()[selection_key] = selection_ranges
        selection_ranges[tag_name] = dict(display_range_entry)

    def _selected_imported_tag_names(self) -> list[str]:
        selected: list[str] = []
        for index in range(self._imported_tags_list.count()):
            item = self._imported_tags_list.item(index)
            tag_name = self._imported_tags_list.tag_name_for_item(item)
            if item is not None and item.isSelected() and tag_name is not None:
                selected.append(tag_name)
        return selected

    def _selected_direct_hierarchy_tag_names(self) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for item in self._hierarchy_tree.selectedItems():
            if item.data(0, ITEM_KIND_ROLE) != TAG_ITEM_KIND:
                continue
            tag_name = self._hierarchy_tree.tag_name(item)
            if tag_name and tag_name not in seen:
                selected.append(tag_name)
                seen.add(tag_name)
        return selected

    def _refresh_tag_unit_presentations(self) -> None:
        self._refresh_imported_tag_unit_tooltips()
        self._refresh_hierarchy_tag_unit_tooltips()
        self._update_plot_support_panels(self._current_plotted_series)

    def _refresh_imported_tag_unit_tooltips(self) -> None:
        for index in range(self._imported_tags_list.count()):
            item = self._imported_tags_list.item(index)
            if item is None:
                continue
            tag_name = self._imported_tags_list.tag_name_for_item(item)
            if tag_name is None:
                continue
            item.setText(self._imported_tag_display_text(tag_name))
            item.setToolTip(self._tag_tooltip_text(tag_name))

    def _refresh_hierarchy_tag_unit_tooltips(self) -> None:
        iterator = QTreeWidgetItemIterator(self._hierarchy_tree)
        while iterator.value() is not None:
            item = iterator.value()
            if item.data(0, ITEM_KIND_ROLE) == TAG_ITEM_KIND:
                tag_name = self._hierarchy_tree.tag_name(item)
                if tag_name is not None:
                    item.setText(0, self._hierarchy_tag_display_text(tag_name))
                    item.setToolTip(0, self._tag_tooltip_text(tag_name))
            iterator += 1

    def _tag_tooltip_text(self, tag_name: str) -> str:
        normalized_tag_name = tag_name.strip()
        if not normalized_tag_name:
            return ""

        lines = [f"Original: {normalized_tag_name}"]
        custom_name = self._custom_name_for_tag(normalized_tag_name)
        if custom_name is not None:
            lines.insert(0, f"Custom: {custom_name}")
        unit = self._unit_for_tag(normalized_tag_name)
        if unit is not None:
            lines.append(f"Unit: {display_unit_text(unit) or unit}")
        return "\n".join(lines)

    def _imported_tag_display_text(self, tag_name: str) -> str:
        custom_name = self._custom_name_for_tag(tag_name)
        unit = self._unit_for_tag(tag_name)
        if custom_name is None and unit is None:
            return tag_name

        parts: list[str] = []
        if custom_name is not None:
            parts.append(custom_name)
            parts.append(tag_name)
        else:
            parts.append(tag_name)
        if unit is not None:
            parts.append(display_unit_text(unit) or unit)
        return " | ".join(parts)

    def _hierarchy_tag_display_text(self, tag_name: str) -> str:
        return self._display_label_for_tag(tag_name, include_unit=True)

    def _display_name_for_tag(self, tag_name: str) -> str:
        return self._custom_name_for_tag(tag_name) or tag_name

    def _display_label_for_tag(self, tag_name: str, *, include_unit: bool = False) -> str:
        label = self._display_name_for_tag(tag_name)
        if not include_unit:
            return label
        unit = self._unit_for_tag(tag_name)
        if unit is None:
            return label
        return f"{label} {display_unit_text(unit) or unit}"

    def _update_plot_support_panels(self, plotted_series: list[TrendPlotSeries]) -> None:
        self._update_legend_table(plotted_series)
        self._update_analytics_table()
        self._sync_trend_window_actions()

    def _handle_plot_visible_stats_changed(self, visible_stats: object) -> None:
        if isinstance(visible_stats, list):
            self._current_visible_stats = [
                stats for stats in visible_stats if isinstance(stats, TrendVisibleSeriesStats)
            ]
        else:
            self._current_visible_stats = []
        self._update_analytics_table()

    def _handle_plot_cursor_stats_changed(self, cursor_stats: object) -> None:
        if isinstance(cursor_stats, TrendCursorStats):
            self._current_cursor_stats = cursor_stats
        else:
            self._current_cursor_stats = None
        self._update_analytics_table()

    def _update_legend_table(self, plotted_series: list[TrendPlotSeries]) -> None:
        if self._legend_table is None:
            return

        active_highlighted_tags = set(self._active_highlighted_tag_names())
        self._suspend_legend_table_updates = True
        try:
            self._legend_table.setRowCount(0)
            if not plotted_series:
                self._legend_table.setRowCount(1)
                placeholder = QTableWidgetItem("No plotted tags.")
                placeholder.setFlags(Qt.NoItemFlags)
                self._legend_table.setItem(0, LEGEND_TAG_COLUMN, placeholder)
                return

            for row_index, plotted in enumerate(plotted_series):
                tag_name = plotted.series.tag_name
                color = QColor(
                    self._current_plot_colors_by_tag.get(
                        tag_name,
                        PLOT_COLORS[row_index % len(PLOT_COLORS)],
                    )
                )
                low_range, high_range = self._resolved_display_range(plotted)
                tooltip = self._tag_tooltip_text(tag_name)

                highlight_item = QTableWidgetItem("")
                highlight_item.setData(Qt.UserRole, tag_name)
                highlight_item.setFlags(
                    (highlight_item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable
                )
                highlight_item.setCheckState(
                    Qt.Checked if tag_name in active_highlighted_tags else Qt.Unchecked
                )
                highlight_item.setToolTip("Check to highlight this tag and dim the others.")
                highlight_item.setTextAlignment(Qt.AlignCenter)

                tag_item = QTableWidgetItem(
                    self._display_label_for_tag(
                        tag_name,
                        include_unit=True,
                    )
                )
                tag_item.setData(Qt.UserRole, tag_name)
                tag_item.setForeground(color)
                tag_item.setToolTip(tooltip)
                tag_item.setFlags(tag_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.insertRow(row_index)
                self._legend_table.setItem(row_index, LEGEND_TAG_COLUMN, tag_item)

                sheet_item = QTableWidgetItem(plotted.sheet.name)
                sheet_item.setFlags(sheet_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, LEGEND_SHEET_COLUMN, sheet_item)

                unit_item = QTableWidgetItem(
                    display_unit_text(self._unit_for_tag(tag_name)) or "-"
                )
                unit_item.setToolTip(tooltip)
                unit_item.setFlags(unit_item.flags() & ~Qt.ItemIsEditable)
                self._legend_table.setItem(row_index, LEGEND_UNIT_COLUMN, unit_item)

                low_item = QTableWidgetItem(_format_range_value(low_range))
                low_item.setData(Qt.UserRole, tag_name)
                self._legend_table.setItem(row_index, LEGEND_LOW_RANGE_COLUMN, low_item)

                high_item = QTableWidgetItem(_format_range_value(high_range))
                high_item.setData(Qt.UserRole, tag_name)
                self._legend_table.setItem(row_index, LEGEND_HIGH_RANGE_COLUMN, high_item)

                self._legend_table.setCellWidget(
                    row_index,
                    LEGEND_COLOR_COLUMN,
                    self._build_legend_color_combo(tag_name, color.name().upper()),
                )
                self._legend_table.setItem(row_index, LEGEND_HIGHLIGHT_COLUMN, highlight_item)
        finally:
            self._suspend_legend_table_updates = False

        self._legend_table.resizeColumnsToContents()

    def _build_legend_color_combo(self, tag_name: str, current_color: str) -> QComboBox:
        combo = QComboBox(self._legend_table)
        combo.setToolTip("Choose the plot color for this tag.")
        for index, color in enumerate(PLOT_COLORS, start=1):
            combo.addItem(_build_color_icon(color), f"Color {index}", color)

        current_index = combo.findData(current_color)
        combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        combo.currentIndexChanged.connect(
            lambda index, *, combo=combo, tag_name=tag_name: self._handle_legend_color_changed(
                tag_name,
                combo.itemData(index),
            )
        )
        return combo

    def _handle_legend_color_changed(self, tag_name: str, color: object) -> None:
        normalized_color = _normalize_plot_color(color)
        if normalized_color is None:
            return
        self._set_plot_color_for_tag(tag_name, normalized_color, persist=True)

    def _handle_legend_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_legend_table_updates:
            return
        if self._legend_table is None:
            return

        if item.column() == LEGEND_HIGHLIGHT_COLUMN:
            self._set_highlighted_tag_names(
                self._checked_highlight_tag_names_from_legend(),
                persist=True,
            )
            return
        if item.column() not in {LEGEND_LOW_RANGE_COLUMN, LEGEND_HIGH_RANGE_COLUMN}:
            return

        tag_item = self._legend_table.item(item.row(), LEGEND_TAG_COLUMN)
        low_item = self._legend_table.item(item.row(), LEGEND_LOW_RANGE_COLUMN)
        high_item = self._legend_table.item(item.row(), LEGEND_HIGH_RANGE_COLUMN)
        if tag_item is None or low_item is None or high_item is None:
            return

        tag_name = str(tag_item.data(Qt.UserRole) or tag_item.text()).strip()
        fallback_low, fallback_high = self._resolved_display_range_for_tag_name(tag_name)

        low_range = _coerce_float(low_item.text())
        high_range = _coerce_float(high_item.text())
        if low_range is None or high_range is None or low_range >= high_range:
            self._restore_legend_range_row(
                row_index=item.row(),
                low_range=fallback_low,
                high_range=fallback_high,
            )
            self.statusBar().showMessage(
                (
                    "Display range for "
                    f"{self._display_label_for_tag(tag_name, include_unit=True)} "
                    "must be numeric with Low < High."
                ),
                5000,
            )
            return

        self._set_display_range(tag_name, low_range, high_range)
        self._restore_legend_range_row(
            row_index=item.row(),
            low_range=low_range,
            high_range=high_range,
        )
        self._refresh_current_plot_ranges()
        self._handle_workspace_changed()

    def _restore_legend_range_row(
        self,
        *,
        row_index: int,
        low_range: float,
        high_range: float,
    ) -> None:
        if self._legend_table is None:
            return

        low_item = self._legend_table.item(row_index, LEGEND_LOW_RANGE_COLUMN)
        high_item = self._legend_table.item(row_index, LEGEND_HIGH_RANGE_COLUMN)
        if low_item is None or high_item is None:
            return

        self._suspend_legend_table_updates = True
        try:
            low_item.setText(_format_range_value(low_range))
            high_item.setText(_format_range_value(high_range))
        finally:
            self._suspend_legend_table_updates = False

    def _refresh_current_plot_ranges(self) -> None:
        if not self._current_preview_tag_names:
            return
        self._preview_tags(self._current_preview_tag_names, persist_selection=False)

    def _show_legend_header_context_menu(self, position) -> None:
        if self._legend_table is None:
            return

        header = self._legend_table.horizontalHeader()
        if header.logicalIndexAt(position) != LEGEND_HIGHLIGHT_COLUMN:
            return

        menu = QMenu(header)
        clear_action = menu.addAction("Clear all")
        clear_action.setEnabled(bool(self._active_highlighted_tag_names()))
        selected_action = menu.exec(header.mapToGlobal(position))
        if selected_action is clear_action:
            self._clear_all_legend_highlights(persist=True)

    def _update_analytics_table(self) -> None:
        if self._analytics_table is None:
            return

        cursor_stats_by_tag: dict[str, TrendCursorSeriesStats] = {}
        if self._current_cursor_stats is not None:
            cursor_stats_by_tag = {
                stats.tag_name: stats
                for stats in self._current_cursor_stats.series_stats
            }

        self._analytics_table.setRowCount(0)
        for row_index, stats in enumerate(self._current_visible_stats):
            self._analytics_table.insertRow(row_index)
            cursor_stats = cursor_stats_by_tag.get(stats.tag_name)
            tag_item = QTableWidgetItem(
                self._display_label_for_tag(stats.tag_name, include_unit=True)
            )
            tag_item.setForeground(QColor(stats.color))
            tag_item.setToolTip(self._tag_tooltip_text(stats.tag_name))
            self._analytics_table.setItem(row_index, 0, tag_item)
            self._analytics_table.setItem(
                row_index,
                1,
                _build_cursor_value_item(cursor_stats),
            )
            self._analytics_table.setItem(
                row_index,
                2,
                _build_numeric_item(stats.minimum_value),
            )
            self._analytics_table.setItem(row_index, 3, _build_numeric_item(stats.maximum_value))
            self._analytics_table.setItem(row_index, 4, _build_numeric_item(stats.average_value))

        self._analytics_table.resizeColumnsToContents()

    def _last_workbook_path(self) -> Path | None:
        value = self._session.settings_state.get("last_workbook_path")
        stored_path: Path | None = None
        if isinstance(value, str) and value.strip():
            stored_path = Path(value)
            if stored_path.exists():
                return stored_path

        relative_value = self._session.settings_state.get("last_workbook_relative_path")
        if isinstance(relative_value, str) and relative_value.strip():
            relative_path = Path(relative_value)
            for base_dir in _session_workbook_search_roots():
                candidate = base_dir / relative_path
                if candidate.exists():
                    return candidate

        workbook_name = self._session.settings_state.get("last_workbook_name")
        if isinstance(workbook_name, str) and workbook_name.strip():
            for base_dir in _session_workbook_search_roots():
                candidate = base_dir / workbook_name.strip()
                if candidate.exists():
                    return candidate

        if stored_path is not None:
            return stored_path

        if isinstance(relative_value, str) and relative_value.strip():
            search_roots = _session_workbook_search_roots()
            if search_roots:
                return search_roots[0] / Path(relative_value)
        return None

    def _store_last_workbook_location(self, source_path: Path) -> None:
        resolved_source_path = source_path.resolve()
        self._session.settings_state["last_workbook_path"] = str(resolved_source_path)
        self._session.settings_state["last_workbook_name"] = resolved_source_path.name
        relative_path = _session_relative_workbook_path(resolved_source_path)
        if relative_path is None:
            self._session.settings_state.pop("last_workbook_relative_path", None)
        else:
            self._session.settings_state["last_workbook_relative_path"] = relative_path.as_posix()

    def _selected_sheet_names(self) -> list[str]:
        value = self._session.settings_state.get("loaded_sheet_names", [])
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []

    def _sync_workbook_actions(self) -> None:
        has_workbook = self._last_workbook_path() is not None
        self._select_sheets_action.setEnabled(has_workbook)
        if self._select_sheets_button is not None:
            self._select_sheets_button.setEnabled(has_workbook)

    def _sync_trend_window_actions(self) -> None:
        self._pop_out_trend_action.setEnabled(bool(self._current_plotted_series))

    def _sync_subcategory_button_state(self) -> None:
        if self._add_subcategory_button is None:
            return
        self._add_subcategory_button.setEnabled(
            self._hierarchy_tree.group_target_for_subcategory() is not None
        )
        if self._delete_selected_button is not None:
            self._delete_selected_button.setEnabled(self._hierarchy_tree.currentItem() is not None)


def _format_numeric(value: float | None) -> str:
    if value is None:
        return "-"
    if abs(value) >= 100:
        return f"{value:,.2f}"
    if abs(value) >= 1:
        return f"{value:,.3f}"
    return f"{value:,.4f}"


def _coerce_positive_int(value: object, *, default: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return coerced if coerced > 0 else default


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_display_range_entry(entry: object) -> tuple[float, float] | None:
    if not isinstance(entry, dict):
        return None

    low_range = _coerce_float(entry.get("low"))
    high_range = _coerce_float(entry.get("high"))
    if low_range is None or high_range is None or low_range >= high_range:
        return None
    return low_range, high_range


def _normalize_display_range(
    minimum_value: float | None,
    maximum_value: float | None,
) -> tuple[float, float]:
    if minimum_value is None or maximum_value is None:
        return 0.0, 1.0
    if minimum_value == maximum_value:
        padding = abs(minimum_value) * 0.05 or 1.0
        return minimum_value - padding, maximum_value + padding
    return float(minimum_value), float(maximum_value)


def _normalize_time_preset_input(value: str) -> str | None:
    duration_seconds = parse_duration_text(value)
    if duration_seconds is None:
        return None
    normalized_values = normalize_duration_presets([value])
    return normalized_values[0] if normalized_values else None


def _normalize_tag_names(tag_names: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag_name in tag_names:
        value = str(tag_name).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_custom_name_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_plot_color(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    for color in PLOT_COLORS:
        if color.casefold() == text.casefold():
            return color
    return None


def _build_color_icon(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _format_range_value(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:,.2f}"
    if abs(value) >= 1:
        return f"{value:,.3f}"
    return f"{value:,.4f}"


def _build_numeric_item(
    value: float | None,
    *,
    timestamp: float | None = None,
    timestamp_label: str = "Sample",
    tooltip: str | None = None,
) -> QTableWidgetItem:
    item = QTableWidgetItem(_format_numeric(value))
    if tooltip is not None:
        item.setToolTip(tooltip)
    elif timestamp is not None:
        item.setToolTip(f"{timestamp_label}: {_format_timestamp(timestamp)}")
    return item


def _build_cursor_value_item(cursor_stats: TrendCursorSeriesStats | None) -> QTableWidgetItem:
    value, timestamp, timestamp_label, tooltip = _resolved_cursor_display_value(cursor_stats)
    return _build_numeric_item(
        value,
        timestamp=timestamp,
        timestamp_label=timestamp_label,
        tooltip=tooltip,
    )


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _build_interpolation_tooltip(cursor_stats: TrendCursorSeriesStats | None) -> str | None:
    if cursor_stats is None:
        return None

    if cursor_stats.interpolation_mode == "exact":
        timestamp = cursor_stats.interpolation_start_timestamp
        if timestamp is None:
            return "Interpolation: exact sample"
        return f"Interpolation: exact sample at {_format_timestamp(timestamp)}"

    if cursor_stats.interpolation_mode == "linear":
        start = cursor_stats.interpolation_start_timestamp
        end = cursor_stats.interpolation_end_timestamp
        if start is None or end is None:
            return "Interpolation: linear"
        return (
            "Interpolation: linear between "
            f"{_format_timestamp(start)} and {_format_timestamp(end)}"
        )

    if cursor_stats.interpolation_mode == "nearest":
        timestamp = cursor_stats.interpolation_start_timestamp
        if timestamp is None:
            return "Interpolation: nearest-sample fallback"
        return f"Interpolation: nearest-sample fallback at {_format_timestamp(timestamp)}"

    return None


def _resolved_cursor_display_value(
    cursor_stats: TrendCursorSeriesStats | None,
) -> tuple[float | None, float | None, str, str | None]:
    if cursor_stats is None:
        return None, None, "Sample", None

    if cursor_stats.interpolated_value is not None:
        return (
            cursor_stats.interpolated_value,
            None,
            "Sample",
            _build_interpolation_tooltip(cursor_stats),
        )

    if cursor_stats.cursor_value is not None:
        return cursor_stats.cursor_value, cursor_stats.sample_timestamp, "Nearest sample", None

    if cursor_stats.previous_value is not None:
        return cursor_stats.previous_value, cursor_stats.previous_timestamp, "Previous sample", None

    if cursor_stats.next_value is not None:
        return cursor_stats.next_value, cursor_stats.next_timestamp, "Next sample", None

    return None, None, "Sample", None


def _session_workbook_search_roots() -> tuple[Path, ...]:
    search_roots: list[Path] = []
    for candidate in (Path.cwd(), Path(__file__).resolve().parents[3]):
        resolved_candidate = candidate.resolve()
        if resolved_candidate not in search_roots:
            search_roots.append(resolved_candidate)
    return tuple(search_roots)


def _session_relative_workbook_path(source_path: Path) -> Path | None:
    resolved_source_path = source_path.resolve()
    for search_root in _session_workbook_search_roots():
        try:
            return resolved_source_path.relative_to(search_root)
        except ValueError:
            continue
    return None
