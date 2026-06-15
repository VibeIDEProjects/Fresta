"""smoke-тесты harvest_twl.py — все ветки парсинга/фильтрации/генерации."""

import importlib.util
import json
import os
import shutil
import sys

# Фикс для Windows-консоли: по умолчанию stdout/stderr в cp1251/cp866, и
# `print("→")` / `print("─")` падают с UnicodeEncodeError. Переключаем
# на utf-8 с errors="replace" — на *nix ничего не меняется, на Windows
# некорректные символы заменяются на U+FFFD (тест не падает, вывод информативен).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # уже закрыт или не текстовый (subprocess-pipe не трогаем)

# Тест лежит в scripts/tests/, а сам скрипт — в scripts/harvest/.
_HARV = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "harvest", "harvest_twl.py"))
spec = importlib.util.spec_from_file_location("harvest_twl", _HARV)
htwl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(htwl)

# Изолированный tmp-каталог (рядом с тестом, не в scripts/)
TMP = os.path.join(os.path.dirname(__file__), "_harv_twl_tmp")
if os.path.isdir(TMP):
    shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)


# ─── 1. looks_like_ip ───────────────────────────────────────────────────────
ip_cases = [
    ("1.2.3.4", True),
    ("255.255.255.255", True),
    ("0.0.0.0", True),
    ("", False),
    ("1.2.3", False),
    ("1.2.3.4.5", False),
    ("1.2.3.256", False),
    ("abc.def.ghi.jkl", False),
    (" 1.2.3.4 ", True),  # strip'нется внутри
]
for raw, expected in ip_cases:
    got = htwl.looks_like_ip(raw)
    assert got == expected, f"looks_like_ip({raw!r}) -> {got}, expected {expected}"
print(f"OK: looks_like_ip ({len(ip_cases)} cases)")


# ─── 2. provider_tag / short_name ───────────────────────────────────────────
tag_cases = [
    ("Yandex.Cloud LLC", "Yandex Cloud"),
    ("Selectel Ltd.", "Selectel"),
    ("TIMEWEB Cloud", "Timeweb"),
    ("Beget LLC", "Beget"),
    ("VK LLC", "VK"),
    ("Cloudflare Inc.", "Cloudflare"),
    ("", None),
    ("Random Provider XYZ", None),
]
for name, expected in tag_cases:
    got = htwl.provider_tag(name)
    assert got == expected, f"provider_tag({name!r}) -> {got!r}, expected {expected!r}"
print(f"OK: provider_tag ({len(tag_cases)} cases)")

s = htwl.short_name("Yandex.Cloud LLC", 200350)
assert "Yandex" in s and "200350" in s, f"short_name: {s!r}"
print(f"OK: short_name -> {s!r}")


# ─── 3. match_provider / match_asn ─────────────────────────────────────────
assert htwl.match_provider("Yandex.Cloud LLC", []) is True
assert htwl.match_provider("Yandex.Cloud LLC", ["yandex"]) is True
assert htwl.match_provider("Yandex.Cloud LLC", ["selectel"]) is False
assert htwl.match_provider("Yandex.Cloud LLC", ["yandex", "selectel"]) is True
assert htwl.match_provider("", ["yandex"]) is False
print("OK: match_provider (5 cases)")

assert htwl.match_asn(200350, []) is True
assert htwl.match_asn(200350, [200350]) is True
assert htwl.match_asn(200350, [12345]) is False
assert htwl.match_asn(200350, [12345, 200350]) is True
print("OK: match_asn (4 cases)")


