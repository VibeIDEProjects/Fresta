# fresta · roadmap

Статус и «что где гонять». Конкретные команды — в `README.md` (быстрый старт) и
`docs/fresta_relay_README.md` (деплой + клиент). Здесь — только чек-лист.
Пути даны от корня репозитория.

**Три среды запуска:**

- 💻 **локально** (ноут / песочница) — оффлайн-логика и сборка.
- 📱 **мобильный канал под белым списком** (раздать с телефона на ноут) — всё, что
  должно подтвердить *реальную проходимость*.
- ☁️ **Yandex Cloud** — деплой функции.

---

## Фаза 0 — разведка (GO / NO-GO)

- [x] 💻 recon-скрипт, цель = РФ-провайдеры (Yandex Cloud во главе)
- [x] 💻 оффлайн-логика протестирована мной (CF-range / classify / verdict / парсинг Cymru)
- [x] 💻 `scripts/whitelist.txt` — 143 домена (реконструкция по сервисам Минцифры)
- [x] 💻 harvest SNI/провайдеров из живой подписки (zieng2/wl) → `scripts/sni_candidates.txt` + `docs/harvest-report.md`
- [ ] 📱 **погонять `python3 scripts/fresta_recon.py scripts/whitelist.txt --probe`** ← *твой ближайший шаг*
      Подтвердить: за доменами реально Yandex Cloud/Selectel и probe-handshake проходит сквозь whitelist.
- [ ] 💻 (опц.) заменить `scripts/whitelist.txt` реальными IP/SNI из репозитория openlibrecommunity/twl

## Метод 2 — serverless fetch-relay

- [x] 💻 `scripts/yc_function/handler.py` + `scripts/fresta_client.py` написаны
- [x] 💻 плумбинг протестирован мной end-to-end на моке (fetch 200 / токен-гейт / SSRF-блок)
- [ ] ☁️ **задеплоить функцию** (yc CLI — см. `docs/fresta_relay_README.md`)
- [ ] 📱 **`python3 scripts/fresta_client.py --check`** — подтвердить, что `functions.yandexcloud.net`
      проходит у твоего оператора и exit-IP = Яндекса
- [ ] 📱 прогнать реальный заблокированный ресурс через CLI

## Фаза 2 — настоящий туннель (не начато)

- [ ] выбрать вектор: WS через API Gateway → VPS exit **или** VLESS + Reality на РФ-VPS
- [ ] ☁️ поднять VPS на whitelisted-провайдере (Timeweb / Selectel / Yandex), проверить плотность /24
- [ ] 💻 конфиг VLESS+Reality: whitelisted-SNI (`storage.yandex.net`, `userapi.com`, `cdnvideo.ru`…) + `fp=chrome`
- [ ] 💻 клиент (sing-box) на устройство или роутер
- [ ] 📱 проверить проходимость и стабильность

---

### Легенда статусов

- [x] сделано
- [ ] предстоит
- ← помечен ближайший шаг

### Что уже можно делать прямо сейчас

1. 💻☁️ Развернуть Метод 2 на Yandex Cloud (если есть аккаунт).
2. 📱 Под мобильным каналом прогнать `fresta_recon.py --probe` и `fresta_client.py --check`.
   Это закрывает GO/NO-GO Фазы 0 и подтверждает рабочий канал Метода 2.
