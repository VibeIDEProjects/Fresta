# fresta · knowledge (контекст-хэндофф)

> Этот файл — полный слепок контекста проекта. Если ты свежий инстанс Claude и
> тебе скормили этот репозиторий — прочитай этот файл первым, и ты поймёшь ВСЁ:
> зачем проект, как устроена задача, что уже сделано, где что брали, какие выводы,
> что дальше. Остальные доки — детализация.

---

## 0. TL;DR

**fresta** — инструмент доступа к открытому интернету под российскими операторскими
**белыми списками** (мобильные сети). Идея в названии (порт. «щель, через которую
пробивается свет»): найти «щель» — инфраструктуру, чьи IP оператор обязан пропускать,
и пустить через неё свой трафик.

Ключевой вывод всего проекта: под белым списком блокировка идёт **по адресу
назначения (IP), до анализа протокола**. Поэтому маскировка (Reality, обфускация)
сама по себе бесполезна — нужен транспорт, физически идущий **на whitelisted-IP**.
В РФ это прежде всего **Yandex Cloud**, а также Beget / Selectel / Timeweb / VK.

Проект — не новое крипто и не новый протокол. Это **recon (найти щель) + оркестрация
+ своя чистая сборка уже известных рабочих методов**. Пространство активно копают
другие (openlibrecommunity, zieng2) — мы строим своё и разбираемся, как всё устроено.

---

## 1. Как устроены белые списки (против чего мы)

Двухуровневая фильтрация на ТСПУ оператора, по умолчанию **drop-all**:

- **L3 (сетевой)** — CIDR-фильтр по IP. Пакет не к разрешённой подсети дропается на
  роутере (≈2-й хоп) ещё до DPI. Для не-whitelist IP не работает НИЧЕГО: ни ICMP, ни
  TCP, ни UDP — 100% packet loss.
- **L7 (приложения)** — DPI читает SNI в TLS ClientHello. Даже если IP разрешён, но
  SNI в чёрном списке → RST. Чёрный список SNI маленький и **неконсистентный** между
  подсетями/операторами (через Яндекс один SNI проходит, через VK тот же режется).

Следствия (эмпирика из статьи zarazaex):

- **UDP практически мёртв**: QUIC (:443), внешний DNS (:53), WireGuard (:51820) —
  NO_RESP. Живут только **TCP 80/443/22**. → транспорт обязан быть TCP/443, WG не вариант.
- **Внешний DNS закрыт** — работает только DNS самого оператора. → в конфигах
  использовать **IP-литералы, а не домены** (иначе резолв падает).
- Белый список ≈ **63 000 IP** (~0.14% рунета). Доминирует **Yandex.Cloud (~каждый
  пятый IP)**, далее VK, Selectel, Timeweb, Ростелеком, Beget, REG.RU.
- Работает **неравномерно**: по регионам, районам, вышкам, операторам. У каждого
  оператора свой список. `max.ru` — всегда и везде; `vk.com`/`ya.ru` — почти всегда;
  банки/маркетплейсы — лотерея.
- Белый список — **слой поверх обычного ТСПУ**, а не замена: TLS-фингерпринт-детект
  VPN никуда не делся. → нужен `fp=chrome`/`firefox` (uTLS) даже после прохождения L3.

---

## 2. Концепция fresta

Единственный пакет, проходящий L3, — адресованный whitelisted-IP. Значит транспорт
должен физически идти на такой IP. «Разрешённый IP, через который можно гнать
произвольный трафик» = инфраструктура крупного провайдера, чьи IP в списке и на
которой **мы можем развернуть свой код/сервер**. В РФ:

- **Yandex Cloud** — главный кандидат. `*.yandexcloud.net`, `functions.yandexcloud.net`
  whitelisted у всех операторов; IP облака нельзя выкинуть (на нём пол-госуслуг).
- **Beget / Selectel / Timeweb / VK / cloud.ru** — РФ-VPS-провайдеры, чьи подсети
  попадают в список → можно арендовать VPS с whitelisted-IP под VLESS+Reality.

Архитектура (распределённая, всегда минимум два узла):

