# fresta · гайд по деплою Метода 1 (VLESS+Reality)

Подробный гайд к двум скриптам, которые автоматизируют весь пайплайн:

| Скрипт | Где запускать | Что делает |
|--------|---------------|------------|
| `scripts/deploy/quickstart.sh` | локально (твоя машина) | генерирует конфиги → копирует на VPS → запускает deploy → скачивает обратно |
| `scripts/deploy/deploy_vps.sh` | на VPS (через ssh) | ставит Xray, кладёт `server.json`, открывает порт, перезапускает сервис |

> **TL;DR (для нетерпеливых):** одна команда делает всё —
> ```bash
> bash scripts/deploy/quickstart.sh --ssh user@your-vps.example.com
> ```
> …и в конце напечатает `client.json` / `links.txt`, готовые к импорту.

---

## Сценарий A: PoC на любом доступном сервере

**Зачем:** проверить, что **архитектура Метода 1 вообще работает** end-to-end (Xray поднимается, Reality-handshake проходит, туннель гонит трафик). Без требований к IP — VPS не обязательно должен быть в whitelisted-подсети.

**Когда применять:** когда у тебя есть любой Linux-сервер с sudo, но **ещё нет** нормального whitelisted-VPS. Также годится для CI/dev-окружения и для обучения.

**Что понадобится:**
- Linux-сервер (Debian/Ubuntu/CentOS/Alma) с systemd, sudo (NOPASSWD или пароль) и доступом по ssh.
- Твоя локальная машина с `bash`, `ssh`, `scp`, `python3`.

**Команда:**
```bash
cd fresta
bash scripts/deploy/quickstart.sh --ssh user@your-server.example.com
```

Скрипт сам:
1. Проверит ssh-доступ (и попросит установить ключ, если не настроен).
2. Узнает exit-IP сервера (через `curl ifconfig.me` на самом VPS).
3. Сгенерирует `server.json`, `client.json`, 19 `vless://`-ссылок (по умолчанию SNI из `scripts/harvest/sni_candidates.txt`).
4. Скопирует `server.json` + `deploy_vps.sh` на сервер.
5. Запустит `deploy_vps.sh` НА СЕРВЕРЕ — тот поставит Xray, положит конфиг, откроет порт в iptables/ufw/firewalld, перезапустит сервис.
6. Напечатает итог: где лежит `client.json`, что импортировать, как проверить.

**Проверка:**
```bash
# 1. TLS-probe (с твоей локальной машины, через Python)
python3 scripts/tests/probe_reality.py
# (полный путь к configs/remote-fresta — неважен, probe_reality ходит прямо на 89.253.255.108:8443)

# 2. Полный e2e через sing-box (нужен локально установленный sing-box)
#    Скопируй client.json из configs/<host>-<date>/ в ~/.config/sing-box/config.json
#    и запусти:
sing-box run -c ~/.config/sing-box/config.json &
#    В другом терминале:
curl --proxy socks5h://127.0.0.1:1080 https://api.github.com/zen
#    → 200 OK, "Favor focus over features."

# 3. Проверка exit-IP:
echo "прямой:    $(curl -sS https://api.ipify.org)"
echo "через прокси: $(curl --proxy socks5h://127.0.0.1:1080 -sS https://api.ipify.org)"
#    Второй = IP твоего VPS.
```

**Ожидаемый результат:** туннель ходит, exit-IP = IP VPS, целевые сайты отвечают.
**Что НЕ работает в этом сценарии:** под белым списком мобильного оператора схема НЕ пройдёт, потому что IP VPS не в whitelisted-подсети. Это нормально — здесь мы проверяли только архитектуру.

---

## Сценарий B: production на whitelisted-VPS

**Зачем:** реальный обход белого списка. Чтобы мобильный оператор пропускал пакеты, **IP-адрес назначения** должен быть в его whitelisted-подсети, **SNI** — в whitelisted-доменах, **TLS-фингерпринт** — под `chrome`.

**Когда применять:** для ежедневного использования.

**Шаги:**

### Шаг 1. Выбрать провайдера

Живые whitelisted-провайдеры (из `../../scripts/harvest/reports/harvest-report.md` + `../../scripts/harvest/twl-data/twl-harvest-report.md`):
- **Timeweb** — есть бесплатный reroll IP, удобно экспериментировать.
- **Selectel** — стабильный, много локаций.
- **Beget** — VPS-хостинг, РФ-юрисдикция.
- **Yandex Cloud** — там же, где и Метод 2.

Дополнительно проверить плотность `/24` подсети в белом списке можно через `fresta_recon.py` (Фаза 0).

### Шаг 2. Запустить quickstart

```bash
cd fresta
bash scripts/deploy/quickstart.sh --ssh root@<новый-VPS>
# ИЛИ с явным IP (если VPS за NAT и exit-IP ≠ IP ssh-хоста):
bash scripts/deploy/quickstart.sh --ssh root@<новый-VPS> --exit-ip <белый-IP>
```

