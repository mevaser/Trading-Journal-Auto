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

function Invoke-DockerPython {
    param([string]$PythonScript)

    Write-Host '[cmd] docker compose exec -T api sh -lc "cd /app && PYTHONPATH=/app python -"' -ForegroundColor DarkGray
    $output = $PythonScript | docker compose exec -T api sh -lc "cd /app && PYTHONPATH=/app python -"
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose exec -T api ... python - failed with exit code $LASTEXITCODE"
    }
    return $output
}

function Convert-LastJsonLine {
    param([object]$OutputObject)

    $lines = @($OutputObject | Out-String -Stream) | Where-Object { $_.Trim() -ne "" }
    if (-not $lines -or $lines.Count -eq 0) {
        throw "No JSON output was returned from the container command."
    }

    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        $line = $lines[$i].Trim()
        if (-not ($line.StartsWith("{") -or $line.StartsWith("["))) {
            continue
        }

        try {
            return ($line | ConvertFrom-Json)
        }
        catch {
            continue
        }
    }

    throw "Could not find a valid JSON line in container output."
}

function Wait-ForApi {
    param(
        [string]$Url,
        [int]$MaxAttempts = 5,
        [int]$DelaySeconds = 3
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Write-Host "[health] Attempt $attempt/$MaxAttempts -> GET $Url" -ForegroundColor DarkGray
            $response = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 20
            if ($response.message -eq "Trading Journal API is live") {
                return $response
            }
        }
        catch {
            if ($attempt -eq $MaxAttempts) {
                throw
            }
        }

        if ($attempt -lt $MaxAttempts) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    throw "API health check failed after $MaxAttempts attempts."
}

