# fresta · roadmap

Статус и «что где гонять». Конкретные команды — в `README.md` (быстрый старт) и
`docs/manuals/ycloud-function/deploy.md` (деплой + клиент). Здесь — только чек-лист.
Пути даны от корня репозитория.

**Три среды запуска:**

- 💻 **локально** (ноут / песочница) — оффлайн-логика и сборка.
- 📱 **мобильный канал под белым списком** (раздать с телефона на ноут) — всё, что
  должно подтвердить *реальную проходимость*.
- ☁️ **Yandex Cloud** — деплой функции.

---

## Фаза 0 — разведка (GO / NO-GO)

- [x] 💻 recon-скрипт, цель = РФ-провайдеры (Yandex Cloud во главе)
- [x] 💻 оффлайн-логика протестирована мной (CF-range / classify / verdict / парсинг Cymru)
- [x] 💻 `scripts/recon/whitelist.txt` — 143 домена (реконструкция по сервисам Минцифры)
- [x] 💻 harvest SNI/провайдеров из живой подписки (zieng2/wl) → `scripts/harvest/sni_candidates.txt` + `scripts/harvest/reports/harvest-report.md`
- [x] 💻 **harvest реальных whitelisted-IP** из openlibrecommunity/twl → \scripts/harvest/harvest_twl.py\ + \scripts/harvest/twl-data/\ (≈44k IP, 498 ASN, 41 /24 с плотностью ≥ 50%). Гайд: \docs/manuals/recon/twl-harvest.md\.
- [x] 💻 **выбор VPS-провайдера под Метод 1** (2026-06-14): анализ twl-data + Team Cymru.
      **Yandex Cloud (AS200350, 8 224 whitelisted-IP) — приоритет №1.** Selectel/Timeweb — запасные, Beget исключён.
      VK (5 032 IP, 8 /24 с плотностью 60-83%) — лидер по плотности, но не сдаёт VPS конечным.
- [ ] 📱 **погонять \python3 scripts/recon/fresta_recon.py scripts/recon/whitelist.txt --probe\** ← *твой ближайший шаг*
> **Autopilot (deferred):** требует мобильной сети с белым списком (нет в текущей среде)
      Подтвердить: за доменами реально Yandex Cloud/Selectel и probe-handshake проходит сквозь whitelist.

## Метод 2 — serverless fetch-relay

- [x] 💻 \scripts/relay/yc_function/handler.py\ + \scripts/relay/fresta_client.py\ написаны
- [x] 💻 плумбинг протестирован мной end-to-end на моке (fetch 200 / токен-гейт / SSRF-блок)

- [ ] ☁️ **задеплоить функцию** (yc CLI — см. `docs/manuals/ycloud-function/deploy.md`)
> **Autopilot (deferred):** требует аккаунта Yandex Cloud / денег на VPS (human-only)
- [ ] 📱 **`python3 scripts/relay/fresta_client.py --check`** — подтвердить, что `functions.yandexcloud.net`
> **Autopilot (deferred):** требует мобильной сети с белым списком (нет в текущей среде)
      проходит у твоего оператора и exit-IP = Яндекса
- [ ] 📱 прогнать реальный заблокированный ресурс через CLI
> **Autopilot (deferred):** требует мобильной сети с белым списком (нет в текущей среде)

## Фаза 2 — настоящий туннель (Метод 1)

> **О терминологии:** «Фаза 2» — стадия roadmap, «Метод 1» — VLESS+Reality
> (см. `docs/knowledge.md`, раздел 5). То, что мы делаем в Фазе 2, **и есть**
> Метод 1. Метод 2 (YC Functions) реализован отдельно и описан в
>> `docs/manuals/ycloud-function/deploy.md`.

**Вектор: VLESS + Reality на РФ-VPS** (стабильнее, чем WS через API Gateway —
тот уже начали банить, см. `docs/knowledge.md`, раздел 5).

