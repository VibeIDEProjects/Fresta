# fresta · публикация на PyPI

Гайд для maintainer'а. **Один раз настроить → дальше релиз одной командой `git tag vX.Y.Z && git push --tags`.**

## TL;DR

```bash
# 1. Подготовка (один раз)
pip install -e .[dev]                          # dev-стек: ruff/mypy/pytest/build/twine
python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])"
# ↑ проверяем, что имя `fresta` свободно на PyPI: https://pypi.org/project/fresta/

# 2. Pre-release чек
make test                                      # все smoke-тесты 5/5
ruff check .                                   # линтер
python -m build                                # собрать sdist + wheel в dist/
twine check dist/*                             # проверить метаданные

# 3. Тестовая публикация (TestPyPI, опционально)
twine upload --repository testpypi dist/*       # или через trusted publishing

# 4. Production-релиз
git tag v0.2.0                                 # bump версии в pyproject.toml ДО тега
git push --tags                                # GitHub Actions workflow сделает всё сам

# Или вручную:
twine upload dist/*                            # залить на PyPI напрямую
```

## Что в репо уже сделано для публикации

- `pyproject.toml` — PEP 621 + SPDX-лицензия (PEP 639) + entry points (`[project.scripts]`)
  + `package-data` для `schemas/*.json` + dev-зависимости для build/twine
- `fresta/__init__.py` — `__version__ = "0.2.0"`, после `pip install fresta` доступно
  как Python-пакет
- `LICENSE` (MIT) — включится в wheel через `license-files`
- `.github/workflows/publish.yml` — авто-публикация по тегу `v*.*.*` через trusted publishing
- `MANIFEST.in` НЕ нужен — setuptools ≥ 68 + `[tool.setuptools.package-data]` всё включает
- `CHANGELOG.md` (Keep a Changelog) — release notes для PyPI

## Что нужно настроить ОДИН РАЗ (manual)

### 1. Аккаунт на PyPI + Trusted Publishing

Рекомендуемый путь — **OIDC trusted publishing** (без API-токенов):

1. Зарегистрироваться на https://pypi.org/account/register/
2. Подтвердить email
3. Создать проект `fresta` через https://pypi.org/manage/projects/ (или trusted publishing
   сам его создаст при первом push'е)
4. Настроить trusted publishing:
   - https://pypi.org/manage/account/publishing/ → "Add a new pending publisher"
   - **Owner:** `<owner>` (твой GitHub username/org)
   - **Repository:** `fresta`
   - **Workflow filename:** `publish.yml`
   - **Environment name:** `release` (создать в GitHub: Settings → Environments → New → `release`)
5. (Опционально) Повторить для https://test.pypi.org/manage/account/publishing/

**Fallback: API-токен.** Если не хочешь OIDC:
- https://pypi.org/manage/account/token/ → "Add API token" → scope: project:fresta
- GitHub: Settings → Secrets → New repository secret: `PYPI_API_TOKEN` = `pypi-...`
- Раскомментировать блок `password: ${{ secrets.PYPI_API_TOKEN }}` в `publish.yml`

### 2. Environment `release` в GitHub

Settings → Environments → New environment → name: `release`.

