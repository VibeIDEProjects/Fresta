# fresta · scripts/

Код проекта, разложен по тематическим подпапкам. Каждая подпапка — самодостаточный
модуль: можно скопировать одну и пользоваться отдельно (с мини-поправкой путей).

## Карта

```
scripts/
├── README.md                   ← этот файл
│
├── recon/                      Фаза 0 — разведка (GO/NO-GO)
│   ├── fresta_recon.py         резолв whitelist-доменов → ASN → GO/NO-GO
│   ├── whitelist.txt           143 домена Минцифры (реконструкция)
│   └── whitelist.sample.txt    пример формата
│
├── harvest/                    открытые источники (whitelist-IP, SNI)
│   ├── harvest_subscription.py выжимка SNI из zieng2/wl
│   ├── harvest_twl.py          harvest whitelisted-IP из openlibrecommunity/twl
│   ├── sni_candidates.txt      сильные SNI (19 шт, harvest)
│   ├── twl-data/               выход harvest_twl: ips.txt / subnets.txt / report / meta
│   └── reports/                снимки harvest'ов (отчёты)
│       └── harvest-report.md   снимок подписки zieng2/wl (провайдеры, SNI по частоте)
│
├── deploy/                     Метод 1 — VLESS+Reality (генер + деплой + эксплуатация + аудит)
│   ├── fresta_gen_vless.py     генератор server.json / client.json / vless://
│   ├── deploy_vps.sh           серверный деплой (ставить Xray, открыть порт, рестарт)
│   ├── quickstart.sh           локальный одноступенчатый: генер + scp + deploy + scp
│   ├── check_health.py         health-check деплоя: SOCKS5 alive? exit-IP = IP VPS?
│   ├── bench.py                мини-бенчмарк (latency + throughput) туннеля
│   ├── rotate_keys.sh          ротация UUID/X25519/shortId на VPS без переустановки
│   ├── validate_config.py      stdlib-валидатор server.json / client.json по schemas/*.json
│   ├── diff_configs.py         diff двух server/client.json (UUID/ключи маскируются)
│   └── configs/                сгенерированные наборы
│       ├── default/            демо (CHANGE_ME.IP.LITERAL, плейсхолдеры)
│       └── remote-fresta/      PoC (89.253.255.108, end-to-end пройден)
│
├── relay/                      Метод 2 — serverless fetch-relay (Yandex Cloud)
│   ├── fresta_client.py        локальный клиент: CLI + HTTP-proxy
│   └── yc_function/handler.py  функция relay (deploy на Yandex Cloud)
│
├── check/                      pre-flight проверки окружения
│   └── sanity.py               python3, openssl, ssh, scp, xray, sing-box, yc, … (`--required-only` / `--json`)
│
└── tests/                      smoke-тесты (60+ кейсов) + run-скрипты
    ├── README.md               детали по каждому тесту
    ├── run_tests.sh            прогон (Linux/macOS/WSL/Git Bash)
    ├── run_tests.ps1           то же (Windows PowerShell)
    ├── probe_reality.py        TLS-probe к fresta.ru:8443 по SNI из harvest
    ├── test_gen_vless.py       10 кейсов
    ├── test_handler.py         14 кейсов
    ├── test_harvest.py         8 кейсов
    ├── test_harvest_twl.py     17 кейсов
    └── test_recon.py           11 кейсов
```

**Всего:** 60+ smoke-кейсов, сетевых зависимостей нет (только `test_handler` делает
один реальный fetch к `https://example.com/`), зависимостей нет (только stdlib).

## Что откуда и зачем

