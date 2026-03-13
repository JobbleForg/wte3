from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..data_manager import LoadedTrendWorkbook, TrendDataManager
from ..session import SessionStore, SessionTreeNode, WorkspaceSession
from ..workbook import WorkbookInspector
from .dialogs.sheet_selection_dialog import SheetSelectionDialog
from .widgets.hierarchy_tree import (
    GROUP_ITEM_KIND,
    ITEM_KIND_ROLE,
    TAG_ITEM_KIND,
    SearchableHierarchyTree,
)
from .widgets.imported_tag_list import SearchableImportedTagList
from .widgets.trend_plot_widget import (
    PLOT_COLORS,
    TrendPlotSeries,
    TrendPlotWidget,
    TrendVisibleSeriesStats,
)


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

        self._imported_tags_list = SearchableImportedTagList(self)
        self._imported_tags_list.tagsChanged.connect(self._handle_workspace_changed)
        self._imported_tags_list.itemSelectionChanged.connect(
            self._handle_imported_tag_selection_changed
        )

        self._imported_count_label: QLabel | None = None
        self._add_subcategory_button: QPushButton | None = None
        self._delete_selected_button: QPushButton | None = None
        self._select_sheets_button: QPushButton | None = None
        self._left_workspace_splitter: QSplitter | None = None
        self._main_workspace_splitter: QSplitter | None = None
        self._bottom_tabs: QTabWidget | None = None
        self._trend_plot_widget: TrendPlotWidget | None = None
        self._legend_list: QListWidget | None = None
        self._analytics_table: QTableWidget | None = None
        self._current_plotted_series: list[TrendPlotSeries] = []
        self._current_visible_stats: list[TrendVisibleSeriesStats] = []
        self._current_preview_tag_names: list[str] = []

        self._build_toolbar()
        self.addDockWidget(Qt.LeftDockWidgetArea, self._build_left_workspace_dock())
        self.setCentralWidget(self._build_main_workspace())

        if restore_last_session:
            self._restore_last_session()
        else:
            self._apply_session(WorkspaceSession())
            self._persist_last_session(show_errors=False)

        self._sync_workbook_actions()
        self._sync_subcategory_button_state()
        self._update_trend_summary()

    def set_imported_tags(self, tags: list[str], *, persist: bool = True) -> None:
        self._imported_tags_list.set_tags(tags, emit_change=False)
        if self._imported_count_label is not None:
            self._imported_count_label.setText(f"{len(tags)} tags loaded")
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
        self._trend_plot_widget.panFractionChanged.connect(self._handle_workspace_changed)
        self._trend_plot_widget.legendStateChanged.connect(self._handle_workspace_changed)

        layout.addWidget(title)
        layout.addWidget(self._trend_plot_widget, stretch=1)
        return viewport

    def _build_bottom_workspace(self) -> QWidget:
        self._bottom_tabs = QTabWidget(self)
        self._bottom_tabs.addTab(self._build_legend_tab(), "Legend")
        self._bottom_tabs.addTab(self._build_settings_tab(), "Settings")
        self._bottom_tabs.addTab(self._build_analytics_tab(), "Analytics")
        self._bottom_tabs.currentChanged.connect(self._handle_workspace_changed)
        return self._bottom_tabs

    def _build_legend_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._legend_list = QListWidget(container)
        self._legend_list.setAlternatingRowColors(True)
        self._legend_list.setSelectionMode(QAbstractItemView.SingleSelection)

        layout.addWidget(self._legend_list)
        return container

    def _build_settings_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addStretch()
        return container

    def _build_analytics_tab(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        self._analytics_table = QTableWidget(0, 5, container)
        self._analytics_table.setHorizontalHeaderLabels(
            ["Tag", "Visible Last", "Window Min", "Window Max", "Window Avg"]
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
        self._session.settings_state["last_workbook_path"] = str(result.source_path)
        self._session.settings_state["last_workbook_name"] = result.source_path.name
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
        self._restore_live_workbook_data(show_errors=False)
        self.statusBar().showMessage("Restored last session.", 4000)

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
                self._trend_plot_widget.apply_legend_state(session.legend_state)

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
            legend_state = self._trend_plot_widget.legend_state()
        else:
            legend_state = dict(self._session.legend_state)

        return WorkspaceSession(
            version=self._session.version,
            hierarchy=self._snapshot_hierarchy(),
            imported_tags=self._imported_tags_list.tags(),
            trend_state=trend_state,
            legend_state=legend_state,
            analytics_state=dict(self._session.analytics_state),
            settings_state=dict(self._session.settings_state),
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

        children = [
            self._snapshot_tree_item(item.child(index))
            for index in range(item.childCount())
        ]
        return SessionTreeNode(name=item.text(0), kind=kind, children=children)

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
        self._current_visible_stats = []
        self._current_preview_tag_names = []
        self._update_trend_summary()

    def _update_trend_summary(self) -> None:
        if self._trend_plot_widget is None:
            return

        if self._loaded_workbook is None:
            self._trend_plot_widget.show_empty(
                "No live trend data loaded.\n"
                "Open a workbook to prepare sheets and tags for plotting."
            )
            self._update_plot_support_panels([])
            return

        sheet_names = ", ".join(self._loaded_workbook.selected_sheet_names)
        self._trend_plot_widget.show_empty(
            f"{self._loaded_workbook.source_path.name}\n"
            f"Sheets: {sheet_names}\n"
            f"Rows: {self._loaded_workbook.total_row_count:,} | "
            f"Tags: {self._loaded_workbook.tag_count:,}\n"
            "Select one or more imported tags to preview the loaded trends."
        )
        self._update_plot_support_panels([])

    def _handle_imported_tag_selection_changed(self) -> None:
        selected_tag_names = self._selected_imported_tag_names()
        if not selected_tag_names:
            self._current_plotted_series = []
            self._current_visible_stats = []
            self._current_preview_tag_names = []
            self._update_trend_summary()
            self._handle_workspace_changed()
            return

        self._preview_tags(selected_tag_names, persist_selection=True)

    def _handle_hierarchy_selection_changed(self) -> None:
        self._sync_subcategory_button_state()

        current_item = self._hierarchy_tree.currentItem()
        if current_item is None:
            return
        if current_item.data(0, ITEM_KIND_ROLE) != TAG_ITEM_KIND:
            return

        self._preview_tags([current_item.text(0)], persist_selection=True)

    def _preview_tags(self, tag_names: list[str], *, persist_selection: bool) -> bool:
        if self._loaded_workbook is None or self._trend_plot_widget is None:
            self._current_plotted_series = []
            self._current_visible_stats = []
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
            self._current_visible_stats = []
            self._current_preview_tag_names = []
            self._update_trend_summary()
            return False

        self._current_preview_tag_names = [
            plotted.series.tag_name for plotted in plotted_series
        ]
        self._current_plotted_series = list(plotted_series)
        self._trend_plot_widget.plot_series_group(
            workbook_name=self._loaded_workbook.source_path.name,
            plotted_series=plotted_series,
        )
        self._update_plot_support_panels(plotted_series)
        if persist_selection:
            self._handle_workspace_changed()
        return True

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
                matching_items = self._imported_tags_list.findItems(tag_name, Qt.MatchExactly)
                if not matching_items:
                    continue
                item = matching_items[0]
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

    def _selected_imported_tag_names(self) -> list[str]:
        selected: list[str] = []
        for index in range(self._imported_tags_list.count()):
            item = self._imported_tags_list.item(index)
            if item is not None and item.isSelected():
                selected.append(item.text())
        return selected

    def _update_plot_support_panels(self, plotted_series: list[TrendPlotSeries]) -> None:
        self._update_legend_list(plotted_series)
        self._update_analytics_table(self._current_visible_stats)

    def _handle_plot_visible_stats_changed(self, visible_stats: object) -> None:
        if isinstance(visible_stats, list):
            self._current_visible_stats = [
                stats for stats in visible_stats if isinstance(stats, TrendVisibleSeriesStats)
            ]
        else:
            self._current_visible_stats = []
        self._update_analytics_table(self._current_visible_stats)

    def _update_legend_list(self, plotted_series: list[TrendPlotSeries]) -> None:
        if self._legend_list is None:
            return

        self._legend_list.clear()
        if not plotted_series:
            placeholder = QListWidgetItem("No plotted tags.")
            placeholder.setFlags(Qt.NoItemFlags)
            self._legend_list.addItem(placeholder)
            return

        for index, plotted in enumerate(plotted_series):
            item = QListWidgetItem(
                f"{plotted.series.tag_name}  |  Sheet: {plotted.sheet.name}"
            )
            item.setForeground(QColor(PLOT_COLORS[index % len(PLOT_COLORS)]))
            item.setData(Qt.UserRole, plotted.series.tag_name)
            self._legend_list.addItem(item)

    def _update_analytics_table(self, visible_stats: list[TrendVisibleSeriesStats]) -> None:
        if self._analytics_table is None:
            return

        self._analytics_table.setRowCount(0)
        for row_index, stats in enumerate(visible_stats):
            self._analytics_table.insertRow(row_index)
            values = [
                stats.tag_name,
                _format_numeric(stats.latest_value),
                _format_numeric(stats.minimum_value),
                _format_numeric(stats.maximum_value),
                _format_numeric(stats.average_value),
            ]
            for column_index, value in enumerate(values):
                self._analytics_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(value),
                )

        self._analytics_table.resizeColumnsToContents()

    def _last_workbook_path(self) -> Path | None:
        value = self._session.settings_state.get("last_workbook_path")
        if isinstance(value, str) and value.strip():
            return Path(value)
        return None

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
