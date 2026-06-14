#!/usr/bin/env bash
# fresta · quickstart.sh
# Локальный одноступенчатый деплой Метода 1 (VLESS+Reality).
#
# Что делает одной командой:
#   1. Генерирует server.json / client.json / vless://-ссылки локально
#      (через fresta_gen_vless.py).
#   2. Копирует server.json + fresta_gen_vless.py + deploy_vps.sh на сервер по ssh.
#   3. Запускает deploy_vps.sh НА СЕРВЕРЕ (тот ставит Xray, кладёт конфиг,
#      открывает порт, рестартит).
#   4. Скачивает client.json + links.txt обратно.
#   5. Печатает итог: что импортировать в клиент, как проверить.
#
# Поведение:
#   - Интерактивное: спрашивает, если что-то непонятно.
#   - Идемпотентное: можно запускать повторно (server.json перезапишется,
#     ключи перегенерируются → клиент тоже надо обновить).
#   - Без sudo на твоей локальной машине не нужно.
#
# Требования локально: bash, ssh, scp, python3, sshpass (если ssh по паролю).
#
# Использование:
#   bash quickstart.sh --ssh user@vps.example.com                    # exit-ip = авто
#   bash quickstart.sh --ssh user@vps --exit-ip 5.181.1.1 --port 443 # явные параметры
#   bash quickstart.sh --ssh user@vps --sni ads.x5.ru --no-scp-deploy # только генернуть и скачать
#
# Полный гайд: docs/deploy-guide.md.

set -euo pipefail

# --- утилиты --------------------------------------------------------------

die() { printf '\033[1;31m[ERR]\033[0m %s\n' "$*" >&2; exit 1; }
log() { printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
ok() { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

# --- пути -----------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# SNI-файл лежит в scripts/harvest/ (другой модуль), относительно deploy/ — ../harvest/
SCRIPTS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GEN_VLESS="$SCRIPT_DIR/fresta_gen_vless.py"
DEPLOY_VPS="$SCRIPT_DIR/deploy_vps.sh"
DEFAULT_SNI_FILE="$SCRIPTS_ROOT/harvest/sni_candidates.txt"

[ -f "$GEN_VLESS" ]   || die "не нашёл $GEN_VLESS"
[ -f "$DEPLOY_VPS" ]  || die "не нашёл $DEPLOY_VPS (должен лежать рядом с quickstart.sh)"

# --- парсинг аргументов ---------------------------------------------------

SSH_TARGET=""
EXIT_IP=""      # авто = узнать на сервере через curl ifconfig.me
EXIT_PORT="443"
DEST="www.google.com:443"
FP="chrome"
SNI_LIST=()     # пусто = из sni_candidates.txt
SNI_FILE="$DEFAULT_SNI_FILE"
OUT_NAME=""     # имя подкаталога в configs/; default = <ssh-host>-<date>
NO_DEPLOY=0     # --no-scp-deploy: только сгенерировать локально
ASSUME_YES=0

usage() {
    cat <<'USAGE'
Использование:
  bash quickstart.sh --ssh user@vps.example.com [опции]

Опции:
  --ssh TARGET         ssh-целевой хост (обязательно; формат user@host)
  --exit-ip IP         внешний IP VPS (default: узнать на сервере через curl)
  --exit-port PORT     порт inbound (default 443)
  --dest DEST          dest для Reality (default www.google.com:443)
  --fp FP              uTLS fingerprint (default chrome)
  --sni SNI            добавить SNI (можно несколько раз)
  --sni-file PATH      файл со списком SNI (default scripts/harvest/sni_candidates.txt)
  --out NAME           имя подкаталога (default <host>-<YYYYMMDD>)
  --no-scp-deploy      только сгенерировать конфиги, НЕ заливать на сервер
  --yes                неинтерактивный режим
  -h, --help           справка
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --ssh)        SSH_TARGET="$2"; shift 2 ;;
        --exit-ip)    EXIT_IP="$2"; shift 2 ;;
        --exit-port)  EXIT_PORT="$2"; shift 2 ;;
        --dest)       DEST="$2"; shift 2 ;;
        --fp)         FP="$2"; shift 2 ;;
        --sni)        SNI_LIST+=("$2"); shift 2 ;;
        --sni-file)   SNI_FILE="$2"; shift 2 ;;
        --out)        OUT_NAME="$2"; shift 2 ;;
        --no-scp-deploy) NO_DEPLOY=1; shift ;;
        --yes)        ASSUME_YES=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *) die "неизвестный аргумент: $1 (--help для справки)" ;;
    esac
