"""
Парсер VLESS-ссылок (vless://...).

Формат ссылки (стандарт, совместимый с v2rayN / Xray):

    vless://<uuid>@<host>:<port>?<query-параметры>#<remark>

Основные query-параметры:
    encryption   - всегда "none" для VLESS
    flow         - xtls-rprx-vision и т.п. (для REALITY/XTLS)
    security     - none | tls | reality
    sni          - Server Name Indication для TLS/REALITY
    fp           - fingerprint (chrome, firefox, safari, ...)
    pbk          - publicKey для REALITY
    sid          - shortId для REALITY
    spx          - spiderX для REALITY (необязательно)
    alpn         - список протоколов ALPN через запятую
    type         - тип транспорта: tcp | ws | grpc | http | quic | kcp
    path         - путь для WebSocket
    host         - HTTP Host заголовок для WebSocket/H2
    serviceName  - имя сервиса для gRPC
    headerType   - тип маскировки заголовков TCP (none | http)
"""

from __future__ import annotations

import dataclasses
import urllib.parse


class VlessParseError(ValueError):
    """Ошибка разбора vless:// ссылки."""


@dataclasses.dataclass
class VlessConfig:
    """Структурированное представление распарсенной VLESS-ссылки."""

    uuid: str
    address: str
    port: int
    remark: str = ""

    encryption: str = "none"
    flow: str = ""

    security: str = "none"          # none | tls | reality
    sni: str = ""
    fingerprint: str = ""
    alpn: list[str] = dataclasses.field(default_factory=list)

    # REALITY
    public_key: str = ""
    short_id: str = ""
    spider_x: str = ""

    # Транспорт
    network: str = "tcp"            # tcp | ws | grpc | http | quic | kcp
    ws_path: str = ""
    ws_host: str = ""
    grpc_service_name: str = ""
    header_type: str = "none"

    raw_query: dict = dataclasses.field(default_factory=dict)


def parse_vless_url(url: str) -> VlessConfig:
    """Разбирает строку vless://... в объект VlessConfig.

    Бросает VlessParseError при некорректном формате.
    """

    url = url.strip()
    if not url:
        raise VlessParseError("Пустая строка")

    if not url.lower().startswith("vless://"):
        raise VlessParseError("Ссылка должна начинаться с 'vless://'")

    parsed = urllib.parse.urlparse(url)

    if not parsed.username:
        raise VlessParseError("Не найден UUID пользователя перед '@'")

    uuid = urllib.parse.unquote(parsed.username)

    if not parsed.hostname:
        raise VlessParseError("Не найден адрес сервера (host)")

    address = parsed.hostname
    port = parsed.port
    if not port:
        raise VlessParseError("Не найден порт сервера")

    remark = urllib.parse.unquote(parsed.fragment) if parsed.fragment else ""

    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))

    cfg = VlessConfig(
        uuid=uuid,
        address=address,
        port=int(port),
        remark=remark or address,
        raw_query=query,
    )

    cfg.encryption = query.get("encryption", "none")
    cfg.flow = query.get("flow", "")

    cfg.security = query.get("security", "none").lower()
    cfg.sni = query.get("sni", query.get("peer", ""))
    cfg.fingerprint = query.get("fp", "")
    alpn_raw = query.get("alpn", "")
    cfg.alpn = [a for a in alpn_raw.split(",") if a] if alpn_raw else []

    cfg.public_key = query.get("pbk", "")
    cfg.short_id = query.get("sid", "")
    cfg.spider_x = query.get("spx", "")

    cfg.network = query.get("type", "tcp").lower()
    cfg.ws_path = query.get("path", "/")
    cfg.ws_host = query.get("host", cfg.sni or address)
    cfg.grpc_service_name = query.get("serviceName", "")
    cfg.header_type = query.get("headerType", "none")

    # Базовая валидация обязательных для REALITY полей
    if cfg.security == "reality":
        if not cfg.public_key:
            raise VlessParseError("Для REALITY отсутствует параметр 'pbk' (publicKey)")

    if cfg.network == "grpc" and not cfg.grpc_service_name:
        raise VlessParseError("Для транспорта gRPC отсутствует параметр 'serviceName'")

    return cfg
