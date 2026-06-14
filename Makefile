# fresta · Makefile
#
# Типовые команды для разработки и эксплуатации. На Windows: используйте
# Git Bash / WSL / scoop shim (`scoop install make`).
#
#   make help         — список целей
#   make test         — прогнать smoke-тесты
#   make lint         — ruff check + format --check
#   make fix          — авто-форматирование + авто-фикс ruff
#   make harvest-all  — пересобрать оба harvest'а (zieng2 + twl)
#   make deploy       — деплой vless-vps одной командой (нужен SSH-таргет)
#   make relay-check  — проверить канал ycloud-function
#   make probe        — TLS-probe к PoC-серверу fresta.ru:8443

SHELL := /usr/bin/env bash
PY    := python3
SSH   ?= user@your-vps.example.com

.DEFAULT_GOAL := help

.PHONY: help
help:  ## список целей
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test:  ## прогнать smoke-тесты (60+ кейсов)
	bash scripts/tests/run_tests.sh

.PHONY: test-pytest
test-pytest:  ## то же через pytest (если установлен: pip install -e .[dev])
	$(PY) -m pytest scripts/tests -q

.PHONY: lint
lint:  ## ruff check + format --check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

.PHONY: fix
fix:  ## авто-форматирование + авто-фикс ruff
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

.PHONY: sanity
sanity:  ## pre-flight check зависимостей (ssh, openssl, python, …)


.PHONY: validate
validate:  ## валидация server.json / client.json по schemas/*.schema.json
	@for f in scripts/deploy/configs/*/server.json scripts/deploy/configs/*/client.json; do \
	  [ -f "$$f" ] || continue; \

	done

.PHONY: diff


.PHONY: harvest-sni
harvest-sni:  ## harvest SNI из zieng2/wl → sni_candidates.txt
	$(PY) scripts/harvest/harvest_subscription.py \
	  --sni-out scripts/harvest/sni_candidates.txt \
	  --report-out scripts/harvest/reports/harvest-report.md

.PHONY: harvest-twl
harvest-twl:  ## harvest whitelisted-IP из openlibrecommunity/twl
	$(PY) scripts/harvest/harvest_twl.py

.PHONY: harvest-all
harvest-all: harvest-sni harvest-twl  ## оба harvest'а разом

.PHONY: recon
recon:  ## Phase 0 recon (без probe — оффлайн-логика)
	$(PY) scripts/recon/fresta_recon.py scripts/recon/whitelist.txt

.PHONY: probe
probe:  ## TLS-probe к PoC-серверу fresta.ru:8443 по SNI из harvest
	$(PY) scripts/tests/probe_reality.py

.PHONY: gen-config
gen-config:  ## сгенерировать VLESS+Reality конфиги (без деплоя)
	$(PY) scripts/deploy/fresta_gen_vless.py --out scripts/deploy/configs/local

.PHONY: deploy
deploy:  ## деплой vless-vps одной командой (SSH=…)
	bash scripts/deploy/quickstart.sh --ssh $(SSH)

.PHONY: deploy-gen
deploy-gen:  ## сгенерировать конфиги под указанный VPS (SSH=…)
	bash scripts/deploy/quickstart.sh --ssh $(SSH) --no-deploy

.PHONY: relay-check
relay-check:  ## проверить канал ycloud-function (нужны FRESTA_FUNC_URL/TOKEN)
	$(PY) scripts/relay/fresta_client.py --check

.PHONY: health
health:  ## health-check деплоя vless-vps (нужен client.json)
	$(PY) scripts/deploy/check_health.py

.PHONY: bench
bench:  ## бенчмарк туннеля (latency + throughput)
	$(PY) scripts/deploy/bench.py

.PHONY: rotate
rotate:  ## ротация UUID/X25519 на существующем сервере (SSH=…)
	bash scripts/deploy/rotate_keys.sh $(SSH)

.PHONY: clean
clean:  ## убрать __pycache__ и временные фикстуры
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf scripts/tests/_tmp scripts/tests/_harv_tmp scripts/tests/_harv_twl_tmp
	rm -f scripts/harvest/_harv*.txt
