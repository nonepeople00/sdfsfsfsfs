"""
Построение JSON-конфигураций для xray-core и sing-box на основе
распарсенного VLESS-конфига (см. vless_parser.py).

xray-core используется в режиме "системный прокси" (SOCKS5/HTTP на
localhost). sing-box используется в режиме TUN, потому что у него есть
встроенный TUN-inbound и не нужен отдельный tun2socks.
"""

from __future__ import annotations

from typing import Any

from .vless_parser import VlessConfig

# Локальные порты, на которых поднимаются inbound'ы (SOCKS5 / HTTP)
LOCAL_SOCKS_PORT = 10808
LOCAL_HTTP_PORT = 10809


def _stream_settings_xray(cfg: VlessConfig) -> dict[str, Any]:
    """Формирует блок streamSettings для xray-core."""

    stream: dict[str, Any] = {
        "network": cfg.network,
        "security": cfg.security,
    }

    if cfg.security == "tls":
        stream["tlsSettings"] = {
            "serverName": cfg.sni or cfg.address,
            "fingerprint": cfg.fingerprint or "chrome",
            "alpn": cfg.alpn or None,
            "allowInsecure": False,
        }
    elif cfg.security == "reality":
        stream["realitySettings"] = {
            "serverName": cfg.sni or cfg.address,
            "fingerprint": cfg.fingerprint or "chrome",
            "publicKey": cfg.public_key,
            "shortId": cfg.short_id,
            "spiderX": cfg.spider_x or "/",
        }

    if cfg.network == "ws":
        stream["wsSettings"] = {
            "path": cfg.ws_path or "/",
            "headers": {"Host": cfg.ws_host} if cfg.ws_host else {},
        }
    elif cfg.network == "grpc":
        stream["grpcSettings"] = {
            "serviceName": cfg.grpc_service_name,
            "multiMode": False,
        }
    elif cfg.network == "tcp" and cfg.header_type == "http":
        stream["tcpSettings"] = {
            "header": {
                "type": "http",
                "request": {
                    "path": [cfg.ws_path or "/"],
                    "headers": {"Host": [cfg.ws_host or cfg.address]},
                },
            }
        }

    return stream


def build_xray_config(cfg: VlessConfig) -> dict[str, Any]:
    """Собирает полный конфиг xray-core: inbounds + outbounds + routing."""

    user: dict[str, Any] = {"id": cfg.uuid, "encryption": cfg.encryption or "none"}
    if cfg.flow:
        user["flow"] = cfg.flow

    outbound_vless = {
        "tag": "proxy",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": cfg.address,
                    "port": cfg.port,
                    "users": [user],
                }
            ]
        },
        "streamSettings": _stream_settings_xray(cfg),
        "mux": {"enabled": False},
    }

    config: dict[str, Any] = {
        "log": {"loglevel": "info"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": LOCAL_SOCKS_PORT,
                "protocol": "socks",
                "settings": {"udp": True, "auth": "noauth"},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            },
            {
                "tag": "http-in",
                "listen": "127.0.0.1",
                "port": LOCAL_HTTP_PORT,
                "protocol": "http",
                "settings": {},
            },
        ],
        "outbounds": [
            outbound_vless,
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "block", "protocol": "blackhole", "settings": {}},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            ],
        },
    }

    return config


def build_singbox_config(cfg: VlessConfig, *, tun_interface: str = "tun-vless") -> dict[str, Any]:
    """Собирает конфиг sing-box с TUN-интерфейсом для полного
    туннелирования системного трафика (требует root или CAP_NET_ADMIN).
    """

    tls_block: dict[str, Any] = {}
    if cfg.security in ("tls", "reality"):
        tls_block = {
            "enabled": True,
            "server_name": cfg.sni or cfg.address,
            "utls": {"enabled": True, "fingerprint": cfg.fingerprint or "chrome"},
        }
        if cfg.security == "reality":
            tls_block["reality"] = {
                "enabled": True,
                "public_key": cfg.public_key,
                "short_id": cfg.short_id,
            }

    transport: dict[str, Any] = {}
    if cfg.network == "ws":
        transport = {
            "type": "ws",
            "path": cfg.ws_path or "/",
            "headers": {"Host": cfg.ws_host} if cfg.ws_host else {},
        }
    elif cfg.network == "grpc":
        transport = {"type": "grpc", "service_name": cfg.grpc_service_name}

    outbound_vless: dict[str, Any] = {
        "type": "vless",
        "tag": "proxy",
        "server": cfg.address,
        "server_port": cfg.port,
        "uuid": cfg.uuid,
        "packet_encoding": "xudp",
    }
    if cfg.flow:
        outbound_vless["flow"] = cfg.flow
    if tls_block:
        outbound_vless["tls"] = tls_block
    if transport:
        outbound_vless["transport"] = transport

    config = {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": tun_interface,
                "inet4_address": "172.19.0.1/30",
                "auto_route": True,
                "strict_route": True,
                "sniff": True,
                "stack": "system",
            }
        ],
        "outbounds": [
            outbound_vless,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "rules": [
                {"ip_is_private": True, "outbound": "direct"},
            ],
            "final": "proxy",
        },
    }

    return config
