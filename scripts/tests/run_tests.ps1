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

# Cleanup any leftover fail logs from previous run.
Get-ChildItem -Filter "_fail_*.log" -ErrorAction SilentlyContinue | Remove-Item -Force

$failed = 0
Get-ChildItem -Filter "test_*.py" | ForEach-Object {
    Write-Host "=== $($_.Name) ===" -ForegroundColor Cyan
    $logfile = "_fail_$($_.BaseName).log"
    # -u = unbuffered: строки идут в лог сразу, в CI видно место фейла.
    # Весь stdout+stderr теста идёт в _fail_<test>.log, чтобы при фейле
    # upload-artifact в tests.yml мог приложить его к GitHub Actions.
    & python -u $_.Name *> $logfile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $($_.Name)  (exit=$LASTEXITCODE)  -- full output saved to $logfile" -ForegroundColor Red
        # Показать хвост прямо в логе (последние 30 строк)
        Get-Content -Path $logfile -Tail 30
        $failed += 1
    } else {
        Remove-Item -Force $logfile
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "ALL_TESTS_OK" -ForegroundColor Green
} else {
    Write-Host "FAILED: $failed тестов упало" -ForegroundColor Red
    exit 1
}