```
[клиент: устройство/роутер]  --TLS,SNI=whitelisted-домен-->  [whitelisted-вход]  -->  [exit]  --> открытый интернет
   твоё, sing-box/Xray                                        Yandex Cloud / РФ-VPS      твой VPS
```

---

## 3. Хронология решений и пивотов (как мы сюда пришли)

1. **Старт:** разбирали WireGuard (нативен в Keenetic, но НЕ маскируется → режется
   на раз) vs VLESS+Reality (маскируется под легит-TLS → живуч). Вывод: под
   блокировками нужен VLESS+Reality, не WG.
2. **DPN-роутер (Deeper Connect) ≠ VLESS.** DPN — децентрализованная P2P-сеть, трафик
   через случайные чужие узлы. Против белых списков **бесполезен** (чужие IP не в
   списке) + юридический риск (чужой трафик через твой IP).
3. **Понимание задачи:** против белого списка не помогает «более хитрый протокол» —
   блокировка по IP до протокола. Родилась идея «захватить разрешённый сервис как
   транспорт» → ресёрч domain fronting.
4. **Domain fronting research:** классический фронтинг прикрыли AWS/Google; выживает
   на AWS Lambda (работа CensorLess), части CDN, serverless. Исторически — meek
   (Tor), Psiphon, Lantern. Изначально fresta замышлялась на **западных CDN**.
5. **Нейминг:** перебрали слова «щель/брешь/лазейка» на куче языков. Выбрали
   **fresta** (порт., свет сквозь щель) — тёплый фрейм «доступ/свобода»,
   беспроблемно произносится/пишется. Раннер-ап — **faille** (фр., «уязвимость в
   защите», хакерский фрейм). Домен fresta.ru.
6. **ГЛАВНЫЙ ПИВОТ (статья zarazaex на Хабре):** белый список — это L3+L7, и он почти
   целиком из РФ-инфры. Западных CDN в нём практически нет. → «щель» в РФ это не
   Cloudflare, а **Yandex Cloud** (Метод 2/3 из статьи). Переписали recon под РФ-
   провайдеров (Yandex Cloud во главе).
7. **Метод 2 собран и протестирован:** serverless fetch-relay на Yandex Cloud Functions.
8. **Подписка zieng2/wl:** живой почасовой VLESS-фид. Сделали harvest → реальный
   набор whitelisted-SNI + подтверждение РФ-провайдеров. Усвоили уроки (IP-литералы,
   latency-test, fp-разнообразие).

---

## 4. Источники и что из них взяли

| Источник | Что это | Что взяли |
|----------|---------|-----------|
| Минцифры / kod.ru | Официальный перечень белого списка (по названиям сервисов) | `whitelist.txt` — 143 домена (реконструкция «сервис → домен») |
| Хабр, zarazaex, `habr.com/ru/articles/1027276` | Технический разбор + скан белых списков | Модель L3+L7, UDP/DNS мёртвы, состав списка (Yandex Cloud доминирует), 6 методов обхода, пивот концепции |
| `github.com/openlibrecommunity/twl` | Эмпирический скан whitelisted-IP + ~1176 SNI по операторам | Источник реальных IP/SNI под своего оператора (ещё не подключён — в roadmap) |
| `github.com/zieng2/wl` | Почасовая VLESS-подписка для обхода | `sni_candidates.txt` (19 SNI) + `scripts/harvest/reports/harvest-report.md`; подтверждение РФ-провайдеров; инженерные уроки |

---

## 5. Методы обхода (от рабочего к экспериментальному)

1. **VLESS + Reality на РФ-VPS** — основной, стабильный. VPS на whitelisted-провайдере
   (Beget/Selectel/Timeweb/Yandex) + whitelisted-SNI + `fp=chrome` + IP-литерал. ~2000₽/мес.
2. **Yandex Cloud Functions** (наш Метод 2, собран) — serverless fetch-relay, бесплатно
   (free tier ~1M вызовов/мес). НЕ туннель (stateless): только HTTP-семантика.
3. **API Gateway + WebSocket → VPS exit** (Метод 3) — настоящий туннель (дуплекс).
   **ВНИМАНИЕ: этот вектор уже начали банить** после публикации статьи.
