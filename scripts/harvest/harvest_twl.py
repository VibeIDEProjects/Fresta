#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fresta · harvest_twl.py — забирает whitelisted-IP из openlibrecommunity/twl
                          и превращает в формат, пригодный для fresta.

Зачем:
  В twl лежат РЕАЛЬНЫЕ IP российских/SNG-провайдеров, которые мобильные
  операторы обязаны пропускать (по статье zarazaex, см. docs/knowledge.md §1).
  Это база для:
    - выбора VPS-провайдера под Метод 1 (нужен whitelisted-IP, иначе
      оператор дропнет пакет на L3 ещё до DPI);
    - оценки плотности /24 подсети (если 90% IP в подсети whitelisted,
      она почти гарантированно принадлежит этому провайдеру).

Что качает из twl (main):
    code/sort/out/sorted.c.json     IP, сгруппированные по ASN (проверенные)
    code/subnet/out/subnets.c.json  /24 с плотностью (проверенные)
    code/scan/out/verify/verified.txt  плоский список IP (для cross-check)

Что генерит (по умолчанию в scripts/twl-data/):
    ips.txt                  IP-литералы, по одному на строку,
                             с комментариями '# <provider> AS<asn> (<n> IP)'
    subnets.txt              CIDR с плотностью ≥ --min-subnet-density
    twl-harvest-report.md    статистика + источник + дата + commit SHA
    meta.json                структурированный мета (для CI)
    last_commit.txt          SHA последнего коммита twl (для дельты)
    repo/                    клон twl (если --keep-repo)

НЕ ТРОГАЕТ:
  scripts/whitelist.txt     (Минцифры — домены, другой набор данных)
  scripts/sni_candidates.txt (SNI из zieng2/wl, другой источник)

Использование:
    # Свежий harvest с дефолтами
    python3 scripts/harvest_twl.py

    # Только Yandex Cloud / Selectel / Timeweb, /24 плотность ≥ 70%
    python3 scripts/harvest_twl.py \
        --providers yandex --providers selectel --providers timeweb \
        --min-subnet-density 0.7

    # Оставить клон (повторный прогон = git pull, быстро)
    python3 scripts/harvest_twl.py --keep-repo

    # Из уже склонированного (оффлайн / CI кэш)
    python3 scripts/harvest_twl.py --repo-dir ./twl-mirror

    # Машинный вывод для CI
    python3 scripts/harvest_twl.py --json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ─────────── константы ──────────────────────────────────────────────────────

REPO_URL  = "https://github.com/openlibrecommunity/twl.git"
REPO_RAW  = "https://raw.githubusercontent.com/openlibrecommunity/twl"
BRANCH    = "main"

# Что качаем (относительно корня twl)
FILE_SORTED   = "code/sort/out/sorted.c.json"     # IP по ASN (проверенные)
FILE_SUBNETS  = "code/subnet/out/subnets.c.json"  # /24 подсети
FILE_VERIFIED = "code/scan/out/verify/verified.txt"  # плоский список

# Подстроки имени провайдера → человеко-читаемый тег (для комментариев и отчёта).
# Если name из twl содержит подстроку, ставим тег. Иначе — name из twl как есть.
PROVIDER_TAGS = [
    ("yandex",         "Yandex Cloud"),
    ("selectel",       "Selectel"),
    ("timeweb",        "Timeweb"),
    ("beget",          "Beget"),
    ("vk",             "VK"),
    ("cloud.ru",       "cloud.ru"),
    ("rostelecom",     "Rostelecom"),
    ("mts",            "MTS"),
    ("beeline",        "Beeline"),
    ("megafon",        "MegaFon"),
    ("tele2",          "Tele2"),
    ("datagroup",      "Datagroup"),
    ("telia",          "Telia"),
    ("retn",           "RETN"),
    ("cogent",         "Cogent"),
    ("ovh",            "OVH"),
    ("hetzner",        "Hetzner"),
    ("selectel-msk",   "Selectel-MSK"),
    ("cloudflare",     "Cloudflare"),
]

# ─────────── утилиты ────────────────────────────────────────────────────────

def log(msg, *, json_mode=False):
    if json_mode:
        return  # в JSON-режиме логи не нужны
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)

