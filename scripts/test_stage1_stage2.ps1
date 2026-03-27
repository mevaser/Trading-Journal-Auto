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
    Write-Section "Running Stage 1 and Stage 2 pytest suites inside api container"
    $pytestCommand = 'docker compose exec api sh -lc "cd /app && PYTHONPATH=/app pytest -q tests/test_stage1_canonical_ingestion.py tests/test_stage2_lifecycle_projection.py"'
    Invoke-CheckedCommand -Command $pytestCommand -ScriptBlock {
        docker compose exec api sh -lc "cd /app && PYTHONPATH=/app pytest -q tests/test_stage1_canonical_ingestion.py tests/test_stage2_lifecycle_projection.py"
    }

    Write-Host ""
    Write-Host "Stage 1 and Stage 2 test suites passed." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "test_stage1_stage2 failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
