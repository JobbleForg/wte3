from __future__ import annotations


APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #151A1F;
    color: #D8DFE6;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QToolBar {
    background-color: #1B2128;
    border: none;
    border-bottom: 1px solid #313A44;
    spacing: 6px;
    padding: 6px;
}

QToolButton {
    background-color: #242C34;
    color: #D8DFE6;
    border: 1px solid #3A4550;
    border-radius: 4px;
    padding: 6px 10px;
}

QToolButton:hover {
    background-color: #2C3540;
}

QDockWidget {
    border: 1px solid #313A44;
}

QDockWidget::title {
    background-color: #20262D;
    color: #E4EAF0;
    padding: 6px 8px;
    border-bottom: 1px solid #313A44;
    font-weight: 600;
}

QSplitter::handle {
    background-color: #2A3139;
}

QFrame#panelCard,
QFrame#trendViewport,
QFrame#floatingLegendOverlay,
QListWidget,
QTreeWidget,
QTableWidget,
QTabWidget::pane {
    background-color: #20262D;
    border: 1px solid #37414B;
}

QListWidget,
QTreeWidget,
QTableWidget {
    background-color: #171D23;
    alternate-background-color: #1C232B;
    selection-background-color: #35506B;
    selection-color: #F1F5F8;
    outline: none;
}

QHeaderView::section {
    background-color: #242C34;
    color: #D8DFE6;
    border: 1px solid #3A4550;
    padding: 6px;
    font-weight: 600;
}

QPushButton {
    background-color: #242C34;
    color: #D8DFE6;
    border: 1px solid #3A4550;
    border-radius: 4px;
    padding: 6px 10px;
}

QPushButton:hover {
    background-color: #2C3540;
}

QPushButton:disabled,
QToolButton:disabled {
    color: #7B8792;
    background-color: #1E252C;
    border-color: #313A44;
}

QTabBar::tab {
    background-color: #20262D;
    color: #B8C1C9;
    border: 1px solid #37414B;
    padding: 6px 12px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #2A3139;
    color: #F1F5F8;
}

QStatusBar {
    background-color: #1B2128;
    color: #BFC8D0;
    border-top: 1px solid #313A44;
}

QLabel {
    color: #D8DFE6;
}

QFrame#floatingLegendOverlay {
    background-color: rgba(23, 29, 35, 236);
    border: 1px solid #4A5662;
    border-radius: 6px;
}

QWidget#floatingLegendHeader {
    background-color: rgba(32, 38, 45, 245);
    border-bottom: 1px solid #37414B;
}

QFrame#floatingLegendEntry {
    background-color: rgba(42, 49, 57, 190);
    border: 1px solid rgba(74, 86, 98, 180);
    border-radius: 4px;
}

QPushButton#floatingLegendToggle {
    padding: 0;
    min-width: 0;
}

QScrollArea#floatingLegendScrollArea {
    background-color: transparent;
    border: none;
}
"""
