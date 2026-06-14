#!/usr/bin/env bash
# fresta · deploy_vps.sh
# Серверная часть деплоя Метода 1 (VLESS+Reality).
# Запускать НА VPS через ssh (от пользователя с sudo).
#
# Делает:
#   1. (опц.) ставит Xray через официальный install-release.sh
#   2. копирует server.json в /usr/local/etc/xray/config.json
#   3. (опц.) открывает TCP-порт в iptables (или предупреждает, если фаервол
#      управляется через панель хостера)
#   4. (опц.) рестартит Xray и показывает статус
#
# Поведение по умолчанию — НЕразрушающее: если Xray уже стоит и работает,
# конфиг обновится, сервис перезапустится, всё прочее — без изменений.
# Используй --yes для не-интерактивного режима (без подтверждений).
#
# Зависимости на сервере: bash, curl, sudo (или root), iptables ИЛИ ufw.

set -euo pipefail

# --- дефолты --------------------------------------------------------------
XRAY_CONFIG="/usr/local/etc/xray/config.json"
XRAY_BIN="/usr/local/bin/xray"
XRAY_SERVICE="xray"
INSTALL_SH_URL="https://github.com/XTLS/Xray-install/raw/main/install-release.sh"

# --- утилиты --------------------------------------------------------------

die() { printf '\033[1;31m[ERR]\033[0m %s\n' "$*" >&2; exit 1; }
log() { printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
ok() { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

# Запустить с sudo, если мы не root.
as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo -n "$@" || die "нужен sudo без пароля (NOPASSWD) или запуск от root"
    fi
}

usage() {
    cat <<'USAGE'
Использование:
  bash deploy_vps.sh --config <path-to-server.json> [опции]

Опции:
  --config PATH        путь к server.json (обязательно)
  --port PORT          порт для inbound (для iptables; default берётся из server.json)
  --[no-]install       ставить Xray, если его нет (default: --install)
  --[no-]firewall      открыть порт в iptables (default: --firewall)
  --[no-]restart       рестарт Xray после копирования (default: --restart)
  --[no-]validate      прогнать xray run -test перед запуском (default: --validate)
  --yes                неинтерактивный режим (без подтверждений)
  -h, --help           эта справка

Что НЕ делает:
  - Не генерирует конфиги (это fresta_gen_vless.py).
  - Не трогает TLS-сертификаты (Reality их не требует).
  - Не настраивает клиент (это quickstart.sh / импорт links.txt).
USAGE
}

# --- парсинг аргументов ----------------------------------------------------

CONFIG=""
PORT=""
DO_INSTALL=1
DO_FIREWALL=1
DO_RESTART=1
DO_VALIDATE=1
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --config)   CONFIG="$2"; shift 2 ;;
        --port)     PORT="$2"; shift 2 ;;
        --install)    DO_INSTALL=1; shift ;;
        --no-install) DO_INSTALL=0; shift ;;
        --firewall)    DO_FIREWALL=1; shift ;;
        --no-firewall) DO_FIREWALL=0; shift ;;
        --restart)    DO_RESTART=1; shift ;;
        --no-restart) DO_RESTART=0; shift ;;
        --validate)    DO_VALIDATE=1; shift ;;
        --no-validate) DO_VALIDATE=0; shift ;;
        --yes)        ASSUME_YES=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *) die "неизвестный аргумент: $1 (--help для справки)" ;;
    esac
done

[ -n "$CONFIG" ] || { usage; die "--config обязателен"; }
[ -f "$CONFIG" ] || die "файл $CONFIG не найден"

# --- 1. Определить порт из server.json, если не задан ----------------------

if [ -z "$PORT" ]; then
    PORT=$(grep -oE '"port"[[:space:]]*:[[:space:]]*[0-9]+' "$CONFIG" | head -1 | grep -oE '[0-9]+' || true)
    [ -n "$PORT" ] || die "не удалось извлечь port из $CONFIG (передай --port явно)"
fi
log "конфиг: $CONFIG  →  /usr/local/etc/xray/config.json  (порт $PORT)"

# --- 2. Подтверждение ------------------------------------------------------

if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
    echo
    echo "Будет сделано:"
    [ "$DO_INSTALL"   -eq 1 ] && echo "  - установка Xray (если не установлен)"
    echo "  - копирование $CONFIG → $XRAY_CONFIG"
    [ "$DO_FIREWALL"  -eq 1 ] && echo "  - открытие TCP-порта $PORT в iptables"
    [ "$DO_RESTART"   -eq 1 ] && echo "  - рестарт $XRAY_SERVICE"
    echo
    read -r -p "Продолжить? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || { echo "отменено"; exit 0; }
fi

# --- 3. Установка Xray -----------------------------------------------------

if [ "$DO_INSTALL" -eq 1 ]; then
    if have xray; then
        ok "Xray уже установлен: $(xray version 2>&1 | head -1)"
    else
        log "устанавливаю Xray (это требует root)…"
        if [ "$(id -u)" -ne 0 ]; then
            warn "для install-release.sh нужен root. Запусти от root или с sudo."
        fi
        as_root bash -c "curl -L '$INSTALL_SH_URL' | bash @ install"
        have xray || die "Xray не появился в PATH после установки"
        ok "Xray установлен: $(xray version 2>&1 | head -1)"
    fi
fi

# --- 4. Положить конфиг ----------------------------------------------------

log "копирую $CONFIG → $XRAY_CONFIG"
as_root mkdir -p "$(dirname "$XRAY_CONFIG")"
as_root cp "$CONFIG" "$XRAY_CONFIG"
as_root chmod 644 "$XRAY_CONFIG"
ok "конфиг на месте"