- [x] 💻 `scripts/deploy/fresta_gen_vless.py` — генератор server.json / client.json / vless://-ссылок
      под whitelisted-SNI (X25519 через openssl, плейсхолдеры для IP/ключей если надо)
- [x] 💻 `scripts/deploy/configs/default/` — пример сгенерированного набора на все 19 SNI
- [x] 💻 `docs/manuals/vless-vps/reality-params.md` — деплой Xray на VPS + импорт в sing-box / Shadowrocket
- [x] 🧪 **PoC end-to-end на fresta.ru (89.253.255.108): 2026-06-14**
      - Xray v26.3.27 поднят, systemd, порт 8443 (443 занят docker-proxy)
      - TLS-probe: 19/19 whitelisted-SNI ответили валидным TLS (`scripts/tests/probe_reality.py`)
      - sing-box 1.13.13 локально → Reality-туннель → `curl https://api.github.com/zen` = 200 OK,
        тело `Favor focus over features.`
      - exit-IP: `65.185.73.55` (мой) → `89.253.255.108` (наш сервер) — трафик реально идёт через туннель
      - артефакты PoC: `scripts/deploy/configs/remote-fresta/` (client.json / client_full.json / links.txt / info.txt)
- [x] 🛠 **deploy-автоматизация** (2026-06-14):
      - `scripts/deploy/deploy_vps.sh` — серверный деплой (Xray install + config + iptables/ufw/firewalld + systemd)
      - `scripts/deploy/quickstart.sh` — локальный одноступенчатый (генерация → scp → deploy → scp обратно)
      - `docs/manuals/vless-vps/deploy.md` — полный гайд с двумя сценариями (любой сервер / whitelisted-VPS) + troubleshooting
- [ ] ☁️ поднять VPS на whitelisted-провайдере (Timeweb / Selectel / Beget / Yandex),
> **Autopilot (deferred):** требует аккаунта Yandex Cloud / денег на VPS (human-only)
      проверить плотность /24 по `scripts/harvest/reports/harvest-report.md` + `scripts/harvest/twl-data/subnets.txt`
- [ ] 💻 `bash scripts/deploy/quickstart.sh --ssh root@<новый-VPS>` — сгенерировать и задеплоить
> **Autopilot (deferred):** требует готового VPS (см. пункт выше)
- [ ] 💻 клиент (sing-box) на устройство или роутер, или `links.txt` в Shadowrocket/v2rayNG
> **Autopilot (deferred):** требует готового VPS + устройство пользователя (human-only)
- [ ] 📱 проверить проходимость и стабильность под мобильным каналом с белым списком
> **Autopilot (deferred):** требует мобильной сети с белым списком (нет в текущей среде)
- [ ] ⏭ перейти к Фазе 3: ротация фронтов
> **Autopilot (deferred):** все пункты Фазы 3 заблокированы (см. ниже)

---

### Легенда статусов

- [x] сделано
- [ ] предстоит
- ← помечен ближайший шаг

### Что уже можно делать прямо сейчас

1. 💻☁️ Развернуть Метод 2 на Yandex Cloud (если есть аккаунт).
2. 📱 Под мобильным каналом прогнать `fresta_recon.py --probe` и `fresta_client.py --check`.
   Это закрывает GO/NO-GO Фазы 0 и подтверждает рабочий канал Метода 2.

---

## DevEx / CI / инфра (2026-06-14) — этот коммит

Что добавлено одним пакетом (всё подробно — в `CHANGELOG.md`):

- [x] 💻 **`pyproject.toml`** — PEP 621, конфиги **ruff** (линт+формат) + **mypy** + **pytest**.
      `pip install -e .[dev]` поднимает dev-стек одной командой.
