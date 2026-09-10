"""Тёмная современная тема (QSS) для приложения."""

DARK_STYLE = """
QWidget {
    background-color: #1e1f26;
    color: #e6e6e6;
    font-family: "Cantarell", "Noto Sans", sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #34353f;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9ea4b0;
}

QLineEdit, QPlainTextEdit {
    background-color: #14151b;
    border: 1px solid #34353f;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #3b82f6;
}

QPushButton {
    background-color: #2b2d38;
    border: 1px solid #3c3e4a;
    border-radius: 8px;
    padding: 8px 14px;
}

QPushButton:hover {
    background-color: #363844;
}

QPushButton:checked {
    background-color: #2563eb;
    border-color: #2563eb;
    color: white;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QToolButton {
    color: #e6e6e6;
    padding: 4px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
}

QScrollBar::handle:vertical {
    background: #3c3e4a;
    border-radius: 5px;
}
"""
