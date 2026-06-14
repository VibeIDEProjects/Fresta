#!/usr/bin/env python3
"""
fresta · fresta_client.py

Локальный клиент к relay-функции на Yandex Cloud.
Единственное исходящее соединение клиента — к functions.yandexcloud.net
(IP и SNI в белом списке), внутри — конверт с реальным запросом.

Режимы:
  python3 fresta_client.py --check                 # показать exit-IP (должен быть Яндекса)
  python3 fresta_client.py https://api.github.com/zen
  python3 fresta_client.py -X POST https://httpbin.org/post -d '{"a":1}'
  python3 fresta_client.py --proxy 8080            # локальный HTTP-прокси (только http:// цели)

Переменные окружения:
  FRESTA_FUNC_URL  — URL функции, напр. https://functions.yandexcloud.net/<id>
  FRESTA_TOKEN     — общий секрет (тот же, что в env функции)
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FUNC_URL = os.environ.get("FRESTA_FUNC_URL", "")
TOKEN = os.environ.get("FRESTA_TOKEN", "")

HOP_RESP = {"connection", "keep-alive", "transfer-encoding", "content-length",
            "content-encoding", "te", "trailers", "upgrade"}


def relay(url, method="GET", headers=None, body=None, timeout=30):
    """Прогнать один запрос через функцию. -> (status, headers_dict, bytes)."""
    if not FUNC_URL or not TOKEN:
        raise RuntimeError("Задай FRESTA_FUNC_URL и FRESTA_TOKEN в окружении")
    env = {"url": url, "method": method, "headers": headers or {}}
    if body:
        env["body_b64"] = base64.b64encode(body).decode()
    req = urllib.request.Request(
        FUNC_URL, data=json.dumps(env).encode(), method="POST",
        headers={"X-Fresta-Token": TOKEN, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"функция отклонила запрос: HTTP {e.code} — {detail}") from None
    # Платформа отдаёт тело функции уже декодированным; на всякий случай
    # терпим и вариант, когда пришёл base64(json).
    try:
        out = json.loads(raw)
    except ValueError:
        out = json.loads(base64.b64decode(raw))
    return out["status"], out.get("headers", {}), base64.b64decode(out["body_b64"])


def cli(args):
    if args.check:
        status, _, data = relay("https://api.ipify.org?format=json")
        print(f"[*] Канал жив. Ответ функции: HTTP {status}")
        print(f"[*] Exit-IP (адрес, с которого функция ходит в сеть): {data.decode().strip()}")
        print("    Если это IP Яндекса — relay работает сквозь whitelist.")
        return
    body = args.data.encode() if args.data else None
    status, headers, data = relay(args.url, args.method, dict(args.header or []), body)
    print(f"HTTP {status}", file=sys.stderr)
    ctype = headers.get("Content-Type", "")
    if any(t in ctype for t in ("text", "json", "xml", "html")) or not ctype:
        sys.stdout.write(data.decode(errors="replace"))
    else:
        sys.stdout.buffer.write(data)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self):
        if not self.path.startswith("http://"):
            self.send_error(400, "fresta minimal: только absolute-form http:// (HTTP-proxy mode)")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()}
        try:
            status, rheaders, data = relay(self.path, self.command, headers, body)
        except Exception as e:  # noqa: BLE001
            self.send_error(502, f"relay error: {e}")
            return
        self.send_response(status)
        for k, v in rheaders.items():
            if k.lower() not in HOP_RESP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_HEAD = _proxy

    def do_CONNECT(self):
        self.send_error(
            501,
            "fresta minimal mode: HTTPS CONNECT-туннель не поддержан. "
            "Для https-целей используй CLI; для прозрачного туннеля — апгрейд на WS/VPS exit.",
        )

    def log_message(self, *a):
        pass  # тихо


def proxy(port):
    print(f"[*] fresta HTTP-proxy на 127.0.0.1:{port} (только http:// цели)")
    print(f"    Пример: http_proxy=http://127.0.0.1:{port} curl http://example.com")
    ThreadingHTTPServer(("127.0.0.1", port), ProxyHandler).serve_forever()


def main():
    ap = argparse.ArgumentParser(description="fresta client — запросы через Yandex Cloud relay")
    ap.add_argument("url", nargs="?", help="URL цели (http/https)")
    ap.add_argument("-X", "--method", default="GET", help="HTTP-метод")
    ap.add_argument("-d", "--data", help="тело запроса")
    ap.add_argument("-H", "--header", action="append", type=lambda s: s.split(":", 1),
                    help="доп. заголовок 'Key: Value' (можно несколько)")
    ap.add_argument("--check", action="store_true", help="проверить канал и показать exit-IP")
    ap.add_argument("--proxy", type=int, metavar="PORT", help="поднять локальный HTTP-proxy")
    args = ap.parse_args()

    if args.proxy:
        proxy(args.proxy)
    elif args.check or args.url:
        cli(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