**Отличия от сценария A:**
- Порт по умолчанию = `443` (не 8443, как на тестовом сервере, где 443 был занят).
- Провайдерские VPS обычно требуют открыть порт **через панель** (не через iptables) — `deploy_vps.sh` попытается через iptables, но если у провайдера свой фаервол, открой порт 443/tcp руками и перезапусти скрипт с `--no-firewall`.

### Шаг 3. Под мобильным каналом с белым списком

1. Подключи свой телефон к мобильной сети с белым списком и **раздай интернет на ноут** (USB-модем или точка доступа).
2. На ноуте запусти `sing-box run` с `client.json` (см. выше).
3. `curl --proxy socks5h://127.0.0.1:1080 https://twitter.com` (или другой заблокированный ресурс).
4. Если **работает** — ура, связка прошла сквозь белый список.
5. Если **не работает** — см. troubleshooting ниже.

### Шаг 4. Импортировать в мобильный клиент

Самый простой путь — `links.txt` (19 vless://-ссылок). Скопируй в Shadowrocket / v2rayNG / NekoBox / Throne / Karing. Если один SNI не заходит у оператора — попробуй следующий. Ротировать можно вручную.

---

## Повторный деплой (обновление конфигов)

`quickstart.sh` **идемпотентен** — можно запускать повторно. При повторном запуске:
- Перегенерируются **новые ключи** (UUID, X25519, shortId).
- Старый `server.json` на сервере перезапишется.
- Старый `client.json` / `links.txt` локально **перезапишутся** (предыдущие ключи перестанут работать).
- Xray рестартует, порт открыт, всё на месте.

Если просто хочется перезалить конфиг **без новых ключей** (например, поправил SNI), отредактируй `server.json` руками и перезапусти деплой:
```bash
# На сервере:
sudo cp /path/to/new-server.json /usr/local/etc/xray/config.json
sudo xray run -test -config /usr/local/etc/xray/config.json   # валидация
sudo systemctl restart xray
```

---

## Опции `quickstart.sh`

| Флаг | Что делает | Default |
|------|------------|---------|
| `--ssh TARGET` | ssh-целевой хост (`user@host`) | **обязателен** |
| `--exit-ip IP` | внешний IP VPS (если не резолвится автоматом) | авто через `curl` |
| `--exit-port PORT` | порт inbound | `443` |
| `--dest DEST` | dest для Reality (куда проксировать «чужих») | `www.google.com:443` |
| `--fp FP` | uTLS fingerprint: `chrome` / `firefox` / `safari` / `edge` / `qq` | `chrome` |
| `--sni SNI` | один конкретный SNI (можно несколько раз) | `sni_candidates.txt` |
| `--sni-file PATH` | файл со списком SNI | `scripts/harvest/sni_candidates.txt` |
| `--out NAME` | имя подкаталога в `configs/` | `<host>-<YYYYMMDD>` |
| `--no-scp-deploy` | только сгенерировать, **НЕ** заливать | off |
| `--yes` | неинтерактивный режим | off (есть подтверждения) |

## Опции `deploy_vps.sh`

| Флаг | Что делает | Default |
|------|------------|---------|
| `--config PATH` | путь к `server.json` НА СЕРВЕРЕ | **обязателен** |
| `--port PORT` | порт для iptables (берётся из server.json, если не задан) | авто |
| `--[no-]install` | ставить Xray, если его нет | `--install` |
| `--[no-]firewall` | открыть порт в iptables/ufw/firewalld | `--firewall` |
| `--[no-]restart` | рестарт Xray после копирования конфига | `--restart` |
| `--[no-]validate` | прогнать `xray run -test` перед запуском | `--validate` |
| `--yes` | неинтерактивный режим | off |

---

## Troubleshooting

### `ssh: Permission denied (publickey)`

Ключ не настроен. Варианты:
```bash
ssh-copy-id user@host              # один раз
# или
sshpass -p 'пароль' bash scripts/deploy/quickstart.sh --ssh user@host   # каждый раз с паролем
# (поставь sshpass: apt install sshpass / brew install sshpass)
```

### `bind: address already in use` на 443

Порт занят (apache / nginx / docker-proxy). Варианты:
- Выбери другой порт: `--exit-port 8443` в `quickstart.sh`.
- Или останови «лишний» сервис: `sudo systemctl stop nginx`.

### `iptables: Permission denied`

sudo без пароля не настроен. `deploy_vps.sh` сам поймёт и спросит. Или добавь себя в `sudoers`:
```bash
echo "user ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/user-nopasswd
```

### `iptables-save: command not found` / правило не переживёт ребут

На Debian/Ubuntu поставь `iptables-persistent`:
```bash
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

### `xray: command not found` после установки

Установка не удалась. Смотри причину:
```bash
sudo /tmp/install-xray.sh install    # запустить руками, увидишь ошибки
```

### `Configuration is invalid: ...` от `xray run -test`

Сгенерированный конфиг битый. Возможные причины:
- openssl очень старый (< 1.1.1) — поставь `openssl` посвежее.
- В `sni_candidates.txt` мусор — почисти или передай `--sni` явно.

### sing-box: `loglevel: unknown field`

Это поле от Xray, у sing-box оно называется `level`. Наш `client.json` уже использует `level` (мы генерим в sing-box-формате). Если ты редактировал руками — замени.

### `FATAL: address already in use` (sing-box локально)

Порт 1080 занят другим SOCKS/HTTP-прокси. Смени порт в `client_full.json`:
```json
"listen_port": 2080
```

### `TLS probe OK, но curl через прокси не отвечает`

- Проверь, что sing-box запустился: `ps aux | grep sing-box` (или `Get-Process sing-box`).
- Проверь логи sing-box (`loglevel: "info"` в `client_full.json`).
- Проверь, что **наш ключ** (UUID, publicKey, shortId) в `client.json` совпадает с **server.json** на VPS. Если ты перезапускал `quickstart.sh` — ключи сменились, **обязательно** скачай свежий `client.json`.

### Под белым списком оператора не работает

Это **не баг скриптов**, а проверка того, что whitelisted-VPS реально в whitelisted-подсети. Возможные причины:
- IP VPS не в whitelisted-подсети → возьми другой IP (reroll у Timeweb бесплатный).
- SNI порезался → попробуй другой из `links.txt` (там 19 штук).
- DPI у оператора подозревает `chrome` fingerprint → смени `--fp` на `firefox` или `safari`.
- У оператора **жёсткий** белый список без SNI-разрешений на крупные сервисы → пробуй другого провайдера из `../../scripts/harvest/reports/harvest-report.md`.

### Где посмотреть, что делал деплой

```bash
# На сервере — логи Xray:
sudo journalctl -u xray -n 50 --no-pager

# Локально — локальные артефакты:
ls -la scripts/deploy/configs/<host>-<date>/
cat scripts/deploy/configs/<host>-<date>/info.txt
```

---

## Что лежит в `configs/<host>-<date>/`

| Файл | Что | Куда |
|------|-----|------|
| `server.json`     | Xray inbound (VLESS+Reality+TCP) | уже на сервере в `/usr/local/etc/xray/config.json` |
| `client.json`     | sing-box outbound | импортируй в sing-box (см. ниже) |
| `links.txt`       | 19 `vless://`-ссылок | импортируй в мобильный клиент (Shadowrocket / v2rayNG) |
| `info.txt`        | UUID / publicKey / shortId | держи в секрете |
| `gen-keys.sh`     | перегенерация X25519, если надо | (опц.) |
| `README.md`       | деплой + импорт под ЭТУ конкретную сборку | автогенерирован |

---

## Импорт `client.json` в sing-box (локально)

Для полноценного end-to-end (SOCKS5 inbound + Reality outbound) используй `client_full.json` из нашего PoC (`scripts/deploy/configs/remote-fresta/client_full.json`) — там есть готовый inbound `mixed` на 127.0.0.1:1080. Если генеришь заново — добавь inbound руками:

```json
{
  "log": {"level": "info"},
  "inbounds": [
    {"type": "mixed", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 1080}
  ],
  "outbounds": [ /* …вставь сюда наш VLESS-outbound из client.json… */ ],
  "route": {"final": "fresta-reality"}
}
```

```bash
# Linux/macOS/WSL
mkdir -p ~/.config/sing-box
cp scripts/deploy/configs/<host>-<date>/client.json ~/.config/sing-box/config.json
sing-box check -c ~/.config/sing-box/config.json
sing-box run -c ~/.config/sing-box/config.json &

# В другом терминале:
curl --proxy socks5h://127.0.0.1:1080 https://api.github.com/zen
```

---

## Где это в доках проекта

- **`docs/specification.md`** — модель угроз, архитектура.
- **`docs/knowledge.md`** — контекст-хэндофф, разделы 5 (методы), 6 (что построено), 8 (уроки).
- **`docs/ROADMAP.md`** — Фаза 0/2, статус.
- **`reality-params.md`** (рядом) — параметры Reality (что значат `dest`, `serverNames`, `shortId`).
- **`../../scripts/harvest/reports/harvest-report.md`** — живые SNI/провайдеры из подписки.
- **`scripts/deploy/fresta_gen_vless.py`** — генератор (если хочется поковыряться руками).
- **`scripts/tests/`** — smoke-тесты (60+ кейсов).
- **`scripts/tests/probe_reality.py`** — TLS-probe ко всем SNI.