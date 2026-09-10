"""
Менеджер фонового процесса ядра (xray-core или sing-box).

Используется QProcess, чтобы вывод (stdout/stderr) ядра приходил в GUI
через сигналы Qt без блокировки интерфейса.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


class CoreManager(QObject):
    """Запускает/останавливает xray-core или sing-box и транслирует логи."""

    log_line = pyqtSignal(str)
    status_changed = pyqtSignal(bool)  # True = запущено, False = остановлено
    error_occurred = pyqtSignal(str)

    def __init__(self, binary_path: str = "xray", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.binary_path = binary_path
        self._process: QProcess | None = None
        self._config_path: Path | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() == QProcess.ProcessState.Running

    def start(self, config: dict) -> None:
        """Записывает конфиг во временный файл и запускает ядро."""

        if self.is_running:
            self.log_line.emit("Ядро уже запущено, повторный запуск проигнорирован.")
            return

        fd, path = tempfile.mkstemp(prefix="vless_gui_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self._config_path = Path(path)

        self._process = QProcess(self)
        self._process.setProgram(self.binary_path)
        self._process.setArguments(["run", "-c", str(self._config_path)])
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        self._process.start()
        started = self._process.waitForStarted(3000)
        if not started:
            self.error_occurred.emit(
                f"Не удалось запустить '{self.binary_path}'. "
                "Проверьте, что бинарник установлен и доступен в PATH."
            )
            return

        self.log_line.emit(f"[core] запущен, конфиг: {self._config_path}")
        self.status_changed.emit(True)

    def stop(self) -> None:
        if not self.is_running or self._process is None:
            self.status_changed.emit(False)
            return

        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()
            self._process.waitForFinished(1000)

        self.log_line.emit("[core] остановлен пользователем.")
        self.status_changed.emit(False)
        self._cleanup_config()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.log_line.emit(line)

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.log_line.emit(f"[stderr] {line}")

    def _on_finished(self, exit_code: int, exit_status) -> None:  # noqa: ANN001
        self.log_line.emit(f"[core] процесс завершился (код выхода {exit_code}).")
        self.status_changed.emit(False)
        self._cleanup_config()

    def _on_error(self, error) -> None:  # noqa: ANN001
        self.error_occurred.emit(f"Ошибка процесса ядра: {error}")

    def _cleanup_config(self) -> None:
        if self._config_path and self._config_path.exists():
            try:
                self._config_path.unlink()
            except OSError:
                pass
            self._config_path = None
