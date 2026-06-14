"""fresta · инструмент доступа к открытому интернету под российскими операторскими
белыми списками (мобильные сети).

Метапакет: содержит только версию и метаинформацию. Вся функциональность
лежит в `scripts/` и доступна через CLI-скрипты (см. pyproject.toml
[project.scripts] для entry points). После `pip install fresta` пользователь
получает в PATH: `fresta-recon`, `fresta-harvest-sni`, `fresta-gen-vless`,
`fresta-validate`, `fresta-sanity`, `fresta-diff` и т.д.

Использование:
    import fresta
    print(fresta.__version__)
    print(fresta.__doc__)
"""

# `__version__` синхронизирован с [project.version] в pyproject.toml.
# Должен быть ОДИН источник правды — сейчас это pyproject.toml,
# и сюда мы его копируем руками при bump (см. docs/PUBLISH.md).
__version__ = "0.2.0"

# Краткое описание для `python -c "import fresta; help(fresta)"`
__summary__ = "Обход операторских IP-белых списков через whitelisted-инфраструктуру (Yandex Cloud, РФ-VPS)"

# Маркеры, помогающие авто-тестам/докам понять, что это не библиотека для импорта,
# а набор CLI-скриптов.
__all__ = ["__version__", "__summary__"]
