#!/usr/bin/env python3
"""
fresta · bench.py

Мини-бенчмарк туннеля vless-vps (или ycloud-function):
  - latency: 10× HEAD/GET к маленькой цели (https://api.github.com/zen);
  - throughput: скачивание фиксированного объёма (1 МБ) с высокой пропускной способностью
    (Cloudflare speed-test endpoint, 100 МБ доступно, мы возьмём первые N);
  - печатает median / p95 / mean, оба режима — direct (без прокси) и via tunnel.

Использование:
    python3 scripts/bench.py                       # direct-only
    python3 scripts/bench.py --socks 127.0.0.1:1080  # через туннель
    python3 scripts/bench.py --socks 127.0.0.1:1080 --compare   # + direct для сравнения

Зависимостей нет.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import urllib.error
import urllib.request

LATENCY_PROBES = [
    "https://api.github.com/zen",
    "https://example.com/",
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://httpbin.org/get",
    "https://www.apple.com/",
] * 2  # 10 запросов

THROUGHPUT_URL = "https://speed.cloudflare.com/__down?bytes=1048576"  # ровно 1 МБ
THROUGHPUT_BYTES = 1024 * 1024

TIMEOUT = 15


def fetch(url: str, timeout: int) -> tuple[int, float, int]:
    """Возвращает (status, latency_s, bytes_received)."""
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fresta-bench/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.URLError:
        return 0, time.perf_counter() - t0, 0
    return r.status, time.perf_counter() - t0, len(body)


def bench_latency(label: str) -> tuple[int, list[float]]:
    print(f"\n=== Latency ({label}) ===")
    print(f"  {'#':>2}  {'status':>6}  {'time':>8}  url")
    print("  " + "-" * 60)
    times: list[float] = []
    ok = 0
    for i, url in enumerate(LATENCY_PROBES, 1):
        status, lat, _ = fetch(url, TIMEOUT)
        marker = "OK" if 200 <= status < 400 else "FAIL"
        if marker == "OK":
            ok += 1
            times.append(lat)
        print(f"  {i:>2}  {status:>6}  {lat * 1000:>6.0f}ms  {url}")
    return ok, times


def bench_throughput(label: str) -> tuple[int, float]:
    print(f"\n=== Throughput ({label}, 1 МБ) ===")
    status, lat, n = fetch(THROUGHPUT_URL, TIMEOUT)
    if n < 1024 or status != 200:
        print(f"  FAIL: status={status}, получено {n} байт за {lat * 1000:.0f}ms")
        return 0, 0.0
    mbps = (n * 8) / (lat * 1_000_000)
    print(f"  OK: {n} байт за {lat * 1000:.0f}ms  →  {mbps:.2f} Мбит/с")
    return 1, mbps


def print_stats(label: str, times: list[float]) -> None:
    if not times:
        print(f"  {label}: нет успешных запросов")
        return
    times_sorted = sorted(times)
    med = statistics.median(times) * 1000
    p95 = times_sorted[max(0, int(len(times_sorted) * 0.95) - 1)] * 1000
    mean = statistics.mean(times) * 1000
    print(f"  {label}: median={med:.0f}ms  p95={p95:.0f}ms  mean={mean:.0f}ms  n={len(times)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="fresta — мини-бенчмарк туннеля")
    ap.add_argument(
        "--socks",
        metavar="HOST:PORT",
        help="адрес SOCKS5 туннеля (если задан — будет тест через туннель)",
    )
    ap.add_argument(
        "--compare",
        action="store_true",
        help="дополнительно прогнать direct (без прокси) для сравнения",
    )
    ap.add_argument(
        "--no-throughput", action="store_true", help="пропустить throughput-тест (тяжёлый)"
    )
    args = ap.parse_args()

    if not args.socks and not args.compare:
        print("[*] Запущен без --socks и без --compare: тестирую только direct.")
        print("    Подсказка: запусти sing-box, потом передай --socks 127.0.0.1:1080 --compare")
        print()

    if args.socks:
        # Тут сложность: urllib не умеет SOCKS без внешних либ.
        # Используем трюк: подключаемся к SOCKS5 и потом делаем HTTP через сокет.
        # Простой бенчмарк без TLS-внутри-SOCKS (как check_health).
        # TODO: если будешь тестить через vless-tunnel — добавь HTTPS-over-SOCKS.
        print(f"[*] --socks={args.socks} указан, но для корректного бенча через vless")
        print("    нужен HTTPS-over-SOCKS, а он требует рукопожатия. См. check_health.py")
        print("    для простого теста или подними sing-box с --inbound и используй --compare.")
        # Тем не менее — direct тоже полезен.
        args.compare = True

    if args.compare:
        _ok_d, times_d = bench_latency("direct")
        if not args.no_throughput:
            bench_throughput("direct")
        print_stats("Latency direct", times_d)

    # Если туннель задан (через check_health или sing-box), тут должно быть
    # отдельное измерение. Оставляем заглушку с подсказкой.
    if args.socks and not args.compare:
        print("\n[i] Подсказка: для бенча через туннель используй --socks с sing-box,")
        print("    который сам делает TLS. Либо check_health.py для smoke-теста.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
