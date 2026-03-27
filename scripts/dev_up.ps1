param([switch]$Reset)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Show-ApiLogsForDiagnostics {
    Write-Host "[cmd] docker compose logs api --tail=100" -ForegroundColor DarkGray
    docker compose logs api --tail=100
}

function Handle-ExitCode137 {
    Write-Host ""
    Write-Host "Container likely crashed or was killed (exit code 137)." -ForegroundColor Red
    Write-Host "Possible causes:"
    Write-Host "- Docker ran out of memory"
    Write-Host "- Container crashed during startup"
    Write-Host "- API container not fully ready"
    Write-Host ""
    Write-Host "API container crashed during migration." -ForegroundColor Red
    Write-Host ""
    Show-ApiLogsForDiagnostics
    exit 1
}

function Run-CommandSafe {
    param(
        [string]$Command,
        [scriptblock]$ScriptBlock,
        [string]$FailureMessage = "Command failed."
    )

    Write-Host "[cmd] $Command" -ForegroundColor DarkGray
    & $ScriptBlock
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        return
    }

    if ($exitCode -eq 137) {
        Handle-ExitCode137
    }

    throw "$FailureMessage Exit code: $exitCode"
}

function Get-ServiceContainerId {
    param([string]$ServiceName)

    $containerId = docker compose ps -q $ServiceName
    if (-not $containerId) {
        throw "Could not resolve container id for service '$ServiceName'."
    }
    return $containerId.Trim()
}

function Get-ContainerReadiness {
    param([string]$ContainerId)

    $format = "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}"
    return (docker inspect --format=$format $ContainerId).Trim()
}

function Get-ContainerStateStatus {
    param([string]$ContainerId)

    return (docker inspect -f "{{.State.Status}}" $ContainerId).Trim()
}

function Get-ContainerRestartCount {
    param([string]$ContainerId)

    $restartCount = docker inspect -f "{{.RestartCount}}" $ContainerId
    if (-not $restartCount) {
        throw "Could not read RestartCount for container '$ContainerId'."
    }
    return [int]$restartCount.Trim()
}

function Wait-ForServiceReady {
    param(
        [string]$ServiceName,
        [string[]]$AcceptableStates,
        [int]$TimeoutSeconds = 180
    )

    $containerId = Get-ServiceContainerId -ServiceName $ServiceName
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        $state = Get-ContainerReadiness -ContainerId $containerId
        Write-Host "[$ServiceName] state=$state"
        if ($AcceptableStates -contains $state) {
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Timed out waiting for service '$ServiceName' to reach one of: $($AcceptableStates -join ', ')"
}

function Wait-ForHttpReady {
    param(
        [string]$Url,
        [int]$MaxAttempts = 5,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Write-Host "[health] Attempt $attempt/$MaxAttempts -> GET $Url" -ForegroundColor DarkGray
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 10 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            if ($attempt -eq $MaxAttempts) {
                throw "Endpoint did not become ready after $MaxAttempts attempts: $Url"
            }
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Endpoint did not become ready: $Url"
}

function Wait-ForApiStability {
    param(
        [int]$MaxWaitSeconds = 30,
        [int]$StableSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)

    while ((Get-Date) -lt $deadline) {
        $containerId = Get-ServiceContainerId -ServiceName "api"
        $restartCountBefore = Get-ContainerRestartCount -ContainerId $containerId
        $stateBefore = Get-ContainerStateStatus -ContainerId $containerId

        if ($restartCountBefore -gt 0) {
            Write-Host "API container is restarting. Waiting for stability..."
        }

        if ($stateBefore -ne "running") {
            Write-Host "[api] state=$stateBefore"
            Start-Sleep -Seconds 2
            continue
        }

        Start-Sleep -Seconds $StableSeconds

        $containerIdAfter = Get-ServiceContainerId -ServiceName "api"
        $restartCountAfter = Get-ContainerRestartCount -ContainerId $containerIdAfter
        $stateAfter = Get-ContainerStateStatus -ContainerId $containerIdAfter

        if ($restartCountBefore -eq $restartCountAfter -and $stateAfter -eq "running") {
            return
        }

        Write-Host "API container is restarting. Waiting for stability..."
    }

    throw "API container did not become stable within $MaxWaitSeconds seconds."
}

try {
    Write-Section "Checking Docker"
    try {
        Run-CommandSafe -Command "docker info" -ScriptBlock {
            docker info | Out-Null
        } -FailureMessage "Docker is not available."
    }
    catch {
        Write-Host ""
        Write-Host "Docker Desktop is not running. Please start Docker Desktop and retry." -ForegroundColor Red
        exit 1
    }

    if ($Reset) {
        Write-Section "Reset requested"
        try {
            Run-CommandSafe -Command "docker compose down -v" -ScriptBlock {
                docker compose down -v
            } -FailureMessage "Failed to stop containers."
        }
        catch {
            Write-Host ""
            Write-Host "Failed to stop containers. Docker may not be running." -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "Normal startup requested."
    }

    Write-Section "Starting services"
    Run-CommandSafe -Command "docker compose up -d" -ScriptBlock {
        docker compose up -d
    } -FailureMessage "Failed to start Docker services."

    Write-Section "Waiting for DB"
    Wait-ForServiceReady -ServiceName "db" -AcceptableStates @("healthy")

    Write-Section "Waiting for API"
    Wait-ForServiceReady -ServiceName "api" -AcceptableStates @("healthy", "running")
    Wait-ForHttpReady -Url "http://localhost:8000/docs"
    Wait-ForHttpReady -Url "http://localhost:8000/openapi.json"

    Write-Section "Checking API stability"
    Wait-ForApiStability

    Write-Section "Running migrations"
    $migrationSucceeded = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Migration attempt $attempt/3"

            Write-Host "[cmd] docker compose ps -q api" -ForegroundColor DarkGray
            $apiContainerId = Get-ServiceContainerId -ServiceName "api"

            $restartCount = Get-ContainerRestartCount -ContainerId $apiContainerId
            if ($restartCount -gt 0) {
                Write-Host "API container is restarting. Waiting for stability..."
                Wait-ForApiStability
            }

            Run-CommandSafe -Command 'docker compose exec api python -c "print(''ready'')"' -ScriptBlock {
                docker compose exec api python -c "print('ready')"
            } -FailureMessage "API container pre-migration readiness check failed."

            Run-CommandSafe -Command 'docker compose exec api sh -lc "cd /app && alembic upgrade head"' -ScriptBlock {
                docker compose exec api sh -lc "cd /app && alembic upgrade head"
            } -FailureMessage "Alembic upgrade failed."

            $migrationSucceeded = $true
            break
        }
        catch {
            if ($attempt -ge 3) {
                throw
            }
            Start-Sleep -Seconds 2
            Wait-ForApiStability
        }
    }

    if (-not $migrationSucceeded) {
        throw "Alembic upgrade failed after 3 attempts."
    }

    Write-Host ""
    Write-Host "Development environment is ready." -ForegroundColor Green
    Write-Host "API: http://localhost:8000/docs"
    Write-Host "Streamlit: http://localhost:8501"
}
catch {
    Write-Host ""
    Write-Host "dev_up failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