4. **olcRTC** — туннель через whitelisted-видеозвонки (Telemost/Jazz/wbstream), WebRTC. Экспериментально.
5. **xDNS** — туннель через DNS. Только где UDP:53 открыт (часто нет). Медленно.
6. **TURN relay** (VK/Яндекс) — быстро банят/шейпят.

Не работают: QUIC/HTTP3, ECH/ESNI (бесполезен — блок по IP, а не SNI), обычный
зарубежный VPN (IP не в списке).

---

## 6. Что построено и как протестировано

- `fresta_recon.py` (Фаза 0) — резолвит whitelist-домены → ASN/CDN (Cloudflare по
  оффлайн-диапазонам, остальное через bulk-whois Team Cymru) → вердикт GO/NO-GO.
  Цель = РФ-провайдеры, Yandex Cloud первым. **Оффлайн-логика протестирована мной**
  (range-match, classify, verdict, парсинг Cymru). Probe = TLS-handshake (не ping).
  Под реальной мобильной сетью ещё не гонялся.
- `whitelist.txt` — 143 домена белого списка (реконструкция, проверить/подчистить).
- `yc_function/handler.py` + `fresta_client.py` (Метод 2) — fetch-relay + клиент
  (CLI + HTTP-proxy). **Плумбинг протестирован end-to-end на моке платформы**:
  реальный fetch (200), токен-гейт (403), SSRF-защита (loopback заблокирован).
  На самой Yandex Cloud ещё не задеплоено.
- `harvest_subscription.py` → `sni_candidates.txt` + `scripts/harvest/reports/harvest-report.md` — выжимка из
  живой подписки. Прогнан на zieng2/wl.
- `harvest_twl.py` → `scripts/harvest/twl-data/` (`ips.txt`, `subnets.txt`, `twl-harvest-report.md`,
  `meta.json`) — **живой harvest** из openlibrecommunity/twl. 498 ASN, ≈44k IP,
  41 /24 с плотностью ≥ 50% (топ-1: Yandex Cloud AS200350 = 8224 IP). Гайд:
  `docs/manuals/recon/twl-harvest.md`.
- `fresta_gen_vless.py` (Фаза 2) — генератор server.json (Xray) / client.json (sing-box) /
  vless://-ссылок под whitelisted-SNI. X25519-ключи через `openssl` subprocess
  (фолбэк — плейсхолдеры + `gen-keys.sh`). **Протестирован мной** на сборке с парой
  SNI: server.json валидный, links.txt содержит 19 vless://-ссылок (по одной на SNI).
  На VPS ещё не деплоился.
- `scripts/tests/test_*.py` (60+ кейсов) + `run_tests.sh` / `run_tests.ps1` — smoke-тесты (рядом, в `scripts/tests/`)
  всех 4 скриптов. Прогоняются локально (test_handler дополнительно делает реальный
  fetch к `https://example.com/`). **Все зелёные.** Поймали и починили 3 бага:
  1) `fresta_recon.cymru_bulk` перезаписывал последний ASN — IP Яндекса (origin 13238 +
     announcing 208398/TELETECH) ложно классифицировались как TELETECH → **NO-GO** для
     всей Фазы 0. Фикс: `info[ip] = list[(asn, asname)]`, `classify` итерирует по
     `CDN_SIGNATURES` (приоритет yes > hard > no).
  2) `yc_function/handler.handler` падал с `AttributeError` на «валидный JSON, но не
     объект» (строка/массив). Фикс: `isinstance(req, dict)` после `json.loads`.
  3) `harvest_subscription.is_strong` давал ложные срабатывания на подстроках
     (`"rutube" in "rutube123.evil.ru"` → True). Фикс: регексп по `\b.` границам
     доменного лейбла.
- `scripts/deploy/check_health.py` (новое) — health-check деплоя vless-vps: SOCKS5 alive?
  exit-IP совпадает? 5 синтетических проб (ipify / github / example / cloudflare /
  httpbin), latency median+p95, вердикт OK/PARTIAL.
- `scripts/deploy/bench.py` (новое) — мини-бенчмарк (latency × 10 + 1 МБ throughput через
  Cloudflare speed-test). Прямой режим без зависимостей, через-SOCKS режим — подсказка
  на check_health для полноценного бенча.
