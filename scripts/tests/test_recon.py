"""smoke-тесты fresta_recon.py — multi-ASN классификация и базовые случаи."""

import importlib.util
import os

# Тест лежит в scripts/tests/, а сам скрипт — в scripts/recon/.
_RECON_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "recon", "fresta_recon.py")
)
spec = importlib.util.spec_from_file_location("r", _RECON_PATH)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


# 1. Один ASN → старая логика работает
cdn, dep, det = r.classify("1.2.3.4", [("13215", "YANDEX")])
assert cdn == "Yandex Cloud" and dep == "yes", cdn
print(f"OK: single ASN Yandex -> {cdn}/{dep}")


# 2. Два ASN: YANDEX (origin) + TELETECH (announcing) — origin должен выиграть
cdn, dep, det = r.classify(
    "5.255.255.77",
    [
        ("13238", "YANDEX - YANDEX LLC, RU"),
        ("208398", "TELETECH - Edge Technology Plus d.o.o. Beograd, RS"),
    ],
)
assert cdn == "Yandex Cloud" and dep == "yes", cdn
assert "TELETECH" in det, f"detail должен упомянуть TELETECH: {det}"
print(f"OK: multi-ASN (YANDEX + TELETECH) -> {cdn}, detail: {det}")


# 3. Два ASN в обратном порядке: TELETECH первый в списке (как отдаёт Cymru
#    bulk: AS13238 идёт раньше AS208398, но проверим, что порядок не важен —
#    YANDEX всё равно выигрывает по приоритету CDN_SIGNATURES).
cdn, dep, det = r.classify(
    "5.255.255.77",
    [("208398", "TELETECH - Edge Technology Plus"), ("13238", "YANDEX - YANDEX LLC, RU")],
)
assert cdn == "Yandex Cloud", f"порядок ASN не должен ломать приоритет: {cdn}"
print(f"OK: порядок ASN неважен, Yandex всё равно приоритетный -> {cdn}")


# 4. Только TELETECH (без origin) — должен попасть в 'no' (оператор)
cdn, dep, det = r.classify("5.255.255.77", [("208398", "TELETECH - Edge Technology Plus")])
assert cdn == "TELETECH/AS208398" and dep == "no", cdn
print(f"OK: только TELETECH -> {cdn}/{dep}")


# 5. Неизвестная AS (например, банковская) — попадает в '?'
cdn, dep, det = r.classify("1.2.3.4", [("15632", "Alfa-Bank-AS - JSC Alfa-Bank, RU")])
assert dep == "?" and "AS15632" in cdn, cdn
print(f"OK: неизвестная AS -> {cdn}/{dep}")


# 6. Пустой список — fallback
cdn, dep, det = r.classify("1.2.3.4", [])
assert cdn == "неизвестно" and dep == "?", cdn
print(f"OK: пустой список -> {cdn}/{dep}")


# 7. Cloudflare range — оффлайн-сигнал выигрывает у ASN
cdn, dep, det = r.classify("104.16.0.0", [("13335", "CLOUDFLARE - Cloudflare, Inc., US")])
assert cdn == "Cloudflare" and dep == "yes", cdn
print(f"OK: CF-диапазон -> {cdn}/{dep} (offline signal beats ASN)")


# 8. Несколько ASN в детали указываются для отладки
cdn, dep, det = r.classify(
    "8.8.8.8", [("15169", "GOOGLE - Google LLC, US"), ("36040", "YOUTUBE - Google LLC, US")]
)
assert dep == "?" and "AS36040" in det, det
print(f"OK: multi-ASN для '?' -> detail содержит 'ещё AS: AS36040': {det}")


# 9. build() с multi-ASN данными — лучший CDN по домену выбирается правильно
per_domain, per_cdn = r.build(
    {"yandex.ru": ["5.255.255.77"], "google.com": ["8.8.8.8"]},
    {
        "5.255.255.77": [
            ("13238", "YANDEX - YANDEX LLC, RU"),
            ("208398", "TELETECH - Edge Technology Plus"),
        ],
        "8.8.8.8": [("15169", "GOOGLE - Google LLC, US")],
    },
)
assert per_domain["yandex.ru"][1] == "Yandex Cloud", per_domain
assert per_domain["google.com"][1] == "GOOGLE - Google LLC, US (AS15169)", per_domain
print(f"OK: build() multi-ASN: yandex.ru -> {per_domain['yandex.ru'][1]}")


# 10. read_domains: дедуп, нормализация, комментарии
with open("_recon_test.txt", "w", encoding="utf-8") as f:
    f.write("# comment\n\nfoo.ru\nhttps://bar.ru/path\nfoo.ru\n  \n")
ds = r.read_domains("_recon_test.txt")
assert ds == ["foo.ru", "bar.ru"], ds
os.remove("_recon_test.txt")
print("OK: read_domains dedup + scheme-strip + comments")


# 11. CDN_SIGNATURES: TELETECH добавлен
sig_keys = [k for k, *_ in r.CDN_SIGNATURES]
assert "TELETECH" in sig_keys
assert "YANDEX" in sig_keys
print("OK: TELETECH сигнатура добавлена")


print("\nALL_RECON_OK")
