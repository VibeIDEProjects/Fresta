#!/usr/bin/env bash
# fresta · прогон smoke-тестов (лежит рядом с тестами, в scripts/tests/)
# Использование: bash scripts/tests/run_tests.sh
# Или:           cd scripts/tests && bash run_tests.sh

set -euo pipefail

# Уже в scripts/tests/ — тесты лежат рядом, дополнительный cd не нужен.
cd "$(dirname "$0")"

# Диагностика окружения (полезно при фейле в CI).
echo "--- env ---"
python3 --version || echo "python3 not found"
which python3 || true
echo "PWD: $(pwd)"
echo "--- env end ---"
echo

# Cleanup any leftover fail logs from previous run.
rm -f _fail_*.log _last_run.log 2>/dev/null || true

fail=0
for t in test_*.py; do
    echo "=== $t ==="
    # -u = unbuffered: строки выводятся сразу, в логе CI видно место фейла.
    # Весь stdout+stderr теста идёт в _fail_<test>.log, чтобы при фейле
    # upload-artifact в tests.yml мог приложить его к GitHub Actions.
    logfile="_fail_${t%.py}.log"
    if ! python3 -u "$t" >"$logfile" 2>&1; then
        rc=$?
        echo "FAIL: $t  (exit=$rc)  -- full output saved to $logfile"
        # Показать хвост прямо в логе (последние 30 строк)
        tail -n 30 "$logfile" || true
        fail=$((fail+1))
    else
        # Тест прошёл — почистить временный лог
        rm -f "$logfile"
    fi
done

echo
if [ "$fail" -eq 0 ]; then
    echo "ALL_TESTS_OK"
else
    echo "FAILED: $fail тестов упало"
    exit 1
fi
