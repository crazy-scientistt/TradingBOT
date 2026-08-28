$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path -Path $PSScriptRoot -ChildPath '..')).Path
$target = Join-Path -Path $repoRoot -ChildPath '.env.autonomous'
if (Test-Path -LiteralPath $target) {
    throw "Refusing to overwrite existing .env.autonomous."
}

function New-Token {
    try {
        $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    }
    catch {
        # Windows PowerShell 5.1 lacks the static Int32 overload; use the
        # equivalent instance API without changing the token size/source.
        $bytes = New-Object byte[] 32
        $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $generator.GetBytes($bytes)
        }
        finally {
            $generator.Dispose()
        }
    }
    return [Convert]::ToBase64String($bytes)
}

$content = @"
GOLDGUARD_ENVIRONMENT=development
GOLDGUARD_MODE=paper
GOLDGUARD_DATA_DIR=/app/data
GOLDGUARD_SESSION_SECRET=$(New-Token)
OPENCODEX_API_AUTH_TOKEN=$(New-Token)
OPENCODEX_ADMIN_AUTH_TOKEN=$(New-Token)
HERMES_BRIDGE_TOKEN=$(New-Token)
BINANCE_API_KEY=
BINANCE_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"@

$bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($content)
$stream = $null
try {
    $stream = [System.IO.File]::Open(
        $target,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
}
catch [System.IO.IOException] {
    if (Test-Path -LiteralPath $target) {
        throw "Refusing to overwrite existing .env.autonomous."
    }
    throw $_
}
finally {
    if ($null -ne $stream) {
        $stream.Dispose()
    }
}

Write-Output 'created .env.autonomous'
