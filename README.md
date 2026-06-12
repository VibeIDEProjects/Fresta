# fresta

> Свет проходит даже сквозь щель.

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

```
fresta/
├── README.md                 ← этот файл
├── scripts/                  ← код
│   ├── fresta_recon.py
│   ├── fresta_client.py
│   ├── harvest_subscription.py
│   ├── whitelist.txt
│   ├── whitelist.sample.txt
│   ├── sni_candidates.txt
│   └── yc_function/handler.py
└── docs/                     ← документация
    ├── specification.md
    ├── ROADMAP.md
    ├── fresta_relay_README.md
    ├── harvest-report.md
    └── knowledge.md
```

## Компоненты

| Файл | Что | Фаза |
|------|-----|------|
| `docs/specification.md` | Идея, threat model, архитектура, роадмап | — |
| `docs/ROADMAP.md` | Чек-лист: что сделано и что погонять где | — |
| `docs/fresta_relay_README.md` | Деплой и использование relay | 2 |
| `scripts/fresta_recon.py` | Recon: за каким провайдером сидят whitelisted-домены → GO/NO-GO | 0 |
| `scripts/whitelist.txt` | Домены белого списка Минцифры (реконструкция по сервисам) | 0 |
| `scripts/whitelist.sample.txt` | Пример формата ввода | 0 |
| `scripts/yc_function/handler.py` | Relay-функция на Yandex Cloud (fetch-on-behalf) | 2 |
| `scripts/fresta_client.py` | Локальный клиент: CLI + HTTP-proxy | 2 |
| `scripts/harvest_subscription.py` | Выжимает SNI + провайдеров из VLESS-подписки | 0 |
| `scripts/sni_candidates.txt` | Whitelisted-SNI для своего Reality-конфига | 0 |
| `docs/harvest-report.md` | Снимок: SNI и провайдеры из живой подписки | — |
| `docs/knowledge.md` | Полный контекст-хэндофф проекта (читать первым) | — |

## Статус

- ✅ Имя, концепция, спека.
- ✅ Фаза 0: recon-скрипт (цель — российские провайдеры, Yandex Cloud во главе) + список доменов. Оффлайн-логика протестирована.
- ✅ Метод 2: минимальный serverless fetch-relay. Плумбинг протестирован end-to-end.
- ⬜ Фаза 2: настоящий туннель (WS через API Gateway → VPS exit, либо VLESS+Reality на РФ-VPS).
- ⬜ Подключить реальные whitelisted-IP/SNI под своего оператора (репозиторий openlibrecommunity/twl).

## Быстрый старт

```bash
cd scripts

# Фаза 0 — есть ли щель у твоего оператора (запускать под мобильным каналом)
python3 fresta_recon.py whitelist.txt --probe

# Метод 2 — проверить канал (деплой и детали в docs/fresta_relay_README.md)
python3 fresta_client.py --check
```

## Методы обхода (от простого к сложному)

1. **VLESS + Reality на РФ-VPS** — основной, стабильный. IP в whitelist + whitelisted-SNI + `fp=chrome`.
2. **Yandex Cloud Functions** (этот репо, Метод 2) — serverless fetch-relay, бесплатно, но не туннель.
3. **API Gateway + WebSocket → VPS** — настоящий туннель; вектор уже начали банить.
4. **olcRTC / xDNS** — экспериментальные (видеозвонки, DNS); см. openlibrecommunity.

Подробный разбор уровней фильтрации и методов — в `docs/specification.md` и статье
zarazaex на Хабре (habr.com/ru/articles/1027276).

## Рамка

Обход операторских ограничений и проксирование через чужой serverless — серая зона и
нарушение ToS провайдеров (функции/серверы сносят, идёт арм-рейс). Инструмент — для
доступа к открытому интернету; оценка рисков и решение на пользователе.
