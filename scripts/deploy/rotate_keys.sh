#!/usr/bin/env bash
#
# fresta · rotate_keys.sh — ротация UUID / X25519 / shortId на сервере
#                         без переустановки Xray.
#
# Что делает:
#   1. Подключается к VPS по ssh;
#   2. Снимает бэкап /usr/local/etc/xray/config.json → config.json.bak.<ts>;
#   3. Генерит НОВЫЕ UUID (uuidgen) + X25519-пару (openssl) + shortId (openssl rand -hex 4);
#   4. Патчит server.json: clients[].id, realitySettings.privateKey, realitySettings.shortIds;
#   5. xray run -test (валидация);
#   6. systemctl restart xray;
#   7. Показывает НОВЫЙ client.json + links.txt (в stdout), чтобы ты обновил
#      sing-box / Shadowrocket / v2rayNG.
#
# Использование:
#   bash scripts/rotate_keys.sh user@your-vps.example.com
#   bash scripts/rotate_keys.sh root@vps --port 443
#
# Опции:
#   --port PORT        порт inbound (по умолчанию 443)
#   --config PATH      путь к server.json НА СЕРВЕРЕ
#                      (по умолчанию /usr/local/etc/xray/config.json)
#   --no-restart       не делать systemctl restart (только показать новые ключи)

set -euo pipefail

# --- дефолты ----------------------------------------------------------------

SSH_TARGET="${1:-}"
shift || true

PORT=443
SERVER_JSON_PATH="/usr/local/etc/xray/config.json"
DO_RESTART=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)        PORT="$2"; shift 2;;
    --config)      SERVER_JSON_PATH="$2"; shift 2;;
    --no-restart)  DO_RESTART=0; shift;;
    -h|--help)
      sed -n '2,30p' "$0"; exit 0;;
    *)
      echo "[!] неизвестный флаг: $1" >&2; exit 2;;
  esac
done

if [[ -z "$SSH_TARGET" ]]; then
  echo "Использование: bash scripts/rotate_keys.sh user@host [--port 443] [--config PATH] [--no-restart]" >&2
  exit 2
fi

# --- генерация новых ключей ЛОКАЛЬНО ---------------------------------------

echo "[*] Генерирую новые UUID + X25519 + shortId…"

NEW_UUID="$(command -v uuidgen >/dev/null && uuidgen || python3 -c 'import uuid; print(uuid.uuid4())')"
echo "    UUID:     $NEW_UUID"

# X25519 (см. fresta_gen_vless.py — последние 32 байта DER = raw key).
TMP_PRIV="$(mktemp)"
trap 'rm -f "$TMP_PRIV"' EXIT
openssl genpkey -algorithm X25519 -out "$TMP_PRIV" 2>/dev/null

NEW_PRIV_B64URL="$(openssl pkey -in "$TMP_PRIV" -outform DER 2>/dev/null | tail -c 32 | base64 | tr -d '=' | tr '+/' '-_')"
NEW_PUB_B64URL="$(openssl pkey -in "$TMP_PRIV" -pubout -outform DER 2>/dev/null | tail -c 32 | base64 | tr -d '=' | tr '+/' '-_')"
echo "    privKey:  $NEW_PRIV_B64URL"
echo "    pubKey:   $NEW_PUB_B64URL"

NEW_SID="$(openssl rand -hex 4)"
echo "    shortId:  $NEW_SID"

# --- бэкап + патч на сервере -----------------------------------------------

echo
echo "[*] Подключаюсь к $SSH_TARGET…"

# Считываем текущий server.json + бэкапим.
LOCAL_BAK="$(mktemp -d)/server.json.bak.$(date -u +%Y%m%dT%H%M%SZ)"
ssh "$SSH_TARGET" "sudo cat $SERVER_JSON_PATH" > "$LOCAL_BAK"
echo "[*] Бэкап локально: $LOCAL_BAK"

# Патчим через python (на сервере тоже есть python3 в 99% случаев).
# Меняем только нужные поля; всё остальное сохраняем как есть.
PATCHED="$(python3 - "$LOCAL_BAK" <<PY
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    cfg = json.load(f)
ib = cfg["inbounds"][0]
# clients[*].id -> новый UUID
for c in ib["settings"].get("clients", []):
    c["id"] = "$NEW_UUID"
# privateKey + shortIds
rs = ib["streamSettings"]["realitySettings"]
rs["privateKey"] = "$NEW_PRIV_B64URL"
# Сохраняем старые shortId в массиве (для совместимости с уже-выпущенными
# клиентами, если такие есть) + новый.
existing = rs.get("shortIds", [])
rs["shortIds"] = list(dict.fromkeys(existing + ["$NEW_SID", ""]))  # "" = пустой shortId
print(json.dumps(cfg, indent=2, ensure_ascii=False))
PY
)"

echo "[*] Применяю на сервере…"
echo "$PATCHED" | ssh "$SSH_TARGET" "sudo tee $SERVER_JSON_PATH >/dev/null"

# Валидация + рестарт.
ssh "$SSH_TARGET" "sudo xray run -test -config $SERVER_JSON_PATH" \
  || { echo "[!] xray run -test FAILED — откатываю" >&2
       ssh "$SSH_TARGET" "sudo cp $LOCAL_BAK $SERVER_JSON_PATH" >/dev/null
       exit 1; }

if [[ "$DO_RESTART" == "1" ]]; then
  ssh "$SSH_TARGET" "sudo systemctl restart xray"
  echo "[*] Xray перезапущен."
  sleep 1
  ssh "$SSH_TARGET" "systemctl is-active xray" || true
else
  echo "[i] --no-restart: рестарт не делал, конфиг обновлён, xray работает со старыми ключами."
fi

# --- печатаем НОВЫЙ client.json + links.txt --------------------------------

echo
echo "================================================================"
echo "  НОВЫЕ КЛЮЧИ (старые больше не работают)"
echo "================================================================"
echo "UUID:    $NEW_UUID"
echo "pubKey:  $NEW_PUB_B64URL"
echo "shortId: $NEW_SID"
echo
echo "Подставь их в свой client.json (vless.outbound.tls.reality.public_key)"
echo "и/или в vless://-ссылку (pbk=, sid=)."
echo
echo "================================================================"
echo "  Шаблон vless://-ссылки (подставь свой SNI и IP):"
echo "================================================================"
cat <<TPL
vless://$NEW_UUID@<YOUR.SERVER.IP>:$PORT?encryption=none&type=tcp&security=reality&sni=<SNI>&fp=chrome&pbk=$NEW_PUB_B64URL&sid=$NEW_SID#fresta-rotated
TPL
echo
echo "[i] Бэкап старого server.json: $LOCAL_BAK"
