# fresta

> Свет проходит даже сквозь щель.


[![CI](https://github.com/fresta/fresta/actions/workflows/tests.yml/badge.svg)](https://github.com/fresta/fresta/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](pyproject.toml)
[![stdlib-only](https://img.shields.io/badge/dependencies-stdlib--only-green.svg)](#зависимости)

> **⚠️ Badges:** owner в URL-ах — placeholder `fresta`. При публикации на GitHub
> замени на свой `<owner>` одним поиском-по-репо: `fresta/fresta` → `<owner>/fresta`.
> CI badges заработают после первого push в `main`.

Инструмент доступа к открытому интернету в условиях операторских **белых списков**
(РФ, мобильные сети). Идея: найти и переиспользовать «щель» — инфраструктуру, чьи IP
оператор обязан пропускать, и пустить через неё свой трафик.

Название — `fresta` (порт. «щель в ставнях, через которую пробивается свет»).

## Как работает белый список (против чего мы)

Двухуровневая фильтрация, по умолчанию drop-all:

- **L3** — CIDR-фильтр по IP. Пакет не к разрешённой подсети дропается ещё до DPI.
- **L7** — DPI смотрит SNI в TLS ClientHello; домен в чёрном списке → RST.

Маскировка протокола (Reality, обфускация) против L3 бесполезна: блокировка идёт по
адресу назначения, до того как протокол себя проявит. Работает только транспорт,
физически идущий **на whitelisted-IP**. В РФ это прежде всего Yandex Cloud (≈каждый
пятый IP в списке), а также VK, Selectel, Timeweb, Ростелеком.

## Структура

Код в `scripts/` разложен по **тематическим подпапкам** (recon / harvest / deploy /
relay / tests). Подробная карта — `scripts/README.md`. Кратко:

```
fresta/
├── README.md                   ← этот файл
├── scripts/                    ← код (см. scripts/README.md)
│   ├── recon/                  Фаза 0: разведка (GO/NO-GO по whitelist-доменам)
│   ├── harvest/                harvest'ы: zieng2/wl (SNI) + openlibrecommunity/twl (IP)
│   ├── deploy/                 Метод 1: VLESS+Reality — генер + деплой на VPS
│   ├── relay/                  Метод 2: Yandex Cloud relay (handler + клиент)
│   ├── tests/                  smoke-тесты (60+ кейсов) + run_tests.{sh,ps1} + probe_reality.py
│   └── README.md               ← карта scripts/
└── docs/                       ← документация
    ├── README.md               ← карта docs/
    ├── knowledge.md            ← прочитать первым (контекст-хэндофф)
    ├── specification.md        идея, threat model, архитектура
    ├── ROADMAP.md              чек-лист: что гонять где
    └── manuals/                пошаговые гайды по методу (карта — manuals/README.md)
        ├── vless-vps/         Метод 1: VLESS+Reality на VPS
        │   ├── deploy.md      quickstart + troubleshooting
        │   └── reality-params.md
        ├── ycloud-function/   Метод 2: YC Functions relay
        │   └── deploy.md
        └── recon/             Phase 0: разведка
            └── twl-harvest.md
```

## Компоненты

| Файл | Что | Фаза |
|------|-----|------|
| `docs/specification.md` | Идея, threat model, архитектура, роадмап | — |
| `docs/ROADMAP.md` | Чек-лист: что сделано и что погонять где | — |
| `docs/knowledge.md` | Полный контекст-хэндофф проекта (читать первым) | — |
| `scripts/harvest/reports/harvest-report.md` | Снимок SNI/провайдеров из живой подписки zieng2/wl | — |
| `docs/manuals/vless-vps/deploy.md` | **vless-vps (Метод 1): quickstart + troubleshooting** (сценарии A/B) | 2 |
| `docs/manuals/vless-vps/reality-params.md` | Reality-параметры + генератор + ручной деплой | 2 |
| `docs/manuals/ycloud-function/deploy.md` | **ycloud-function (Метод 2): YC Functions relay + клиент** | 2 |
| `docs/manuals/recon/twl-harvest.md` | **harvest whitelisted-IP** (twl) | 0 |
| `scripts/recon/fresta_recon.py` | Recon: за каким провайдером сидят whitelisted-домены → GO/NO-GO | 0 |
| `scripts/recon/whitelist.txt` | Домены белого списка Минцифры (реконструкция по сервисам) | 0 |
| `scripts/recon/whitelist.sample.txt` | Пример формата ввода | 0 |
| `scripts/harvest/sni_candidates.txt` | Whitelisted-SNI для своего Reality-конфига (harvest) | 0 |
| `scripts/harvest/harvest_subscription.py` | Выжимает SNI + провайдеров из VLESS-подписки | 0 |
| `scripts/harvest/harvest_twl.py` | **harvest whitelisted-IP** из openlibrecommunity/twl → ips.txt / subnets.txt | 0 |
| `scripts/harvest/twl-data/` | Выход harvest'а: ips.txt (≈44k IP), subnets.txt (41 /24), report.md, meta.json | 0 |
| `scripts/deploy/fresta_gen_vless.py` | **Генератор** Xray/sing-box/vless:// для VLESS+Reality | 2 |
| `scripts/deploy/deploy_vps.sh` | **Серверный деплой** Метода 1: ставит Xray, кладёт конфиг, открывает порт, рестарт | 2 |
| `scripts/deploy/quickstart.sh` | **Локальный одноступенчатый деплой**: генер → scp → deploy → scp обратно | 2 |
| `scripts/deploy/configs/default/` | Пример сгенерированного набора (демо) | 2 |
| `scripts/deploy/configs/remote-fresta/` | PoC-набор для fresta.ru (end-to-end пройден) | 2 |
| `scripts/relay/yc_function/handler.py` | Relay-функция на Yandex Cloud (fetch-on-behalf) | 2 |
| `scripts/relay/fresta_client.py` | Локальный клиент к relay: CLI + HTTP-proxy | 2 |
| `scripts/tests/test_*.py` | Smoke-тесты (60+ кейсов), ловят регрессии | — |
| `scripts/tests/probe_reality.py` | TLS-probe ко всем whitelisted-SNI через sing-box SOCKS5 | — |
| `scripts/tests/run_tests.sh` / `.ps1` | Прогон всех тестов разом | — |

## Статус

- ✅ Имя, концепция, спека.
- ✅ Фаза 0: recon-скрипт (цель — российские провайдеры, Yandex Cloud во главе) + список доменов. Оффлайн-логика протестирована.
- ✅ Метод 2: минимальный serverless fetch-relay. Плумбинг протестирован end-to-end.
- ✅ Фаза 2 (Метод 1): **генератор** VLESS+Reality конфигов + **deploy-скрипты** (`deploy_vps.sh` + `quickstart.sh`).
- ✅ Фаза 2 (Метод 1): **PoC end-to-end на fresta.ru** — Xray v26.3.27 + sing-box 1.13.13, `curl --proxy socks5h https://api.github.com/zen` = 200 OK, exit-IP сменился на 89.253.255.108.
- ⬜ Фаза 2: деплой и прогон на **whitelisted-VPS** под мобильным каналом с белым списком.
- ⬜ Фаза 3: ротация фронтов (несколько VPS × несколько SNI × автоперебор).
- ✅ Подключить реальные whitelisted-IP: `scripts/harvest/harvest_twl.py` (43k+ IP из openlibrecommunity/twl).
- ⬜ Подключить реальные whitelisted-SNI под своего оператора (выжимка из twl по доменам — в планах).

## Быстрый старт

### Деплой Метода 1 (VLESS+Reality) одной командой

```bash
# Из корня репо. Скрипт сам сгенерит конфиги, зальёт на VPS, поставит Xray,
# откроет порт, рестартанёт сервис и вернёт client.json / links.txt тебе.
bash scripts/deploy/quickstart.sh --ssh user@your-vps.example.com
# Подробности, опции, troubleshooting — docs/manuals/vless-vps/deploy.md
```

**Нет whitelisted-VPS под рукой?** Используй **любой** доступный сервер — quickstart
такой же, архитектура работает, но под белым списком оператора пройдёт **только**
когда IP-адрес будет в whitelisted-подсети. PoC на fresta.ru: 89.253.255.108 — end-to-end
пройден, см. `scripts/deploy/configs/remote-fresta/` и `docs/ROADMAP.md`.

### Остальное (по компонентам)

```bash
# Фаза 0 — есть ли щель у твоего оператора (запускать под мобильным каналом)
python3 scripts/recon/fresta_recon.py scripts/recon/whitelist.txt --probe

# Метод 2 — проверить канал (деплой и детали в docs/manuals/ycloud-function/deploy.md)
python3 scripts/relay/fresta_client.py --check

# Фаза 2 (Метод 1) — сгенерировать конфиги без деплоя (например, для теста)
python3 scripts/deploy/fresta_gen_vless.py --exit-ip ВАШ.IP.ЛИТЕРАЛ --out configs/my-vps

# Фаза 0 — реальные whitelisted-IP от openlibrecommunity/twl (≈44k IP, 498 ASN)
python3 scripts/harvest/harvest_twl.py                       # полный harvest
python3 scripts/harvest/harvest_twl.py --providers yandex --min-subnet-density 0.7   # фильтр

# Smoke-тесты (60+ кейсов — ловят регрессии в recon/handler/gen_vless/harvest/twl)
bash scripts/tests/run_tests.sh          # Linux / macOS / WSL / Git Bash
powershell scripts/tests/run_tests.ps1   # Windows PowerShell
```

### Импорт `client.json` в sing-box

```bash
# Linux/macOS/WSL
mkdir -p ~/.config/sing-box
cp scripts/deploy/configs/<host>-<date>/client.json ~/.config/sing-box/config.json
sing-box check -c ~/.config/sing-box/config.json
sing-box run -c ~/.config/sing-box/config.json &
curl --proxy socks5h://127.0.0.1:1080 https://api.github.com/zen   # 200 OK
```

> **На Windows:** используй Git Bash или WSL для bash-скриптов; для sing-box есть
> `winget install SagerNet.sing-box`.

## Методы обхода (от простого к сложному)

1. **VLESS + Reality на РФ-VPS** — основной, стабильный. IP в whitelist + whitelisted-SNI + `fp=chrome`.
2. **Yandex Cloud Functions** (этот репо, Метод 2) — serverless fetch-relay, бесплатно, но не туннель.
3. **API Gateway + WebSocket → VPS** — настоящий туннель; вектор уже начали банить.
4. **olcRTC / xDNS** — экспериментальные (видеозвонки, DNS); см. openlibrecommunity.

Подробный разбор уровней фильтрации и методов — в `docs/specification.md` и статье
zarazaex на Хабре (habr.com/ru/articles/1027276).

## Зависимости

**Рантайм — stdlib-only.** Никаких `pip install` для пользователя; только Python 3.8+
(и `openssl` для X25519, `ssh`/`scp` для деплоя). Это сознательное решение: минимум
поверхности атаки, нулевая стоимость входа, одинаково работает на любом VPS.

**Dev-стек** (опционально, для контрибьюторов): `ruff` + `mypy` + `pytest` —
поднимается одной командой:
```bash
pip install -e .[dev]
make lint test
```

## Для контрибьюторов

- Читай [`CONTRIBUTING.md`](CONTRIBUTING.md) — там workflow, правила приёма PR, что НЕ принимаем.
- История изменений — [`CHANGELOG.md`](CHANGELOG.md).
- Лицензия — [`LICENSE`](LICENSE) (MIT).
- Issues — шаблоны [bug report](.github/ISSUE_TEMPLATE/bug_report.yml) и [feature request](.github/ISSUE_TEMPLATE/feature_request.yml).

## Рамка

Обход операторских ограничений и проксирование через чужой serverless — серая зона и
нарушение ToS провайдеров (функции/серверы сносят, идёт арм-рейс). Инструмент — для
доступа к открытому интернету; оценка рисков и решение на пользователе.