done

[ -n "$SSH_TARGET" ] || { usage; die "--ssh обязателен (например --ssh user@vps.example.com)"; }
have ssh  || die "ssh не найден в PATH"
have scp  || die "scp не найден в PATH"
have python3 || die "python3 не найден в PATH"

# --- имя хоста для подкаталога -------------------------------------------

SSH_HOST="${SSH_TARGET#*@}"   # user@host → host
SSH_HOST="${SSH_HOST%%:*}"    # host:port → host
[ -n "$OUT_NAME" ] || OUT_NAME="${SSH_HOST}-$(date +%Y%m%d)"
OUT_DIR="$SCRIPT_DIR/configs/$OUT_NAME"
log "целевой каталог: $OUT_DIR"

# --- 1. Проверка ssh-доступа (с таймаутом) --------------------------------

log "проверяю ssh-доступ к $SSH_TARGET…"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "echo SSH_OK" >/dev/null 2>&1; then
    if have sshpass; then
        warn "ssh по ключу не зашёл, но есть sshpass — попробую интерактивно позже."
        warn "если хочешь без sshpass — настрой ключ: ssh-copy-id $SSH_TARGET"
    else
        warn "ssh без пароля не зашёл. Возможные причины:"
        warn "  1) нужен пароль — поставь sshpass (apt install sshpass) и запусти ещё раз,"
        warn "     скрипт спросит пароль;"
        warn "  2) ключ не настроен — выполни: ssh-copy-id $SSH_TARGET"
        warn "  3) хост не тот — проверь, что $SSH_TARGET пингуется и sshd слушает."
        die "ssh-доступ не настроен"
    fi
fi
ok "ssh-доступ есть"

# --- 1b. Проверить, свободен ли порт на сервере (если не --no-scp-deploy) ---

if [ "$NO_DEPLOY" -eq 0 ]; then
    log "проверяю, свободен ли TCP-порт $EXIT_PORT на сервере…"
    PORT_FREE=$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
        "if ss -ltn 2>/dev/null | grep -qE ':$EXIT_PORT\b'; then echo BUSY; else echo FREE; fi" 2>/dev/null)
    if [ "$PORT_FREE" = "BUSY" ]; then
        # Поищем первый свободный в типичном диапазоне HTTPS-альтернатив
        NEW_PORT=""
        for try_port in 8443 9443 10443 2053 2083 443; do
            if [ "$try_port" = "$EXIT_PORT" ]; then continue; fi
            T_FREE=$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
                "if ss -ltn 2>/dev/null | grep -qE ':$try_port\b'; then echo BUSY; else echo FREE; fi" 2>/dev/null)
            if [ "$T_FREE" = "FREE" ]; then
                NEW_PORT="$try_port"
                break
            fi
        done
        if [ -n "$NEW_PORT" ]; then
            warn "TCP-порт $EXIT_PORT занят на сервере, переключаюсь на $NEW_PORT"
            EXIT_PORT="$NEW_PORT"
        else
            warn "автодетект не нашёл свободного порта; пробую заданный ($EXIT_PORT) — Xray может упасть"
        fi
    else
        ok "порт $EXIT_PORT свободен"
    fi
fi

# --- 2. Узнать exit-ip, если не задан -------------------------------------

if [ -z "$EXIT_IP" ] && [ "$NO_DEPLOY" -eq 0 ]; then
    log "узнаю внешний IP сервера…"
    EXIT_IP=$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
        "curl -sS --max-time 10 https://ifconfig.me 2>/dev/null \
         || curl -sS --max-time 10 https://api.ipify.org 2>/dev/null \
         || hostname -I 2>/dev/null | awk '{print \$1}'" 2>/dev/null | tr -d '[:space:]')
    if [ -z "$EXIT_IP" ]; then
        die "не удалось узнать exit-ip — передай --exit-ip явно"
    fi
    ok "exit-ip сервера: $EXIT_IP"
