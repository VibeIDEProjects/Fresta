#!/usr/bin/env python3
"""
fresta · diff_configs.py — сравнение двух server.json / client.json.

Полезно после `rotate_keys.sh`: посмотреть, что именно изменилось между старым
и новым набором (UUID? ключи? shortId? IP?). И при смене провайдера —
сравнить конфиги Timeweb и Selectel.

Использование:
    # сравнить два server.json:
    python3 scripts/diff_configs.py scripts/deploy/configs/old-2026-01/server.json
                                 scripts/deploy/configs/new-2026-06/server.json

    # сравнить каталоги (server ↔ server, client ↔ client, links ↔ links):
    python3 scripts/diff_configs.py --dir old-2026-01/ new-2026-06/

    # JSON-вывод (для CI / скриптов):
    python3 scripts/diff_configs.py --json old.json new.json

    # только summary (что изменилось, без полного содержимого):
    python3 scripts/diff_configs.py --summary-only old.json new.json

Зависимостей нет (только stdlib).
"""

import argparse
import difflib
import json
import os
import sys
from typing import Any


def load(path: str) -> Any:
    if not os.path.isfile(path):
        sys.exit(f"[!] нет файла: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def diff_dict(a: Any, b: Any, path: str = "$") -> list[tuple[str, Any, Any]]:
    """Рекурсивный diff двух JSON-структур.
    Возвращает список (path, old, new) для всех различий.
    'old' или 'new' = None, если поле отсутствует с одной из сторон.
    """
    diffs: list[tuple[str, Any, Any]] = []
    if type(a) != type(b):
        diffs.append((path, a, b))
        return diffs
    if isinstance(a, dict):
        for k in set(a) | set(b):
            child = f"{path}.{k}" if path != "$" else f"$.{k}"
            if k not in a:
                diffs.append((child, None, b[k]))
            elif k not in b:
                diffs.append((child, a[k], None))
            else:
                diffs.extend(diff_dict(a[k], b[k], child))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append((f"{path}.len", len(a), len(b)))
        for i, (ai, bi) in enumerate(zip(a, b)):
            diffs.extend(diff_dict(ai, bi, f"{path}[{i}]"))
    else:
        if a != b:
            diffs.append((path, a, b))
    return diffs


def redact(s: str) -> str:
    """Красная маркировка чувствительных значений (UUID / ключи / IP)."""
    s = str(s)
    if len(s) >= 40:                # base64url ключ (43 символа)
        return s[:8] + "..." + s[-4:]
    if len(s) == 36 and s.count("-") == 4:  # UUID
        return s[:8] + "..."
    return s


INTERESTING = {
    # server.json (Xray)
    "$.inbounds[0].settings.clients[0].id": "UUID клиента (server)",
    "$.inbounds[0].streamSettings.realitySettings.privateKey": "privateKey (server)",
    "$.inbounds[0].streamSettings.realitySettings.shortIds[0]": "первый shortId (server)",
    "$.inbounds[0].port": "порт inbound (server)",
    "$.inbounds[0].streamSettings.realitySettings.serverNames": "SNI список (server)",
    # client.json (sing-box)
    "$.outbounds[0].uuid": "UUID клиента (client)",
    "$.outbounds[0].tls.reality.public_key": "publicKey (client)",
    "$.outbounds[0].tls.reality.short_id": "shortId (client)",
    "$.outbounds[0].server_port": "порт inbound (client)",
    "$.outbounds[0].server": "exit IP (client)",
    "$.outbounds[0].tls.server_name": "SNI (client)",
}


def print_summary(diffs: list[tuple[str, Any, Any]]) -> None:
    """Сводка: какие «важные» поля изменились (UUID, ключи, shortId, IP)."""
    print("== Сводка изменений ==")
    changed_paths = {p: (o, n) for p, o, n in diffs}
    shown = 0
    for path, label in INTERESTING.items():
        if path in changed_paths:
            o, n = changed_paths[path]
            print(f"  [DIFF] {label}: {redact(o)!r} -> {redact(n)!r}")
            shown += 1
    if shown == 0:
        print("  важные поля (UUID/ключи/shortId/порт) НЕ изменились")


def print_full(diffs: list[tuple[str, Any, Any]], redact_secrets: bool) -> None:
    print(f"== Полный diff ({len(diffs)} изменений) ==")
    for path, old, new in diffs:
        o, n = (redact(old) if redact_secrets else repr(old)), \
               (redact(new) if redact_secrets else repr(new))
        if old is None:
            print(f"  + {path} = {n}")
        elif new is None:
            print(f"  - {path} = {o}")
        else:
            print(f"  ~ {path}: {o} -> {n}")


def main() -> int:
    ap = argparse.ArgumentParser(description="fresta · diff двух JSON-конфигов")
    ap.add_argument("old", help="путь к старому JSON-файлу или каталогу (с --dir)")
    ap.add_argument("new", help="путь к новому JSON-файлу или каталогу (с --dir)")
    ap.add_argument("--dir", action="store_true",
                    help="сравнивать каталоги: server<->server, client<->client, links<->links")
    ap.add_argument("--summary-only", action="store_true",
                    help="только сводка по важным полям (UUID/ключи/shortId/порт)")
    ap.add_argument("--no-redact", action="store_true",
                    help="НЕ маскировать UUID/ключи в выводе (для собственного дебага)")
    ap.add_argument("--json", action="store_true", help="машинный JSON-вывод")
    args = ap.parse_args()

    if args.dir:
        pairs = []
        for fname in ("server.json", "client.json", "links.txt"):
            a = os.path.join(args.old, fname)
            b = os.path.join(args.new, fname)
            if os.path.isfile(a) and os.path.isfile(b):
                pairs.append((fname, a, b))
        if not pairs:
            sys.exit("[!] в обоих каталогах не нашлось ни server.json, ни client.json, ни links.txt")
    else:
        pairs = [(os.path.basename(args.old), args.old, args.new)]

    all_diffs = {}
    for label, a, b in pairs:
        if label.endswith(".json"):
            da, db = load(a), load(b)
            diffs = diff_dict(da, db)
        else:
            with open(a, encoding="utf-8") as f:
                la = f.read().splitlines()
            with open(b, encoding="utf-8") as f:
                lb = f.read().splitlines()
            sm = difflib.unified_diff(la, lb, fromfile=a, tofile=b, lineterm="")
            diffs = list(sm)
            all_diffs[label] = diffs
            if args.json:
                continue
            print(f"\n=== {label} (text diff) ===")
            for line in diffs:
                print(line)
            continue
        all_diffs[label] = diffs
        if not diffs:
            if not args.json:
                print(f"\n=== {label} ===\n  (identical)")
            continue
        if not args.json:
            print(f"\n=== {label} ===")
            print_summary(diffs)
            if not args.summary_only:
                print()
                print_full(diffs, redact_secrets=not args.no_redact)

    if args.json:
        out = {}
        for label, diffs in all_diffs.items():
            if diffs and isinstance(diffs[0], tuple):
                out[label] = [
                    {"path": p, "old": (str(o) if o is not None else None),
                     "new": (str(n) if n is not None else None)}
                    for p, o, n in diffs
                ]
            else:
                out[label] = diffs
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
