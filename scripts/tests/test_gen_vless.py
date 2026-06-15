"""smoke-тесты fresta_gen_vless.py — негативные кейсы CLI."""

import os
import shutil
import subprocess
import sys

# Тест лежит в scripts/tests/, а сам скрипт — на уровень выше, в scripts/.
SCRIPT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "deploy", "fresta_gen_vless.py")
)
PY = sys.executable


def run(*args, expect_fail=True):
    # Фикс для Windows-консоли (Python 3.13 в пайпе по умолчанию пишет в
    # системной кодировке — cp1251/cp866; родительский encoding="utf-8"
    # тогда падает на кириллице в stderr с UnicodeDecodeError).
    # Заставляем сабпроцесс использовать UTF-8 для stdio через переменные
    # окружения; тогда байты в пайпе — валидный UTF-8 и родитель их прочтёт.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    r = subprocess.run(
        [PY, SCRIPT, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return r


# 1. несуществующий sni-файл
r = run("--sni-file", "nope.txt")
assert r.returncode != 0 and "Нет файла SNI" in r.stderr, r.stderr
print("OK: no-file exit")

# 2. пустой sni-файл
with open("_empty.txt", "w") as fh:
    pass
r = run("--sni-file", "_empty.txt", "--out", "_tmp_empty")
assert r.returncode != 0 and "пуст" in r.stderr, r.stderr
print("OK: empty-file exit")

# 3. подозрительный SNI (с http://)
r = run("--sni", "http://foo.bar/", "--out", "_tmp_bad")
assert r.returncode != 0 and "подозрительно" in r.stderr, r.stderr
print("OK: bad-SNI exit")

# 4. пробел в SNI
r = run("--sni", "foo bar", "--out", "_tmp_bad2")
assert r.returncode != 0, r.stderr
print("OK: whitespace-SNI exit")

# 5. относительный путь с обратным слэшем (Windows-нормализация)
out = r"_tmp\rel"
r = run("--sni", "ads.x5.ru", "--out", out)
assert r.returncode == 0, f"exit={r.returncode} stderr={r.stderr}"
# os.path.normpath(r'tmp\rel') = 'tmp\\rel' (относительный); каталог должен быть создан
norm = os.path.normpath(out)
assert os.path.isdir(norm), f"каталог {norm!r} не создался (cwd={os.getcwd()})"
print(f"OK: relative path normalized -> {norm}")

# 6. длинный список SNI (все 19) — лимиты
r = run("--exit-ip", "5.181.1.1", "--out", "_tmp_full")
assert r.returncode == 0, r.stderr
import json

with open(os.path.join("_tmp_full", "server.json"), encoding="utf-8") as fh:
    srv = json.load(fh)
n_sni = len(srv["inbounds"][0]["streamSettings"]["realitySettings"]["serverNames"])
assert n_sni == 19, f"expected 19 SNI, got {n_sni}"
print(f"OK: full run -> {n_sni} SNI in server.json")

# 7. UUID и shortId — детерминированные через --uuid/--short-id
r = run(
    "--sni",
    "ads.x5.ru",
    "--exit-ip",
    "5.181.1.1",
    "--out",
    "_tmp_det",
    "--uuid",
    "11111111-2222-3333-4444-555555555555",
    "--short-id",
    "deadbeef",
)
assert r.returncode == 0, r.stderr
with open(os.path.join("_tmp_det", "server.json"), encoding="utf-8") as fh:
    srv = json.load(fh)
assert srv["inbounds"][0]["settings"]["clients"][0]["id"] == "11111111-2222-3333-4444-555555555555"
assert srv["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"][0] == "deadbeef"
print("OK: deterministic UUID/shortId")

# 8. vless:// парсятся: scheme=vless, security=reality, все SNI присутствуют
with open(os.path.join("_tmp_full", "links.txt"), encoding="utf-8") as fh:
    links = [line.strip() for line in fh if line.strip()]
assert len(links) == 19, f"expected 19 links, got {len(links)}"
for L in links:
    assert L.startswith("vless://"), L[:60]
    assert "security=reality" in L
    assert "fp=chrome" in L
print("OK: 19 vless:// links, all reality+chrome")

# 9. --dest попадает в server.json
r = run(
    "--sni",
    "ads.x5.ru",
    "--exit-ip",
    "5.181.1.1",
    "--dest",
    "www.microsoft.com:443",
    "--out",
    "_tmp_dest",
)
with open(os.path.join("_tmp_dest", "server.json"), encoding="utf-8") as fh:
    srv = json.load(fh)
assert srv["inbounds"][0]["streamSettings"]["realitySettings"]["dest"] == "www.microsoft.com:443"
print("OK: custom --dest applied")

# 10. fingerprint: --fp firefox
r = run("--sni", "ads.x5.ru", "--exit-ip", "5.181.1.1", "--fp", "firefox", "--out", "_tmp_fp")
with open(os.path.join("_tmp_fp", "client.json"), encoding="utf-8") as fh:
    cli = json.load(fh)
assert cli["outbounds"][0]["tls"]["utls"]["fingerprint"] == "firefox"
print("OK: --fp firefox applied")

# cleanup
for d in (
    "_tmp_empty",
    "_tmp_bad",
    "_tmp_bad2",
    r"_tmp\rel",
    "_tmp_full",
    "_tmp_det",
    "_tmp_dest",
    "_tmp_fp",
    "_empty.txt",
):
    p = os.path.normpath(d)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.isfile(p):
        os.remove(p)

print("\nALL_GEN_VLESS_NEGATIVE_OK")
