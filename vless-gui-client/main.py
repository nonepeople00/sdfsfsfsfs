#!/usr/bin/env python3
"""
Точка входа VLESS GUI Client.

Запуск:
    python3 main.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.style import DARK_STYLE


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("VLESS Client")
    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
