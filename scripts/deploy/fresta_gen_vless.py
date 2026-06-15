#!/usr/bin/env python3
"""
fresta · gen_vless (Фаза 2) — генератор VLESS+Reality конфигов

Собирает связку server (Xray-core) + client (sing-box) + vless://-ссылки
под whitelisted-SNI из scripts/sni_candidates.txt (или свои через --sni).

Что на выходе (в каталоге --out, по умолчанию scripts/configs/default/):
  server.json         Xray inbound: VLESS+Reality+TCP, serverNames=*whitelisted-SNI*
  client.json         sing-box outbound: тот же VLESS+Reality, fp=chrome
  links.txt           vless://-ссылки (по одной на SNI) — для Shadowrocket/v2rayNG/NekoBox
  info.txt            все параметры (UUID, ключи, shortId) в текстовом виде
  gen-keys.sh         команды для `openssl` (если в системе не нашёлся бинарь)
  README.md           что с этим делать (деплой + импорт)

Использование:

  # минимальный прогон — возьмёт 19 SNI из sni_candidates.txt
  python3 fresta_gen_vless.py

  # только пара SNI (например, лидеры по частоте из harvest-report.md)
  python3 fresta_gen_vless.py --sni ads.x5.ru --sni api-maps.yandex.ru

  # полный набор параметров
  python3 fresta_gen_vless.py \\
    --exit-ip 5.181.1.1 \\
    --exit-port 443 \\
    --dest www.google.com:443 \\
    --out configs/beget-2024-12 \\
    --short-id a1b2c3d4

  # свои ключи (если `openssl` не нашёлся или хочется переиспользовать)
  python3 fresta_gen_vless.py \\
    --private-key QL... --public-key QM...

Зависимости: Python 3.8+ stdlib. Для X25519 нужен `openssl` 1.1.1+ в PATH
(если его нет — будет написан gen-keys.sh, ключи попадут в config как
плейсхолдеры, ты их заменишь и пересоберёшь server.json).

Ключевая идея (см. docs/knowledge.md, раздел 8): IP VPS — whitelisted-подсеть
(Timeweb/Selectel/Beget), SNI — из scripts/sni_candidates.txt, fp=chrome обязательно,
в конфиге IP-литерал (внешний DNS у оператора закрыт).
"""

from __future__ import annotations  # PEP 563: lazy annotations, нужно для PEP 585 generic на py3.8

import argparse
import base64
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid
from urllib.parse import quote

# --- дефолты под наш стиль ----------------------------------------------------

# SNI-файл лежит в scripts/harvest/, относительно deploy/ — ../harvest/
DEFAULT_SNI_FILE = os.path.join(os.path.dirname(__file__), "..", "harvest", "sni_candidates.txt")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "configs", "default")
DEFAULT_PORT = 443
DEFAULT_DEST = "www.google.com:443"
DEFAULT_NAME = "fresta-reality"
DEFAULT_FP = "chrome"
DEFAULT_SHORT_ID_LEN = 4  # байта; Reality принимает 0..16

# placeholders в server.json — заметные, чтобы не задеплоить по забывчивости
PH_UUID = "UUID_REPLACE_ME"
PH_PRIV = "PRIVATE_KEY_REPLACE_ME_BASE64URL"
PH_PUB = "PUBLIC_KEY_REPLACE_ME_BASE64URL"
PH_IP = "CHANGE_ME.IP.LITERAL"


# --- утилиты -----------------------------------------------------------------


