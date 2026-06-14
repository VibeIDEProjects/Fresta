#!/usr/bin/env python3
"""
fresta · validate_config.py — валидация server.json / client.json по JSON Schema.

Свой велосипед (без `jsonschema`): базовая проверка типов, required, enum, pattern,
minLength, format=uuid, format=ipv4. Покрывает всё, что мы реально генерим
в fresta_gen_vless.py. Для сложных схем (oneOf/allOf/if-then-else) — ставь
`pip install jsonschema` и используй как альтернативу (`--use-jsonschema`).

Использование:
    # один файл (авто-детект server|client по полю "inbounds" vs "outbounds"):
    python3 scripts/validate_config.py scripts/deploy/configs/my-vps/server.json
    python3 scripts/validate_config.py scripts/deploy/configs/my-vps/client.json

    # явно указать схему:
    python3 scripts/validate_config.py --schema server path/to/server.json
    python3 scripts/validate_config.py --schema client path/to/client.json

    # exit code: 0 = OK, 1 = ошибки, 2 = usage

    # --use-jsonschema — если установлена `jsonschema`, использовать её (полная поддержка).
    #   pip install jsonschema
"""

import argparse
import json
import os
import re
import sys
import uuid
from typing import Any


# Схемы лежат в <корень>/schemas/ (рядом с scripts/), относительно deploy/ — ../../schemas.
SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "schemas")





# ── валидаторы форматов ─────────────────────────────────────────────────────

RE_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
RE_IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
RE_DOMAIN = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$")


def _check_format(value: str, fmt: str) -> bool:
    if fmt == "uuid":
        return bool(RE_UUID.match(value))
    if fmt == "ipv4":
        if not RE_IPV4.match(value):
            return False
        return all(0 <= int(p) <= 255 for p in value.split("."))
    if fmt == "hostname":
        return bool(RE_DOMAIN.match(value))
    return True  # неизвестный формат — не валидируем (предупреждение наверху)


# ── ядро валидатора ────────────────────────────────────────────────────────

class ValidationError:
    def __init__(self, path: str, msg: str):
        self.path = path  # JSON-pointer-like: "$.inbounds[0].port"
        self.msg = msg

    def __str__(self):
        return f"  {self.path}: {self.msg}"


def _validate(value: Any, schema: dict, path: str = "$") -> list[ValidationError]:
    errs: list[ValidationError] = []

    # type
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        py_types = {"string": str, "integer": int, "number": (int, float),
                    "boolean": bool, "array": list, "object": dict, "null": type(None)}
        ok = False
        for want in types:
            py_t = py_types.get(want)
            if py_t is None:
                continue
            if want == "integer" and isinstance(value, bool):
                continue  # bool — это int в Python, но в JSON — отдельный тип
            if isinstance(value, py_t):
                ok = True
                break
        if not ok:
            errs.append(ValidationError(path, f"expected type {t}, got {type(value).__name__}"))
            return errs  # дальше не проверяем (некоторые проверки упадут)

    # const
    if "const" in schema and value != schema["const"]:
        errs.append(ValidationError(path, f"expected const {schema['const']!r}, got {value!r}"))

    # enum
    if "enum" in schema and value not in schema["enum"]:
        errs.append(ValidationError(path, f"value {value!r} not in enum {schema['enum']}"))

    # format (только для строк)
    if "format" in schema and isinstance(value, str):
        if not _check_format(value, schema["format"]):
            errs.append(ValidationError(path, f"value {value!r} not valid format={schema['format']}"))

    # pattern (regex)
    if "pattern" in schema and isinstance(value, str):
        if not re.search(schema["pattern"], value):
            errs.append(ValidationError(path, f"value {value!r} does not match pattern {schema['pattern']!r}"))

    # minLength / maxLength
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(ValidationError(path, f"string length {len(value)} < minLength {schema['minLength']}"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(ValidationError(path, f"string length {len(value)} > maxLength {schema['maxLength']}"))

    # minimum / maximum (для чисел)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(ValidationError(path, f"value {value} < minimum {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(ValidationError(path, f"value {value} > maximum {schema['maximum']}"))

    # minItems / maxItems (для массивов)
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(ValidationError(path, f"array length {len(value)} < minItems {schema['minItems']}"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(ValidationError(path, f"array length {len(value)} > maxItems {schema['maxItems']}"))

    # required + properties (для объектов)
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errs.append(ValidationError(f"{path}.{req}", "required property missing"))

        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs.extend(_validate(v, props[k], f"{path}.{k}"))
            elif schema.get("additionalProperties") is False:
                errs.append(ValidationError(f"{path}.{k}", "additional property not allowed"))

    # items (для массивов)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errs.extend(_validate(item, schema["items"], f"{path}[{i}]"))

    return errs


# ── вход ────────────────────────────────────────────────────────────────────

def detect_schema(path: str) -> str:
    """По содержимому JSON определяем, server это или client."""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if "inbounds" in cfg and isinstance(cfg["inbounds"], list) and cfg["inbounds"]:
        if cfg["inbounds"][0].get("protocol") == "vless" and \
           cfg["inbounds"][0].get("streamSettings", {}).get("security") == "reality":
            return "server"
    if "outbounds" in cfg and isinstance(cfg["outbounds"], list) and cfg["outbounds"]:
        if cfg["outbounds"][0].get("type") == "vless" and \
           "reality" in cfg["outbounds"][0].get("tls", {}):
            return "client"
    raise ValueError(f"не могу определить тип {path} (нет ни 'inbounds' ни 'outbounds' с reality)")


def main() -> int:
    ap = argparse.ArgumentParser(description="fresta · валидация server/client.json по JSON Schema")
    ap.add_argument("path", help="путь к server.json или client.json")
    ap.add_argument("--schema", choices=["server", "client"],
                    help="явно указать тип (по умолчанию — авто-детект)")
    ap.add_argument("--use-jsonschema", action="store_true",
                    help="использовать библиотеку jsonschema, если установлена "
                         "(pip install jsonschema). Покрывает больше кейсов.")
    args = ap.parse_args()

    if not os.path.isfile(args.path):
        print(f"[!] нет файла: {args.path}", file=sys.stderr)
        return 2

    kind = args.schema or detect_schema(args.path)
    schema_path = os.path.join(SCHEMA_DIR, f"{kind}.schema.json")
    if not os.path.isfile(schema_path):
        print(f"[!] нет схемы: {schema_path}", file=sys.stderr)
        return 2

    with open(args.path, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    print(f"[*] {args.path} → {kind} schema ({schema_path})")

    if args.use_jsonschema:
        try:
            import jsonschema
            from jsonschema import Draft202012Validator
            v = Draft202012Validator(schema)
            errs = []
            for e in v.iter_errors(cfg):
                errs.append(ValidationError(
                    ".".join(str(p) for p in e.absolute_path) or "$",
                    e.message,
                ))
        except ImportError:
            print("[!] --use-jsonschema: пакет 'jsonschema' не установлен", file=sys.stderr)
            print("    pip install jsonschema", file=sys.stderr)
            return 2
    else:
        errs = _validate(cfg, schema)

    if errs:
        print(f"[FAIL] найдено ошибок: {len(errs)}")
        for e in errs:
            print(str(e))
        return 1
    print("[OK] валидно")
    return 0


if __name__ == "__main__":
    sys.exit(main())