try {
    Write-Section "Checking API availability"
    $healthResponse = Wait-ForApi -Url "http://localhost:8000/"
    if ($healthResponse.message -ne "Trading Journal API is live") {
        throw "Unexpected API root response."
    }

    Write-Section "Bootstrapping deterministic smoke-test auth context"
    $bootstrapScript = @'
import asyncio
import json

from sqlalchemy import and_, select

from app.auth.passwords import hash_password
from app.auth.tokens import issue_token_pair
from app.core.config import get_settings
from app.db.models import Membership, Tenant, User
from app.db.session import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, 1)
        if tenant is None:
            tenant = Tenant(id=1, slug="default", name="Default", is_active=True)
            db.add(tenant)
            await db.flush()

        user = (await db.execute(select(User).where(User.email == "smoke@example.com"))).scalar_one_or_none()
        if user is None:
            user = User(
                username="smoke_user",
                email="smoke@example.com",
                password_hash=hash_password("smoke-password"),
            )
            db.add(user)
            await db.flush()
        else:
            user.password_hash = hash_password("smoke-password")

        membership = (
            await db.execute(
                select(Membership).where(
                    and_(Membership.user_id == user.id, Membership.tenant_id == tenant.id)
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            membership = Membership(
                tenant_id=tenant.id,
                user_id=user.id,
                role="owner",
                is_active=True,
            )
            db.add(membership)
        else:
            membership.role = "owner"
            membership.is_active = True

        await db.commit()

        token = issue_token_pair(
            user_id=user.id,
            tenant_id=tenant.id,
            roles=["owner"],
            secret_key=get_settings().app_secret_key,
        )
        print(json.dumps({"access_token": token.access_token, "tenant_id": tenant.id}))


asyncio.run(main())
'@
    $bootstrapOutput = Invoke-DockerPython -PythonScript $bootstrapScript
    $auth = Convert-LastJsonLine -OutputObject $bootstrapOutput
    $headers = @{
        Authorization = "Bearer $($auth.access_token)"
        "X-Tenant-ID" = [string]$auth.tenant_id
        "Content-Type" = "application/json"
    }

    Write-Section "Importing canonical executions through the running API"
    $importPayload = @{
        start_time = "2026-03-19T08:00:00Z"
        end_time = "2026-03-19T22:00:00Z"
        async_mode = $false
        broker_account_id = "SMOKE-STAGE2"
        executions = @(
            @{
                external_execution_id = "smoke-stage2-exec-1"
                symbol = "AAPL"
                side = "BUY"
                asset_type = "stock"
                quantity = "2"
                price = "100"
                commission = "0"
                execution_time = "2026-03-19T10:00:00Z"
            },
            @{
                external_execution_id = "smoke-stage2-exec-2"
                symbol = "AAPL"
                side = "SELL"
                asset_type = "stock"
                quantity = "1"
                price = "110"
                commission = "0"
                execution_time = "2026-03-19T12:00:00Z"
            }
        )
    } | ConvertTo-Json -Depth 8

    Write-Host "[cmd] POST http://localhost:8000/broker/ibkr/import" -ForegroundColor DarkGray
    $importResponse = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/broker/ibkr/import" -Headers $headers -Body $importPayload -TimeoutSec 30
    $importRunId = [int]$importResponse.import_run_id
    $imported = [int]$importResponse.summary.imported
    $duplicates = [int]$importResponse.summary.duplicates_skipped
    $failed = [int]$importResponse.summary.failed
    if (($imported + $duplicates) -lt 2) {
        throw "Smoke import did not process both executions as imported or duplicates."
    }

    Write-Section "Running deterministic lifecycle rebuild for the smoke partition"
    $rebuildScript = @'
import asyncio
import json

from sqlalchemy import select

from app.db.models import TradeLifecycleExecutionAllocation, TradeLifecycleProjection
from app.db.session import AsyncSessionLocal
from app.services.lifecycle_projection_service import LifecycleProjectionPartition, LifecycleProjectionService


async def main() -> None:
    partition = LifecycleProjectionPartition(
        tenant_id=1,
        source="ibkr",
        broker_account_id="SMOKE-STAGE2",
        symbol="AAPL",
        asset_type="stock",
    )

    async with AsyncSessionLocal() as db:
        service = LifecycleProjectionService(db)
        result = await service.rebuild_partition_full(partition)

        lifecycle = (
            await db.execute(
                select(TradeLifecycleProjection)
                .where(
                    TradeLifecycleProjection.tenant_id == partition.tenant_id,
                    TradeLifecycleProjection.source == partition.source,
                    TradeLifecycleProjection.broker_account_id == partition.broker_account_id,
                    TradeLifecycleProjection.symbol == partition.symbol,
                    TradeLifecycleProjection.asset_type == partition.asset_type,
                )
                .order_by(TradeLifecycleProjection.lifecycle_seq.asc())
            )
        ).scalar_one()

        allocations = list(
            (
                await db.execute(
                    select(TradeLifecycleExecutionAllocation)
                    .where(TradeLifecycleExecutionAllocation.trade_lifecycle_id == lifecycle.id)
                    .order_by(TradeLifecycleExecutionAllocation.allocation_seq.asc())
                )
            ).scalars()
        )

        payload = {
            "generation": result.generation,
            "lifecycle_count": result.lifecycle_count,
            "allocation_count": result.allocation_count,
            "status": lifecycle.status,
            "remaining_quantity": str(lifecycle.remaining_quantity),
            "allocation_roles": [item.allocation_role for item in allocations],
        }

        if lifecycle.status != "OPEN":
            raise SystemExit("Expected OPEN lifecycle status.")
        if str(lifecycle.remaining_quantity) != "1.00000000":
            raise SystemExit("Expected remaining_quantity=1.00000000.")
        if [item.allocation_role for item in allocations] != ["ENTRY", "EXIT"]:
            raise SystemExit("Expected allocation roles ENTRY, EXIT.")

        print(json.dumps(payload))


asyncio.run(main())
'@
    $rebuildOutput = Invoke-DockerPython -PythonScript $rebuildScript
    $rebuildSummary = Convert-LastJsonLine -OutputObject $rebuildOutput

    Write-Section "Import Summary"
    Write-Host "import_run_id: $importRunId"
    Write-Host "imported: $imported"
    Write-Host "duplicates_skipped: $duplicates"
    Write-Host "failed: $failed"

    Write-Section "Lifecycle Summary"
    Write-Host "generation: $($rebuildSummary.generation)"
    Write-Host "lifecycle_count: $($rebuildSummary.lifecycle_count)"
    Write-Host "allocation_count: $($rebuildSummary.allocation_count)"

    Write-Section "Validation Checks"
    Write-Host "status: $($rebuildSummary.status)"
    Write-Host "remaining_quantity: $($rebuildSummary.remaining_quantity)"
    Write-Host "allocation_roles: $($rebuildSummary.allocation_roles -join ',')"
    Write-Host ""
    Write-Host "Smoke import and rebuild completed successfully." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "smoke_import_and_rebuild failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
