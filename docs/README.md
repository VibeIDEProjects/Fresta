# fresta · docs/

Документация проекта, разложена на **технические документы** (в этом каталоге)
и **пошаговые мануалы** (`manuals/`, сгруппированы по методу обхода).

## Карта

### Технические документы (в этом каталоге)

| Файл | Что | Для кого |
|------|-----|----------|
| **`knowledge.md`** | Контекст-хэндофф: зачем проект, как устроены белые списки, концепция, пивоты, источники, методы, статус, инженерные уроки. **Читать первым** новому инстансу / новому разработчику. | новые участники, ревью, быстрое погружение |
| `specification.md` | Проект-спека: threat model, архитектура, фазы, риски, рамки. | архитекторы, ревьюеры |
| `ROADMAP.md` | Чек-лист done/todo по фазам + где гонять. | трекер прогресса |
| `PUBLISH.md` | Гайд по публикации на PyPI: настройка OIDC, release workflow, FAQ. | maintainer (только для релиза) |

### Мануалы (`manuals/`)

Пошаговые гайды для пользователя, сгруппированы по **имени метода** (Метод 1 = `vless-vps`, Метод 2 = `ycloud-function`). Подробная карта — `manuals/README.md`.

| Метод | Папка | Что | Когда применять |
|-------|-------|-----|----------------|
| **vless-vps** (Метод 1) | `manuals/vless-vps/` | VLESS+Reality на VPS: деплой скриптом + Reality-параметры. | «Хочу туннель, шаг за шагом» |
| **ycloud-function** (Метод 2) | `manuals/ycloud-function/` | Serverless fetch-relay на Yandex Cloud Functions + клиент. | «Бесплатный relay, без VPS, только HTTP» |
| **recon** (Phase 0) | `manuals/recon/` | Harvest whitelisted-IP из openlibrecommunity/twl. | «Какие IP реально whitelisted у операторов» |

## Что читать в каком порядке

**Хочу быстро попробовать (PoC):**
1. `manuals/vless-vps/deploy.md` — сценарий A (любой сервер)
2. `manuals/vless-vps/reality-params.md` — что значат параметры

**Хочу запустить под белым списком:**
1. `manuals/recon/twl-harvest.md` — выбрать whitelisted-VPS провайдера
2. `manuals/vless-vps/deploy.md` — сценарий B (whitelisted-VPS)
3. `manuals/ycloud-function/deploy.md` — для бесплатной альтернативы (YC relay)

**Хочу разобраться в проекте (вносить правки, ревью):**
1. `knowledge.md` ← **первым**
2. `specification.md` — модель угроз
3. `ROADMAP.md` — где сейчас проект
4. `manuals/*/...` — по необходимости

## Что НЕ лежит в docs/

- Снимок harvest'а подписки zieng2/wl — `scripts/harvest/reports/harvest-report.md`
  (провайдеры, SNI по частоте; перегенерируй через
  `manuals/recon/twl-harvest.md` или `scripts/harvest/harvest_subscription.py`).
- Живой harvest-вывод twl (≈44k IP, топ-ASN) — `scripts/harvest/twl-data/twl-harvest-report.md`.
- Сгенерированные конфиги — `scripts/deploy/configs/<host>-<date>/`.
- История smoke-тестов — `scripts/tests/README.md`.
- Карта кода — `scripts/README.md`.
