#!/usr/bin/env bash
# fresta · прогон smoke-тестов (лежит рядом с тестами, в scripts/tests/)
# Использование: bash scripts/tests/run_tests.sh
# Или:           cd scripts/tests && bash run_tests.sh

set -euo pipefail

# Уже в scripts/tests/ — тесты лежат рядом, дополнительный cd не нужен.
cd "$(dirname "$0")"

fail=0
for t in test_*.py; do
    echo "=== $t ==="
    if ! python3 "$t"; then
        echo "FAIL: $t"
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
