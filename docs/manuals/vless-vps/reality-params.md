# fresta · Метод 1: VLESS+Reality на РФ-VPS (Фаза 2)

> **О терминологии:** в проекте есть две разные оси — **«Метод N»** (способ
> обхода, см. `docs/knowledge.md`, раздел 5: Метод 1 = VLESS+Reality,
> Метод 2 = YC Functions) и **«Фаза N»** (стадия roadmap, см. `docs/ROADMAP.md`).
> Этот документ — про **Метод 1**, и он же делается в **Фазе 2**. Не путать
> «Метод 1» с «Фазой 1» (фазы 1 нет, она влилась в Фазу 2).

Генератор server+client-конфигов под **VLESS+Reality** — основной стабильный
метод обхода операторского IP-белого списка. Идея:

- IP-фильтр ТСПУ пропускает пакет, **потому что адрес назначения в белом списке**
  (подсеть Timeweb / Selectel / Beget / Yandex Cloud).
- SNI-фильтр (если есть) пропускает, **потому что SNI = домен крупного сервиса**,
  который точно whitelisted (`ads.x5.ru`, `api-maps.yandex.ru`, `m.vk.com`…).
- TLS-фингерпринт под `chrome` (uTLS) проходит мимо детекта «это VPN».

См. обоснование и модель угроз — `docs/specification.md` (разделы 1, 2, 3, 5) и
`docs/knowledge.md` (разделы 1, 2, 8).

## Что умеет генератор

`scripts/deploy/fresta_gen_vless.py` — stdlib-only Python-скрипт, который собирает:

- `server.json` — Xray-core inbound (VLESS+Reality+TCP).
- `client.json` — sing-box outbound (тот же VLESS+Reality+TCP+utls).
- `links.txt` — vless://-ссылки по одной на каждый whitelisted-SNI (для
  Shadowrocket / v2rayNG / NekoBox / Throne / Karing).
- `info.txt` — UUID / ключи / shortId текстом.
- `gen-keys.sh` — перегенерация X25519-ключей через `openssl` (если бинарь не
  нашёлся во время первого запуска).
- `README.md` — деплой + импорт (отдельный под каждую сборку).

X25519-ключи генерируются через `openssl` 1.1.1+ / 3.x (`subprocess`). Если
`openssl` в PATH нет — скрипт вписывает заметные плейсхолдеры
`PRIVATE_KEY_REPLACE_ME_BASE64URL` / `PUBLIC_KEY_REPLACE_ME_BASE64URL` и
оставляет `gen-keys.sh`, чтобы получить ключи позже.

## Что нужно

- VPS на **whitelisted-провайдере** (Timeweb / Selectel / Beget / Yandex Cloud).
  Список живых подсетей — `../../scripts/harvest/reports/harvest-report.md` (раздел «Провайдеры»)
  + `../../scripts/harvest/twl-data/twl-harvest-report.md` (топ-ASN + /24).