def b64url(raw: bytes) -> str:
    """base64url без padding — формат, который ждут Xray/sing-box для ключей."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def short_id(nbytes: int = DEFAULT_SHORT_ID_LEN) -> str:
    """hex-строка из nbytes случайных байт — то, что Reality называет shortId.
    Серверная сторона принимает 0..16 байт, клиентская — 0..16 hex-символов."""
    return secrets.token_hex(nbytes)


def read_sni_file(path: str) -> list[str]:
    """Список SNI (по одному в строке, # — комментарий). Дефолт — harvest'нутый файл."""
    out: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            d = line.strip()
            if not d or d.startswith("#"):
                continue
            out.append(d)
    return out


# --- генерация X25519 через openssl -----------------------------------------


def gen_x25519_openssl() -> tuple[str, str]:
    """(private_b64url, public_b64url) для X25519.
    OpenSSL CLI: genpkey → приватка PEM → DER (raw 32 байта в хвосте) →
    pubout DER (raw 32 байта в хвосте). Работает в OpenSSL 1.1.1+ / 3.x."""
    openssl = shutil.which("openssl")
    if not openssl:
        raise FileNotFoundError("openssl не найден в PATH")
    with tempfile.TemporaryDirectory() as tmp:
        priv_pem = os.path.join(tmp, "priv.pem")
        r = subprocess.run(
            [openssl, "genpkey", "-algorithm", "X25519", "-out", priv_pem],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"openssl genpkey: {r.stderr.strip()}")
        # Приватка DER: PKCS#8 PrivateKeyInfo для X25519 — последние 32 байта = seed.
        r = subprocess.run(
            [openssl, "pkey", "-in", priv_pem, "-outform", "DER"],
            capture_output=True,
        )
        if r.returncode != 0 or len(r.stdout) < 32:
            raise RuntimeError("openssl pkey DER (private) failed")
        priv_raw = r.stdout[-32:]
        # Публичная DER: SubjectPublicKeyInfo для X25519 — последние 32 байта = raw pub.
        r = subprocess.run(
            [openssl, "pkey", "-in", priv_pem, "-pubout", "-outform", "DER"],
            capture_output=True,
        )
        if r.returncode != 0 or len(r.stdout) < 32:
            raise RuntimeError("openssl pkey DER (public) failed")
        pub_raw = r.stdout[-32:]
    return b64url(priv_raw), b64url(pub_raw)


# --- сборщики конфигов -------------------------------------------------------


def build_server_json(
    snis: list[str], listen_ip: str, port: int, dest: str, private_key: str, short_id_hex: str
) -> dict:
    """Xray-core inbound: VLESS + Reality + TCP. Один клиент (UUID) — на одного тебя.
    show=false — Reality-ответы неотличимы от легит-сайта (см. knowledge.md, раздел 5)."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": listen_ip,
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": PH_UUID, "flow": ""}],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": dest,  # куда Reality проксирует «чужих»
                        "xver": 0,
                        "serverNames": snis,  # whitelisted-SNI, которые мы маскируем
                        "privateKey": private_key,  # 32 байта X25519, base64url без =
                        "shortIds": [short_id_hex, ""],  # пустой shortId тоже пускаем
                    },
                },
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
    }


def build_client_json(
    server_ip: str,
    port: int,
    sni: str,
    uuid_str: str,
    public_key: str,
    short_id_hex: str,
    fingerprint: str,
) -> dict:
    """sing-box outbound: VLESS+Reality+TCP+utls. Один SNI на конфиг —
    для ротации делай --out несколько раз с разными --sni или меняй server_name."""
    return {
        "outbounds": [
            {
                "type": "vless",
                "tag": "fresta-reality",
                "server": server_ip,
                "server_port": port,
                "uuid": uuid_str,
                "flow": "",
                "network": "tcp",
                "tls": {
                    "enabled": True,
                    "server_name": sni,
                    "utls": {
                        "enabled": True,
                        "fingerprint": fingerprint,  # chrome/firefox/safari/edge/qq/random
                    },
                    "reality": {
                        "enabled": True,
                        "public_key": public_key,
                        "short_id": short_id_hex,
                    },
                },
            }
        ],
        "route": {
            # дефолт: всё через наш туннель
            "final": "fresta-reality",
        },
    }


def build_vless_link(
    server_ip: str,
    port: int,
    sni: str,
    uuid_str: str,
    public_key: str,
    short_id_hex: str,
    fingerprint: str,
    name: str,
) -> str:
    """vless:// URI — формат, который жуют Shadowrocket/v2rayNG/NekoBox/Throne.
    encryption=none обязательно (VLESS), flow пустой (Reality), security=reality."""
    qs = (
        f"encryption=none"
        f"&type=tcp"
        f"&security=reality"
        f"&sni={quote(sni)}"
        f"&fp={quote(fingerprint)}"
        f"&pbk={quote(public_key)}"
        f"&sid={quote(short_id_hex)}"
    )
    return f"vless://{uuid_str}@{server_ip}:{port}?{qs}#{quote(name + '-' + sni)}"


# --- шаблоны текстовых артефактов ------------------------------------------

GEN_KEYS_SH = """#!/usr/bin/env bash
# fresta · сгенерируй X25519-ключи для Reality и подставь в server.json / client.json.
# OpenSSL 1.1.1+ / 3.x.

set -euo pipefail

PRIV_PEM="$(mktemp)"
trap 'rm -f "$PRIV_PEM"' EXIT

openssl genpkey -algorithm X25519 -out "$PRIV_PEM"

# privateKey: последние 32 байта DER-кодированной PKCS#8 PrivateKeyInfo
PRIV_B64URL=$(openssl pkey -in "$PRIV_PEM" -outform DER 2>/dev/null | tail -c 32 | base64 | tr -d '=' | tr '+/' '-_')

# publicKey:  последние 32 байта DER-кодированной SubjectPublicKeyInfo
PUB_B64URL=$(openssl pkey -in "$PRIV_PEM" -pubout -outform DER 2>/dev/null | tail -c 32 | base64 | tr -d '=' | tr '+/' '-_')

cat <<EOF
PRIVATE_KEY=$PRIV_B64URL
PUBLIC_KEY=$PUB_B64URL
EOF

echo
echo "Подставь PRIVATE_KEY в server.json → inbounds[].streamSettings.realitySettings.privateKey"
echo "Подставь PUBLIC_KEY  в client.json → outbounds[].tls.reality.public_key"
echo "и/или в vless://-ссылку (links.txt) → параметр pbk=..."
"""


README_TMPL = """\
# fresta · {name}

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

- **exit IP**: `{exit_ip}` (обязательно IP-литерал, не домен)
- **exit port**: `{exit_port}/tcp`
- **UUID**: `{uuid}`
- **shortId**: `{sid}`
- **uTLS fp**: `{fp}`
- **SNI ({n} шт.)**: {sni}
- **Reality dest**: `{dest}`

## Деплой на VPS (короткий чек-лист)

1. Поднять VPS на **whitelisted-провайдере** (Timeweb / Selectel / Beget /
   Yandex Cloud). Проверить, что выданный IP попал в подсеть из
   `../../../harvest/reports/harvest-report.md` (раздел «Провайдеры») +
   `../../../harvest/twl-data/twl-harvest-report.md` (топ-ASN + /24). Если
   провайдер позволяет — выбрать IP, проверив через `fresta_recon.py` или
   eyeball'ом.
2. Поставить Xray-core:
   ```bash
   bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
   ```
3. Положить `server.json` в `/usr/local/etc/xray/config.json` (или другой путь —
   см. `--config` у `xray`).
4. Открыть порт `{exit_port}/tcp` в фаерволе / панели хостера.
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
"""


def render_readme(
    name: str,
    exit_ip: str,
    exit_port: int,
    uuid_str: str,
    sid: str,
    fp: str,
    snis: list[str],
    dest: str,
) -> str:
    if len(snis) <= 6:
        sni_str = ", ".join(f"`{s}`" for s in snis)
    else:
        sni_str = ", ".join(f"`{s}`" for s in snis[:6]) + f", … (+{len(snis) - 6})"
    return README_TMPL.format(
        name=name,
        exit_ip=exit_ip,
        exit_port=exit_port,
        uuid=uuid_str,
        sid=sid,
        fp=fp,
        sni=sni_str,
        n=len(snis),
        dest=dest,
    )


# --- запись ------------------------------------------------------------------


def write_text(path: str, body: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def write_json(path: str, obj: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# --- entrypoint --------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description="fresta · генератор VLESS+Reality конфигов под whitelist",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Примеры:
              %(prog)s
              %(prog)s --sni ads.x5.ru --sni api-maps.yandex.ru
              %(prog)s --exit-ip 5.181.1.1 --out configs/beget-2024-12
        """),
    )
    ap.add_argument(
        "--sni",
        action="append",
        help="whitelisted-SNI (можно несколько). По умолчанию — из "
        f"{os.path.relpath(DEFAULT_SNI_FILE)}",
    )
    ap.add_argument(
        "--sni-file", default=DEFAULT_SNI_FILE, help="файл со списком SNI (по одному в строке)"
    )
    ap.add_argument(
        "--exit-ip",
        default=PH_IP,
        help="IP-литерал VPS (НЕ домен — внешний DNS у оператора закрыт)",
    )
    ap.add_argument(
        "--exit-port",
        type=int,
        default=DEFAULT_PORT,
        help=f"порт inbound на VPS (default {DEFAULT_PORT})",
    )
    ap.add_argument(
        "--listen-ip",
        default="0.0.0.0",
        help="адрес, на котором слушает Xray на VPS (default 0.0.0.0)",
    )
    ap.add_argument(
        "--dest",
        default=DEFAULT_DEST,
        help=f"dest для Reality — куда проксировать «чужих» (default {DEFAULT_DEST})",
    )
    ap.add_argument(
        "--name", default=DEFAULT_NAME, help="имя профиля в клиенте (default fresta-reality)"
    )
    ap.add_argument(
        "--fp",
        default=DEFAULT_FP,
        help=f"uTLS fingerprint (default {DEFAULT_FP}). chrome/firefox/safari/edge/qq/random",
    )
    ap.add_argument("--short-id", default=None, help="shortId hex (default — сгенерируем сами)")
    ap.add_argument("--uuid", default=None, help="UUID клиента (default — сгенерируем v4)")
    ap.add_argument(
        "--private-key", default=None, help="X25519 private key (base64url). По умолчанию — openssl"
    )
    ap.add_argument(
        "--public-key", default=None, help="X25519 public key (base64url). По умолчанию — openssl"
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"каталог для конфигов (default {os.path.relpath(DEFAULT_OUT)})",
    )
    args = ap.parse_args()
    # Нормализуем путь: на Windows `os.path.join` не разворачивает `\\` из CLI.
    args.out = os.path.normpath(args.out)
    args.exit_ip = args.exit_ip.strip()

    # 1. SNI.
    if args.sni:
        snis = list(args.sni)
    else:
        try:
            snis = read_sni_file(args.sni_file)
        except FileNotFoundError:
            sys.exit(f"Нет файла SNI {args.sni_file!r} и не переданы --sni.")
    if not snis:
        sys.exit("Список SNI пуст — нечего генерировать.")
    if not all(s.replace(".", "").replace("-", "").isalnum() for s in snis):
        sys.exit("SNI выглядят подозрительно — проверь ввод.")

    # 2. UUID / shortId.
    uuid_str = args.uuid or str(uuid.uuid4())
    sid = args.short_id or short_id()

    # 3. Ключи.
    priv, pub = args.private_key, args.public_key
    if priv and pub:
        pass  # пользователь принёс свои
    else:
        try:
            priv, pub = gen_x25519_openssl()
        except FileNotFoundError:
            priv, pub = PH_PRIV, PH_PUB
        except RuntimeError as e:
            sys.exit(
                f"Не смог сгенерировать X25519 ({e}). Передай --private-key/--public-key готовыми."
            )

    # 4. Сборка.
    server_cfg = build_server_json(snis, args.listen_ip, args.exit_port, args.dest, priv, sid)
    # подставим реальный UUID вместо плейсхолдера
    server_cfg["inbounds"][0]["settings"]["clients"][0]["id"] = uuid_str

    main_sni = snis[0]
    client_cfg = build_client_json(
        args.exit_ip, args.exit_port, main_sni, uuid_str, pub, sid, args.fp
    )

    links = [
        build_vless_link(args.exit_ip, args.exit_port, s, uuid_str, pub, sid, args.fp, args.name)
        for s in snis
    ]

    # 5. Каталог и запись.
    os.makedirs(args.out, exist_ok=True)
    write_json(os.path.join(args.out, "server.json"), server_cfg)
    write_json(os.path.join(args.out, "client.json"), client_cfg)
    write_text(os.path.join(args.out, "links.txt"), "\n".join(links) + "\n")
    write_text(os.path.join(args.out, "gen-keys.sh"), GEN_KEYS_SH)
    os.chmod(os.path.join(args.out, "gen-keys.sh"), 0o755)
    write_text(
        os.path.join(args.out, "README.md"),
        render_readme(
            args.name, args.exit_ip, args.exit_port, uuid_str, sid, args.fp, snis, args.dest
        ),
    )

    # info.txt — текстом, чтобы не лазить в JSON
    info = [
        "fresta · VLESS+Reality profile",
        "",
        f"  name          {args.name}",
        f"  exit_ip       {args.exit_ip}",
        f"  exit_port     {args.exit_port}/tcp",
        f"  listen_ip     {args.listen_ip}",
        f"  uuid          {uuid_str}",
        f"  private_key   {priv}",
        f"  public_key    {pub}",
        f"  short_id      {sid}",
        f"  fingerprint   {args.fp}",
        f"  dest          {args.dest}",
        f"  sni ({len(snis)})        " + ", ".join(snis),
    ]
    write_text(os.path.join(args.out, "info.txt"), "\n".join(info) + "\n")

    # 6. Итог.
    print(f"[+] Готово. Файлы в {args.out}:")
    print("      server.json     Xray inbound (VLESS+Reality+TCP)")
    print(f"      client.json     sing-box outbound, основной SNI = {main_sni}")
    print(f"      links.txt       {len(links)} vless://-ссылок (по одной на SNI)")
    print("      info.txt        UUID / ключи / shortId текстом")
    print("      gen-keys.sh     chmod +x — перегенерация X25519 (если надо)")
    print("      README.md       деплой на VPS + импорт в клиент")
    print()
    print(f"    UUID        {uuid_str}")
    print(f"    shortId     {sid}")
    print(f"    privateKey  {priv[:8]}…{priv[-4:]}")
    print(f"    publicKey   {pub[:8]}…{pub[-4:]}")
    if args.exit_ip == PH_IP:
        print(f"\n[!] exit_ip — плейсхолдер ({PH_IP}). Перед деплоем передай --exit-ip <IP>.")
    if priv == PH_PRIV:
        print(
            f"[!] `openssl` не нашёлся — ключи-плейсхолдеры. "
            f"Запусти {os.path.join(args.out, 'gen-keys.sh')} и подставь."
        )


if __name__ == "__main__":
    main()