- `scripts/deploy/rotate_keys.sh` (новое) — ротация UUID + X25519 + shortId на сервере
  **без переустановки Xray** (бэкап → python-patch → `xray run -test` → `systemctl restart`).
- **DevEx / CI** (новое): `pyproject.toml` (PEP 621 + ruff + mypy + pytest),
  `.editorconfig`, `LICENSE` (MIT), `CHANGELOG.md` (Keep a Changelog), `CONTRIBUTING.md`,
  `.github/workflows/tests.yml` (тесты на ubuntu × py3.8–3.12 + windows-latest + ruff),
  `.github/dependabot.yml` (auto-PR для dev-зависимостей и GitHub Actions),
  `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.yml`, `Makefile` (12 целей).
  Рантайм остаётся stdlib-only; dev-стек поднимается одной командой `pip install -e .[dev]`.

- **PoC Метода 1 (VLESS+Reality) на fresta.ru:8443 (2026-06-14)**: end-to-end пройден.
  Xray v26.3.27 + sing-box 1.13.13; `curl --proxy socks5h` через туннель дал
  `https://api.github.com/zen` = 200 OK, exit-IP сменился с моего на `89.253.255.108`
  (наш сервер). Подробности и артефакты — в `docs/ROADMAP.md` (Фаза 2 / Метод 1) и
  `scripts/deploy/configs/remote-fresta/`. **Это НЕ под белым списком оператора** (IP
  `89.253.255.108` — не в whitelisted-подсети), но доказывает, что **связка
  рабочая**. С реальным VPS на Timeweb/Selectel/Beget будет работать так же — там
  только IP поменять.

«Протестировано мной» = в песочнице, чистая логика/плумбинг. «Под 📱/☁️» = ещё
предстоит вживую (см. ROADMAP.md).

---

## 7. Конкретные данные (готовы к переиспользованию)

**Whitelisted-SNI для Reality** (harvest, частота в скобках) — домены крупных сервисов,
проходят ТСПУ: `ads.x5.ru` (59, лидер), `api-maps.yandex.ru`, `5post-gate.x5.ru`,
`cdp.x5.ru`, `smartcaptcha.yandexcloud.net`, `max.ru`, `m.vk.com`, `iv.kommersant.ru`,
`rutube.ru`, `api.yandex.ru`, `yandex.ru`, `st.ozone.ru`, `kinopoisk.ru`,
`img.perekrestok.ru`, `passport.yandex.ru`. Полный список — `scripts/harvest/sni_candidates.txt`.
Домены X5 Group доминируют. (Срез точечный, подписка обновляется почасово.)

**Whitelisted-IP по ASN** (twl-harvest, июнь 2026) — ТОП-5 провайдеров с наибольшим
числом IP в `twl-data/ips.txt`:
1. **Yandex.Cloud LLC** (AS200350) — 8224 IP
2. **OOO "Sovremennye setevye tekhnologii"** (AS34879) — 3315 IP
3. **CDNvideo LLC** (AS57363) — 3021 IP
4. **LLC VK** (AS47764) — 2617 IP
5. **YANDEX LLC** (AS13238) — 2230 IP
Полный список — `scripts/harvest/twl-data/twl-harvest-report.md`. ASN-лидер = Yandex Cloud,
что подтверждает основную гипотезу проекта (Метод 2 на YC — рабочая щель).

**/24-подсети с плотностью ≥ 50%** (`twl-data/subnets.txt`) — 41 подсеть, лидер
`95.213.45.0/24` (213/256 = 83.2%). Это кандидаты для оценки «всем ли IP в этой
подсети повезло» (если у нашего VPS IP в таком /24, оператор с высокой вероятностью
его пропустит).

**РФ-провайдеры с whitelisted-IP** (для своего VPS): Beget, Selectel, Timeweb, VK,
cloud.ru, Yandex Cloud. Совпадают с `CDN_SIGNATURES` в recon И с топ-ASN из twl.

**Транспорт у живых узлов:** в основном Reality (152/160), типы tcp/grpc/xhttp/ws,
fp разнообразный (firefox, qq, chrome, safari, random — анти-детект).

