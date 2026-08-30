$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath '..')).Path
Set-Location -LiteralPath $repoRoot

$envFile = Join-Path -Path $repoRoot -ChildPath '.env.autonomous'
if (-not (Test-Path -LiteralPath $envFile)) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'bootstrap_local_env.ps1')
}

$env:UI_REVISION = (git rev-parse --short HEAD)
if (-not $env:UI_REVISION) { $env:UI_REVISION = 'local' }

docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build --force-recreate -d
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

Write-Output ''
Write-Output 'Local development is paper-only. Live stays disarmed.'
Write-Output '  GoldGuard   http://localhost:8000'
Write-Output '  OpenCodex   http://localhost:10100   (add Antigravity / Gemini here)'
Write-Output '  Hermes      http://localhost:8642/health'
Write-Output "  UI revision $($env:UI_REVISION)  (hard-refresh the browser; gold chrome means a stale image)"
Write-Output ''
Write-Output 'If the desk is still gold: docker compose -f docker-compose.local.yml --env-file .env.autonomous build --no-cache goldguard'
Write-Output 'Then:  python scripts/verify_local_stack.py'
Write-Output 'Book:  100 USDT paper · 15m entries · 1h regime · ETH entries off · futures ≤2x'
Write-Output 'Do not set GOLDGUARD_MODE=live.'