# --- 5. Валидация ---------------------------------------------------------

if [ "$DO_VALIDATE" -eq 1 ]; then
    log "валидирую конфиг: $XRAY_BIN run -test -config $XRAY_CONFIG"
    if as_root "$XRAY_BIN" run -test -config "$XRAY_CONFIG" 2>&1 | tail -3; then
        ok "конфиг валиден"
    else
        die "конфиг НЕ валиден (см. вывод выше). Xray не перезапускался."
    fi
fi

# --- 6. Открыть порт в фаерволе -------------------------------------------

open_port() {
    if have iptables; then
        if as_root iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
            ok "iptables: порт $PORT уже открыт"
        else
            as_root iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT
            ok "iptables: открыт TCP $PORT (правило в начало цепочки INPUT)"
            # попробуем сохранить, чтобы пережило ребут
            if have netfilter-persistent; then
                as_root netfilter-persistent save || true
            elif have iptables-save; then
                warn "iptables-save есть, но правило не сохранится через ребут без netfilter-persistent. "\
                     "Сохрани вручную (Debian/Ubuntu: apt install iptables-persistent && netfilter-persistent save)."
            fi
        fi
    elif have ufw; then
        as_root ufw allow "$PORT/tcp" || warn "ufw: не удалось открыть порт (sudo без пароля?)"
        ok "ufw: открыт TCP $PORT"
    elif have firewall-cmd; then
        as_root firewall-cmd --permanent --add-port="$PORT/tcp" || true
        as_root firewall-cmd --reload || true
        ok "firewalld: открыт TCP $PORT"
    else
        warn "не нашёл iptables/ufw/firewalld. Открой порт $PORT вручную (через панель хостера)."
    fi
}

if [ "$DO_FIREWALL" -eq 1 ]; then
    log "открываю TCP-порт $PORT в фаерволе…"
    open_port
fi

# --- 7. Запуск / рестарт ---------------------------------------------------

if [ "$DO_RESTART" -eq 1 ]; then
    if have systemctl && [ -f "/etc/systemd/system/${XRAY_SERVICE}.service" ]; then
        log "рестарт ${XRAY_SERVICE}.service…"
        as_root systemctl reset-failed "${XRAY_SERVICE}.service" 2>/dev/null || true
        as_root systemctl enable --now "${XRAY_SERVICE}.service"
        as_root systemctl restart "${XRAY_SERVICE}.service"
        sleep 1
    elif have systemctl; then
        # нет юнита — попробуем xray@ с конфигом по имени
        warn "нет юнита ${XRAY_SERVICE}.service — пробую запустить как процесс"
        as_root "$XRAY_BIN" run -config "$XRAY_CONFIG" &
    else
        warn "systemd нет. Запусти вручную: $XRAY_BIN run -config $XRAY_CONFIG"
    fi
fi

# --- 8. Статус -------------------------------------------------------------

log "проверяю статус…"
ACTIVE=$(as_root systemctl is-active "$XRAY_SERVICE" 2>/dev/null || echo "unknown")
ENABLED=$(as_root systemctl is-enabled "$XRAY_SERVICE" 2>/dev/null || echo "unknown")
LISTEN=$(as_root ss -ltn 2>/dev/null | grep -E ":$PORT\b" | head -1 || true)

echo
echo "===== СТАТУС ====="
echo "  Xray активен:    $ACTIVE"
echo "  Xray enabled:    $ENABLED"
echo "  Слушает :$PORT:  ${LISTEN:-НЕ СЛУШАЕТ (проверь логи!)}"
echo "  Логи:            journalctl -u $XRAY_SERVICE -n 30 --no-pager"
echo "==================="
echo

# --- 9. Проверка реальной работоспособности ------------------------------
# systemctl restart мог пройти, но если порт занят, Xray упадёт через секунду.
# Подождём чуть-чуть и проверим, что active держится и порт слушает.

if [ "$DO_RESTART" -eq 1 ] && have systemctl; then
    sleep 2
    POST_ACTIVE=$(as_root systemctl is-active "$XRAY_SERVICE" 2>/dev/null || echo "unknown")
    if [ "$POST_ACTIVE" != "active" ]; then
        echo
        warn "Xray НЕ активен после рестарта (status: $POST_ACTIVE)."
        warn "типичная причина: TCP-порт $PORT уже занят другим процессом."
        warn "кто слушает :$PORT:"
        as_root ss -ltnp 2>/dev/null | grep -E ":$PORT\b" | sed 's/^/    /' || true
        warn
        warn "возможные решения:"
        warn "  1) убей процесс на этом порту (если он тебе не нужен),"
        warn "  2) или запусти quickstart.sh с --exit-port 8443 (или другим свободным),"
        warn "  3) или открой порт через панель хостера (если докер/nginx)."
        echo
        die "Xray не запустился. Порт занят — см. предупреждения выше."
    fi
    # Дополнительно: проверяем, что :$PORT слушает именно xray
    if ! as_root ss -ltnp 2>/dev/null | grep -E ":$PORT\b" | grep -qi "xray\|users:(\"xray\""; then
        warn "порт $PORT слушает НЕ xray (см. ss -ltnp). Клиент не подключится."
        as_root ss -ltnp 2>/dev/null | grep -E ":$PORT\b" | sed 's/^/    /' || true
    fi
fi

ok "деплой завершён. Проверь снаружи: nc -vz $PORT  или  curl --resolve ads.x5.ru:$PORT <IP> https://ads.x5.ru/"