- Локально: Python 3.8+ и, желательно, `openssl` 1.1.1+.
- На VPS: Xray-core (ставится одной строкой — см. ниже).
- На устройстве: sing-box (или клиент с поддержкой vless://-ссылок).

## Генерация конфигов

```bash
# из корня репо (любой cwd)
# минимальный прогон — возьмёт 19 SNI из scripts/harvest/sni_candidates.txt
# и сложит в scripts/deploy/configs/default/ с плейсхолдером IP
python3 scripts/deploy/fresta_gen_vless.py

# полный набор параметров (пример: Timeweb VPS, IP-литерал обязателен)
python3 fresta_gen_vless.py \
  --exit-ip 5.181.1.1 \
  --exit-port 443 \
  --dest www.google.com:443 \
  --out configs/beget-2024-12 \
  --fp chrome \
  --short-id a1b2c3d4

# только пара SNI (например, лидеры по частоте из harvest-report.md)
python3 fresta_gen_vless.py --sni ads.x5.ru --sni api-maps.yandex.ru

# свои ключи (если openssl недоступен, или хочется переиспользовать)
python3 fresta_gen_vless.py \
  --private-key QLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  --public-key  QMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

После прогона в `--out`:

```
configs/<ваше-имя>/
├── server.json     # на VPS в /usr/local/etc/xray/config.json
├── client.json     # на устройство в конфиг sing-box
├── links.txt       # импортировать vless:// в мобильный клиент
├── info.txt        # UUID/ключи/shortId (в секрете)
├── gen-keys.sh     # перегенерация X25519, если надо
└── README.md       # деплой + импорт под эту сборку
```

## Деплой server.json на VPS

```bash
# 1. Поставить Xray-core (если ещё не стоит)
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# 2. Положить конфиг
sudo mkdir -p /usr/local/etc/xray
sudo cp configs/<ваше-имя>/server.json /usr/local/etc/xray/config.json
sudo chmod 644 /usr/local/etc/xray/config.json

# 3. Открыть порт
# Timeweb / Selectel / Beget — через панель хостера (Firewall / Security groups).
# Yandex Cloud — security group: разрешить tcp:443 на адрес VPS.
# Внутри ВМ:
sudo ufw allow 443/tcp   # если используешь ufw
# или
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT

# 4. Запустить
sudo systemctl enable --now xray
sudo journalctl -u xray -f   # логи

# 5. Проверить, что слушает
ss -ltnp | grep :443
```

## Импорт client.json / vless:// в клиент

### sing-box (рекомендуется, есть под Android/iOS/Windows/Mac/OpenWrt)

1. `https://sing-box.sagernet.org` → скачать под свою ОС.
2. Положить `client.json` в `~/.config/sing-box/config.json` (или эквивалент).
3. `sing-box run` (или `sing-box check` для валидации).
4. На Android — SagerNet / NekoBox for Android импортируют тот же JSON.

### vless://-ссылка (быстрый старт с мобильного)

1. Открыть Shadowrocket / v2rayNG / NekoBox / Throne / Karing.
2. Скопировать строку из `links.txt` → «Добавить профиль из буфера».
3. Включить. Если выбранный SNI порезался оператором — попробовать следующий.

## Что смотреть, если не работает

| Симптом | Куда смотреть |
|---------|---------------|
| Клиент вообще не подключается | Фаервол VPS, занят ли порт, правильный ли IP-литерал в конфиге |
| TLS-handshake отваливается | Оператор режет SNI → перебирай из `links.txt` (другой домен) |
| Подключается, но страницы не грузит | `dest` недоступен с VPS → поменяй на `www.google.com:443` или `www.microsoft.com:443` |
| Периодически отваливается | Арм-рейс: смени SNI и/или IP (reroll у Timeweb — бесплатно) |
| `fp=chrome` палится | Попробуй `--fp firefox` или `--fp safari` при перегенерации |

## Параметры Reality — что они значат

- `dest` (server.json) — куда Xray проксирует «чужих» (тех, кто не наш клиент).
  Должен быть TLS-endpoint, до которого VPS реально может достучаться.
  Типичные: `www.google.com:443`, `www.microsoft.com:443`, `www.apple.com:443`.
  **Не** путать с `serverNames` (это SNI, под которые маскируемся).
- `serverNames` (server.json) — массив whitelisted-SNI, в которых наш клиент
  приходит. Должны совпадать с `sni=` в `links.txt` и `server_name` в `client.json`.
- `privateKey` / `publicKey` — пара X25519. На сервере приватка, на клиенте публичная.
  Одна пара на всех клиентов; **никому не отдавай приватку**.
- `shortId` (hex) — короткий «секрет» в handshake, можно ротировать, чтобы
  старые не проходили. В `shortIds` на сервере можно держать несколько —
  на этапе отладки удобно добавить `""` (пустой).
- `flow` — пустой. Reality не использует XTLS Vision.
- `fp` (fingerprint) — uTLS. `chrome` самый универсальный; если палится —
  `firefox` / `safari` / `edge`. См. `docs/knowledge.md:204-206`.

## Ротация фронтов (Фаза 3)

В этой версии `links.txt` — это **набор готовых клиентских конфигов** на
один сервер, но с разными SNI. Если оператор срезал конкретный SNI — не
перегенерируешь, просто копируешь следующую строку.

Полноценная ротация (несколько VPS × несколько SNI × автоперебор) — следующий
шаг в `docs/ROADMAP.md` (Фаза 3). Генератор к этому уже готов: вызывай
`fresta_gen_vless.py` с другим `--out` для каждого VPS / провайдера.

## Юридическая рамка

Собственный VPS — наименее серая зона из всех методов: формально это просто
аренда сервера в РФ-датацентре, а клиент-серверная криптография не запрещена.
Но обход **операторского** белого списка — формально нарушение договора с
оператором связи; функции/серверы могут сносить, идёт арм-рейс.
См. `docs/specification.md` (раздел 11).
