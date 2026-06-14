# fresta · harvest-снимок подписки

Источник: `https://raw.githubusercontent.com/zieng2/wl/main/vless_lite.txt`
Снимок точечный (подписка обновляется почасово — перезапусти для свежего).

Серверов: **160** | хосты: 160 IP-литералов, 0 доменных
security: {'tls': 8, 'reality': 152} · type: {'tcp': 114, 'grpc': 33, 'xhttp': 10, 'ws': 3} · fp: {'chrome': 21, 'qq': 58, '-': 2, 'firefox': 56, 'safari': 8, 'random': 15}

## Провайдеры (живые узлы)

| Провайдер | Узлов |
|-----------|------:|
| The Netherlands | 46 |
| Sweden | 43 |
| Germany | 38 |
| Beget | 8 |
| Estonia | 6 |
| Selectel | 4 |
| Timeweb | 4 |
| Finland | 3 |
| Italy | 2 |
| VK | 1 |
| cloud.ru | 1 |
| United Kingdom | 1 |
| Latvia | 1 |
| Poland | 1 |
| United States | 1 |

## Whitelisted-SNI — сильные (крупные сервисы, бери эти)

| SNI | Частота |
|-----|--------:|
| `ads.x5.ru` | 59 |
| `api-maps.yandex.ru` | 13 |
| `5post-gate.x5.ru` | 12 |
| `cdp.x5.ru` | 8 |
| `smartcaptcha.yandexcloud.net` | 7 |
| `max.ru` | 6 |
| `m.vk.com` | 5 |
| `iv.kommersant.ru` | 4 |
| `rutube.ru` | 4 |
| `api.yandex.ru` | 4 |
| `eh.vk.com` | 2 |
| `www.vk.com` | 2 |
| `yandex.ru` | 2 |
| `st.ozone.ru` | 2 |
| `kinopoisk.ru` | 2 |
| `gp.x5.ru` | 1 |
| `img.perekrestok.ru` | 1 |
| `adaptation.sfera.x5.ru` | 1 |
| `passport.yandex.ru` | 1 |

## SNI — осторожные (домены самих операторов узлов)

| SNI | Частота |
|-----|--------:|
| `rruu.persik.host` | 5 |
| `loadtest.dev.urent.ru` | 5 |
| `ya.ru` | 2 |
| `windows64.net` | 1 |
| `serv-ru-2.whit3.net` | 1 |
| `endeavouros.ubuntuhosting.host` | 1 |
| `zib.sempai.site` | 1 |
| `s95692.cdn.ngenix.net` | 1 |
| `id.pervye.ru` | 1 |
| `s46724.cdn.ngenix.net` | 1 |

> Сильные SNI — кандидаты для нашего Reality-конфига (whitelisted у всех операторов). Осторожные могут быть whitelisted не везде — проверяй probe'ом.
