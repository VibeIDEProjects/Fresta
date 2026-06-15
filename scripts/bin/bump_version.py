"""Bump версии fresta: pyproject.toml + fresta/__init__.py.

Использование (из корня репо):
    python scripts/bin/bump_version.py 0.2.2
    python scripts/bin/bump_version.py 0.3.0
    python scripts/bin/bump_version.py       # интерактивный режим

Что делает:
    1. Проверяет, что версия в SemVer (X.Y.Z) и что X.Y.Z > текущей.
    2. Обновляет [project].version в pyproject.toml.
    3. Обновляет __version__ в fresta/__init__.py.
    4. Печатает summary: какие файлы изменены, какие строки, dry-run mode.

После bump:
    git add pyproject.toml fresta/__init__.py
    git commit -m "chore(release): <version>"
    git tag -a v<version> -m "<version> — <краткое summary>"
    git push --follow-tags
    # → CI publish.yml подхватит тег v*.*.* и зальёт на PyPI
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "fresta" / "__init__.py"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def current_version() -> str:
    """Читает version из [project] в pyproject.toml."""
    txt = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', txt, re.M)
    if not m:
        raise SystemExit(f"Не нашёл [project].version в {PYPROJECT}")
    return m.group(1)


def bump(new: str, *, dry_run: bool = False) -> tuple[str, str]:
    """Возвращает (old, new). Если dry_run=True — только печатает, не пишет."""
    if not SEMVER.match(new):
        raise SystemExit(f"Версия '{new}' не в SemVer (X.Y.Z)")

    old = current_version()
    new_tuple = tuple(int(x) for x in new.split("."))
    old_tuple = tuple(int(x) for x in old.split("."))
    if new_tuple <= old_tuple:
        raise SystemExit(f"Новая версия {new} должна быть > текущей {old}")

    print(f"bump: {old} -> {new}  (dry_run={dry_run})")

    # pyproject.toml
    ptxt = PYPROJECT.read_text(encoding="utf-8")
    ptxt2 = re.sub(
        r'^(version\s*=\s*")\d+\.\d+\.\d+(")',
        rf"\g<1>{new}\g<2>",
        ptxt,
        count=1,
        flags=re.M,
    )
    assert ptxt2 != ptxt, f"pyproject.toml: {old} -> {new} не применился"

    # fresta/__init__.py
    itxt = INIT.read_text(encoding="utf-8")
    itxt2 = itxt.replace(f'__version__ = "{old}"', f'__version__ = "{new}"')
    assert itxt2 != itxt, f"fresta/__init__.py: {old} -> {new} не применился"

    if not dry_run:
        PYPROJECT.write_text(ptxt2, encoding="utf-8", newline="")
        INIT.write_text(itxt2, encoding="utf-8", newline="")
        print("OK: pyproject.toml + fresta/__init__.py обновлены")
    else:
        print("(dry_run — файлы НЕ переписаны)")

    return old, new


def main(argv: list[str]) -> int:
    if len(argv) == 1:
        try:
            new = input("Новая версия (X.Y.Z): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nотменено", file=sys.stderr)
            return 130
    elif len(argv) == 2:
        new = argv[1]
    else:
        print("usage: bump_version.py [X.Y.Z]", file=sys.stderr)
        return 2

    dry_run = "--dry-run" in argv
    try:
        bump(new, dry_run=dry_run)
    except SystemExit as e:
        print(f"[ERR] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
