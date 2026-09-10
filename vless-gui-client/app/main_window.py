"""
Главное окно приложения — VLESS GUI Client.

Содержит:
    - Поле ввода vless:// ссылки и кнопку разбора/сохранения
    - Кнопку-переключатель подключения с цветовым индикатором
    - Сворачиваемый блок логов ядра
    - Панель информации о текущем подключении
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config_builder import LOCAL_HTTP_PORT, LOCAL_SOCKS_PORT, build_singbox_config, build_xray_config
from .proxy_manager import SystemProxyManager, TunManager
from .vless_parser import VlessConfig, VlessParseError, parse_vless_url
from .xray_manager import CoreManager

ORG_NAME = "VlessGuiClient"
APP_NAME = "VlessGuiClient"


class CollapsibleBox(QWidget):
    """Простой сворачиваемый блок (используется для логов ядра)."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.toggle_button = QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setStyleSheet("QToolButton { border: none; font-weight: 600; }")
        self.toggle_button.clicked.connect(self._on_toggled)

        self.content_area = QWidget()
        self.content_area.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_area)

    def _on_toggled(self) -> None:
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.content_area.setVisible(checked)

    def set_content_layout(self, layout) -> None:  # noqa: ANN001
        self.content_area.setLayout(layout)


class StatusIndicator(QLabel):
    """Цветной кружок-индикатор статуса подключения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        color = "#2ecc71" if connected else "#e74c3c"
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 7px; border: 1px solid rgba(0,0,0,0.2);"
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VLESS Client")
        self.resize(560, 640)

        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.current_config: VlessConfig | None = None
        self.core_binary = self.settings.value("core_binary", "xray")

        self.core_manager = CoreManager(binary_path=self.core_binary)
        self.core_manager.log_line.connect(self._append_log)
        self.core_manager.status_changed.connect(self._on_core_status_changed)
        self.core_manager.error_occurred.connect(self._on_core_error)

        self.proxy_manager = SystemProxyManager(LOCAL_HTTP_PORT, LOCAL_SOCKS_PORT)
        self.tun_manager = TunManager()

        self._build_ui()
        self._restore_last_link()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(14)
        root.setContentsMargins(18, 18, 18, 18)

        # --- Блок ввода ссылки -----------------------------------------
        link_box = QGroupBox("VLESS-ссылка")
        link_layout = QHBoxLayout(link_box)
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("vless://uuid@host:port?...#name")
        self.link_edit.setClearButtonEnabled(True)
        parse_btn = QPushButton("Сохранить / Парсить")
        parse_btn.clicked.connect(self._on_parse_clicked)
        link_layout.addWidget(self.link_edit, 1)
        link_layout.addWidget(parse_btn)
        root.addWidget(link_box)

        # --- Блок информации о подключении -------------------------------
        info_box = QGroupBox("Текущее подключение")
        info_layout = QVBoxLayout(info_box)
        self.info_host_label = QLabel("Хост/порт: —")
        self.info_transport_label = QLabel("Транспорт: —")
        self.info_security_label = QLabel("Безопасность: —")
        for lbl in (self.info_host_label, self.info_transport_label, self.info_security_label):
            lbl.setStyleSheet("color: #ccc;")
            info_layout.addWidget(lbl)
        root.addWidget(info_box)

        # --- Блок подключения --------------------------------------------
        connect_box = QGroupBox("Управление подключением")
        connect_layout = QVBoxLayout(connect_box)

        status_row = QHBoxLayout()
        self.status_indicator = StatusIndicator()
        self.status_label = QLabel("Отключено")
        status_row.addWidget(self.status_indicator)
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        connect_layout.addLayout(status_row)

        self.connect_btn = QPushButton("Подключить")
        self.connect_btn.setCheckable(True)
        self.connect_btn.setMinimumHeight(40)
        self.connect_btn.clicked.connect(self._on_connect_toggled)
        connect_layout.addWidget(self.connect_btn)

        self.use_tun_checkbox = QPushButton("Режим: системный прокси (нажмите для TUN)")
        self.use_tun_checkbox.setCheckable(True)
        self.use_tun_checkbox.clicked.connect(self._on_mode_toggled)
        connect_layout.addWidget(self.use_tun_checkbox)

        root.addWidget(connect_box)

        # --- Логи (сворачиваемые) -----------------------------------------
        self.log_box = CollapsibleBox("Логи ядра (нажмите, чтобы развернуть)")
        log_layout = QVBoxLayout()
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(2000)
        self.log_output.setMinimumHeight(220)
        log_layout.addWidget(self.log_output)
        self.log_box.set_content_layout(log_layout)
        root.addWidget(self.log_box, 1)

        root.addStretch(0)

    # ------------------------------------------------------------------
    # Обработчики событий
    # ------------------------------------------------------------------

    def _restore_last_link(self) -> None:
        last_link = self.settings.value("last_link", "")
        if last_link:
            self.link_edit.setText(last_link)
            self._try_parse(last_link, silent=True)

    def _on_parse_clicked(self) -> None:
        link = self.link_edit.text().strip()
        if not link:
            QMessageBox.warning(self, "Пустая ссылка", "Вставьте vless:// ссылку перед сохранением.")
            return
        self._try_parse(link, silent=False)

    def _try_parse(self, link: str, *, silent: bool) -> None:
        try:
            cfg = parse_vless_url(link)
        except VlessParseError as exc:
            if not silent:
                QMessageBox.critical(self, "Ошибка разбора ссылки", str(exc))
            self._append_log(f"[parser] ошибка: {exc}")
            return

        self.current_config = cfg
        self.settings.setValue("last_link", link)
        self._update_info_panel(cfg)
        if not silent:
            self._append_log(f"[parser] ссылка успешно разобрана: {cfg.remark}")
            QMessageBox.information(self, "Готово", "Ссылка успешно разобрана и сохранена.")

    def _update_info_panel(self, cfg: VlessConfig) -> None:
        self.info_host_label.setText(f"Хост/порт: {cfg.address}:{cfg.port}")
        self.info_transport_label.setText(f"Транспорт: {cfg.network} (headerType={cfg.header_type})")
        security_extra = ""
        if cfg.security == "reality":
            security_extra = f" | REALITY sni={cfg.sni} fp={cfg.fingerprint or 'chrome'}"
        elif cfg.security == "tls":
            security_extra = f" | TLS sni={cfg.sni}"
        self.info_security_label.setText(f"Безопасность: {cfg.security}{security_extra}")

    def _on_mode_toggled(self) -> None:
        use_tun = self.use_tun_checkbox.isChecked()
        text = "Режим: TUN (нажмите для системного прокси)" if use_tun else "Режим: системный прокси (нажмите для TUN)"
        self.use_tun_checkbox.setText(text)

    def _on_connect_toggled(self) -> None:
        if self.connect_btn.isChecked():
            self._start_connection()
        else:
            self._stop_connection()

    def _start_connection(self) -> None:
        if self.current_config is None:
            QMessageBox.warning(self, "Нет конфигурации", "Сначала вставьте и разберите VLESS-ссылку.")
            self.connect_btn.setChecked(False)
            return

        use_tun = self.use_tun_checkbox.isChecked()

        if use_tun:
            ok, msg = self.tun_manager.check_privileges()
            self._append_log(f"[tun] {msg}")
            if not ok:
                QMessageBox.warning(self, "Недостаточно прав для TUN", msg)
                self.connect_btn.setChecked(False)
                return
            config = build_singbox_config(self.current_config)
            self.core_manager.binary_path = self.settings.value("singbox_binary", "sing-box")
            self.core_manager.start(config)
        else:
            config = build_xray_config(self.current_config)
            self.core_manager.binary_path = self.settings.value("core_binary", "xray")
            self.core_manager.start(config)

            ok, msg = self.proxy_manager.enable()
            self._append_log(f"[proxy] {msg}")
            if not ok:
                QMessageBox.warning(self, "Не удалось включить системный прокси", msg)

        self.connect_btn.setText("Отключить")

    def _stop_connection(self) -> None:
        use_tun = self.use_tun_checkbox.isChecked()
        self.core_manager.stop()
        if not use_tun:
            ok, msg = self.proxy_manager.disable()
            self._append_log(f"[proxy] {msg}")
        self.connect_btn.setText("Подключить")

    def _on_core_status_changed(self, running: bool) -> None:
        self.status_indicator.set_connected(running)
        self.status_label.setText("Подключено" if running else "Отключено")
        self.connect_btn.setChecked(running)
        self.connect_btn.setText("Отключить" if running else "Подключить")

    def _on_core_error(self, message: str) -> None:
        self._append_log(f"[error] {message}")
        QMessageBox.critical(self, "Ошибка ядра", message)
        self.connect_btn.setChecked(False)

    def _append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if self.core_manager.is_running:
            self._stop_connection()
        super().closeEvent(event)
