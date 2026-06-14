# fresta · Метод 2: relay на Yandex Cloud Functions

> **О терминологии:** в проекте «Метод 2» и «Фаза 2» — разные оси. «Метод 2» —
> это YC Functions (см. `docs/knowledge.md`, раздел 5), «Фаза 2» в
> `docs/ROADMAP.md` — это **Метод 1** (VLESS+Reality на VPS). Не путать.

Минимальный рабочий кусок: stateless **fetch-relay**. Клиент шлёт функции конверт
с запросом, функция ходит в открытый интернет со своего yandexcloud-IP (он в белом
списке) и возвращает ответ. Единственное исходящее соединение клиента — к
`functions.yandexcloud.net` (IP и SNI whitelisted).

Это НЕ туннель сырого TCP. Голые Functions так не умеют (stateless, без дуплекса).
Годится для HTTP/HTTPS-запросов: страницы, API, curl. Доказывает, что канал жив.
Прозрачный туннель (браузер, произвольный TCP) — следующий шаг, см. «Дальше».

Пути ниже даны от корня репозитория.

## Файлы

- `scripts/relay/yc_function/handler.py` — функция (stdlib, без зависимостей).
- `scripts/relay/fresta_client.py` — локальный клиент: CLI + минимальный HTTP-proxy.

## Что нужно

- Аккаунт Yandex Cloud (при регистрации дают грант, его хватит надолго).
- Установленный `yc` CLI и `yc init` (привязка к folder).
- Python 3.8+ локально.

## Деплой функции

```bash
cd scripts/relay/yc_function
zip /tmp/fresta-fn.zip handler.py

yc serverless function create --name fresta-relay

yc serverless function version create \
  --function-name fresta-relay \
  --runtime python312 \
  --entrypoint handler.handler \
  --memory 256m \
  --execution-timeout 30s \
  --source-path /tmp/fresta-fn.zip \
  --environment FRESTA_TOKEN=ПРИДУМАЙ_ДЛИННЫЙ_СЕКРЕТ

# сделать публично вызываемой (наш токен-гейт её защищает)
yc serverless function allow-unauthenticated-invoke --name fresta-relay

# узнать URL вызова
yc serverless function get --name fresta-relay --format json | grep -i invoke
# -> https://functions.yandexcloud.net/<function-id>
```

## Клиент

Из корня репо (любой cwd):

```bash
export FRESTA_FUNC_URL="https://functions.yandexcloud.net/<function-id>"
export FRESTA_TOKEN="ТОТ_ЖЕ_СЕКРЕТ_ЧТО_В_ФУНКЦИИ"

# 1. Проверка канала — покажет exit-IP (должен быть Яндекса)
python3 scripts/relay/fresta_client.py --check

# 2. Достать заблокированную страницу/API
python3 scripts/relay/fresta_client.py https://www.google.com/
python3 scripts/relay/fresta_client.py https://api.github.com/zen

# 3. POST с телом
python3 scripts/relay/fresta_client.py -X POST https://httpbin.org/post -d '{"a":1}'

# 4. Локальный HTTP-proxy (только http:// цели — для curl/apt)
python3 scripts/relay/fresta_client.py --proxy 8080
http_proxy=http://127.0.0.1:8080 curl http://example.com
```

Запускать лучше под тем самым мобильным каналом с белым списком — тогда `--check`
заодно подтвердит, что `functions.yandexcloud.net` реально проходит у твоего оператора.

## Ограничения минимального режима

- **Fetch-on-behalf, не туннель.** Функция терминирует TLS до цели сама, то есть
  видит твой трафик в открытом виде. Это ТВОЯ функция, но факт держи в голове.
- **HTTPS только как цель CLI**, не как прозрачный прокси: браузерный `CONNECT`
  вернёт 501. Для браузера целиком нужен настоящий туннель (см. ниже).
- **Без сырого TCP/UDP.** Только HTTP-семантика.
- Потолок тела 6 МБ, таймаут 20–30 с, free tier: ~1M вызовов/мес.

## Безопасность

- `FRESTA_TOKEN` держи в секрете: функция публично вызываемая, токен — единственное,
  что отделяет её от роли открытого прокси (чужой трафик + счёт за вызовы).
- В функции есть SSRF-защита: отказ на приватные/служебные адреса (метаданные
  Яндекса `169.254.*`, loopback, RFC1918).

## Дальше (апгрейд до настоящего туннеля)

1. **API Gateway + WebSocket → VPS exit** (статья, Метод 3): даёт дуплекс, поверх
   него поднимается реальный SOCKS/TCP. Минус — этот вектор уже начали банить.
2. **VLESS + Reality на российском VPS** (Метод 1): IP в whitelist + whitelisted-SNI
   (`storage.yandex.net`, `userapi.com`, `cdnvideo.ru`…) + `fp=chrome`. Самый стабильный.
3. Реальные whitelisted-IP/SNI под своего оператора — из репозитория
   openlibrecommunity/twl, кормить ими `scripts/recon/fresta_recon.py`.

## Юридическая рамка

Проксирование трафика через serverless нарушает ToS Yandex Cloud (функцию могут
снести), и это серая зона по местному регулированию. Инструмент — для доступа к
открытому интернету; риски и решение на тебе.
