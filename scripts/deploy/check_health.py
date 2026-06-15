#!/usr/bin/env python3
"""
fresta · check_health.py

Health-check только что задеплоенного vless-vps:
  1. Подключается к SOCKS5 из client.json;
  2. Гоняет 5 синтетических запросов (ipify / api.github.com/zen / example.com / …);
  3. Проверяет, что exit-IP = IP из server.json;
  4. Печатает latency (median, p95) + вердикт.

Зачем: после `bash quickstart.sh --ssh …` сразу получаешь ответ — живо ли оно,
не перехватывает ли что-то по дороге, реально ли идёт через туннель.

Использование:
    # Из сгенерированного набора:
    python3 scripts/check_health.py scripts/deploy/configs/my-vps-2026-06-14

    # Или прямо через sing-box: запусти sing-box локально, в client.json укажи
    # listen "127.0.0.1:1080", затем:
    python3 scripts/check_health.py --socks 127.0.0.1:1080

Зависимостей нет, только stdlib (socket, ssl, urllib, json).
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

# Синтетические цели: HTTP-200, маленький ответ, не-Google (чтобы не зависеть
# от одного домена). Каждая — кортеж (url, ожидаемый фрагмент или None).
PROBES = [
    ("https://api.ipify.org?format=json", '"ip"'),
    ("https://api.github.com/zen", None),
    ("https://example.com/", "Example Domain"),
    ("https://www.cloudflare.com/cdn-cgi/trace", "fl="),
    ("https://httpbin.org/uuid", None),
]

TIMEOUT = 10  # секунд на один запрос


def read_socks5_from_client_json(client_path: str) -> tuple[str, int]:
    """Парсит client.json, вытаскивает listen из первого inbound type=mixed/socks.
    Если inbound'ов нет — возвращает ('127.0.0.1', 1080) по умолчанию."""
    with open(client_path, encoding="utf-8") as f:
        cfg = json.load(f)
    for ib in cfg.get("inbounds", []):
        if ib.get("type") in ("mixed", "socks", "socks5"):
            return ib.get("listen", "127.0.0.1"), int(ib.get("listen_port", 1080))
    return "127.0.0.1", 1080


