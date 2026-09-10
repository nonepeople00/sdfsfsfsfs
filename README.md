# VLESS GUI Client (Fedora / Silverblue & Workstation)

GUI-клиент для VLESS-протокола на Python 3 + PyQt6. В качестве ядра
используется `xray-core` (режим системного HTTP/SOCKS5 прокси) или
`sing-box` (режим TUN для полного туннелирования системы).

## Структура проекта

```
vless-gui-client/
├── main.py                  # точка входа
├── requirements.txt
├── vless-gui-client.desktop # .desktop файл для меню приложений
└── app/
    ├── __init__.py
    ├── vless_parser.py      # Парсер vless:// ссылок
    ├── config_builder.py    # Сборка JSON-конфигов xray-core / sing-box
    ├── xray_manager.py      # Менеджер фонового процесса ядра (QProcess)
    ├── proxy_manager.py     # Системный прокси GNOME/KDE + TUN privileges
    ├── main_window.py       # PyQt6 интерфейс
    └── style.py             # QSS-тема
```

## Как это работает

1. Вы вставляете `vless://...` ссылку и нажимаете «Сохранить / Парсить».
2. Приложение разбирает ссылку и показывает хост/порт, транспорт и тип безопасности.
3. Выбираете режим: «системный прокси» (по умолчанию, не требует root) или
   «TUN» (полное туннелирование через sing-box, требует root/capabilities).
4. Нажимаете «Подключить» — приложение генерирует временный JSON-конфиг,
   запускает ядро и (в режиме прокси) включает системный прокси через `gsettings`/`kwriteconfig`.
5. Логи xray-core/sing-box выводятся в сворачиваемом блоке в реальном времени.

> **О xray-core и TUN**: сам xray-core не умеет встроенного TUN-инбаунда, поэтому для
> режима полного туннелирования системы (включая UDP/все приложения) приложение
> использует `sing-box`, у которого есть готовый `tun`-inbound (без tun2socks).
> Оба ядра понимают один и тот же разобранный VLESS-конфиг — просто для каждого
> собирается свой формат JSON (см. `app/config_builder.py`).

---

## 1. Установка зависимостей на Fedora

### 1.1. Fedora Workstation (обычная, с dnf)

```bash
# Системные библиотеки, нужные PyQt6 и сети (Wayland/X11, OpenSSL, D-Bus, шрифты)
sudo dnf install -y python3 python3-pip python3-virtualenv \
    qt6-qtbase qt6-qtbase-gui mesa-libGL libxkbcommon libxkbcommon-x11 \
    xcb-util-cursor glibc-langpack-ru dbus-x11 NetworkManager-libnm

# Создаём отдельное окружение Python, чтобы не засорять системный Python
mkdir -p ~/.local/share/vless-gui-client
python3 -m venv ~/.local/share/vless-gui-client/venv
source ~/.local/share/vless-gui-client/venv/bin/activate

pip install --upgrade pip
pip install PyQt6
```

### 1.2. Fedora Silverblue / Kinoite (иммутабельный образ)

На Silverblue `dnf install` напрямую не работает для системных пакетов в runtime —
есть два рабочих подхода:

**Вариан A (рекомендуется) — всё в виртуальном окружении Python (venv), без rpm-ostree**

PyQt6 можно поставить через pip с wheel-пакетами, которые уже содержат
бинарные Qt-библиотеки, поэтому на Silverblue это обычно работает без изменения
базового образа:

```bash
sudo dnf install -y python3-pip python3-virtualenv   # сработает через rpm-ostree overlay
# или, если хотите без лишних наложений на базовый образ — используйте toolbox (ниже)

python3 -m venv ~/.local/share/vless-gui-client/venv
source ~/.local/share/vless-gui-client/venv/bin/activate
pip install --upgrade pip
pip install PyQt6
```

Если `python3-pip`/`python3-virtualenv` отсутствуют в базовом образе, добавьте их
через layered package:

```bash
sudo rpm-ostree install python3-pip python3-virtualenv
systemctl reboot   # нужен рестарт, чтобы новый образ вступил в силу
```

**Вариан B — разработка/запуск в toolbox-контейнере** (удобно для тестирования,
но GUI-приложения из toolbox требуют дополнительной настройки X11/Wayland socket):

```bash
toolbox create vless-dev
toolbox enter vless-dev
sudo dnf install -y python3 python3-pip qt6-qtbase-gui mesa-libGL libxkbcommon-x11
pip install --user PyQt6
```

Для системного прокси (`gsettings`) и TUN (`ip`, `nmcli`, `setcap`) рекомендуется **запускать
само приложение на хост-системе** (вариан A), а не внутри toolbox, так как
`gsettings`/`nmcli` внутри контейнера не влияют на сессию хоста.

---

## 2. Установка ядер — xray-core и sing-box

Бинарники в репозиториях Fedora отсутствуют, поэтому ставим из официальных
GitHub-релизов (работает одинаково на Workstation и Silverblue, так как это просто
бинарник в `/usr/local/bin`):

### 2.1. xray-core