| Подпапка | Назначение | Документация |
|----------|-----------|--------------|
| `recon/`   | Phase 0: понять, есть ли щель у твоего оператора | `docs/specification.md` §6 |
| `harvest/` | Сбор живых whitelisted-IP/SNI из открытых источников | `docs/manuals/recon/twl-harvest.md`, `scripts/harvest/reports/harvest-report.md` |
| `deploy/`  | Phase 2: развернуть VPS-туннель (VLESS+Reality, метод vless-vps) + валидация/diff конфигов | `docs/manuals/vless-vps/deploy.md`, `docs/manuals/vless-vps/reality-params.md`, `schemas/*.json` |
| `relay/`   | Phase 2 (alt): бесплатный serverless fetch-relay (метод ycloud-function) | `docs/manuals/ycloud-function/deploy.md` |
| `check/`   | Pre-flight sanity-чек зависимостей (ssh/openssl/xray/…) перед деплоем | `Makefile` (`make sanity`) |
| `tests/`   | Ловят регрессии в каждом из вышеуказанных модулей | `docs/knowledge.md` §6 |

## Запуск (быстрый старт)

Из корня репо:

```bash
# Pre-flight: проверить, что на машине есть всё нужное
python3 scripts/check/sanity.py                    # или: make sanity

# Валидация server.json / client.json по schemas/*.schema.json
python3 scripts/deploy/validate_config.py scripts/deploy/configs/default/server.json
python3 scripts/deploy/validate_config.py scripts/deploy/configs/default/client.json

# Diff двух наборов (после rotate_keys — что изменилось)
python3 scripts/deploy/diff_configs.py OLD/new.json NEW/new.json

# Фаза 0: GO/NO-GO под мобильным каналом с белым списком
python3 scripts/recon/fresta_recon.py scripts/recon/whitelist.txt

# Harvest: реальные whitelisted-IP от openlibrecommunity/twl (~44k IP, 498 ASN)
python3 scripts/harvest/harvest_twl.py

# Метод 1: деплой VLESS+Reality на VPS (одной командой)
bash scripts/deploy/quickstart.sh --ssh user@your-vps.example.com

# Метод 1 (после деплоя): health-check / бенчмарк / ротация
python3 scripts/deploy/check_health.py scripts/deploy/configs/<host>-<date>
python3 scripts/deploy/bench.py
bash scripts/deploy/rotate_keys.sh user@your-vps.example.com

# Метод 2: проверка канала через YC relay
python3 scripts/relay/fresta_client.py --check

# Прогон всех тестов
bash scripts/tests/run_tests.sh            # Linux / macOS / WSL / Git Bash
powershell scripts/tests/run_tests.ps1     # Windows PowerShell
```

## Что НЕ нужно путать

- `scripts/harvest/whitelist.txt` vs `scripts/recon/whitelist.txt` — **разные** файлы:
  - `recon/whitelist.txt` = **домены** Минцифры (вход для recon).
  - `harvest/sni_candidates.txt` = **SNI** из zieng2/wl (вход для Reality-конфига).
  - `harvest/twl-data/ips.txt` = **IP** из openlibrecommunity/twl (выбор VPS-провайдера).
- `scripts/deploy/configs/default/` — демо с плейсхолдерами, **не** для деплоя.
- `scripts/deploy/configs/remote-fresta/` — реальный PoC, **не** использовать как шаблон
  (там утекли реальные ключи от fresta.ru).
- `scripts/check/sanity.py` — pre-flight чек **зависимостей** (есть ли в PATH python3/ssh/xray).
  Не путать с `fresta_recon.py` (Phase 0: есть ли щель у оператора).
- `scripts/deploy/validate_config.py` (форма конфигов: type/required/UUID/base64url) — **не**
  заменяет ручную проверку `xray run -test` / `sing-box check` (семантика рантайма).

## Какие файлы НЕ хранятся в репо

- `__pycache__/` — в `.gitignore`.
- `deploy/configs/<host>-<date>/` — твой **свой** деплой с реальными ключами, в `.gitignore`.
- `harvest/twl-data/{ips,subnets}.txt` — большие (~44k+ строк), в `.gitignore`.
- `harvest/twl-data/repo/` — клон twl, в `.gitignore`.
- `harvest/twl-data/{twl-harvest-report.md, meta.json}` — tracked (история harvest'ов).
- `fresta.egg-info/`, `fresta_cli.egg-info/`, `dist/` — артефакты сборки (`*.egg-info/`, `dist/` в `.gitignore`).