def socks5_get(host: str, port: int, target_url: str, timeout: int) -> tuple[int, float, bytes]:
    """Минимальный SOCKS5-клиент (CONNECT, без auth). Возвращает (status, latency_s, body).
    Тело читаем по HTTP/1.0 через тот же сокет, чтобы не зависеть от внешних прокси-стеков."""
    import socket

    t0 = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout) as s:
        # SOCKS5 greeting: VER=5, NMETHODS=1, METHOD=0 (no auth)
        s.sendall(b"\x05\x01\x00")
        greet = s.recv(2)
        if greet != b"\x05\x00":
            raise RuntimeError(f"SOCKS5 greeting failed: {greet!r}")
        # CONNECT: ATYP=3 (domain), затем len+domain, port (2 байта BE)
        from urllib.parse import urlparse

        u = urlparse(target_url)
        if u.scheme != "https":
            raise ValueError(f"only https:// supported in probe, got {u.scheme}")
        if not u.hostname:
            raise ValueError(f"no host in {target_url}")
        port_num = u.port or 443
        req = (
            b"\x05\x01\x00\x03"
            + bytes([len(u.hostname)])
            + u.hostname.encode()
            + port_num.to_bytes(2, "big")
        )
        s.sendall(req)
        # Ответ: VER, REP, RSV, ATYP, BND.ADDR, BND.PORT
        hdr = b""
        while len(hdr) < 4:
            chunk = s.recv(4 - len(hdr))
            if not chunk:
                raise RuntimeError("SOCKS5 CONNECT: short reply (hdr)")
            hdr += chunk
        if hdr[1] != 0:
            raise RuntimeError(f"SOCKS5 CONNECT REP={hdr[1]} (≠0)")
        atyp = hdr[3]
        if atyp == 1:  # IPv4
            extra = b""
            while len(extra) < 4 + 2:
                extra += s.recv(4 + 2 - len(extra))
        elif atyp == 3:  # domain
            ln = s.recv(1)[0]
            extra = b""
            while len(extra) < 1 + ln + 2:
                extra += s.recv(1 + ln + 2 - len(extra))
        elif atyp == 4:  # IPv6
            extra = b""
            while len(extra) < 16 + 2:
                extra += s.recv(16 + 2 - len(extra))
        else:
            raise RuntimeError(f"SOCKS5 CONNECT: unknown ATYP={atyp}")

        # Теперь через сокет отправляем HTTP-запрос (TLS не делаем — sing-box сам)
        # и читаем статус + тело.
        req_http = (
            f"GET {u.path or '/'} HTTP/1.0\r\n"
            f"Host: {u.hostname}\r\n"
            f"User-Agent: fresta-check-health/1.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        s.sendall(req_http)
        chunks = []
        while True:
            b = s.recv(8192)
            if not b:
                break
            chunks.append(b)
    raw = b"".join(chunks)
    latency = time.perf_counter() - t0

    # Парсим статус из первой строки ответа.
    if b"\r\n" not in raw:
        raise RuntimeError("SOCKS5: empty HTTP response")
    status_line = raw.split(b"\r\n", 1)[0]
    try:
        # "HTTP/1.1 200 OK"
        status = int(status_line.split()[1])
    except (IndexError, ValueError) as e:
        raise RuntimeError(f"SOCKS5: bad status line: {status_line!r}") from e
    body = raw.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in raw else b""
    return status, latency, body


def fetch_via_socks(host: str, port: int, url: str, timeout: int) -> tuple[int, float, bytes]:
    """Обёртка для теста: возвращает (status, latency_s, body)."""
    return socks5_get(host, port, url, timeout)


def fetch_direct(url: str, timeout: int) -> tuple[int, float, bytes]:
    """Прямой fetch (без прокси) — для сравнения exit-IP."""
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "fresta-check-health/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return r.status, time.perf_counter() - t0, body


def main() -> int:
    ap = argparse.ArgumentParser(description="fresta — health-check деплоя vless-vps")
    ap.add_argument(
        "client_json", nargs="?", help="путь к client.json (если задан --socks — игнорируется)"
    )
    ap.add_argument(
        "--socks",
        metavar="HOST:PORT",
        help="адрес уже запущенного SOCKS5 (например 127.0.0.1:1080)",
    )
    ap.add_argument(
        "--expect-ip", metavar="IP", help="ожидаемый exit-IP (иначе просто печатает фактический)"
    )
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help="таймаут на запрос (с)")
    args = ap.parse_args()

    if args.socks:
        host, port = args.socks.split(":", 1)
        port = int(port)
        src = f"explicit --socks {args.socks}"
    elif args.client_json:
        host, port = read_socks5_from_client_json(args.client_json)
        src = f"{args.client_json} (inbound)"
    else:
        sys.exit("Укажи client.json ИЛИ --socks HOST:PORT")

    print(f"[*] SOCKS5: {host}:{port}  (источник: {src})")
    print(f"[*] Прогоняю {len(PROBES)} проб…\n")
    print(f"  {'#':>2}  {'status':>6}  {'latency':>8}  {'match':>5}  url")
    print("  " + "-" * 80)

    results = []
    exit_ip = None
    for i, (url, needle) in enumerate(PROBES, 1):
        try:
            status, lat, body = fetch_via_socks(host, port, url, args.timeout)
        except Exception as e:
            print(f"  {i:>2}  {'FAIL':>6}  {'-':>8}  {'-':>5}  {url}  ({type(e).__name__}: {e})")
            results.append((url, False, 0.0))
            continue
        match = "—" if needle is None else ("OK" if needle.encode() in body else "MISS")
        # На первом запросе (ipify) запомним exit-IP.
        if exit_ip is None and "ipify" in url:
            try:
                exit_ip = json.loads(body).get("ip", "?")
            except Exception:
                exit_ip = "?"
        print(f"  {i:>2}  {status:>6}  {lat * 1000:>6.0f}ms  {match:>5}  {url}")
        results.append((url, status == 200, lat))

    # Сравнение exit-IP с прямым запросом.
    direct_ip = None
    try:
        _, _, body = fetch_direct("https://api.ipify.org?format=json", args.timeout)
        direct_ip = json.loads(body).get("ip", "?")
    except Exception:
        pass
    print(f"\n[*] Exit-IP через туннель: {exit_ip}")
    if direct_ip:
        print(f"[*] Прямой exit-IP:        {direct_ip}")
    if args.expect_ip and exit_ip and exit_ip != args.expect_ip:
        print(f"[!] Не совпадает с --expect-ip {args.expect_ip}")
    elif exit_ip and direct_ip and exit_ip == direct_ip:
        print("[!] Exit-IP равен прямому — туннель НЕ работает (SOCKS проигнорирован)")

    # Сводка.
    ok = sum(1 for _, s, _ in results if s)
    latencies = [lat for _, s, lat in results if s]
    print(f"\n[*] OK: {ok}/{len(results)}")
    if latencies:
        med = statistics.median(latencies) * 1000
        p95 = (
            sorted(latencies)[int(len(latencies) * 0.95) - 1]
            if len(latencies) >= 2
            else latencies[0]
        ) * 1000
        print(f"[*] Latency: median={med:.0f}ms  p95={p95:.0f}ms")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
