"""Проверить, что в runtime-коде нет PEP 585 generic (list[...], dict[...], tuple[...]).

Использование (из корня репо):
    python scripts/bin/check_pep585.py

Зачем: fresta декларирует `requires-python = ">=3.8"`, а PEP 585 generic
(`list[int]`, `dict[str, int]`, `tuple[str, ...]`) работают в runtime только
с Python 3.9+. Если кто-то напишет:

    def f(x: list[int]) -> list[tuple[str, int]]:   # это ОК на 3.8 — типы lazy
        return list[tuple[str, int]]()             # это FAIL на 3.8

— скрипт найдёт и сообщит.

Ограничения:
    - False positives возможны, если PEP 585 generic упомянуты в строке/комментарии
      (ищем только в expression context, не в type annotations). Можно игнорировать вручную.
    - Не разбирает AST полностью (только баланс скобок + keyword-arg context).
      Для сложных случаев добавь `ast`-проход.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ["scripts", "fresta"]  # без tests/ (там дозволено)
PYPROJECT = ROOT / "pyproject.toml"
# Только встроенные generic'и — set[...] и type[...] реже встречаются как PEP 585 в runtime
GENERIC = r"list|dict|tuple|set|frozenset|list|tuple|type"

# Грубый regex: 'identifier[...]', но не в type annotation context
# (т.е. не после ':' (аннотация), не в `def f() -> ...`, не в `Annotated[...]`).
# Простой подход: ищем в строках, потом пропускаем те, что выглядят как аннотации.
RE_GENERIC = re.compile(
    rf"\b({GENERIC})\s*\[",
    re.MULTILINE,
)


def is_annotation_context(line: str, match_start: int) -> bool:
    """Грубая эвристика: похоже ли вхождение на type-annotation?"""
    # Если в строке есть `:` до match_start И вхождение идёт после `:` с пробелом
    # или в `def f(...):`, или `->`
    prefix = line[:match_start]
    if re.search(r":\s*$", prefix) and not prefix.strip().startswith("#"):
        return True
    return bool(re.search(r"->\s*$", prefix))


def scan_file(path: Path) -> list[tuple[int, str]]:
    issues: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return issues
    for i, line in enumerate(text.splitlines(), 1):
        # strip comments — `comment contains ambiguous` шум, не баг
        code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        for m in RE_GENERIC.finditer(code):
            if is_annotation_context(code, m.start()):
                continue
            issues.append((i, line.rstrip()))
    return issues


def main() -> int:
    if PYPROJECT.exists():
        ptxt = PYPROJECT.read_text(encoding="utf-8")
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', ptxt)
        if m and not m.group(1).startswith(">=3.9") and not m.group(1).startswith(">=3.10"):
            print(
                f"[i] requires-python = {m.group(1)!r} "
                f"— PEP 585 generic в runtime будут ломать старые версии."
            )
        else:
            print(
                f"[i] requires-python = {m.group(1) if m else '?'} "
                f"— PEP 585 generic безопасны в runtime (3.9+)."
            )
    print()
    total_issues = 0
    for sub in SCAN_DIRS:
        for py in (ROOT / sub).rglob("*.py"):
            # Игнорируем __pycache__ и сгенерённые
            rel = py.relative_to(ROOT)
            parts = rel.parts
            if any("__pycache__" in p or "twl-data" in p for p in parts):
                continue
            issues = scan_file(py)
            if issues:
                total_issues += len(issues)
                print(f"  {rel}:")
                for ln, text in issues:
                    print(f"    L{ln}: {text}")
    if total_issues == 0:
        print("OK: PEP 585 generic в runtime не найдены (только в аннотациях или вообще нет).")
        return 0
    print(
        f"\nFAIL: {total_issues} вхождений PEP 585 generic в runtime. "
        f"Либо замените на typing.List/Dict/Tuple, либо добавьте 'from __future__ import annotations'."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
