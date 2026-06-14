# fresta · twl-harvest — реальные whitelisted-IP от openlibrecommunity

Скрипт `scripts/harvest/harvest_twl.py` забирает **живой** список whitelisted-IP из
[openlibrecommunity/twl](https://github.com/openlibrecommunity/twl)
(проект zarazaex: эмпирический скан «открытый 443 у РФ/SNG-провайдеров»).

Это **другой** набор данных, не `scripts/recon/whitelist.txt`:

| Файл | Источник | Что |
|------|----------|-----|
| `scripts/recon/whitelist.txt`            | kod.ru / Минцифры (реконструкция) | **домены** (143 шт) |
| `scripts/harvest/sni_candidates.txt`     | zieng2/wl (живая подписка)        | **SNI** (19 шт)    |
| `scripts/harvest/twl-data/ips.txt`       | openlibrecommunity/twl (harvest)  | **IP** (≈44k)      |
| `scripts/harvest/twl-data/subnets.txt`   | openlibrecommunity/twl (harvest)  | **/24 подсети** (≈41 /24 с плотностью ≥ 50%) |

То есть twl **не даёт SNI** — для SNI используй `sni_candidates.txt` (zieng2).
А для выбора **своего** VPS-провайдера и проверки **реальной** плотности
whitelisted-IP в подсети — `twl-data/`.

## Что генерит harvest

- `ips.txt` — IP-литералы, по одному на строку, с группами `# ── <tag> AS<asn> (N IP) ──`
- `subnets.txt` — `/24` с плотностью ≥ порога (`# cidr    # count/total = percent%`)
- `twl-harvest-report.md` — статистика, источник, commit SHA, топ-20 ASN
- `meta.json` — структурированный мета (для CI: можно сравнивать `commit_sha`,
  детектить новые ASN, автоматизировать PR)
- `repo/` — клон twl (если `--keep-repo`)

## Использование

### Базовый прогон

```bash
# из корня репо
python3 scripts/harvest/harvest_twl.py
```

Создаст `scripts/harvest/twl-data/` со всеми артефактами. Займёт ~30-60 сек (git clone).

### Только интересные провайдеры

```bash
# только Yandex Cloud + Selectel + Timeweb, /24 плотность ≥ 70%
python3 scripts/harvest/harvest_twl.py \
    --providers yandex --providers selectel --providers timeweb \
    --min-subnet-density 0.7
```

Поддерживается несколько `--providers` (substring match по полю `name` в twl).

### По конкретным ASN

```bash
# 200350 = Yandex Cloud, 49505 = Selectel, 41535 = Beget
python3 scripts/harvest/harvest_twl.py --asns 200350 --asns 49505 --asns 41535
```

### CI-режим (машинный JSON-вывод)

```bash
python3 scripts/harvest/harvest_twl.py --json > twl-meta.json
```

`meta.json` содержит:
- `commit_sha` — для детекта обновлений upstream
- `asn_count`, `ip_count`, `subnet_count` — числа для алертов
- `top_asn` — список топ-ASN (для графиков)
- `filters` — какие фильтры применились (для воспроизводимости)

### Повторный прогон из локального клона

```bash
# первый раз: с --keep-repo
python3 scripts/harvest/harvest_twl.py --keep-repo

# последующие разы: быстро (git pull + парсинг)
python3 scripts/harvest/harvest_twl.py --repo-dir scripts/harvest/twl-data/repo
```

### Без git (если git недоступен)

```bash
python3 scripts/harvest/harvest_twl.py --no-git
```

Fallback: качает три файла напрямую через `https://raw.githubusercontent.com/`.
`commit_sha` может быть недоступен (если GitHub API тоже недоступен).

## Использование выходов

### `ips.txt` → выбор VPS-провайдера

```bash
# какие подсети — у Yandex Cloud?
grep -E '^# ── Yandex Cloud' scripts/harvest/twl-data/ips.txt -A 1000 \
  | tail -n +2 | awk -F. '{print $1"."$2"."$3".0/24"}' | sort -u | head
```

Если ты арендуешь VPS у Beget / Selectel / Timeweb / VK / Yandex — его IP
**с высокой вероятностью** в этом списке. Прогони `--probe` из
`scripts/recon/fresta_recon.py` против своего IP для подтверждения.

### `subnets.txt` → оценка «свой /24»

```bash
# мой провайдер — Selectel, я знаю что мой IP в 95.213.45.0/24?
grep "95.213.45.0/24" scripts/harvest/twl-data/subnets.txt
# 95.213.45.0/24    # 213/256 = 83.2%
# → 83% IP в подсети whitelisted → почти все IP этого /24 пройдут
```

### `meta.json` → автоматизация

```python
import json
meta = json.load(open("scripts/harvest/twl-data/meta.json"))
if meta["commit_sha"] != last_known_sha:
    print(f"twl обновился: новых ASN={meta['asn_count']}, IP={meta['ip_count']}")
    # → PR / Slack-уведомление / auto-merge в whitelist
```

## Что НЕ делает

- **Не заменяет** `scripts/recon/whitelist.txt` (Минцифры, домены) — это разные наборы.
- **Не заменяет** `scripts/harvest/sni_candidates.txt` (SNI из zieng2/wl) — twl не даёт SNI.
- **Не проксирует** ничего — это чистый harvest + форматирование.
- **Не проверяет** реальную проходимость IP через твоего оператора —
  для этого есть `fresta_recon.py --probe` (Phase 0). twl даёт **теоретическую**
  базу, а probe подтверждает практику.

## Ограничения и caveats

- twl обновляется **эпизодически** (нет расписания). `meta.commit_sha` —
  единственный надёжный индикатор свежести.
- `ips.txt` большой (44k+ строк на июнь 2026) — НЕ в репо (`.gitignore`).
  `twl-harvest-report.md` и `meta.json` — в репо (история harvest'ов).
- Под провайдерским белым списком **L3+L7** — twl даёт IP для L3, но не
  гарантирует, что SNI к этому IP пройдёт L7 (SNI нужен свой).
- Формат `subnets.c.json` (twl) — `{cidr, count, total, percent, ips}`,
  `percent` хранится в 0..100 (НЕ в 0..1). Скрипт сам нормализует при фильтрации.
- ASN-список в twl может содержать провайдеров, которые **уже не whitelisted**
  (или появились новые). Периодически сверяй с `wly.zarazaex.xyz/check?ip=…`.

## Связанные скрипты и доки

- `scripts/harvest/harvest_subscription.py` — выжимка **SNI** из zieng2/wl (другая подписка)
- `scripts/recon/fresta_recon.py` — Phase 0 recon (GO/NO-GO через проверку IP)
- `docs/knowledge.md` §1 — как устроены белые списки (L3+L7)
- `docs/specification.md` — углублённая модель угроз
- `README.md` — общая структура репо