elif [ -z "$EXIT_IP" ] && [ "$NO_DEPLOY" -eq 1 ]; then
    EXIT_IP="CHANGE_ME.IP.LITERAL"
    warn "exit-ip не задан (режим --no-scp-deploy), конфиг будет с плейсхолдером"
fi

# --- 3. Генерация конфигов -------------------------------------------------

log "генерирую конфиги (gen_vless)…"
GEN_CMD=(python3 "$GEN_VLESS" --exit-ip "$EXIT_IP" --exit-port "$EXIT_PORT"
         --dest "$DEST" --fp "$FP" --out "$OUT_DIR")
if [ ${#SNI_LIST[@]} -gt 0 ]; then
    for s in "${SNI_LIST[@]}"; do GEN_CMD+=(--sni "$s"); done
else
    [ -f "$SNI_FILE" ] || die "нет SNI: ни --sni, ни файла $SNI_FILE"
    GEN_CMD+=(--sni-file "$SNI_FILE")
fi
"${GEN_CMD[@]}"
ok "конфиги в $OUT_DIR"

# --- 4. Скачать обратно client.json / links.txt / info.txt ----------------
# (всё уже локально, это просто sanity-check)

for f in server.json client.json links.txt info.txt; do
    [ -f "$OUT_DIR/$f" ] || die "генератор не создал $f"
done
ok "все файлы на месте: $(ls -1 "$OUT_DIR" | tr '\n' ' ')"

# --- 5. Деплой на сервер --------------------------------------------------

if [ "$NO_DEPLOY" -eq 1 ]; then
    log "режим --no-scp-deploy: пропускаю заливку на сервер"
else
    log "копирую server.json + deploy_vps.sh на $SSH_TARGET…"
    REMOTE_DIR="~/fresta-deploy"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "mkdir -p $REMOTE_DIR"
    scp "${SSH_OPTS[@]}" "$OUT_DIR/server.json"  "$SSH_TARGET:$REMOTE_DIR/server.json"
    scp "${SSH_OPTS[@]}" "$DEPLOY_VPS"          "$SSH_TARGET:$REMOTE_DIR/deploy_vps.sh"

    log "запускаю deploy_vps.sh на $SSH_TARGET…"
    DEPLOY_ARGS=(--config "$REMOTE_DIR/server.json" --port "$EXIT_PORT" --yes)
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash $REMOTE_DIR/deploy_vps.sh ${DEPLOY_ARGS[*]}"
    ok "деплой на сервере завершён"
fi

# --- 6. Итог --------------------------------------------------------------

cat <<EOF

================================================================
  ГОТОВО
================================================================
  Сервер:        $SSH_TARGET
  Exit IP:       $EXIT_IP
  Порт:          $EXIT_PORT/tcp
  SNI (штук):    $(grep -c 'sni=' "$OUT_DIR/links.txt" || echo "?")
  SNI (первый):  $(grep -m1 -oE 'sni=[^&]+' "$OUT_DIR/links.txt" | cut -d= -f2)

  Конфиги:       $OUT_DIR/
    server.json     на сервере (уже задеплоен)
    client.json     sing-box outbound
    links.txt       vless://-ссылки для мобильного клиента
    info.txt        UUID/ключи/shortId (в секрете)

  Как проверить (с твоей локальной машины):
    nc -vz $EXIT_IP $EXIT_PORT
    python3 $SCRIPTS_ROOT/tests/probe_reality.py     # TLS-probe по всем SNI

  Как подключиться:
    - sing-box:  скопируй client.json → ~/.config/sing-box/config.json
    - Shadowrocket/v2rayNG:  открой links.txt, вставь первую строку

================================================================
EOF
ok "деплой Метода 1 завершён. Подробности и troubleshooting — docs/deploy-guide.md"
