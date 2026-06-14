# Changelog

Все значимые изменения проекта документируются здесь. Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added
- **Подготовка к PyPI** (этот коммит): Python-пакет `fresta/` с `__version__` + `py.typed`
  (PEP 561). `pyproject.toml` обновлён до PEP 621 + SPDX-лицензии (PEP 639) +
  `[project.scripts]` с 7 entry points (`fresta-recon`, `fresta-harvest-sni`,
  `fresta-harvest-twl`, `fresta-gen-vless`, `fresta-validate`, `fresta-sanity`,
  `fresta-diff`). `[tool.setuptools.package-data]` — `schemas/*.json` уходят в wheel
  (чтобы `validate_config.py` работал после `pip install`). dev extras дополнены
  `build`+`twine`. `.github/workflows/publish.yml` — авто-публикация на PyPI по тегу
  `v*.*.*` через Trusted Publishing (OIDC), с fallback на API-токен. `PUBLISH.md` —
  гайд для maintainer'а (проверка имени, настройка OIDC, release workflow, FAQ).
- **JSON Schema для конфигов** (закрывает техдолг): `schemas/server.schema.json` (Xray
  server.json: inbounds/outbounds/realitySettings) + `schemas/client.schema.json`
  (sing-box client.json: vless+reality+utls). Формальная валидация формы — type,
  required, enum, pattern (UUID, base64url, regex для SNI), format=uuid/ipv4.
- **`scripts/validate_config.py`** — stdlib-валидатор (без `jsonschema`).
  Авто-детект server↔client по полю `inbounds`/`outbounds`. Опция `--use-jsonschema`
  для полной поддержки (oneOf/allOf/if-then-else), если поставишь пакет.
- **`.pre-commit-config.yaml`** — ловушка ошибок ДО CI: ruff+format, trailing-WS,
  EOF-newline, check-yaml/json/toml, detect-private-key, **наш** хук
  `fresta-validate-config` (валидирует server/client.json при коммите).
- **`.gitattributes`** — нормализация LF/CRLF: `*.sh/*.py/*.md` → LF, `*.bat/*.ps1` → CR+LF.
  Больше никаких `\r` в bash-скриптах, никаких LF-багов в cmd.
- **`scripts/sanity.py`** — pre-flight check зависимостей: python3, openssl, ssh,
  scp, git, sshpass, curl, nc, jq, xray, sing-box, yc, schemas. Удобно перед первым
  запуском на новом ноуте. `--required-only` / `--json` режимы.
- **`scripts/diff_configs.py`** — diff двух server/client.json (или каталогов через `--dir`).
  Видно, что изменилось между старым и новым набором после `rotate_keys.sh`. Режимы
  `--summary-only` (только важное: UUID/ключи/shortId/порт) и `--json` (для CI).
  UUID и base64url-ключи маскируются по умолчанию (`--no-redact` отключает).
- **Makefile**: новые цели `make sanity`, `make validate`, `make diff OLD=… NEW=…`.

### Changed
- **README.md**: заполнены `<owner>` placeholder'ы в badge-URL (→ `fresta/fresta` —
  имя репо при публикации; в шапке README явная подсказка заменить на свой owner).
  Добавлен callout про badges.
- **CHANGELOG.md**: `[Unreleased]` и `[0.1.0]` ссылки `https://github.com/<owner>/fresta/…`
  → `https://github.com/fresta/fresta/…` (placeholder owner).

### Ранее в Unreleased
- **Реорганизация `scripts/`**: `check_health.py`, `bench.py`, `rotate_keys.sh` перенесены
  из корня `scripts/` в `scripts/deploy/`. Логика: все три — **post-deploy операции vless-vps**,
  рядом с `quickstart.sh` / `deploy_vps.sh` / `fresta_gen_vless.py` они образуют единый пайплайн.
  В корне `scripts/` остаются только подпапки-категории (`recon/`, `harvest/`, `deploy/`,
  `relay/`, `tests/`) + `README.md`.
- **DevEx / CI** (предыдущий коммит): `pyproject.toml` (PEP 621 + ruff + mypy + pytest),
  `.editorconfig`, `LICENSE` (MIT), `CHANGELOG.md` (Keep a Changelog), `CONTRIBUTING.md`,
  `.github/workflows/tests.yml` (тесты на ubuntu × py3.8–3.12 + windows-latest + ruff),
  `.github/dependabot.yml` (auto-PR для dev-зависимостей и GitHub Actions),
  `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.yml`, `Makefile` (12 целей).
  Рантайм остаётся stdlib-only; dev-стек поднимается одной командой `pip install -e .[dev]`.

## [0.1.0] - 2026-06-14

### Added
- **Phase 0 recon** (`scripts/recon/fresta_recon.py`): резолв whitelist-доменов → ASN/CDN →
  GO/NO-GO. Поддержка multi-ASN классификации (origin vs announcing).
- **Harvest SNI** из zieng2/wl (`scripts/harvest/harvest_subscription.py`): 19 сильных SNI,
  `sni_candidates.txt`, `harvest-report.md`.
- **Harvest whitelisted-IP** из openlibrecommunity/twl (`scripts/harvest/harvest_twl.py`):
  43811 IP в 498 ASN, top — Yandex Cloud (8224).
- **Phase 2 — Метод 1 (VLESS+Reality)**: `fresta_gen_vless.py` (генератор server/client.json +
  vless://-ссылок), `quickstart.sh` (одноступенчатый деплой), `deploy_vps.sh` (серверный
  деплой через ssh). End-to-end пройден на fresta.ru:8443 (`scripts/deploy/configs/remote-fresta/`).
- **Phase 2 — Метод 2 (Yandex Cloud Functions relay)**: `scripts/relay/yc_function/handler.py`
  (stateless fetch-relay, stdlib), `scripts/relay/fresta_client.py` (CLI + HTTP-proxy).
- **Smoke-тесты** (60+ кейсов): `test_recon.py` (11), `test_harvest.py` (8),
  `test_harvest_twl.py` (17), `test_gen_vless.py` (10), `test_handler.py` (14).
  Все 5/5 зелёные. `run_tests.sh` (bash) + `run_tests.ps1` (PowerShell).
- **`docs/`**: `knowledge.md` (полный контекст-хэндофф), `ROADMAP.md`, `specification.md`,
  `manuals/{recon,vless-vps,ycloud-function}/`.
- **PoC** на fresta.ru: 89.253.255.108, Xray v26.3.27 + sing-box 1.13.13, exit-IP
  подтверждён, `curl --proxy socks5h https://api.github.com/zen` = 200 OK.

### Security
- **Не утекают** ключи пользовательских деплоев (в `.gitignore`), только PoC-конфиги.

[Unreleased]: https://github.com/fresta/fresta/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fresta/fresta/releases/tag/v0.1.0
