# fresta · tests

Smoke-тесты основных скриптов. Зависимостей нет (только stdlib + Python 3.8+).
Сеть используется частично: `test_handler` ходит на `https://example.com/` для
одного реального fetch (если сети нет — тест упадёт; это не баг теста).

## Прогон

Из корня репо (любой cwd):

```bash
bash scripts/tests/run_tests.sh            # Linux / macOS / Git Bash / WSL
powershell scripts/tests/run_tests.ps1     # Windows PowerShell
```

Из `scripts/tests/` (рядом с тестами):

```bash
bash run_tests.sh            # если уже cd scripts/tests
```

Или вручную, по одному (тоже из `scripts/tests/`):

```bash
python3 test_gen_vless.py
python3 test_handler.py
python3 test_harvest.py
python3 test_harvest_twl.py
python3 test_recon.py
```

Ожидаемый финал каждого теста — строка `ALL_*_OK`. Кейсы `OK: ...` —
промежуточные assert'ы (видно, какая ветка кода отработала).

## Что покрыто

| Тест | Кейсов | Что проверяет |
|------|-------:|---------------|
| `test_gen_vless.py`   | 10 | Негативные CLI-флаги (нет файла, пустой, битый SNI, пробел, относительный путь с `\\`); детерминированные UUID/shortId; `vless://`-парсинг; `--dest` / `--fp` |
| `test_handler.py`     | 14 | Токен-гейт (3 ветки), 4 «плохой конверт», 6 SSRF-целей, isBase64Encoded body, **реальный fetch к example.com** (200), POST с body, HOP-фильтр, defense-in-depth |
| `test_harvest.py`     |  8 | `provider_from_label` (эмодзи/флаги/url-encoded), `is_strong` (регексп по границам лейбла), `load` (plain / base64 / no-marker / garbage), `harvest` счётчики, `report` |
| `test_harvest_twl.py` | 17 | `looks_like_ip`, `provider_tag/short_name`, `match_provider/asn`, парсинг `sorted.c.json` + `subnets.c.json` (с фильтрацией мусора), все ветки `write_*` (фильтры по providers/asns/min_count/min_density), `write_report_md`, `write_meta` round-trip |
| `test_recon.py`       | 11 | Multi-ASN (приоритет `CDN_SIGNATURES`, порядок ASN неважен, fallback), edge-CF бьёт ASN, `read_domains` (dedup/комменты/scheme-strip) |

**Итого: 60+ кейсов, все зелёные на момент коммита.**

## Какие баги были пойманы и починены (для git blame)

Зафиксировано в `docs/knowledge.md`, раздел 6.

| Файл | Что было | Как починено |
|------|----------|--------------|
| `recon/fresta_recon.py` | `cymru_bulk` перезаписывал IP последним ASN; IP Яндекса (origin 13238/YANDEX + announcing 208398/TELETECH) ошибочно классифицировались как TELETECH → **NO-GO** для Фазы 0 | `info[ip] = list[(asn, asname)]`; `classify` итерирует по `CDN_SIGNATURES` (приоритет yes > hard > no); добавлена сигнатура `TELETECH/AS208398` (no) |
| `relay/yc_function/handler.py` | `req.get("url", "")` падал с `AttributeError`, если body — валидный JSON, но не объект (строка/массив) | После `json.loads` явная проверка `isinstance(req, dict)` |
| `harvest/harvest_subscription.py` | `is_strong` давал ложные срабатывания: `"rutube" in "rutube123.evil.ru"` → `True` | Регексп `r'(?:^|\.){hint}(?:\.|$)'` — hint матчится как отдельный доменный лейбл |
| `test_gen_vless.py` | `subprocess.run(..., text=True)` без `encoding=` берёт cp1251 на Windows; тесты на кириллице в stderr падают с UnicodeDecodeError | Добавлен `encoding="utf-8"` в `run()` |

## Когда запускать

- Перед каждым коммитом, трогающим `recon/fresta_recon.py`, `deploy/fresta_gen_vless.py`,
  `relay/yc_function/handler.py`, `harvest/harvest_subscription.py`, `harvest/harvest_twl.py`.
- После обновления `scripts/harvest/sni_candidates.txt` (чтобы убедиться, что
  `is_strong` корректно отделяет сильные SNI от мусора).
- После правок в `fresta_recon.CDN_SIGNATURES`.

## Известные ограничения

- `test_handler` **использует сеть** для одного финального fetch к
  `https://example.com/` (200 OK проверяется). Без сети этот кейс упадёт.
  Запускайте на машине с интернетом или пропускайте этот кейс.
- `test_harvest` создаёт временные файлы `_harv_tmp/` рядом со скриптом и
  удаляет их в конце. Если тест упал — проверьте, не остались ли мусорные
  файлы (в `.gitignore` стоит на всякий случай).
- `test_harvest_twl` создаёт `_harv_twl_tmp/` и тоже чистит за собой.
- `test_gen_vless` создаёт `_tmp*` директории. Cleanup в финале есть.

## Связанные модули

- `scripts/README.md` — общая карта scripts/.
- `docs/knowledge.md` §6 — фиксированные баги + контекст.