- [x] 💻 **`.editorconfig`** — единые правила (LF, UTF-8, 4 spaces, final newline).
- [x] 💻 **`LICENSE`** (MIT) + **`CHANGELOG.md`** (Keep a Changelog) + **`CONTRIBUTING.md`**.
- [x] 💻 **`.github/workflows/tests.yml`** — CI: smoke-тесты на каждом push (ubuntu × py3.8–3.12, windows-latest) + ruff.
- [x] 💻 **`.github/dependabot.yml`** — авто-PR для dev-зависимостей и GitHub Actions.
- [x] 💻 **`.github/ISSUE_TEMPLATE/{bug_report,feature_request}.yml`** — структурированные шаблоны.
- [x] 💻 **`Makefile`** — `make help | test | lint | fix | harvest-all | deploy | relay-check | health | bench | rotate | clean`.
- [x] 💻 **`scripts/deploy/check_health.py`** — health-check деплоя vless-vps:
      SOCKS5 alive? exit-IP правильный? 5 синтетических проб, latency median/p95.
- [x] 💻 **`scripts/deploy/bench.py`** — мини-бенчмарк (latency × 10 + 1 МБ throughput).
- [x] 💻 **`scripts/deploy/rotate_keys.sh`** — ротация UUID/X25519/shortId на сервере
      **без переустановки Xray** (бэкап → patch → `xray run -test` → `systemctl restart`).
- [x] 🐛 **фикс:** `fresta_gen_vless.py` (шаблон `README_TMPL`) — устаревшая ссылка
      `docs/harvest-report.md` → актуальная на `../../../harvest/reports/harvest-report.md`.
- [x] 🛠 **.gitignore** — добавлены `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`, `.idea/`, `*.egg-info/`, `htmlcov/`, `.coverage`.

### Аудит / валидация / DX (этот коммит) — 2026-06-14

- [x] 💻 **`schemas/server.schema.json`** + **`schemas/client.schema.json`** — JSON Schema
      для Xray server.json и sing-box client.json (закрывает техдолг валидации формы).
- [x] 💻 **`scripts/validate_config.py`** — stdlib-валидатор по схемам (без зависимости
      на `jsonschema`). Авто-детект server↔client. Опция `--use-jsonschema` для полной
      поддержки (oneOf/allOf/if-then-else).
- [x] 💻 **`.pre-commit-config.yaml`** — хуки ruff+format, trailing-WS, EOF-newline,
      check-yaml/json/toml, detect-private-key, наш `fresta-validate-config`. Ставится
      `pip install pre-commit && pre-commit install`. Ловит ошибки ДО CI.
- [x] 💻 **`.gitattributes`** — нормализация LF/CRLF: `*.sh/*.py/*.md/*.yml/*.json` → LF,
      `*.bat/*.ps1/*.cmd` → CR+LF. Никаких `\r` в bash-скриптах.
- [x] 💻 **`scripts/sanity.py`** — pre-flight check: python3, openssl, ssh, scp, git,
      sshpass, curl, nc, jq, xray, sing-box, yc, schemas. Режимы `--required-only` /
      `--json`. Полезно при первом запуске на новой машине.
- [x] 💻 **`scripts/diff_configs.py`** — diff двух server/client.json (или каталогов
      через `--dir`). После `rotate_keys.sh` — видно, что изменилось (UUID, ключи,
      shortId, порт). Режимы `--summary-only` / `--json`. UUID/base64url маскируются
      по умолчанию (`--no-redact` отключает).
- [x] 💻 **Makefile**: `make sanity`, `make validate`, `make diff OLD=… NEW=…`.
- [x] 🛠 README.md: `<owner>` placeholder'ы в badge-URL → `fresta/fresta` (имя репо)
      + callout с инструкцией «замени на свой owner при публикации».
- [x] 🛠 CHANGELOG.md: `<owner>` placeholder'ы в ссылках → `fresta/fresta`.

### Подготовка к PyPI (этот коммит)

- [x] 💻 **`fresta/__init__.py`** — Python-пакет с `__version__ = "0.2.0"` + `__summary__`.
      После `pip install fresta` доступен `import fresta; fresta.__version__`.
