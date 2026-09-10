"""
Управление системным прокси GNOME/KDE и (опционально) поднятием
TUN-режима через sing-box.

Для GNOME используется утилита `gsettings` (схема org.gnome.system.proxy).
Для KDE используется `kwriteconfig5`/`kwriteconfig6` + сигнал
переприменения настроек через dbus-send.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def detect_desktop_environment() -> str:
    """Пытается определить текущее окружение рабочего стола."""

    xdg = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in xdg:
        return "gnome"
    if "kde" in xdg or "plasma" in xdg:
        return "kde"
    return "unknown"


class SystemProxyManager:
    """Включает/выключает системный HTTP/SOCKS5 прокси на localhost."""

    def __init__(self, http_port: int, socks_port: int) -> None:
        self.http_port = http_port
        self.socks_port = socks_port
        self.desktop = detect_desktop_environment()

    def enable(self) -> tuple[bool, str]:
        if self.desktop == "gnome":
            return self._enable_gnome()
        if self.desktop == "kde":
            return self._enable_kde()
        return False, "Неизвестное окружение рабочего стола: настройте прокси вручную."

    def disable(self) -> tuple[bool, str]:
        if self.desktop == "gnome":
            return self._disable_gnome()
        if self.desktop == "kde":
            return self._disable_kde()
        return False, "Неизвестное окружение рабочего стола: сбросьте прокси вручную."

    # --- GNOME ---------------------------------------------------------

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def _enable_gnome(self) -> tuple[bool, str]:
        if not shutil.which("gsettings"):
            return False, "Утилита 'gsettings' не найдена."

        cmds = [
            ["gsettings", "set", "org.gnome.system.proxy", "mode", "manual"],
            ["gsettings", "set", "org.gnome.system.proxy.http", "host", "127.0.0.1"],
            ["gsettings", "set", "org.gnome.system.proxy.http", "port", str(self.http_port)],
            ["gsettings", "set", "org.gnome.system.proxy.https", "host", "127.0.0.1"],
            ["gsettings", "set", "org.gnome.system.proxy.https", "port", str(self.http_port)],
            ["gsettings", "set", "org.gnome.system.proxy.socks", "host", "127.0.0.1"],
            ["gsettings", "set", "org.gnome.system.proxy.socks", "port", str(self.socks_port)],
        ]
        for cmd in cmds:
            result = self._run(cmd)
            if result.returncode != 0:
                return False, f"Ошибка выполнения {' '.join(cmd)}: {result.stderr.strip()}"
        return True, "Системный прокси GNOME включён (127.0.0.1)."

    def _disable_gnome(self) -> tuple[bool, str]:
        if not shutil.which("gsettings"):
            return False, "Утилита 'gsettings' не найдена."
        result = self._run(["gsettings", "set", "org.gnome.system.proxy", "mode", "none"])
        if result.returncode != 0:
            return False, f"Ошибка сброса прокси GNOME: {result.stderr.strip()}"
        return True, "Системный прокси GNOME отключён."

    # --- KDE -------------------------------------------------------------

    def _kwriteconfig_bin(self) -> str | None:
        for candidate in ("kwriteconfig6", "kwriteconfig5"):
            if shutil.which(candidate):
                return candidate
        return None

    def _enable_kde(self) -> tuple[bool, str]:
        binary = self._kwriteconfig_bin()
        if not binary:
            return False, "Утилита 'kwriteconfig5/6' не найдена."

        proxy_str = f"http://127.0.0.1 {self.http_port}"
        socks_str = f"socks://127.0.0.1 {self.socks_port}"

        cmds = [
            [binary, "--file", "kioslaverc", "--group", "Proxy Settings", "--key", "ProxyType", "1"],
            [binary, "--file", "kioslaverc", "--group", "Proxy Settings", "--key", "httpProxy", proxy_str],
            [binary, "--file", "kioslaverc", "--group", "Proxy Settings", "--key", "httpsProxy", proxy_str],
            [binary, "--file", "kioslaverc", "--group", "Proxy Settings", "--key", "socksProxy", socks_str],
        ]
        for cmd in cmds:
            result = self._run(cmd)
            if result.returncode != 0:
                return False, f"Ошибка выполнения {' '.join(cmd)}: {result.stderr.strip()}"

        self._run([
            "dbus-send", "--type=signal", "/KIO/Scheduler",
            "org.kde.KIO.Scheduler.reparseSlaveConfiguration", "string:",
        ])
        return True, "Системный прокси KDE включён (127.0.0.1)."

    def _disable_kde(self) -> tuple[bool, str]:
        binary = self._kwriteconfig_bin()
        if not binary:
            return False, "Утилита 'kwriteconfig5/6' не найдена."
        result = self._run([binary, "--file", "kioslaverc", "--group", "Proxy Settings", "--key", "ProxyType", "0"])
        if result.returncode != 0:
            return False, f"Ошибка сброса прокси KDE: {result.stderr.strip()}"
        self._run([
            "dbus-send", "--type=signal", "/KIO/Scheduler",
            "org.kde.KIO.Scheduler.reparseSlaveConfiguration", "string:",
        ])
        return True, "Системный прокси KDE отключён."


class TunManager:
    """Проверка возможности запуска sing-box в режиме TUN (нужен root или CAP_NET_ADMIN)."""

    def __init__(self, singbox_binary: str = "sing-box") -> None:
        self.singbox_binary = singbox_binary

    def check_privileges(self) -> tuple[bool, str]:
        """Проверяет, может ли бинарник поднимать TUN без sudo (через capabilities)."""

        path = shutil.which(self.singbox_binary)
        if not path:
            return False, f"Бинарник '{self.singbox_binary}' не найден в PATH."

        result = subprocess.run(["getcap", path], capture_output=True, text=True, check=False)
        if "cap_net_admin" in result.stdout:
            return True, "У бинарника есть нужные capabilities (cap_net_admin)."

        if os.geteuid() == 0:
            return True, "Приложение запущено от root."

        return False, (
            "Для TUN-режима нужны права. Выполните один раз:\n"
            f"  sudo setcap cap_net_admin,cap_net_bind_service=+ep {path}\n"
            "или запускайте приложение через 'pkexec'/'sudo'."
        )
