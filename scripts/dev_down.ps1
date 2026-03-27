param([switch]$Reset)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-CheckedCommand {
    param(
        [string]$Command,
        [scriptblock]$ScriptBlock
    )

    Write-Host "[cmd] $Command" -ForegroundColor DarkGray
    & $ScriptBlock
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command"
    }
}

try {
    if ($Reset) {
        Write-Section "Stopping Docker services and removing volumes"
        Invoke-CheckedCommand -Command "docker compose down -v" -ScriptBlock {
            docker compose down -v
        }
    }
    else {
        Write-Section "Stopping Docker services"
        Invoke-CheckedCommand -Command "docker compose down" -ScriptBlock {
            docker compose down
        }
    }

    Write-Host ""
    Write-Host "Local development stack is stopped." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "dev_down failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