---

## 8. Инженерные уроки (важно держать в голове)

- **IP-литералы, не домены** в конфигах: внешний DNS под белым списком закрыт.
- **Проверять latency/URL-test (реальный TLS-коннект), не TCP/ICMP-пинг**: ICMP может
  быть выключен, TCP-пинг не отражает доступность под ограничениями.
- **`fp=chrome`/`firefox` (uTLS) обязателен**: обычный ТСПУ палит VPN по фингерпринту
  поверх белого списка. Reality сама по себе не спасает при палевном fp.
- **«Разрешить небезопасные»** (ослабленная валидация TLS) расширяет список рабочих серверов.
- **Серверы быстро умирают** (арм-рейс) → автообновление/ротация.
- **Метод 2 (fetch-relay) терминирует TLS до цели сам** → видит трафик в открытом
  виде. Это твоя функция, но факт; для прозрачного e2e нужен туннель (WS/VPS).
- **Cymru bulk отдаёт несколько ASN на один IP** (origin + announcing после перепродажи
  блока). Реальный кейс: IP Яндекса в 2024+ отдают пару (13238/YANDEX, 208398/TELETECH).
  Нельзя брать последнюю запись — теряешь origin. Бери **список** и итерируй приоритеты
  сигнатур.
- **«Валидный JSON» ≠ «JSON-объект»**: после `json.loads` всегда проверяй `isinstance(d, dict)`
  перед `d.get(...)`. Иначе строка `"foo"` в body крашит хендлер `AttributeError`.
- **Подстрочный поиск в доменах — источник ложных срабатываний**. `"yandex" in "yandexcloud.net"`
  True, `"rutube" in "rutube123.evil.ru"` True. Для матчинга по доменным лейблам — регексп
  с границами по `.`.

---

## 9. Структура репозитория

```
fresta/
├── README.md                       обзор проекта
├── LICENSE                         MIT
├── CHANGELOG.md                    Keep a Changelog
├── CONTRIBUTING.md                 гайд для контрибьюторов
├── pyproject.toml                  ruff + mypy + pytest + метаданные
├── Makefile                        make test / lint / harvest-all / deploy / …
├── .editorconfig                   единые правила оформления
├── .github/                        CI + шаблоны issues
│   ├── workflows/tests.yml         smoke-тесты × 5 OS × 5 Python
│   ├── dependabot.yml              авто-PR зависимостей
│   └── ISSUE_TEMPLATE/             bug_report.yml + feature_request.yml
├── scripts/                        код (см. scripts/README.md)
│   ├── README.md                   карта scripts/ (что в каждой подпапке)
│   ├── recon/                      Фаза 0: GO/NO-GO по whitelist-доменам
│   │   ├── fresta_recon.py
│   │   ├── whitelist.txt           домены белого списка (реконструкция)
│   │   └── whitelist.sample.txt    пример формата
│   ├── harvest/                    открытые источники (whitelist-IP, SNI)
│   │   ├── harvest_subscription.py выжимка SNI/провайдеров из VLESS-подписки
│   │   ├── harvest_twl.py          harvest whitelisted-IP из openlibrecommunity/twl
│   │   ├── sni_candidates.txt      whitelisted-SNI для Reality (harvest)
│   │   └── twl-data/               выход harvest'а: ips.txt / subnets.txt / report.md / meta.json
│   ├── deploy/                     Метод 1: VLESS+Reality
│   │   ├── fresta_gen_vless.py     генератор конфигов
│   │   ├── deploy_vps.sh           серверный деплой
│   │   ├── quickstart.sh           локальный одноступенчатый деплой
│   │   ├── check_health.py         health-check деплоя (SOCKS5 + exit-IP)
│   │   ├── bench.py                мини-бенчмарк (latency + throughput)
│   │   ├── rotate_keys.sh          ротация UUID/X25519/shortId на сервере
│   │   └── configs/                сгенерированные наборы (default/ + remote-fresta/)
│   ├── relay/                      Метод 2: Yandex Cloud relay
│   │   ├── yc_function/handler.py  функция relay
│   │   └── fresta_client.py        локальный клиент (CLI + HTTP-proxy)
│   └── tests/                      smoke-тесты (60+ кейсов) + probe_reality.py
│       ├── run_tests.sh            прогон на Linux/macOS/WSL/Git Bash
│       └── run_tests.ps1           прогон на Windows PowerShell
└── docs/
    ├── README.md                   карта docs/
    ├── specification.md            идея, threat model, архитектура, роадмап
    ├── ROADMAP.md                  чек-лист done/todo + где гонять
    ├── knowledge.md                ← этот файл
    └── manuals/                    пошаговые гайды (карта — manuals/README.md)
        ├── deploy-method1.md       Метод 1: quickstart + troubleshooting
        ├── reality-params.md       Reality-параметры + генератор
        ├── relay-method2.md        Метод 2: YC Functions relay + клиент
        └── twl-harvest.md          harvest whitelisted-IP (twl)

# Отчёты (данные, не доки)
#   scripts/harvest/reports/harvest-report.md      снимок подписки zieng2/wl
#   scripts/harvest/twl-data/twl-harvest-report.md снимок harvest_twl (≈44k IP)
```

