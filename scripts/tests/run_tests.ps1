# fresta · прогон smoke-тестов (PowerShell, Windows, лежит рядом с тестами в scripts/tests/)
# Использование: powershell -ExecutionPolicy Bypass -File scripts\tests\run_tests.ps1
# Или:           cd scripts\tests; powershell -File run_tests.ps1

$ErrorActionPreference = "Stop"
# Уже в scripts/tests/ — тесты лежат рядом, дополнительный Set-Location не нужен.
Set-Location -Path $PSScriptRoot

$failed = 0
Get-ChildItem -Filter "test_*.py" | ForEach-Object {
    Write-Host "=== $($_.Name) ===" -ForegroundColor Cyan
    & python $_.Name
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $($_.Name)" -ForegroundColor Red
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
