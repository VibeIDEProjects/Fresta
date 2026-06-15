"""
fresta · yc_function/handler.py

Минимальный relay на Yandex Cloud Functions (Метод 2).
Stateless «сходи-за-меня»: принимает конверт {url, method, headers, body_b64},
ходит в открытый интернет со своего (yandexcloud, whitelisted) IP и возвращает ответ.

Это НЕ туннель сырого TCP — голые Functions так не умеют (stateless, без дуплекса).
Это fetch-relay: годится для HTTP/HTTPS запросов (страницы, API), доказывает канал.

Деплой и переменные — см. fresta_relay_README.md.
Зависимостей нет, только stdlib.
"""

import base64
import ipaddress
import json
import os
import socket
import urllib.error
import urllib.request

TOKEN = os.environ.get("FRESTA_TOKEN", "")  # задаётся в env функции
TIMEOUT = int(os.environ.get("FRESTA_TIMEOUT", "20"))
MAX_BODY = 6 * 1024 * 1024  # 6 МБ потолок на тело

# Заголовки, которые НЕ пробрасываем на целевой сервер.
HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "accept-encoding",
    "x-fresta-token",
}


def _ok(status, headers, body_bytes):
    """Завернуть ответ цели в конверт и отдать функцией наружу."""
    env = {"status": status, "headers": headers, "body_b64": base64.b64encode(body_bytes).decode()}
    payload = json.dumps(env).encode()
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "isBase64Encoded": True,
        "body": base64.b64encode(payload).decode(),
    }


def _err(code, msg):
    return {"statusCode": code, "body": msg}


def _blocked_host(host):
    """SSRF-защита: не пускаем функцию на приватные/служебные адреса
    (метаданные Яндекса 169.254.*, loopback, RFC1918 и т.п.)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def handler(event, context):
    # 1. Токен-гейт: функция публично-вызываемая, но чужие ею не попользуются.
    hdrs = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not TOKEN or hdrs.get("x-fresta-token", "") != TOKEN:
        return _err(403, "forbidden")

    # 2. Разобрать конверт.
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw)
    elif isinstance(raw, str):
        raw = raw.encode()
    try:
        req = json.loads(raw)
    except (ValueError, TypeError):
        return _err(400, "bad envelope")
    if not isinstance(req, dict):
        # Валидный JSON, но не объект (напр. "строка" или [1,2,3]) — считаем битым конвертом.
        return _err(400, "envelope must be a JSON object")

    url = req.get("url", "")
    method = (req.get("method") or "GET").upper()
    if not url.startswith(("http://", "https://")):
        return _err(400, "url must be http(s)")

    host = urllib.request.urlparse(url).hostname or ""
    if not host or _blocked_host(host):
        return _err(403, "target blocked")

    # 3. Собрать чистые заголовки и выполнить запрос.
    out_headers = {k: v for k, v in (req.get("headers") or {}).items() if k.lower() not in HOP}
    out_headers.setdefault("User-Agent", "Mozilla/5.0 (fresta-relay)")
    body = base64.b64decode(req["body_b64"]) if req.get("body_b64") else None

    r = urllib.request.Request(url, data=body, method=method, headers=out_headers)
    try:
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            data = resp.read(MAX_BODY)
            return _ok(resp.status, dict(resp.headers), data)
    except urllib.error.HTTPError as e:
        data = e.read(MAX_BODY)
        return _ok(e.code, dict(e.headers), data)
    except Exception as e:
        return _err(502, f"upstream error: {type(e).__name__}: {e}")