Опционально: required reviewers (1–2 maintainer'а должны одобрить перед публикацией).

### 3. Проверить, что имя `fresta` свободно

```bash
curl -sI https://pypi.org/project/fresta/ | head -1
# Если 200 OK — имя занято. Тогда:
#   - вариант A: добавить суффикс (`fresta-vpn`, `fresta-relay`)
#   - вариант B: связаться с тем, кто занял, попросить передать
#   - вариант C: использовать собственную организации (fresta-org/fresta)
# Если 404 — имя свободно.
```

## Release workflow (от начала до конца)

### Подготовка

1. **Закройте milestone / issues** — посмотрите `git log v0.1.0..HEAD --oneline`,
   выделите breaking changes, новые фичи, фиксы.
2. **Обновите `CHANGELOG.md`** — переименуйте `## [Unreleased]` в `## [X.Y.Z] - YYYY-MM-DD`,
   добавьте ссылку сравнения `[X.Y.Z]: https://github.com/<owner>/fresta/compare/vA.B.C...vX.Y.Z`.
3. **Бампните версию в двух местах:**
   - `pyproject.toml:3` — `version = "X.Y.Z"`
   - `fresta/__init__.py:21` — `__version__ = "X.Y.Z"`
4. **Закоммитьте:** `git commit -am "release: vX.Y.Z"`
5. **Прогоните тесты:** `make test && ruff check .`

### Публикация

```bash
git tag -s vX.Y.Z -m "vX.Y.Z"             # подписанный тег (-s требует GPG-ключ)
git push origin main --tags                 # push ветки + тегов
# → GitHub Actions workflow .github/workflows/publish.yml запустится:
#   1. build sdist + wheel
#   2. twine check (метаданные)
#   3. upload to PyPI (через OIDC trusted publishing)
# → через ~2 минуты: https://pypi.org/project/fresta/vX.Y.Z/
```

### Post-release

1. **Проверьте страницу:** `pip install --upgrade fresta && python -c "import fresta; print(fresta.__version__)"`
2. **GitHub Release:** https://github.com/<owner>/fresta/releases/new → tag = vX.Y.Z →
   description = copy-paste из `CHANGELOG.md` → publish
3. **Bump до dev-версии** (опц.): `version = "X.Y.Z+dev"` в `pyproject.toml`,
   чтобы было видно, что master сейчас ahead of release.

## Версионирование — SemVer

`MAJOR.MINOR.PATCH`:
- **MAJOR** (1.0.0) — breaking changes (например, переписали API генератора,
  изменили формат конфигов)
- **MINOR** (0.2.0) — новая фича с обратной совместимостью
- **PATCH** (0.2.1) — баг-фикс без breaking changes

До `1.0.0` — это «быстро итерируем», breaking changes разрешены в MINOR.
После `1.0.0` — strict SemVer.

Текущая: **0.2.0** (стадия Beta по classifier'у). До 1.0 скорее всего будет ещё пара MINOR.

## Частые проблемы

| Проблема | Решение |
|---|---|
| `twine upload: 403 Forbidden` | Имя занято. Проверить `https://pypi.org/project/fresta/`. Варианты: добавить суффикс, OIDC настроен не на тот `owner`/`repo`. |
| `Package name 'fresta' already exists` | То же — имя занято. См. выше. |
| `error: invalid command 'bdist_wheel'` | Забыл `pip install -e .[dev]` (там `build`, `twine`). |
| `error: Microsoft Visual C++ 14.0 or greater is required` | Кто-то воткнул C-расширение в `dependencies`. У нас всё stdlib — этой ошибки быть не должно. |
| `Workflow runs but does nothing on tag push` | Проверь формат тега: должен быть `vX.Y.Z` (с `v` префиксом). Тег `0.2.0` без `v` не сматчит. |
| `Environment 'release' not found` | Settings → Environments → создать `release`. |
| `OIDC: no matching pending publisher` | На PyPI: https://pypi.org/manage/account/publishing/ — добавить pending publisher с правильным `Owner`/`Repository`/`Workflow filename`/`Environment`. |

## Ручной аплоад (если не хочешь GitHub Actions)

```bash
# один раз: получить API-токен на https://pypi.org/manage/account/token/
# и сохранить в ~/.pypirc:
cat > ~/.pypirc <<EOF
[pypi]
username = __token__
password = pypi-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
EOF

# собрать и залить
python -m build
twine check dist/*
twine upload dist/*
```

После ручного аплоада можно вручную создать GitHub Release через UI.

## См. также

- `CHANGELOG.md` — история версий
- `CONTRIBUTING.md` — как контрибьютить
- `pyproject.toml` — все метаданные в одном месте
- `fresta/__init__.py` — `__version__` (single source of truth внутри кода)
- https://packaging.python.org/tutorials/packaging-projects/ — официальный гайд PyPA
- https://docs.pypi.org/trusted-publishers/ — про Trusted Publishing