# ─── 4. parse_sorted / parse_subnets (мок-данные) ───────────────────────────
mock_sorted = [
    {
        "name": "Yandex.Cloud LLC",
        "asn": 200350,
        "count": 5,  # в реальном twl count == len(ips)
        "ips": ["130.193.35.68", "130.193.39.184", "130.193.42.148", "not-an-ip", "1.2.3.999"],
    },
    {
        "name": "Selectel Ltd.",
        "asn": 49505,
        "count": 3,  # 3 валидных IP
        "ips": ["95.213.45.1", "95.213.45.2", "95.213.45.3"],
    },
    {
        "name": "Beget LLC",
        "asn": 198610,
        "count": 4,  # 4 валидных IP
        "ips": ["5.181.1.1", "5.181.1.2", "5.181.1.3", "5.181.1.4"],
    },
]
mock_sorted_path = os.path.join(TMP, "sorted.json")
with open(mock_sorted_path, "w", encoding="utf-8") as f:
    json.dump(mock_sorted, f, ensure_ascii=False)
groups = htwl.parse_sorted(mock_sorted_path)
assert len(groups) == 3
# В Yandex было 5 IP в JSON (3 валидных + 2 мусорных); парсер фильтрует мусор
assert groups[0]["count"] == 3, f"yandex: {groups[0]}"
assert groups[0]["ips"] == ["130.193.35.68", "130.193.39.184", "130.193.42.148"]
assert "not-an-ip" not in groups[0]["ips"]
assert "1.2.3.999" not in groups[0]["ips"]
assert groups[1]["ips"] == ["95.213.45.1", "95.213.45.2", "95.213.45.3"]
assert groups[2]["count"] == 4
print("OK: parse_sorted (3 groups, фильтрация невалидных IP)")

mock_subnets = [
    {
        "cidr": "95.213.45.0/24",
        "count": 213,
        "total": 256,
        "percent": 83.2,
        "ips": ["95.213.45.1", "95.213.45.2"],
    },
    {
        "cidr": "5.181.1.0/24",
        "count": 4,
        "total": 256,
        "percent": 1.56,
        "ips": ["5.181.1.1", "5.181.1.2"],
    },
    {
        "cidr": "1.2.3.0/24",
        "count": 200,
        "total": 256,
        "percent": 78.1,
        "ips": ["1.2.3.1", "1.2.3.2"],
    },
]
mock_subnets_path = os.path.join(TMP, "subnets.json")
with open(mock_subnets_path, "w", encoding="utf-8") as f:
    json.dump(mock_subnets, f, ensure_ascii=False)
subnets = htwl.parse_subnets(mock_subnets_path)
assert len(subnets) == 3
assert subnets[0]["cidr"] == "95.213.45.0/24"
print("OK: parse_subnets (3 /24)")


# ─── 5. write_ips_txt / write_subnets_txt / write_report_md ─────────────────
ips_out = os.path.join(TMP, "ips.txt")
n_ips, n_asn = htwl.write_ips_txt(
    groups,
    providers=[],
    asns=[],
    min_count=1,
    out_path=ips_out,
)
assert n_ips == 3 + 3 + 4, f"n_ips={n_ips}"  # все 10 IP
assert n_asn == 3
# Проверим структуру файла
text = open(ips_out, encoding="utf-8").read()
assert "# ── Yandex Cloud AS200350" in text
assert "# ── Selectel AS49505" in text
assert "130.193.35.68" in text
assert "not-an-ip" not in text  # мусор отфильтрован
print(f"OK: write_ips_txt ({n_ips} IP, {n_asn} ASN)")

# min_count=5 → Yandex (3) и Selectel (3) выпадут, Beget (4) останется
n_ips2, n_asn2 = htwl.write_ips_txt(
    groups,
    providers=[],
    asns=[],
    min_count=5,
    out_path=ips_out,
)
assert n_asn2 == 0, f"должно быть 0 ASN при min_count=5, got {n_asn2}"
# Файл всё равно переписан (только заголовки, без IP)
text2 = open(ips_out, encoding="utf-8").read()
assert "групп (ASN): 0" in text2
print("OK: write_ips_txt (min_count=5 фильтрует)")