```bash
cd /tmp
curl -L -o xray.zip https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip
mkdir -p xray-tmp && unzip xray.zip -d xray-tmp
sudo install -Dm755 xray-tmp/xray /usr/local/bin/xray
sudo mkdir -p /usr/local/share/xray
sudo install -Dm644 xray-tmp/geoip.dat xray-tmp/geosite.dat /usr/local/share/xray/
xray version   # проверка
```

### 2.2. sing-box (только если нужен режим TUN)

```bash
cd /tmp
ver=$(curl -s https://api.github.com/repos/SagerNet/sing-box/releases/latest | grep tag_name | cut -d '"' -f4 | tr -d v)
curl -L -o sing-box.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v${ver}/sing-box-${ver}-linux-amd64.tar.gz"
tar xzf sing-box.tar.gz
sudo install -Dm755 sing-box-${ver}-linux-amd64/sing-box /usr/local/bin/sing-box
sing-box version   # проверка

# Чтобы TUN-режим работал без запуска всего приложения от root,
# выдаём бинарнику только нужные capabilities:
sudo setcap cap_net_admin,cap_net_bind_service=+ep /usr/local/bin/sing-box
```

`/usr/local/bin` на Fedora (включая Silverblue) уже входит в `$PATH` и является частью
записываемой части файловой системы (`/var`), поэтому этот шаг не требует
`rpm-ostree` и перезагрузки.

---

## 3. Разворачивание исходного кода приложения

```bash
# Распакуйте проект в постоянное место, например:
sudo mkdir -p /opt/vless-gui-client
sudo cp -r vless-gui-client/* /opt/vless-gui-client/
sudo chown -R "$USER":"$USER" /opt/vless-gui-client

# Активируем виртуальное окружение и запускаем
source ~/.local/share/vless-gui-client/venv/bin/activate
cd /opt/vless-gui-client
python3 main.py
```

При первом запуске откроется окно приложения. Вставьте свою `vless://` ссылку,
нажмите «Сохранить / Парсить», затем «Подключить».

---

## 4. Создание `.desktop` файла для запуска из меню приложений

Файл `vless-gui-client.desktop` уже лежит в корне проекта. Поскольку приложение
запускается в venv, удобнее всего сделать небольшой скрипт-обёртку:

```bash
cat > /opt/vless-gui-client/run.sh << 'EOF'
#!/bin/bash
source "$HOME/.local/share/vless-gui-client/venv/bin/activate"
exec python3 /opt/vless-gui-client/main.py "$@"
EOF
chmod +x /opt/vless-gui-client/run.sh
```

Затем обновите `Exec=` в `.desktop` файле, чтобы он указывал на этот скрипт:

```ini
[Desktop Entry]
Type=Application
Name=VLESS Client
Comment=GUI-клиент для VLESS (xray-core / sing-box)
Exec=/opt/vless-gui-client/run.sh
Icon=network-vpn
Terminal=false
Categories=Network;Security;
StartupNotify=true
```

Установка ярлыка в меню приложений (только для текущего пользователя, без root):

```bash
mkdir -p ~/.local/share/applications
cp /opt/vless-gui-client/vless-gui-client.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications   # обновить кэш меню
```

После этого приложение «VLESS Client» появится в обзоре приложений GNOME/KDE.
Если иконка не найдена — замените `Icon=network-vpn` на путь к своей `.png`/`.svg` иконке.

### Как запускать TUN-режим без ввода пароля каждый раз

Графическое приложение не должно целиком запускаться от root — достаточно выдать
только бинарнику `sing-box` нужные capabilities, как показано в шаге 2.2
(`setcap cap_net_admin,cap_net_bind_service=+ep`). После этого приложение запускает
`sing-box` от обычного пользователя, а TUN-интерфейс всё равно поднимается.

---

## 5. Частые проблемы

- **`QXcbConnection: Could not connect to display`** — запускайте приложение из графической
  сессии, а не через SSH без X11 forwarding.
- **Не найден 'xray'/'sing-box'** — проверьте, что `/usr/local/bin` есть в `$PATH`
  (`echo $PATH`), либо укажите полный путь в настройках приложения.
- **Прокси не применяется в приложениях GTK** — GNOME читает настройки из
  `gsettings` автоматически, но некоторым аппам нужен перезапуск; QT/Electron приложения
  часто читают переменные окружения `http_proxy`/`all_proxy` вместо `gsettings`.
- **TUN не поднимается даже после setcap** — убедитесь, что файловая система,
  где лежит бинарник, не смонтирована с `nosuid`, и что ядро не перезапущено после
  выполнения `setcap`.

---

## 6. Ограничения и дальнейшие шаги

- Парсер покрывает наиболее распространённый формат vless:// ссылок (совместимый с
  v2rayN/Xray). Если ваш провайдер использует нестандартные параметры, добавьте их
  обработку в `app/vless_parser.py`.
- Для продакшн-готового использования рекомендуется: хранить несколько профилей
  в QSettings/JSON, подтягивать геоип/геосайт базы (`geoip.dat`/`geosite.dat`) автоматически,
  добавить автозапуск при старте системы через systemd user unit.
# VLESS-Client-on-Linux
# sdfsfsfsfs
