"""smoke-тесты harvest_subscription.py — все ветки парсинга."""

import base64
import importlib.util
import os
import shutil
import sys

# Фикс для Windows-консоли: по умолчанию stdout/stderr в cp1251/cp866, и
# `print("→")` / `print("🇷🇺")` падают с UnicodeEncodeError. Переключаем
# на utf-8 с errors="replace" — на *nix ничего не меняется, на Windows
# некорректные символы заменяются на U+FFFD (тест не падает, вывод информативен).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # уже закрыт или не текстовый (subprocess-pipe не трогаем)

# Тест лежит в scripts/tests/, а сам скрипт — в scripts/harvest/.
_HARV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "harvest", "harvest_subscription.py")
)
spec = importlib.util.spec_from_file_location("h", _HARV_PATH)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

# --- tmpdir для фикстур: tests/_harv_tmp/ (рядом с тестом, не в scripts/) --
TMP = os.path.join(os.path.dirname(__file__), "_harv_tmp")
if os.path.isdir(TMP):
    shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
F_PLAIN = os.path.join(TMP, "plain.txt")
F_B64 = os.path.join(TMP, "b64.txt")
F_B64B = os.path.join(TMP, "b64b.txt")
F_GARB = os.path.join(TMP, "garbage.txt")


# --- 1. provider_from_label: эмодзи/флаги в начале, '— #N' в конце ---------
cases = [
    ("🇷🇺 Beget — #2", "Beget"),
    ("🇳🇱 The Netherlands — #14", "The Netherlands"),
    ("☁ Timeweb, Cloud Hosting", "Timeweb, Cloud Hosting"),
    ("🏴☠️ Selectel #1", "Selectel"),  # pirate flag, спецсимволы
    ("# просто коммент", "?"),  # после stripper остаётся пусто
    ("   ", "?"),
    ("vk.com%20—%20#5", "vk.com"),  # url-encoded
]
for raw, expected in cases:
    got = h.provider_from_label(raw)
    assert got == expected, f"provider_from_label({raw!r}) -> {got!r}, expected {expected!r}"
print(f"OK: provider_from_label ({len(cases)} cases)")


# --- 2. is_strong: проверка границ ----------------------------------------
strong_cases = [
    ("ads.x5.ru", True),  # x5.ru
    ("api-maps.yandex.ru", True),  # yandex
    ("smartcaptcha.yandexcloud.net", True),  # yandexcloud
    ("m.vk.com", True),
    ("max.ru", True),
    ("rutube.ru", True),
    ("rutube123.evil.ru", False),  # не в whitelist
    ("some-random-host.com", False),
    ("", False),
]
for sni, expected in strong_cases:
    got = h.is_strong(sni)
    assert got == expected, f"is_strong({sni!r}) -> {got}, expected {expected}"
print(f"OK: is_strong ({len(strong_cases)} cases)")


# --- 3. load(): файл (plain vless://) --------------------------------------
plain_fixture = "\n".join(
    [
        "vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443?security=reality&type=tcp&sni=ads.x5.ru&fp=chrome#🇷🇺 Beget — #1",
        "vless://22222222-2222-2222-2222-222222222222@5.6.7.8:443?security=reality&type=grpc&sni=api.yandex.ru&fp=firefox#🇳🇱 The Netherlands — #5",
        "# это комментарий, не vless://",
        "",
        "garbage line without scheme",
        "vless://badhostnoport/",
    ]
)
try:
    with open(F_PLAIN, "w", encoding="utf-8") as f:
        f.write(plain_fixture)
    lines = h.load(F_PLAIN)
    # load() фильтрует только по префиксу "vless://" — невалидные URI тоже проходят.
    # В нашей фикстуре таких 3 (две валидные + "vless://badhostnoport/").
    assert len(lines) == 3, f"expected 3 vless:// lines, got {len(lines)}"
    print(f"OK: load(plain file) -> {len(lines)} vless lines (вкл. мусорные)")

    # --- 4. load(): файл в base64 ------------------------------------------
    b64_fixture = base64.b64encode(plain_fixture.encode()).decode()
    with open(F_B64, "w") as f:
        f.write(b64_fixture)
    lines = h.load(F_B64)
    assert len(lines) == 3, f"expected 3 from base64, got {len(lines)}"
    print(f"OK: load(base64 file) -> {len(lines)} vless lines")

    # --- 5. load(): base64 без vless://, но после декода есть ---------------
    #  (типичный кейс — подписка, обёрнутая в base64 целиком)
    b64_no_marker = base64.b64encode(b"vless://abc@1.1.1.1:443?sni=test\n").decode()
    with open(F_B64B, "w") as f:
        f.write(b64_no_marker + "\n")
    lines = h.load(F_B64B)
    assert len(lines) == 1, f"expected 1 from base64 no-marker, got {len(lines)}"
    print("OK: load(base64 no-marker) → decode → 1 line")

    # --- 6. load(): мусор (не base64, не vless) → [] без падения -----------
    with open(F_GARB, "w") as f:
        f.write("this is not vless and not base64\njust garbage\n")
    lines = h.load(F_GARB)
    assert lines == [], f"expected [], got {lines}"
    print("OK: load(garbage) -> []")
finally:
    # Гарантированный cleanup (даже если упал assert / KeyboardInterrupt).
    shutil.rmtree(TMP, ignore_errors=True)


# --- 7. harvest(): все счётчики --------------------------------------------
res = h.harvest(
    [
        "vless://u@1.2.3.4:443?security=reality&type=tcp&sni=ads.x5.ru&fp=chrome#🇷🇺 Beget — #1",
        "vless://u@5.6.7.8:443?security=reality&type=grpc&sni=api.yandex.ru&fp=firefox#🇷🇺 Beget — #2",
        "vless://u@9.10.11.12:443?security=tls&type=ws&sni=m.vk.com&fp=qq#🇳🇱 The Netherlands — #3",
        "vless://u@0.0.0.0:443?sni=placeholder",  # плейсхолдер → пропускается
        "vless://u@example.com:443?sni=test.com#no flag",  # доменный хост
        "vless://00000000-0000-0000-0000-000000000000@1.1.1.1:443?sni=also-placeholder",  # плейсхолдер UUID
    ]
)
assert res["real"] == 4, f"real: {res['real']}"
assert res["ip_hosts"] == 3, f"ip_hosts: {res['ip_hosts']}"
assert res["dom_hosts"] == 1, f"dom_hosts: {res['dom_hosts']}"
assert res["sni"]["ads.x5.ru"] == 1
assert res["sni"]["api.yandex.ru"] == 1
assert res["sni"]["m.vk.com"] == 1
assert res["providers"]["Beget"] == 2, f"Beget: {res['providers']}"
assert res["providers"]["The Netherlands"] == 1
assert res["providers"]["no flag"] == 1
assert res["sec"]["reality"] == 2
assert res["sec"]["tls"] == 1
assert res["typ"]["tcp"] == 1
assert res["typ"]["grpc"] == 1
assert res["typ"]["ws"] == 1
assert res["fp"]["chrome"] == 1
print(
    f"OK: harvest() counts: {res['real']} real, "
    f"ip={res['ip_hosts']}, dom={res['dom_hosts']}, "
    f"sni={len(res['sni'])}, providers={len(res['providers'])}"
)


# --- 8. report(): smoke — должен быть валидный markdown --------------------
r = h.report(res, "test-source")
assert "# fresta · harvest-снимок подписки" in r
assert "ads.x5.ru" in r
assert "The Netherlands" in r
print(f"OK: report() produced {len(r.splitlines())} lines")


print("\nALL_HARVEST_OK")
