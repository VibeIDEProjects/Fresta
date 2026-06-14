#!/usr/bin/env python3
"""
fresta · sanity.py — pre-flight чек зависимостей.

Проверяет, что на машине есть всё, что нужно для деплоя и работы с проектом.
Полезно перед первым запуском или после переезда на новый ноут.

Что проверяет:
  - python3 (>= 3.8)             — для запуска скриптов
  - openssl (>= 1.1.1)           — для X25519 (Reality)
  - ssh + scp                    — для деплоя
  - sshpass                      — опционально, для деплоя по паролю
  - git                          — для harvest_twl
  - curl                         — для health-check relay
  - yc (Yandex Cloud CLI)        — для Метода 2 (опционально)
  - xray + sing-box              — на сервере после деплоя (опционально)
  - json модуль (stdlib)         — для validate_config
  - наличие schema-файлов        — для validate_config

Использование:
    python3 scripts/sanity.py                  # все проверки, exit 0/1
    python3 scripts/sanity.py --required-only  # только обязательные (ssh, openssl, python)
    python3 scripts/sanity.py --json           # машинный вывод

Зависимостей нет (только stdlib + subprocess).
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys


# Обязательные = без них `quickstart.sh` / `fresta_gen_vless.py` / `harvest_twl.py` не работают.
# Опциональные = нужны только для конкретного метода/сценария.

CHECKS = [
    # ── обязательные ──────────────────────────────────────────────────────
    ("python3",      "python3",  "3.8+",    True,
     "для запуска всех скриптов (нужен stdlib)"),
    ("openssl",      "openssl",  "1.1.1+",  True,
     "для X25519 в fresta_gen_vless.py / rotate_keys.sh"),
    ("ssh",          "ssh",      "любая",   True,
     "для деплоя (quickstart.sh / deploy_vps.sh / rotate_keys.sh)"),
    ("scp",          "scp",      "любая",   True,
     "для копирования конфигов на сервер"),
    ("git",          "git",      "любая",   True,
     "для harvest_twl.py (клонирует openlibrecommunity/twl)"),
    # ── опциональные ─────────────────────────────────────────────────────
    ("sshpass",      "sshpass",  "любая",   False,
     "если деплой по ssh-паролю (иначе настрой ключ)"),
    ("curl",         "curl",     "любая",   False,
     "для Метода 2 (yc install) и health-check relay"),
    ("nc",           "nc",       "любая",   False,
     "для `nc -vz` проверки открытости порта"),
    ("jq",           "jq",       "любая",   False,
     "удобство: читать JSON в шелле"),
    ("xray",         "xray",     "любая",   False,
     "должен стоять на VPS (ставится deploy_vps.sh)"),
    ("sing-box",     "sing-box", "любая",   False,
     "клиент на устройстве/роутере"),
    ("yc",           "yc",       "любая",   False,
     "Yandex Cloud CLI (для Метода 2 — деплой функции)"),
]


# Per-tool подсказки (выводятся ТОЛЬКО если тул не нашёлся)
HINTS = {
    "openssl":  "OpenSSL 1.1.1+ для X25519: choco install openssl / brew install openssl / apt install openssl",
    "sshpass":  "sshpass для деплоя по паролю: apt install sshpass / brew install hudochenkov/sshpass/sshpass. "
                "Альтернатива: ssh-copy-id user@host (тогда ключ без пароля)",
    "nc":       "netcat для `nc -vz` проверки порта: choco install netcat / apt install netcat-openbsd",
    "jq":       "jq для JSON в шелле: choco install jq / apt install jq / scoop install jq",
    "xray":     "Xray ставится автоматически через scripts/deploy/deploy_vps.sh на VPS. Локально не нужен.",
    "sing-box": "sing-box — клиент: https://sing-box.sagernet.org / winget install SagerNet.sing-box",
    "yc":       "Yandex Cloud CLI для Метода 2: https://cloud.yandex.ru/docs/cli/quickstart",
}


# Схемы тоже считаем обязательными (для validate_config.py)
SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schemas")
REQUIRED_SCHEMAS = ["server.schema.json", "client.schema.json"]


def get_version(cmd: str) -> str:
    """Получить первую строку `cmd --version` (или '-' если не удалось)."""
    for flag in ("--version", "-V", "-version"):
        try:
            r = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout:
                return r.stdout.splitlines()[0].strip()[:80]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "-"


def python_version() -> tuple[str, bool]:
    v = platform.python_version()
    major, minor = (int(x) for x in v.split(".")[:2])
    return v, (major, minor) >= (3, 8)


def check_python() -> dict:
    v, ok = python_version()
    return {"name": "python3", "version": v, "ok": ok}


def check_openssl() -> dict:
    if not shutil.which("openssl"):
        return {"name": "openssl", "version": None, "ok": False}
    v = get_version("openssl")
    ok = any(s in v for s in ("OpenSSL 1.1.1", "OpenSSL 3", "OpenSSL 2"))
    return {"name": "openssl", "version": v, "ok": ok}


def check_cmd(name: str) -> dict:
    path = shutil.which(name)
    return {"name": name, "version": get_version(name) if path else None, "ok": path is not None}


def check_schemas() -> dict:
    missing = [s for s in REQUIRED_SCHEMAS if not os.path.isfile(os.path.join(SCHEMA_DIR, s))]
    return {"name": "schemas", "version": f"{len(REQUIRED_SCHEMAS) - len(missing)}/{len(REQUIRED_SCHEMAS)}",
            "ok": not missing, "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(description="fresta · pre-flight check зависимостей")
    ap.add_argument("--required-only", action="store_true",
                    help="проверять только обязательные (ssh, openssl, python, git, scp, schemas)")
    ap.add_argument("--json", action="store_true", help="машинный JSON-вывод")
    args = ap.parse_args()

    results = [check_python(), check_openssl(), check_cmd("ssh"), check_cmd("scp"), check_cmd("git")]

    if not args.required_only:
        results.extend([
            check_cmd("sshpass"), check_cmd("curl"), check_cmd("nc"), check_cmd("jq"),
            check_cmd("xray"), check_cmd("sing-box"), check_cmd("yc"),
        ])
    results.append(check_schemas())

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        all_ok = all(r["ok"] for r in results)
        return 0 if all_ok else 1

    # human-readable
    ok_count = sum(1 for r in results if r["ok"])
    print(f"fresta · pre-flight check ({ok_count}/{len(results)} OK)\n")
    print(f"  {'NAME':<14} {'VERSION':<60} STATUS")
    print("  " + "-" * 80)
    for r in results:
        status = "OK ✅" if r["ok"] else "FAIL ❌"
        v = r.get("version") or "(не найден)"
        print(f"  {r['name']:<14} {v:<60} {status}")
        if r["name"] == "schemas" and not r["ok"]:
            for m in r.get("missing", []):
                print(f"      ↳ не хватает: {m}")

    # per-tool подсказки (только для реально отсутствующих)
    if ok_count < len(results):
        failed = [r["name"] for r in results if not r["ok"]]
        print(f"\n[!] {len(failed)} проблем. Что-то может не работать.")
        hints = {h: HINTS[h] for h in failed if h in HINTS}
        if hints:
            print("    Подсказки (только по отсутствующим):")
            for k, v in hints.items():
                print(f"      • {k}: {v}")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
