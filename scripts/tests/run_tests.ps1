# fresta · прогон smoke-тестов (PowerShell, Windows, лежит рядом с тестами в scripts/tests/)
# Использование: powershell -ExecutionPolicy Bypass -File scripts\tests\run_tests.ps1
# Или:           cd scripts\tests; powershell -File run_tests.ps1

$ErrorActionPreference = "Stop"
# Уже в scripts/tests/ — тесты лежат рядом, дополнительный Set-Location не нужен.
Set-Location -Path $PSScriptRoot

# Диагностика окружения (полезно при фейле в CI).
Write-Host "--- env ---" -ForegroundColor DarkGray
& python --version 2>&1
Write-Host "PWD: $PWD"
Write-Host "--- env end ---" -ForegroundColor DarkGray
Write-Host ""

$failed = 0
Get-ChildItem -Filter "test_*.py" | ForEach-Object {
    Write-Host "=== $($_.Name) ===" -ForegroundColor Cyan
    # -u = unbuffered: строки идут в лог сразу, в CI видно место фейла.
    & python -u $_.Name
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $($_.Name)  (exit=$LASTEXITCODE)" -ForegroundColor Red
        $failed += 1
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "ALL_TESTS_OK" -ForegroundColor Green
} else {
    Write-Host "FAILED: $failed тестов упало" -ForegroundColor Red
    exit 1
}
