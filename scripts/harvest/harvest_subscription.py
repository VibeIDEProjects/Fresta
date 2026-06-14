#!/usr/bin/env python3
"""
fresta · harvest_subscription.py

Выжимает из VLESS-подписки агрегат, полезный для своего Reality-конфига:
  - whitelisted-SNI по частоте (их реально пропускает ТСПУ — переиспользуем);
  - распределение живых серверов по провайдерам (из меток конфигов);
  - статистику по security / type / fp.

НЕ дампит сами конфиги (это чужие операционные данные) — только агрегат.

Источник по умолчанию — публичная подписка zieng2/wl (обновляется почасово),
но можно скормить любой URL или локальный файл.

    python3 harvest_subscription.py                       # дефолтный источник
    python3 harvest_subscription.py path/or/url           # свой источник
    python3 harvest_subscription.py --sni-out sni.txt --report-out report.md

Зависимостей нет, только stdlib.
"""

import argparse
import base64
import collections
import ipaddress
import re
import sys
import urllib.parse as up
import urllib.request

DEFAULT_SRC = "https://raw.githubusercontent.com/zieng2/wl/main/vless_lite.txt"

# «Сильные» SNI — домены крупных сервисов, которые в whitelist у всех операторов.
# Остальные (домены самих операторов узлов) помечаем как осторожные.
STRONG_SNI_HINTS = (
    "yandex", "yandexcloud", "x5.ru", "vk.com", "vk.ru", "max.ru", "rutube",
    "ozon", "ozone", "kinopoisk", "kommersant", "perekrestok", "mail.ru",
    "sber", "gosuslugi", "wildberries", "avito",
)


def load(src):
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=30) as r:
            data = r.read()
    else:
        data = open(src, "rb").read()
    text = data.decode("utf-8", "replace")
    if "vless://" not in text:  # вероятно base64-подписка
        try:
            text = base64.b64decode(text + "===").decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
    return [l.strip() for l in text.splitlines() if l.strip().startswith("vless://")]


def provider_from_label(label):
    """'🇷🇺 Beget — #2' -> 'Beget'."""
    label = up.unquote(label)
    head = re.split(r"[—#]", label, 1)[0]          # отрезаем '— #N'
    head = re.sub(r"^[^0-9A-Za-zА-Яа-я.]+", "", head).strip()  # снять флаг/эмодзи
    return head or "?"


def is_strong(sni):
    """Hint встречается как отдельный доменный лейбл (между точками или по краям),
    а не как подстрока. Иначе 'rutube123.evil.ru' ложно матчит hint='rutube'."""
    s = sni.lower()
    return any(re.search(rf"(?:^|\.){re.escape(h)}(?:\.|$)", s)
               for h in STRONG_SNI_HINTS)


def harvest(lines):
    sni = collections.Counter()
    providers = collections.Counter()
    sec = collections.Counter()
    typ = collections.Counter()
    fp = collections.Counter()
    ip_hosts = dom_hosts = 0
    real = 0
    for l in lines:
        u = up.urlsplit(l)
        host = u.hostname or ""
        if host in ("0.0.0.0", "") or (u.username or "").startswith("00000000"):
            continue  # плейсхолдер
        real += 1
        q = dict(up.parse_qsl(u.query))
        s = q.get("sni") or q.get("host") or ""
        if s:
            sni[s] += 1
        sec[q.get("security", "-")] += 1
        typ[q.get("type", "-")] += 1
        fp[q.get("fp", "-")] += 1
        if u.fragment:
            providers[provider_from_label(u.fragment)] += 1
        try:
            ipaddress.ip_address(host)
            ip_hosts += 1
        except ValueError:
            dom_hosts += 1
    return {
        "real": real, "sni": sni, "providers": providers,
        "sec": sec, "typ": typ, "fp": fp,
        "ip_hosts": ip_hosts, "dom_hosts": dom_hosts,
    }


def report(h, src):
    out = []
    p = out.append
    p(f"# fresta · harvest-снимок подписки\n")
    p(f"Источник: `{src}`")
    p(f"Снимок точечный (подписка обновляется почасово — перезапусти для свежего).\n")
    p(f"Серверов: **{h['real']}** | хосты: {h['ip_hosts']} IP-литералов, "
      f"{h['dom_hosts']} доменных")
    p(f"security: {dict(h['sec'])} · type: {dict(h['typ'])} · fp: {dict(h['fp'])}\n")

    p("## Провайдеры (живые узлы)\n")
    p("| Провайдер | Узлов |")
    p("|-----------|------:|")
    for prov, c in h["providers"].most_common():
        p(f"| {prov} | {c} |")

    strong = [(s, c) for s, c in h["sni"].most_common() if is_strong(s)]
    weak = [(s, c) for s, c in h["sni"].most_common() if not is_strong(s)]
    p("\n## Whitelisted-SNI — сильные (крупные сервисы, бери эти)\n")
    p("| SNI | Частота |")
    p("|-----|--------:|")
    for s, c in strong:
        p(f"| `{s}` | {c} |")
    p("\n## SNI — осторожные (домены самих операторов узлов)\n")
    p("| SNI | Частота |")
    p("|-----|--------:|")
    for s, c in weak:
        p(f"| `{s}` | {c} |")
    p("\n> Сильные SNI — кандидаты для нашего Reality-конфига (whitelisted у всех "
      "операторов). Осторожные могут быть whitelisted не везде — проверяй probe'ом.")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Выжать SNI и провайдеров из VLESS-подписки")
    ap.add_argument("src", nargs="?", default=DEFAULT_SRC, help="URL или файл подписки")
    ap.add_argument("--sni-out", help="записать сильные SNI (по одному в строке)")
    ap.add_argument("--report-out", help="записать markdown-отчёт")
    args = ap.parse_args()

    lines = load(args.src)
    if not lines:
        sys.exit("Не нашёл vless:// конфигов в источнике.")
    h = harvest(lines)

    # консольная сводка
    print(f"Серверов: {h['real']} | IP-литералов: {h['ip_hosts']}, доменных: {h['dom_hosts']}")
    print(f"security={dict(h['sec'])} type={dict(h['typ'])} fp={dict(h['fp'])}")
    print("\nПровайдеры:")
    for prov, c in h["providers"].most_common():
        print(f"  {c:3}  {prov}")
    print(f"\nУникальных SNI: {len(h['sni'])} (сильных: "
          f"{sum(1 for s in h['sni'] if is_strong(s))})")
    for s, c in h["sni"].most_common(15):
        tag = "★" if is_strong(s) else " "
        print(f"  {tag} {c:3}  {s}")

    if args.sni_out:
        strong = [s for s, _ in h["sni"].most_common() if is_strong(s)]
        with open(args.sni_out, "w", encoding="utf-8") as f:
            f.write("# Сильные whitelisted-SNI (harvest из подписки). По одному в строке.\n")
            f.write("\n".join(strong) + "\n")
        print(f"\n[+] SNI -> {args.sni_out} ({len(strong)} шт.)")
    if args.report_out:
        with open(args.report_out, "w", encoding="utf-8") as f:
            f.write(report(h, args.src))
        print(f"[+] отчёт -> {args.report_out}")


if __name__ == "__main__":
    main()