# providers=['yandex'] → только Yandex
n_ips3, n_asn3 = htwl.write_ips_txt(
    groups,
    providers=["yandex"],
    asns=[],
    min_count=1,
    out_path=ips_out,
)
assert n_asn3 == 1
assert n_ips3 == 3
text3 = open(ips_out, encoding="utf-8").read()
assert "Yandex" in text3
assert "Selectel" not in text3
assert "Beget" not in text3
print("OK: write_ips_txt (providers=['yandex'])")

# asns=[49505] → только Selectel
n_ips4, n_asn4 = htwl.write_ips_txt(
    groups,
    providers=[],
    asns=[49505],
    min_count=1,
    out_path=ips_out,
)
assert n_asn4 == 1
assert "Selectel" in open(ips_out, encoding="utf-8").read()
print("OK: write_ips_txt (asns=[49505])")

# subnets: min_density=0.5 → 95.213.45.0/24 (83%) и 1.2.3.0/24 (78%) пройдут
subnets_out = os.path.join(TMP, "subnets.txt")
n_sub = htwl.write_subnets_txt(subnets, min_density=0.5, out_path=subnets_out)
assert n_sub == 2
text_sub = open(subnets_out, encoding="utf-8").read()
assert "95.213.45.0/24" in text_sub
assert "5.181.1.0/24" not in text_sub  # 1.56% не прошла
print(f"OK: write_subnets_txt (min_density=0.5 → {n_sub} подсетей)")

# min_density=0.9 → ни одна не пройдёт
n_sub2 = htwl.write_subnets_txt(subnets, min_density=0.9, out_path=subnets_out)
assert n_sub2 == 0
print("OK: write_subnets_txt (min_density=0.9 → 0)")

# report.md
meta = {
    "ok": True,
    "source_repo": "https://example.com",
    "branch": "main",
    "commit_sha": "abc123def",
    "generated_at": "2026-06-14T17:00:00+00:00",
    "filters": {"providers": [], "asns": [], "min_count": 1, "min_subnet_density": 0.5},
    "files": {"sorted": True, "subnets": True, "verified": True},
    "asn_count": 3,
    "ip_count": 10,
    "subnet_count": 2,
    "top_asn": [
        {"name": "Yandex.Cloud LLC", "asn": 200350, "ip_count": 3, "tag": "Yandex Cloud"},
        {"name": "Selectel Ltd.", "asn": 49505, "ip_count": 3, "tag": "Selectel"},
        {"name": "Beget LLC", "asn": 198610, "ip_count": 4, "tag": "Beget"},
    ],
    "outputs": {
        "ips": "ips.txt",
        "subnets": "subnets.txt",
        "report": "report.md",
        "meta": "meta.json",
    },
}
report_path = os.path.join(TMP, "report.md")
htwl.write_report_md(meta, report_path)
report_text = open(report_path, encoding="utf-8").read()
assert "# fresta · twl-harvest отчёт" in report_text
assert "`abc123def`" in report_text
assert "Yandex.Cloud LLC" in report_text
assert "200350" in report_text
print("OK: write_report_md")

# meta.json
meta_path = os.path.join(TMP, "meta.json")
htwl.write_meta(meta, meta_path)
loaded = json.loads(open(meta_path, encoding="utf-8").read())
assert loaded["commit_sha"] == "abc123def"
assert loaded["asn_count"] == 3
print("OK: write_meta (round-trip)")


# ─── 6. build_provider_summary ─────────────────────────────────────────────
summary = htwl.build_provider_summary(groups, providers=[], asns=[], min_count=1)
assert summary["asn_count"] == 3
assert summary["ip_count"] == 3 + 3 + 4
assert summary["top_asn"][0]["ip_count"] == 4  # Beget лидирует
print("OK: build_provider_summary (top-1 = Beget)")

# фильтр по yandex
summary2 = htwl.build_provider_summary(groups, providers=["yandex"], asns=[], min_count=1)
assert summary2["asn_count"] == 1
assert summary2["ip_count"] == 3
print("OK: build_provider_summary (фильтр yandex)")


# cleanup
shutil.rmtree(TMP, ignore_errors=True)

print("\nALL_HARVEST_TWL_OK")
