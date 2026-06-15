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

fail=0
for t in test_*.py; do
    echo "=== $t ==="
    # -u = unbuffered: строки выводятся сразу, в логе CI видно место фейла.
    if ! python3 -u "$t"; then
        echo "FAIL: $t  (exit=$?)"
        fail=$((fail+1))
    fi
done

echo
if [ "$fail" -eq 0 ]; then
    echo "ALL_TESTS_OK"
else
    echo "FAILED: $fail тестов упало"
    exit 1
fi
