# fresta · fresta-reality

Сгенерировано `fresta_gen_vless.py` для поднятия VLESS+Reality на VPS с
whitelisted-IP (Timeweb / Selectel / Beget / Yandex Cloud). Защита от
операторского IP-белого списка: клиент идёт на IP, который у оператора в списке,
в SNI ставит whitelisted-домен, TLS-фингерпринт маскируется под `chrome`.

## Состав

| Файл | Что |
|------|-----|
| `server.json`     | Xray-core inbound (поставить на VPS) |
| `client.json`     | sing-box outbound (поставить на устройство / роутер) |
| `links.txt`       | vless://-ссылки, по одной на каждый SNI — импортируй в клиент |
| `info.txt`        | UUID, ключи, shortId, IP, порт — держи в секрете |
| `gen-keys.sh`     | если пришлось перегенерировать X25519-пару |

## Параметры этой сборки

- **exit IP**: `CHANGE_ME.IP.LITERAL` (обязательно IP-литерал, не домен)
- **exit port**: `443/tcp`
- **UUID**: `70d09de6-48bb-4477-8c98-2ea7a2b7d845`
- **shortId**: `aa51b05c`
- **uTLS fp**: `chrome`
- **SNI (19 шт.)**: `ads.x5.ru`, `api-maps.yandex.ru`, `5post-gate.x5.ru`, `cdp.x5.ru`, `smartcaptcha.yandexcloud.net`, `max.ru`, … (+13)
- **Reality dest**: `www.google.com:443`

## Деплой на VPS (короткий чек-лист)

1. Поднять VPS на **whitelisted-провайдере** (Timeweb / Selectel / Beget /
   Yandex Cloud). Проверить, что выданный IP попал в подсеть из
   `../../../harvest/reports/harvest-report.md` (раздел «Провайдеры») + `../../../harvest/twl-data/twl-harvest-report.md` (топ-ASN + /24). Если провайдер позволяет —
   выбрать IP, проверив через `fresta_recon.py` или eyeball'ом.
2. Поставить Xray-core:
   ```bash
   bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
   ```
3. Положить `server.json` в `/usr/local/etc/xray/config.json` (или другой путь —
   см. `--config` у `xray`).
4. Открыть порт `443/tcp` в фаерволе / панели хостера.
5. Запустить: `systemctl enable --now xray`. Логи: `journalctl -u xray -f`.
6. С мобильного канала с белым списком проверить, что порт не зафильтрован:
   ```bash
   python3 ../fresta_recon.py
   ```

## Клиент

### Вариант A: sing-box (рекомендуется, есть под Android/iOS/Windows/Mac/OpenWrt)

1. Поставить sing-box (`https://sing-box.sagernet.org`).
2. Положить `client.json` в `~/.config/sing-box/config.json` (или эквивалент).
3. `sing-box run`. На Android — SagerNet / NekoBox for Android импортируют
   тот же JSON.

### Вариант B: vless://-ссылка (самый быстрый старт)

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

## Юридическая рамка

См. `docs/specification.md`. Проксирование через собственный VPS — наименее
серая зона из всех методов, но операторский белый список обходить — формально
нарушение договора с оператором. Решение и риски — на тебе.