- [x] 💻 **`fresta/py.typed`** — маркер PEP 561 (сигнализирует type-checker'ам).
- [x] 🛠 **pyproject.toml**:
  - **SPDX-лицензия** по PEP 639: `license = "MIT"` + `license-files = ["LICENSE"]`
    (раньше был устаревший `license = { text = "MIT" }`).
  - **`[project.scripts]`** — 7 entry points, попадают в `$PATH` после `pip install`:
    `fresta-recon`, `fresta-harvest-sni`, `fresta-harvest-twl`, `fresta-gen-vless`,
    `fresta-validate`, `fresta-sanity`, `fresta-diff`. .sh-скрипты (ssh+scp зависимости)
    НЕ входят — пользователь берёт их из исходников или `python -m fresta.scripts.<name>`.
  - **`[tool.setuptools.packages]`** — явно перечислены `fresta` + `scripts` + 5 sub-packages
    (чтобы entry points работали).
  - **`[tool.setuptools.package-data]`** — `schemas/*.json` уйдут в wheel
    (иначе `validate_config.py` после `pip install` не найдёт схем).
  - **dev extras** дополнены: `build>=1.0` + `twine>=5.0` для ручной публикации.
- [x] 💻 **`.github/workflows/publish.yml`** — авто-публикация wheel+sdist на PyPI
      при пуше тега `v*.*.*` через **Trusted Publishing (OIDC)**.
      Триггеры: tag push, `workflow_dispatch` (с `to_testpypi` / `dry_run` флагами).
      Fallback на API-токен закомментирован (если OIDC не настроен).
- [x] 💻 **`PUBLISH.md`** — полный гайд для maintainer'а: проверка имени на PyPI,
      настройка trusted publishing, pre-release чек, release workflow (tag → push →
      auto-publish), post-release, ручной аплоад через `twine`, FAQ с частыми проблемами.

### Что дальше (Phase 3, ротация фронтов)

- [ ] 💻 Фаза 3: `scripts/orchestrate.py` — N VPS × M SNI × автоперебор (live-config, мониторинг, health-check каждые 60 с, автопереключение).
> **Autopilot (deferred):** требует N работающих VPS для оркестрации (нет в наличии)
- [ ] 💻 `scripts/wly_check.py` — проверка IP через `wly.zarazaex.xyz/check?ip=…` (оффлайн-сигнал не 100%).
> **Autopilot (deferred):** эндпоинт wly.zarazaex.xyz недоступен (404/403)
- [ ] 💻 `scripts/bench_aggregated.py` — бенчмарк по всем развёрнутым VPS, json-вывод для сравнения.
> **Autopilot (deferred):** требует работающих VPS для бенчмарка (нет в наличии)
- [ ] 📱 **whitelisted-VPS** деплой + прогон под мобильным каналом — главный открытый TODO.
> **Autopilot (deferred):** требует мобильной сети с белым списком (нет в текущей среде)
- [ ] 📱 Метод 2 — задеплоить функцию на YC, прогнать под мобильным каналом.
> **Autopilot (deferred):** требует мобильной сети с белым списком (нет в текущей среде)

### Техдолг (когда-нибудь)

- [ ] Перевести smoke-тесты на **pytest** (`make test-pytest` уже работает, но классический `run_tests.{sh,ps1}` остаётся для Windows-надёжности).
> **Autopilot (deferred):** make test-pytest уже работает; классические скрипты остаются для совместимости


- [ ] Перевести печать прогресса в `harvest_*` и `recon` на `rich` (зависимость — обсуждаемо).
> **Autopilot (deferred):** добавляет внешнюю зависимость (обсуждаемо)
- [ ] Перевести `urllib` → `httpx` (если согласимся на внешнюю зависимость; сейчас всё stdlib-only).
> **Autopilot (deferred):** добавляет внешнюю зависимость (обсуждаемо); стек stdlib-only работает
