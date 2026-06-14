# fresta · twl-harvest отчёт

- **источник**: [https://github.com/openlibrecommunity/twl.git](https://github.com/openlibrecommunity/twl.git) (branch `main`)
- **commit**: `984ff2dd26ade907240011a7150e56516f55dfee`
- **дата harvest'а**: 2026-06-14T15:22:24+00:00
- **фильтры**: providers=—, asns=—, min_count=1, min_subnet_density=0.5
- **файлов в twl**: OK sorted, OK subnets, OK verified

## IP по ASN (топ-20)

Всего IP: **43811** в 498 ASN.

| # | Провайдер | ASN | IP |
|---|-----------|----:|---:|
| 1 | Yandex.Cloud LLC | 200350 | 8224 |
| 2 | OOO "Sovremennye setevye tekhnologii" | 34879 | 3315 |
| 3 | CDNvideo LLC | 57363 | 3021 |
| 4 | LLC VK | 47764 | 2617 |
| 5 | YANDEX LLC | 13238 | 2230 |
| 6 | GLOBAL CLOUD NETWORK LLC | 204720 | 2029 |
| 7 | LLC VK | 47541 | 1964 |
| 8 | PJSC Rostelecom | 12389 | 1643 |
| 9 | DDOS-GUARD LTD | 57724 | 1321 |
| 10 | EuroByte LLC | 210079 | 1097 |
| 11 | SERVICEPIPE LLC | 201706 | 1020 |
| 12 | "Domain names registrar REG.RU", Ltd | 197695 | 895 |
| 13 | PJSC "Vimpelcom" | 3216 | 841 |
| 14 | HLL LLC | 51115 | 783 |
| 15 | Regional State Institution "Regional Center of automated information resource o | 48316 | 520 |
| 16 | LLC IVI.RU | 57629 | 511 |
| 17 | JSC Selectel | 49505 | 511 |
| 18 | JSC "TIMEWEB" | 9123 | 484 |
| 19 | LLC VK | 28709 | 451 |
| 20 | VKontakte Ltd | 47542 | 366 |

## /24 подсети

С плотностью ≥ 50%: **41** подсетей (см. `subnets.txt`).

## Использование

- `ips.txt` — IP-литералы для `fresta_recon.py --probe` (проверить, что наш
  провайдер реально их пропускает) или для выбора VPS-провайдера под Метод 1.
- `subnets.txt` — /24-подсети с высокой плотностью whitelisted-IP, удобно для
  оценки «всем ли IP в этой подсети повезло».
- `meta.json` — структурированный мета (CI может сравнивать commit SHA,
  детектить новые ASN и т.п.).

## Что НЕ делает

- **Не заменяет** `whitelist.txt` (Минцифры, домены) — это разные наборы.
- **Не заменяет** `sni_candidates.txt` (SNI из zieng2/wl) — twl не даёт SNI.
- **Не проксирует** ничего — это чистый harvest + форматирование.