## 10. Что дальше (next steps)

1. 📱 Под реальной мобильной сетью с белым списком: `python3 scripts/recon/fresta_recon.py
   scripts/recon/whitelist.txt --probe` (закрыть GO/NO-GO) и
   `python3 scripts/relay/fresta_client.py --check` (подтвердить, что
   `functions.yandexcloud.net` проходит у оператора).
2. ☁️ Задеплоить Метод 2 (ycloud-function) на Yandex Cloud (`docs/manuals/ycloud-function/deploy.md`).
3. **Фаза 2 — настоящий туннель:** генератор `fresta_gen_vless.py` готов, осталось
   задеплоить. План: VPS на Beget/Selectel/Timeweb (проверить плотность /24-подсети
   в whitelist по `scripts/harvest/reports/harvest-report.md` + `scripts/harvest/twl-data/subnets.txt`) → `python3 fresta_gen_vless.py --exit-ip <IP>
   --out configs/<имя>` → `server.json` на VPS в `/usr/local/etc/xray/config.json` →
   `client.json` или `links.txt` в sing-box/Shadowrocket → проверить под мобильным
   каналом. Подробности — `docs/manuals/vless-vps/reality-params.md`.
4. ✅ **Подключён `openlibrecommunity/twl`** — `scripts/harvest/harvest_twl.py` уже
   собирает реальные whitelisted-IP (498 ASN, ≈44k IP, 41 /24 с плотностью ≥ 50%).
   Топ-1: Yandex Cloud (8224 IP), топ-2: Sovremennye setevye tekhnologii (3315),
   топ-3: CDNvideo (3021), топ-4: VK (2617), топ-5: YANDEX LLC (2230).
   Использовать: `python3 scripts/harvest/harvest_twl.py --providers <имя>` для фильтра,
   `scripts/harvest/twl-data/ips.txt` для выбора VPS-провайдера,
   `scripts/harvest/twl-data/subnets.txt` для оценки плотности /24.
   Подробности — `docs/manuals/recon/twl-harvest.md`.
5. ⏭ **Фаза 3 — ротация фронтов:** несколько VPS × несколько SNI × автоперебор при
   отвале. Генератор к этому уже готов (вызов с разными `--out`).

## 11. Рамки и caveats

- Серая зона по регулированию; **нарушение ToS** провайдеров (абуз serverless,
  фронтинг CDN, проксирование) — функции/серверы сносят, идёт арм-рейс.
- **Чужие подписки/DPN** = доверие оператору выходного узла (он видит твой трафик);
  «разрешить небезопасные» ослабляет валидацию. Свой exit этого лишён.
- Это инструмент доступа к открытому интернету; оценка рисков и решение — на пользователе.

## 12. Инструментарий, который применялся

web_search / web_fetch (ресёрч и чтение статей/репо), Python stdlib (recon, relay,
harvest — без внешних зависимостей), Team Cymru bulk-whois (ASN), urllib, sing-box /
Xray (рекомендованные клиенты), `yc` CLI (деплой функции). Клиенты для подписок:
Shadowrocket, v2rayNG, NekoBox, Throne, Karing.
