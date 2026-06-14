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
    python3 scripts/check/sanity.py              # все проверки, exit 0/1
    python3 scripts/check/sanity.py --required-only  # только обязательные
    python3 scripts/check/sanity.py --json           # машинный вывод
    fresta-sanity                                  # через entry point после pip install

Зависимостей нет (только stdlib + subprocess).
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys


CHECKS = [
    ("python3",      "python3",  "3.8+",    True,  "для запуска всех скриптов"),
    ("openssl",      "openssl",  "1.1.1+",  True,  "для X25519 в fresta_gen_vless.py"),
    ("ssh",          "ssh",      "любая",   True,  "для деплоя"),
    ("scp",          "scp",      "любая",   True,  "для копирования конфигов"),
    ("git",          "git",      "любая",   True,  "для harvest_twl.py"),
    ("sshpass",      "sshpass",  "любая",   False, "деплой по паролю"),
    ("curl",         "curl",     "любая",   False, "для Метода 2 / health-check"),
    ("nc",           "nc",       "любая",   False, "проверка открытости порта"),
    ("jq",           "jq",       "любая",   False, "JSON в шелле"),
    ("xray",         "xray",     "любая",   False, "на VPS (ставится deploy_vps.sh)"),
    ("sing-box",     "sing-box", "любая",   False, "клиент"),
    ("yc",           "yc",       "любая",   False, "Yandex Cloud CLI (Метод 2)"),
]

HINTS = {
    "openssl":  "choco install openssl / brew install openssl / apt install openssl",
    "sshpass":  "apt install sshpass / brew install hudochenkov/sshpass/sshpass. Альтернатива: ssh-copy-id",
    "nc":       "choco install netcat / apt install netcat-openbsd",
    "jq":       "choco install jq / apt install jq / scoop install jq",
    "xray":     "ставится автоматически через deploy_vps.sh на VPS. Локально не нужен.",
    "sing-box": "https://sing-box.sagernet.org / winget install SagerNet.sing-box",
    "yc":       "https://cloud.yandex.ru/docs/cli/quickstart",
}

# scripts/check/ → scripts/ → repo root → schemas/
SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "schemas")
REQUIRED_SCHEMAS = ["server.schema.json", "client.schema.json"]


def get_version(cmd):
    for flag in ("--version", "-V", "-version"):
        try:
            r = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout:
                return r.stdout.splitlines()[0].strip()[:80]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "-"


def python_version():
    v = platform.python_version()
    major, minor = (int(x) for x in v.split(".")[:2])
    return v, (major, minor) >= (3, 8)


def check_python():
    v, ok = python_version()
    return {"name": "python3", "version": v, "ok": ok}


def check_openssl():
    if not shutil.which("openssl"):
        return {"name": "openssl", "version": None, "ok": False}
    v = get_version("openssl")
    ok = any(s in v for s in ("OpenSSL 1.1.1", "OpenSSL 3", "OpenSSL 2"))
    return {"name": "openssl", "version": v, "ok": ok}


def check_cmd(name):
    path = shutil.which(name)
    return {"name": name, "version": get_version(name) if path else None, "ok": path is not None}


def check_schemas():
    missing = [s for s in REQUIRED_SCHEMAS if not os.path.isfile(os.path.join(SCHEMA_DIR, s))]
    return {"name": "schemas", "version": f"{len(REQUIRED_SCHEMAS) - len(missing)}/{len(REQUIRED_SCHEMAS)}",
            "ok": not missing, "missing": missing}


def main():
    ap = argparse.ArgumentParser(description="fresta · pre-flight check зависимостей")
    ap.add_argument("--required-only", action="store_true",
                    help="только обязательные (ssh, openssl, python, git, scp, schemas)")
    ap.add_argument("--json", action="store_true", help="машинный JSON-вывод")
    args = ap.parse_args()

    results = [check_python(), check_openssl(), check_cmd("ssh"), check_cmd("scp"), check_cmd("git")]
    if not args.required_only:
        results.extend([check_cmd("sshpass"), check_cmd("curl"), check_cmd("nc"), check_cmd("jq"),
                        check_cmd("xray"), check_cmd("sing-box"), check_cmd("yc")])
    results.append(check_schemas())

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(r["ok"] for r in results) else 1

    ok_count = sum(1 for r in results if r["ok"])
    print(f"fresta · pre-flight check ({ok_count}/{len(results)} OK)\n")
    print(f"  {'NAME':<14} {'VERSION':<60} STATUS")
    print("  " + "-" * 80)
    for r in results:
        status = "OK" if r["ok"] else "FAIL"
        v = r.get("version") or "(не найден)"
        print(f"  {r['name']:<14} {v:<60} {status}")
        if r["name"] == "schemas" and not r["ok"]:
            for m in r.get("missing", []):
                print(f"      missing: {m}")

    if ok_count < len(results):
        failed = [r["name"] for r in results if not r["ok"]]
        print(f"\n[!] {len(failed)} проблем(ы). Подсказки:")
        for k in failed:
            if k in HINTS:
                print(f"    {k}: {HINTS[k]}")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
