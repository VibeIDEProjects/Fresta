#!/usr/bin/env python3
"""
fresta · recon (Фаза 0) — GO / NO-GO

Берёт список разрешённых доменов (белый список оператора), резолвит их в IP,
определяет, за каким CDN они живут, и говорит главное: есть ли среди них CDN,
на котором МЫ можем развернуть relay (в РФ это прежде всего Yandex Cloud,
а также Selectel / Timeweb и прочий российский VPS — см. скан twl).
Если да — щель есть, fresta имеет смысл. Если нет — проект мёртв на старте,
и хорошо, что мы это узнали за 5 минут, а не за месяц.

Запуск (лучше с того самого ограниченного мобильного канала — тогда заодно
проверишь реальную доступность edge):

    python3 fresta_recon.py whitelist.txt
    python3 fresta_recon.py whitelist.txt --probe        # + тест TLS-handshake к найденному CDN

whitelist.txt — по одному домену в строке, # для комментариев.

Зависимостей нет. Только стандартная библиотека Python 3.8+.
"""

import argparse
import concurrent.futures as cf
import ipaddress
import socket
import ssl
import sys

# --- Cloudflare публикует свои IPv4-диапазоны, они стабильны. -----------------
# Оффлайн-сигнал высокой точности: если IP попал сюда — это точно Cloudflare,
# даже если whois-имя по какой-то причине нечитаемо.
CLOUDFLARE_V4 = [ipaddress.ip_network(c) for c in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
)]

# --- Сигнатуры CDN по имени AS. ----------------------------------------------
# deploy: "yes"  — можем развернуть relay (наш сценарий)
#         "hard" — теоретически можно, но болезненно / фронтинг прикрыт
#         "no"   — relay не развернуть, как вход не годится
CDN_SIGNATURES = [
    # --- Российская инфра: то, что реально лежит в РФ-белом списке (по скану twl) ---
    ("YANDEX",     "Yandex Cloud", "yes",  "Functions / API Gateway / VPS — главный кандидат в РФ"),
    ("SELECTEL",   "Selectel",     "yes",  "VPS — бери IP в whitelisted-подсети"),
    ("TIMEWEB",    "Timeweb",      "yes",  "VPS, бесплатный reroll IP"),
    ("BEGET",      "Beget",        "yes",  "VPS-хостинг"),
    ("REG.RU",     "REG.RU",       "yes",  "VPS / хостинг"),
    ("REGRU",      "REG.RU",       "yes",  "VPS / хостинг"),
    ("RUVDS",      "RUVDS",        "yes",  "VPS-хостинг"),
    ("AEZA",       "Aeza",         "yes",  "VPS-хостинг"),
    ("VKONTAKTE",  "VK Cloud",     "hard", "VPS есть, но сложная верификация"),
    ("MAIL.RU",    "VK/Mail Cloud","hard", "VPS есть, верификация"),
    ("CDNVIDEO",   "CDNvideo",     "no",   "CDN — relay не развернуть, но годится как SNI"),
    ("DDOS-GUARD", "DDoS-Guard",   "no",   "WAF/CDN, edge закрыт (возможный SNI)"),
    ("ROSTELECOM", "Ростелеком",   "no",   "оператор, не разворачиваемо"),
    ("VIMPELCOM",  "Билайн",       "no",   "оператор"),
    ("MEGAFON",    "МегаФон",      "no",   "оператор"),
    # --- Западные CDN: в РФ-белом списке почти не встречаются, но мало ли ---
    ("CLOUDFLARE", "Cloudflare",   "yes",  "Workers (в РФ-БС редко)"),
    ("FASTLY",     "Fastly",       "yes",  "Compute@Edge (в РФ-БС редко)"),
    ("CLOUDFRONT", "CloudFront",   "yes",  "AWS CloudFront (в РФ-БС редко)"),
    ("AMAZON",     "Amazon/AWS",   "hard", "AWS (в РФ-БС практически нет)"),
    ("AKAMAI",     "Akamai",       "no",   "edge не развернуть"),
]

