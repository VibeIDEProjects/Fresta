# fresta · manuals/

Пошаговые гайды для пользователя. **Технические документы** (концепция, спека,
статус, данные) лежат в `../` (родительский `docs/`).

Мануалы сгруппированы **по методу обхода**. Рядом с «Метод N» в скобках — новое
имя-синоним (например, **vless-vps** = Метод 1). Оба имени валидны, но в
структуре `manuals/` используется **имя**, а не номер.

## Карта

| Метод (синоним) | Папка | Что внутри |
|-----------------|-------|------------|
| **vless-vps** (Метод 1) | [`vless-vps/`](vless-vps/) | VLESS+Reality на VPS — основной метод |
| **ycloud-function** (Метод 2) | [`ycloud-function/`](ycloud-function/) | Yandex Cloud Functions relay — бесплатный, только HTTP |
| **recon** (Phase 0) | [`recon/`](recon/) | Разведка: harvest whitelisted-IP из открытых источников |

## Что в каждой папке

### `vless-vps/` — Метод 1

| Мануал | Когда |
|--------|-------|
| **`deploy.md`** | Деплой одной командой через `quickstart.sh` / `deploy_vps.sh`. Сценарии A (любой сервер, PoC) / B (whitelisted-VPS, production). Опции, troubleshooting, импорт в sing-box. |
| `reality-params.md` | Параметры Reality: что значат `dest`, `serverNames`, `shortId`, `privateKey`/`publicKey`, `fp`. Генератор `fresta_gen_vless.py` (полный набор флагов). Ручной деплой Xray (если `quickstart.sh` не подходит). |

### `ycloud-function/` — Метод 2

| Мануал | Когда |
|--------|-------|
| **`deploy.md`** | Деплой serverless fetch-relay на Yandex Cloud Functions. `yc` CLI, токен-гейт, ограничения (только HTTP, не туннель). Локальный клиент `fresta_client.py` (CLI + HTTP-proxy). |

### `recon/` — Phase 0

| Мануал | Когда |
|--------|-------|
| **`twl-harvest.md`** | Harvest whitelisted-IP из openlibrecommunity/twl: фильтры по провайдерам / ASN, плотность /24, CI-режим. Выход: `ips.txt` (≈44k) / `subnets.txt` (41 /24) / `meta.json` / `twl-harvest-report.md`. |

## Как мануалы связаны

```
                  recon/twl-harvest.md
                  (выбор whitelisted-VPS провайдера)
                            ↓
vless-vps/deploy.md ←──── vless-vps/reality-params.md
(деплой одной        (Reality-параметры,
 командой)             ручной деплой)
        ↓
   sing-box / Shadowrocket

   ycloud-function/deploy.md
   (альтернатива: YC Functions, без VPS, только HTTP)
```

## Где технические детали

- **Концепция / модель угроз / статус / источники** — `../knowledge.md` (хэндофф),
  `../specification.md` (спека), `../ROADMAP.md` (статус).
- **Конкретные данные** (провайдеры, SNI по частоте) — `../../scripts/harvest/reports/harvest-report.md`
  (снимок zieng2/wl) и `../../scripts/harvest/twl-data/twl-harvest-report.md`
  (снимок twl).

## Что НЕ путать

- `vless-vps/deploy.md` (сценарии A/B, **скрипты**) ≠ `vless-vps/reality-params.md`
  (Reality изнутри, **генератор**). Один про автоматизацию, другой про ручную
  настройку. У них пересечение — описание SNI / IP-литералов; это нормально,
  читаются вместе.
- `recon/twl-harvest.md` — это **про скрипт `harvest_twl.py`** (открытый источник
  whitelisted-IP), а **не** про общую концепцию harvest'а.
  Для SNI-выжимки из zieng2/wl — `../../scripts/harvest/harvest_subscription.py`
  + `../../scripts/harvest/reports/harvest-report.md` (снимок).
- **«Метод 1» / «vless-vps»** и **«Метод 2» / «ycloud-function»** — это
  синонимы (нумерация и имена). В `manuals/` выбраны **имена** (понятнее).
  В `docs/knowledge.md` раздел 5 — сохранена **нумерация** (устоявшаяся
  терминология проекта).
