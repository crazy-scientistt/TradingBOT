$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath '..')).Path
Set-Location -LiteralPath $repoRoot

$envFile = Join-Path -Path $repoRoot -ChildPath '.env.autonomous'
if (-not (Test-Path -LiteralPath $envFile)) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'bootstrap_local_env.ps1')
}

docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

Write-Output ''
Write-Output 'Local development is paper-only. Live stays disarmed.'
Write-Output '  GoldGuard   http://localhost:8000'
Write-Output '  OpenCodex   http://localhost:10100   (add Antigravity / Gemini here)'
Write-Output '  Hermes      http://localhost:8642/health'
Write-Output ''
Write-Output 'Then:  python scripts/verify_local_stack.py'
Write-Output 'Book:  100 USDT paper · 15m entries · 1h regime · ETH entries off · futures ≤2x'
Write-Output 'Do not set GOLDGUARD_MODE=live.'