def die(msg, *, json_mode=False, **extra):
    if json_mode:
        out = {"ok": False, "error": msg}
        out.update(extra)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(1)
    print(f"[ERR] {msg}", file=sys.stderr)
    sys.exit(1)

def have(cmd):
    return shutil.which(cmd) is not None

def provider_tag(name):
    """Маппинг twl.name → короткий тег (для комментариев). None = не нашли."""
    if not name:
        return None
    n = name.lower()
    for substr, tag in PROVIDER_TAGS:
        if substr in n:
            return tag
    return None

def short_name(name, asn, maxlen=40):
    """Короткое имя для комментария: тег | name | AS<asn>."""
    tag = provider_tag(name) or name or "?"
    short = f"{tag} AS{asn}"
    if len(short) > maxlen:
        short = short[:maxlen-1] + "…"
    return short

def looks_like_ip(s):
    """Грубая проверка IPv4-литерала."""
    s = s.strip()
    if not s or s.count(".") != 3:
        return False
    parts = s.split(".")
    if not all(p.isdigit() for p in parts):
        return False
    return all(0 <= int(p) <= 255 for p in parts)

# ─────────── получение исходников twl ───────────────────────────────────────

def fetch_via_git(args, repo_dir):
    """git clone (или pull, если уже есть) + возврат commit SHA."""
    if not have("git"):
        die("git не найден в PATH; поставь git или используй --no-git (curl fallback)")

    if os.path.isdir(os.path.join(repo_dir, ".git")):
        log(f"repo уже есть в {repo_dir}, делаю git fetch + reset")
        subprocess.run(["git", "-C", repo_dir, "fetch", "--depth=1", "origin", BRANCH],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "reset", "--hard", f"origin/{BRANCH}"],
                       check=True, capture_output=True)
    else:
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
        os.makedirs(repo_dir, exist_ok=True)
        log(f"git clone --depth=1 {REPO_URL} → {repo_dir}")
        r = subprocess.run(
            ["git", "clone", "--depth=1", "--branch", BRANCH, REPO_URL, repo_dir],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            die(f"git clone упал: {r.stderr.strip() or r.stdout.strip()}")

    sha = subprocess.run(
        ["git", "-C", repo_dir, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return sha

def fetch_via_curl(repo_dir, http_timeout=30):
    """Fallback без git: тянем три файла напрямую через HTTPS."""
    if not have("curl"):
        die("ни git, ни curl не найдены — нечем качать twl")

    os.makedirs(repo_dir, exist_ok=True)
    sha = None
    # Пытаемся достать SHA последнего коммита через GitHub API
    try:
        with urllib.request.urlopen(
            f"https://api.github.com/repos/openlibrecommunity/twl/branches/{BRANCH}",
            timeout=http_timeout,
        ) as r:
            data = json.loads(r.read().decode("utf-8"))
            sha = data.get("commit", {}).get("sha")
    except Exception as e:
        log(f"не удалось узнать commit SHA через API ({e!r}); ok, продолжим без него")

    for rel in (FILE_SORTED, FILE_SUBNETS, FILE_VERIFIED):
        url = f"{REPO_RAW}/{BRANCH}/{rel}"
        dst = os.path.join(repo_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        log(f"curl {url} → {os.path.relpath(dst, repo_dir)}")
        try:
            with urllib.request.urlopen(url, timeout=http_timeout) as r:
                content = r.read()
            with open(dst, "wb") as f:
                f.write(content)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log(f"  404 — файл отсутствует в twl (пропускаю): {rel}")
            else:
                die(f"curl {url} → HTTP {e.code}: {e.reason}")
        except Exception as e:
            die(f"curl {url} → {e!r}")
    return sha

# ─────────── парсинг ────────────────────────────────────────────────────────

def parse_sorted(path):
    """sorted.c.json → [(provider_name, asn, count, [ip, ...]), ...].

    `count` отражает число ВАЛИДНЫХ IP (после фильтрации looks_like_ip),
    чтобы он совпадал с len(ips) и сортировка в write_ips_txt была корректной
    (в реальном twl count == len(ips) — это входной контракт, но мы не
    доверяем на 100% и считаем сами)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for entry in data:
        name = (entry.get("name") or "").strip()
        asn  = entry.get("asn") or 0
        ips_filtered = [ip for ip in (entry.get("ips") or []) if looks_like_ip(ip)]
        out.append({
            "name":  name,
            "asn":   asn,
            "count": len(ips_filtered),
            "ips":   ips_filtered,
        })
    return out

def parse_subnets(path):
    """subnets.c.json → [(cidr, count, total, percent, [ip, ...]), ...]."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for entry in data:
        out.append({
            "cidr":    entry.get("cidr", "").strip(),
            "count":   entry.get("count", 0),
            "total":   entry.get("total", 0),
            "percent": entry.get("percent", 0.0),
            "ips":     [ip for ip in (entry.get("ips") or []) if looks_like_ip(ip)],
        })
    return out

# ─────────── фильтры ────────────────────────────────────────────────────────

def match_provider(name, providers):
    """None = пропустить фильтр; [] = ничего не подходит; ['x'] = подстрока."""
    if not providers:
        return True
    if not name:
        return False
    n = name.lower()
    return any(p.lower() in n for p in providers)

def match_asn(asn, asns):
    if not asns:
        return True
    return asn in asns

# ─────────── генерация выходов ──────────────────────────────────────────────

def write_ips_txt(groups, providers, asns, min_count, out_path):
    """Группы по ASN, отсортированные по count ↓, фильтры применены.
    Формат: '# <tag> (N IP)' (заголовок группы), затем IP по одному на строку."""
    filtered = [
        g for g in groups
        if match_provider(g["name"], providers) and match_asn(g["asn"], asns)
        and g["count"] >= min_count
    ]
    filtered.sort(key=lambda g: g["count"], reverse=True)
    total_ips = 0
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# fresta · twl whitelisted-IP, отсортировано по count ↓\n")
        f.write(f"# источник: openlibrecommunity/twl ({FILE_SORTED})\n")
        f.write(f"# сгенерировано: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
        f.write(f"# фильтры: providers={providers or '—'} asns={asns or '—'} min_count={min_count}\n")
        f.write(f"# групп (ASN): {len(filtered)}\n\n")
        for g in filtered:
            tag = short_name(g["name"], g["asn"])
            f.write(f"\n# ── {tag} ({g['count']} IP) ──\n")
            for ip in g["ips"]:
                f.write(ip + "\n")
                total_ips += 1
    return total_ips, len(filtered)


def write_subnets_txt(subnets, min_density, out_path):
    """CIDR с плотностью ≥ порога. Каждый /24 — отдельная строка.

    Фильтр по провайдерам для /24 не реализован: в subnets.c.json twl
    нет прямой связи cidr→ASN. Если нужна связь — беги по IP вручную
    (эвристика: «/24 принадлежит X, если большинство его IP в группах X»)."""
    if not subnets:
        # Нет файла подсетей — пишем пустой файл с комментарием
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# подсети (/24) не получены (twl не содержит subnets.c.json)\n")
        return 0

    # twl хранит percent в 0..100 (напр. 83.2); пользовательский --min-subnet-density
    # в 0..1 (напр. 0.5). Нормализуем.
    min_percent = min_density * 100.0
    filtered = [s for s in subnets if s["percent"] >= min_percent]
    filtered.sort(key=lambda s: s["percent"], reverse=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# fresta · twl whitelisted-/24, отфильтровано по плотности\n")
        f.write(f"# источник: openlibrecommunity/twl ({FILE_SUBNETS})\n")
        f.write(f"# плотность ≥ {min_density * 100:.0f}%\n")
        f.write(f"# подсетей: {len(filtered)}\n\n")
        for s in filtered:
            f.write(f"{s['cidr']}    # {s['count']}/{s['total']} = {s['percent']:.1f}%\n")
    return len(filtered)


def build_provider_summary(groups, providers, asns, min_count):
    """Сводка для отчёта: топ-N ASN + total."""
    filtered = [
        g for g in groups
        if match_provider(g["name"], providers) and match_asn(g["asn"], asns)
        and g["count"] >= min_count
    ]
    filtered.sort(key=lambda g: g["count"], reverse=True)
    total_ips = sum(g["count"] for g in filtered)
    return {
        "asn_count": len(filtered),
        "ip_count":  total_ips,
        "top_asn":   [
            {
                "name":  g["name"],
                "asn":   g["asn"],
                "ip_count": g["count"],
                "tag":   provider_tag(g["name"]) or g["name"] or "?",
            }
            for g in filtered[:20]
        ],
    }


def write_report_md(meta, out_path):
    """Markdown-отчёт: статистика + источник + дата + commit SHA."""
    lines = []
    a = lines.append
    a("# fresta · twl-harvest отчёт")
    a("")
    a(f"- **источник**: [{REPO_URL}]({REPO_URL}) (branch `{BRANCH}`)")
    a(f"- **commit**: `{meta.get('commit_sha', '?')}`")
    a(f"- **дата harvest'а**: {meta['generated_at']}")
    a(f"- **фильтры**: providers={meta['filters']['providers'] or '—'}, "
      f"asns={meta['filters']['asns'] or '—'}, min_count={meta['filters']['min_count']}, "
      f"min_subnet_density={meta['filters']['min_subnet_density']}")
    a(f"- **файлов в twl**: "
      f"{'OK' if meta['files']['sorted']   else 'нет'} sorted, "
      f"{'OK' if meta['files']['subnets']  else 'нет'} subnets, "
      f"{'OK' if meta['files']['verified'] else 'нет'} verified")
    a("")
    a("## IP по ASN (топ-20)")
    a("")
    a(f"Всего IP: **{meta['ip_count']}** в {meta['asn_count']} ASN.")
    a("")
    a("| # | Провайдер | ASN | IP |")
    a("|---|-----------|----:|---:|")
    for i, t in enumerate(meta["top_asn"], 1):
        a(f"| {i} | {t['name']} | {t['asn']} | {t['ip_count']} |")
    a("")
    if meta.get("subnet_count", 0) > 0:
        a("## /24 подсети")
        a("")
        a(f"С плотностью ≥ {meta['filters']['min_subnet_density'] * 100:.0f}%: "
          f"**{meta['subnet_count']}** подсетей (см. `subnets.txt`).")
        a("")
    a("## Использование")
    a("")
    a("- `ips.txt` — IP-литералы для `fresta_recon.py --probe` (проверить, что наш")
    a("  провайдер реально их пропускает) или для выбора VPS-провайдера под Метод 1.")
    a("- `subnets.txt` — /24-подсети с высокой плотностью whitelisted-IP, удобно для")
    a("  оценки «всем ли IP в этой подсети повезло».")
    a("- `meta.json` — структурированный мета (CI может сравнивать commit SHA,")
    a("  детектить новые ASN и т.п.).")
    a("")
    a("## Что НЕ делает")
    a("")
    a("- **Не заменяет** `whitelist.txt` (Минцифры, домены) — это разные наборы.")
    a("- **Не заменяет** `sni_candidates.txt` (SNI из zieng2/wl) — twl не даёт SNI.")
    a("- **Не проксирует** ничего — это чистый harvest + форматирование.")
    a("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_meta(meta, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ─────────── main ────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="harvest_twl.py",
        description="Скачивает whitelisted-IP из openlibrecommunity/twl и "
                    "генерит ips.txt / subnets.txt / report.md под fresta.",
    )
    p.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "twl-data"
    ), help="куда положить результаты (default: scripts/twl-data/)")
    p.add_argument("--keep-repo", action="store_true",
                   help="оставить клон twl в <out-dir>/repo/ для последующих прогонов")
    p.add_argument("--repo-dir", default=None,
                   help="использовать уже склонированный twl (оффлайн / CI кэш)")
    p.add_argument("--no-git", action="store_true",
                   help="использовать curl вместо git clone (если git недоступен)")
    p.add_argument("--providers", action="append", default=[],
                   help="фильтр по подстроке имени провайдера (можно несколько)")
    p.add_argument("--asns", type=int, action="append", default=[],
                   help="фильтр по ASN (можно несколько; напр. 200350 для Yandex Cloud)")
    p.add_argument("--min-count", type=int, default=1,
                   help="минимальное число IP в ASN (default: 1, без фильтра)")
    p.add_argument("--min-subnet-density", type=float, default=0.5,
                   help="минимальная плотность /24 (0.0..1.0, default: 0.5)")
    p.add_argument("--http-timeout", type=int, default=30, help="таймаут HTTP, сек")
    p.add_argument("--json", action="store_true", help="машинный JSON-вывод (для CI)")
    args = p.parse_args()

    jm = args.json
    try:
        os.makedirs(args.out_dir, exist_ok=True)

        # 1. получаем исходники twl
        if args.repo_dir:
            repo_dir = args.repo_dir
            log(f"использую локальный repo: {repo_dir}", json_mode=jm)
            sha = subprocess.run(
                ["git", "-C", repo_dir, "rev-parse", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip() or None
        elif args.no_git or not have("git"):
            repo_dir = os.path.join(args.out_dir, "repo")
            sha = fetch_via_curl(repo_dir, args.http_timeout)
        else:
            repo_dir = os.path.join(args.out_dir, "repo")
            sha = fetch_via_git(args, repo_dir)

        # 2. парсим
        sorted_path   = os.path.join(repo_dir, FILE_SORTED)
        subnets_path  = os.path.join(repo_dir, FILE_SUBNETS)
        verified_path = os.path.join(repo_dir, FILE_VERIFIED)

        groups   = parse_sorted(sorted_path)  if os.path.isfile(sorted_path)   else []
        subnets  = parse_subnets(subnets_path) if os.path.isfile(subnets_path) else []
        verified = []
        if os.path.isfile(verified_path):
            with open(verified_path, encoding="utf-8") as f:
                verified = [line.strip() for line in f if looks_like_ip(line.strip())]

        log(f"распарсил: {len(groups)} ASN, {len(subnets)} /24, {len(verified)} verified IP",
            json_mode=jm)

        # 3. генерим выходы
        ips_path     = os.path.join(args.out_dir, "ips.txt")
        subnets_path_out = os.path.join(args.out_dir, "subnets.txt")
        report_path  = os.path.join(args.out_dir, "twl-harvest-report.md")
        meta_path    = os.path.join(args.out_dir, "meta.json")

        total_ips, asn_count = write_ips_txt(
            groups, args.providers, args.asns, args.min_count, ips_path,
        )
        subnet_count = write_subnets_txt(
            subnets, args.min_subnet_density, subnets_path_out,
        )

        # 4. meta
        summary = build_provider_summary(groups, args.providers, args.asns, args.min_count)
        meta = {
            "ok":              True,
            "source_repo":     REPO_URL,
            "branch":          BRANCH,
            "commit_sha":      sha,
            "generated_at":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "filters": {
                "providers":         args.providers,
                "asns":              args.asns,
                "min_count":         args.min_count,
                "min_subnet_density": args.min_subnet_density,
            },
            "files": {
                "sorted":   os.path.isfile(sorted_path),
                "subnets":  os.path.isfile(subnets_path),
                "verified": os.path.isfile(verified_path),
            },
            "asn_count":    summary["asn_count"],
            "ip_count":     summary["ip_count"],
            "subnet_count": subnet_count,
            "top_asn":      summary["top_asn"],
            "outputs": {
                "ips":     os.path.relpath(ips_path,        args.out_dir),
                "subnets": os.path.relpath(subnets_path_out, args.out_dir),
                "report":  os.path.relpath(report_path,     args.out_dir),
                "meta":    os.path.relpath(meta_path,       args.out_dir),
            },
        }

        write_report_md(meta, report_path)
        write_meta(meta, meta_path)

        # 5. финал
        if not args.keep_repo and not args.repo_dir:
            shutil.rmtree(repo_dir, ignore_errors=True)
            log("клон twl удалён (используй --keep-repo чтобы оставить)", json_mode=jm)

        log(f"готово: ips={total_ips}, asn={asn_count}, /24={subnet_count}", json_mode=jm)

        if jm:
            print(json.dumps(meta, ensure_ascii=False, indent=2))
        else:
            print()
            print(f"  ips.txt             {total_ips} IP, {asn_count} ASN")
            print(f"  subnets.txt         {subnet_count} /24 (плотность ≥ "
                  f"{args.min_subnet_density * 100:.0f}%)")
            print(f"  twl-harvest-report.md")
            print(f"  meta.json")
            print()
            print(f"  commit: {sha or '?'}")
            print(f"  out:    {args.out_dir}")
            print()
            print("  подробности — в twl-harvest-report.md")
    except SystemExit:
        raise
    except Exception as e:
        die(f"неожиданная ошибка: {e!r}", json_mode=jm)


if __name__ == "__main__":
    main()