"""smoke-тесты yc_function/handler.py — все ветки через мок event/context."""
import base64
import importlib.util
import json
import os
import sys

# 1. Загружаем модуль handler.py как обычный Python-модуль (не как пакет)
#    и подменяем TOKEN на тестовый.
# Тест лежит в scripts/tests/, а handler — в scripts/yc_function/.
_HANDLER_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "relay", "yc_function", "handler.py"))
spec = importlib.util.spec_from_file_location("handler", _HANDLER_PATH)
handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)
handler.TOKEN = "TEST_TOKEN_abc123"
handler.TIMEOUT = 5  # быстрее
handler.MAX_BODY = 1024 * 1024  # 1 МБ для теста


# Sentinel: token=_SENTINEL значит «вообще не добавлять заголовок» (имит. отсутствие).
# По умолчанию — корректный токен.
_SENTINEL = object()
DEFAULT_TOKEN = "TEST_TOKEN_abc123"


def call(body_obj=None, headers=None, token=DEFAULT_TOKEN, is_b64=False):
    """Сконструировать API Gateway-совместимый event и позвать handler()."""
    raw = json.dumps(body_obj).encode() if body_obj is not None else b""
    if is_b64:
        body_str = base64.b64encode(raw).decode()
    else:
        body_str = raw.decode()
    h = dict(headers or {})
    if token is not _SENTINEL:
        h["X-Fresta-Token"] = token
    evt = {
        "httpMethod": "POST",
        "headers": h,
        "body": body_str,
        "isBase64Encoded": is_b64,
    }
    return handler.handler(evt, None)


# --- 1. Токен-гейт ---------------------------------------------------------
r = call({"url": "https://example.com"}, token="WRONG")
assert r["statusCode"] == 403, f"bad token: {r}"
print("OK: 403 on wrong token")

# token не передан вообще (sentinel) — заголовок отсутствует
r = call({"url": "https://example.com"}, token=_SENTINEL)
assert r["statusCode"] == 403, f"missing token: {r}"
print("OK: 403 on missing token")

# Для остальных тестов — дефолтный токен подставляется автоматически.


# --- 2. Плохой конверт -----------------------------------------------------
r = call(None)
assert r["statusCode"] == 400, f"empty body: {r}"
print("OK: 400 on empty body")

r = call("not json at all")
assert r["statusCode"] == 400, f"non-json: {r}"
print("OK: 400 on non-json")

r = call({"no_url": True})
assert r["statusCode"] == 400, f"missing url: {r}"
print("OK: 400 on missing url")

r = call({"url": "ftp://example.com"})
assert r["statusCode"] == 400 and "http(s)" in r["body"], f"non-http url: {r}"
print("OK: 400 on ftp:// url")


# --- 3. SSRF-защита --------------------------------------------------------
for bad in ("http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.1/x",
            "http://192.168.0.1/x", "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/x"):
    r = call({"url": bad})
    assert r["statusCode"] == 403, f"SSRF {bad}: {r}"
print("OK: 403 on private/loopback/link-local targets (6 cases)")

# resolve-фейл (несуществующий хост) — _blocked_host должен вернуть True
r = call({"url": "http://nonexistent-fresta-test.invalid/x"})
assert r["statusCode"] == 403, f"unresolvable: {r}"
print("OK: 403 on unresolvable host (SSRF covers it)")


# --- 4. isBase64Encoded в body ---------------------------------------------
r = call({"url": "https://example.com"}, is_b64=True)
# Сеть в этой среде есть, example.com ответит 200 (или апстрим-ошибка 502)
assert r["statusCode"] in (200, 502), f"unexpected: {r['statusCode']}"
print(f"OK: isBase64Encoded body accepted -> status {r['statusCode']}")


# --- 5. Без сети: реальный запрос к example.com ---------------------------
# Если сеть есть, функция вернёт 200. Если нет — 502. Оба варианта — не 4xx.
r = call({"url": "https://example.com/", "method": "GET"})
assert r["statusCode"] in (200, 502), f"unexpected: {r}"
print(f"OK: real fetch -> status {r['statusCode']}")
if r["statusCode"] == 200:
    # isBase64Encoded=True — тело придёт к платформе уже декодированным, но
    # в нашей моде (handler.handler возвращает dict, как на API Gateway) body
    # всё ещё в base64. Клиент fresta_client.py:55-58 умеет оба варианта.
    import base64
    body_b64 = r["body"]
    try:
        payload = json.loads(body_b64)
    except ValueError:
        payload = json.loads(base64.b64decode(body_b64))
    assert "status" in payload and "body_b64" in payload
    print(f"   status={payload['status']}, headers={len(payload.get('headers', {}))} шт, "
          f"body={len(payload['body_b64'])} б64")


# --- 6. POST с телом -------------------------------------------------------
import base64 as b64
body = b64.b64encode(b'{"a":1}').decode()
r = call({"url": "https://httpbin.org/post", "method": "POST", "body_b64": body})
assert r["statusCode"] in (200, 502), f"unexpected: {r}"
print(f"OK: POST with body -> status {r['statusCode']}")


# --- 7. HOP-заголовки не пробрасываются -----------------------------------
# Это сложно проверить без мока urllib, но мы можем проверить, что функция
# хотя бы не падает, если в headers есть "connection", "host" и пр.
r = call({
    "url": "https://example.com",
    "headers": {"Host": "evil.com", "Connection": "keep-alive", "X-Fresta-Token": "leak"}
})
assert r["statusCode"] in (200, 502)
print("OK: HOP-header pass-through doesn't crash")


# --- 8. Токен-гейт: пустой TOKEN в модуле ---------------------------------
handler.TOKEN = ""
r = call({"url": "https://example.com"}, token="anything")
assert r["statusCode"] == 403, f"empty token config: {r}"
print("OK: 403 when module TOKEN is empty (defense-in-depth)")

print("\nALL_HANDLER_OK")