DEPLOY_RANK = {"yes": 0, "hard": 1, "no": 2, "?": 3}


def read_domains(path):
    out, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            d = line.strip()
            if not d or d.startswith("#"):
                continue
            d = d.split("//")[-1].split("/")[0]  # терпим к https://dom/path
            if d not in seen:
                seen.add(d)
                out.append(d)
    return out


def resolve(domain):
    """Домен -> множество IP (v4 и v6). Использует системный резолвер,
    т.е. ровно тот, что у тебя на канале."""
    ips = set()
    try:
        for fam, _, _, _, sockaddr in socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP):
            ips.add(sockaddr[0])
    except (socket.gaierror, UnicodeError) as e:
        return domain, set(), str(e)
    return domain, ips, None


def resolve_all(domains, workers=32):
    res, errors = {}, {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for domain, ips, err in ex.map(resolve, domains):
            res[domain] = ips
            if err:
                errors[domain] = err
    return res, errors


def cymru_bulk(ips):
    """IP -> (asn, as_name) через bulk-whois Team Cymru (без ключей).
    Если сеть не пускает к whois.cymru.com:43 — вернём пусто и обойдёмся
    оффлайн-сигналами (диапазоны Cloudflare)."""
    info = {}
    v4 = [ip for ip in ips if ":" not in ip]
    targets = v4 or list(ips)
    if not targets:
        return info
    payload = "begin\nverbose\n" + "\n".join(targets) + "\nend\n"
    try:
        with socket.create_connection(("whois.cymru.com", 43), timeout=15) as s:
            s.sendall(payload.encode())
            chunks = []
            while True:
                b = s.recv(8192)
                if not b:
                    break
                chunks.append(b)
        text = b"".join(chunks).decode(errors="replace")
    except OSError as e:
        print(f"[!] Team Cymru недоступен ({e}); работаю по оффлайн-сигналам.", file=sys.stderr)
        return info
    for line in text.splitlines():
        if "|" not in line or line.lower().startswith("bulk"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        asn, ip, _prefix, _cc, _reg, _alloc, asname = parts[:7]
        if not (asn.isdigit() or asn == "NA"):
            continue
        info[ip] = (asn, asname)
    return info


def is_cloudflare_range(ip):
    if ":" in ip:
        return False
    addr = ipaddress.ip_address(ip)
    return any(addr in net for net in CLOUDFLARE_V4)


def classify(ip, cymru):
    """IP -> (cdn_name, deploy, detail). Сначала точный оффлайн-сигнал CF,
    потом имя AS из Cymru."""
    if is_cloudflare_range(ip):
        return ("Cloudflare", "yes", "Workers — основной кандидат")
    asn, asname = cymru.get(ip, ("?", ""))
    up = asname.upper()
    for key, name, deploy, detail in CDN_SIGNATURES:
        if key in up:
            return (name, deploy, detail)
    if asname:
        return (f"{asname} (AS{asn})", "?", "не распознан как разворачиваемый CDN")
    return ("неизвестно", "?", "нет данных ASN")


def build(domains_ips, cymru):
    """Сводка: домен -> лучший CDN; и CDN -> домены/IP."""
    per_domain = {}
    per_cdn = {}
    for domain, ips in domains_ips.items():
        best = None  # (deploy_rank, cdn, deploy, detail)
        for ip in ips:
            cdn, deploy, detail = classify(ip, cymru)
            bucket = per_cdn.setdefault(cdn, {"deploy": deploy, "detail": detail,
                                              "domains": set(), "ips": set()})
            bucket["domains"].add(domain)
            bucket["ips"].add(ip)
            cand = (DEPLOY_RANK[deploy], cdn, deploy, detail)
            if best is None or cand < best:
                best = cand
        per_domain[domain] = best
    return per_domain, per_cdn


def probe(ip, sni, timeout=10):
    """Тест входа: TCP+TLS к edge-IP с разрешённым доменом в SNI.
    Проверяем, что handshake вообще проходит сквозь whitelist (не валидируем
    цепочку — нас интересует достижимость, а не аутентификация)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, 443), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=sni) as tls:
                proto = tls.version()
                cert = tls.getpeercert(binary_form=True)
                return True, f"{proto}, сертификат получен ({len(cert)} байт)"
    except Exception as e:  # noqa: BLE001 — нам нужен любой провал как «не прошло»
        return False, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description="fresta recon — есть ли в белом списке разворачиваемый CDN")
    ap.add_argument("whitelist", help="файл со списком разрешённых доменов (по одному в строке)")
    ap.add_argument("--probe", action="store_true",
                    help="после анализа проверить TLS-handshake к лучшему найденному CDN")
    ap.add_argument("--sni", help="домен для SNI в probe (по умолчанию — разрешённый домен за этим CDN)")
    args = ap.parse_args()

    try:
        domains = read_domains(args.whitelist)
    except FileNotFoundError:
        sys.exit(f"Нет файла {args.whitelist!r}. Создай его: по домену в строке.")
    if not domains:
        sys.exit("Список пуст.")

    print(f"[*] Резолвлю {len(domains)} доменов…")
    domains_ips, errors = resolve_all(domains)
    all_ips = {ip for ips in domains_ips.values() for ip in ips}
    if errors:
        print(f"[!] Не зарезолвились ({len(errors)}): {', '.join(sorted(errors))}")
    if not all_ips:
        sys.exit("Ни один домен не зарезолвился — проверь канал/DNS.")

    print(f"[*] Определяю ASN/CDN для {len(all_ips)} IP…")
    cymru = cymru_bulk(all_ips)
    per_domain, per_cdn = build(domains_ips, cymru)

    print("\n=== Что за каким CDN ===")
    for cdn, b in sorted(per_cdn.items(), key=lambda kv: DEPLOY_RANK[kv[1]["deploy"]]):
        mark = {"yes": "[GAP]", "hard": "[~]", "no": "[--]", "?": "[?]"}[b["deploy"]]
        ips_sample = ", ".join(sorted(b["ips"])[:3])
        print(f"\n{mark} {cdn}  ({b['detail']})")
        print(f"      доменов: {len(b['domains'])} | пример IP: {ips_sample}")
        print(f"      {', '.join(sorted(b['domains'])[:6])}"
              + (" …" if len(b["domains"]) > 6 else ""))

    # --- Вердикт ---
    deployable = {c: b for c, b in per_cdn.items() if b["deploy"] == "yes"}
    print("\n=== Вердикт ===")
    if deployable:
        best_cdn = min(deployable, key=lambda c: DEPLOY_RANK[deployable[c]["deploy"]])
        b = deployable[best_cdn]
        print(f"GO ✅  Щель есть: {best_cdn} — {b['detail']}")
        print(f"       За ним {len(b['domains'])} разрешённых домен(ов).")
        if best_cdn.startswith("Yandex"):
            print("       План: relay на Yandex Cloud (Functions / API Gateway / VPS).")
            print("       Эндпоинт *.yandexcloud.net обычно в whitelist у всех операторов.")
        else:
            print(f"       План: поднимаешь VPS/relay на {best_cdn} с whitelisted-IP.")
        print("       SNI бери из этих доменов, НО не из SNI-блеклиста")
        print("       (twitter/x/youtube местами палятся — проверь probe'ом).")
        if args.probe:
            sni = args.sni or sorted(b["domains"])[0]
            ip = sorted(b["ips"])[0]
            print(f"\n[*] Probe: TLS к {ip} с SNI={sni} …")
            ok, detail = probe(ip, sni)
            print(("    ОК ✅  " if ok else "    FAIL ❌  ") + detail)
            if ok:
                print("    Edge достижим сквозь whitelist и handshake проходит — вход рабочий.")
            else:
                print("    Edge не ответил: возможно whitelist режет и сам CDN, либо нужен другой SNI/IP.")
    else:
        print("NO-GO ⛔  В белом списке нет CDN, на котором можно развернуть relay.")
        print("        Фронтить не через что. Этим способом задача не решается —")
        print("        нужен другой вектор (или у проекта на этом канале нет щели).")


if __name__ == "__main__":
    main()
