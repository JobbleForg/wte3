from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import TrendViewerMainWindow
from .ui.styles.theme import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WTE Trend Viewer")
    app.setStyleSheet(APP_STYLESHEET)

    window = TrendViewerMainWindow()
    window.show()

    return app.exec()
