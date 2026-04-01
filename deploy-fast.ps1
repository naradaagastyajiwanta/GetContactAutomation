# =============================================================
# Fast Deploy to VPS
# Usage:
#   .\deploy-fast.ps1                    # Deploy ALL (orchestrator + frontend + whatsapp)
#   .\deploy-fast.ps1 -Service orchestrator   # Orchestrator only (quick restart)
#   .\deploy-fast.ps1 -Service frontend       # Frontend only (rebuild)
#   .\deploy-fast.ps1 -Service whatsapp       # WhatsApp only (rebuild)
#   .\deploy-fast.ps1 -Mode full              # Force full rebuild (no cache)
#   .\deploy-fast.ps1 -File orchestrator/playwright_ig.py  # Single file + restart
# =============================================================

param(
    [ValidateSet("quick", "build", "full")]
    [string]$Mode = "",

    [ValidateSet("orchestrator", "frontend", "whatsapp", "all")]
    [string]$Service = "all",

    [string]$File = "",

    [string]$User = "root",
    [string]$VPSHost = "103.253.145.84",
    [string]$RemoteDir = "/opt/getcontact-ai-agent"
)

$VPS = "${User}@${VPSHost}"
$ErrorActionPreference = "Stop"

function Write-Step($step, $total, $msg) {
    Write-Host "`n[$step/$total] $msg" -ForegroundColor Yellow
}

function Write-Ok($msg) {
    Write-Host "  $msg" -ForegroundColor Green
}

function Write-Info($msg) {
    Write-Host "  $msg" -ForegroundColor Gray
}

# ---------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------
function Create-TarArchive($projectDir, $archiveName, $tarArgs) {
    $archivePath = Join-Path $env:TEMP "$archiveName.tar.gz"
    if (Test-Path $archivePath) {
        Remove-Item $archivePath -Force
    }

    $tarParams = @("-czf", $archivePath, "-C", $projectDir) + $tarArgs
    & tar.exe @tarParams
    if ($LASTEXITCODE -ne 0) {
        throw "tar.exe failed while creating $archiveName.tar.gz"
    }

    return $archivePath
}

function Upload-Orchestrator {
    Write-Info "Uploading orchestrator files..."
    foreach ($f in @("requirements.txt", "Dockerfile.orchestrator", "docker-compose.yml")) {
        $localPath = Join-Path $PSScriptRoot $f
        if (Test-Path $localPath) {
            scp $localPath "${VPS}:${RemoteDir}/${f}" 2>$null
        }
    }
    $projectDir = $PSScriptRoot
    $tmpTar = Create-TarArchive $projectDir "orchestrator_deploy" @("--exclude=__pycache__", "--exclude=*.pyc", "orchestrator", "scripts")
    $tarSize = [math]::Round((Get-Item $tmpTar).Length / 1KB, 1)
    Write-Info "Uploading orchestrator archive ($tarSize KB)..."
    scp $tmpTar "${VPS}:${RemoteDir}/orchestrator_deploy.tar.gz"
    ssh $VPS "cd $RemoteDir && tar -xzf orchestrator_deploy.tar.gz && rm -f orchestrator_deploy.tar.gz"
    Remove-Item $tmpTar -ErrorAction SilentlyContinue
    Write-Ok "Orchestrator uploaded"
}

function Upload-Frontend {
    Write-Info "Uploading frontend source files..."
    foreach ($f in @("Dockerfile.frontend", "docker-compose.yml", "docker-compose.override.yml")) {
        $localPath = Join-Path $PSScriptRoot $f
        if (Test-Path $localPath) { scp $localPath "${VPS}:${RemoteDir}/${f}" 2>$null }
    }
    $projectDir = $PSScriptRoot
    $tmpTar = Create-TarArchive $projectDir "frontend_deploy" @("--exclude=node_modules", "--exclude=dist", "frontend", "nginx")
    $tarSize = [math]::Round((Get-Item $tmpTar).Length / 1KB, 1)
    Write-Info "Uploading frontend archive ($tarSize KB)..."
    scp $tmpTar "${VPS}:${RemoteDir}/frontend_deploy.tar.gz"
    ssh $VPS "cd $RemoteDir && tar -xzf frontend_deploy.tar.gz && rm -f frontend_deploy.tar.gz"
    Remove-Item $tmpTar -ErrorAction SilentlyContinue
    Write-Ok "Frontend uploaded"
}

function Deploy-Frontend-Local {
    # Build locally, SCP dist to server, docker cp into container.
    # Much faster than docker build on server (avoids slow npm ci on VPS).
    Write-Info "Building frontend locally..."
    Push-Location (Join-Path $PSScriptRoot "frontend")
    try {
        npm run build 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Info $_ }
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally {
        Pop-Location
    }
    Write-Ok "Local build complete"

    Write-Info "Uploading dist to server..."
    $distPath = Join-Path $PSScriptRoot "frontend\dist"
    scp -r $distPath "${VPS}:/tmp/frontend-dist-new" 2>$null
    Write-Ok "dist uploaded"

    Write-Info "Copying dist into container..."
    ssh $VPS "docker cp /tmp/frontend-dist-new/. gc-frontend:/app/dist/ && rm -rf /tmp/frontend-dist-new"
    Write-Ok "dist deployed to container (no restart needed)"
}

function Upload-Whatsapp {
    Write-Info "Uploading whatsapp-service files..."
    foreach ($f in @("Dockerfile.whatsapp", "docker-compose.yml")) {
        $localPath = Join-Path $PSScriptRoot $f
        if (Test-Path $localPath) { scp $localPath "${VPS}:${RemoteDir}/${f}" 2>$null }
    }
    $projectDir = $PSScriptRoot
    $tmpTar = Create-TarArchive $projectDir "whatsapp_deploy" @("--exclude=node_modules", "--exclude=dist", "--exclude=data", "--exclude=auth_store", "--exclude=auth_store_backup", "--exclude=auth_store_device_*", "whatsapp-service")
    $tarSize = [math]::Round((Get-Item $tmpTar).Length / 1KB, 1)
    Write-Info "Uploading whatsapp archive ($tarSize KB)..."
    scp $tmpTar "${VPS}:${RemoteDir}/whatsapp_deploy.tar.gz"
    ssh $VPS "cd $RemoteDir && tar -xzf whatsapp_deploy.tar.gz && rm -f whatsapp_deploy.tar.gz"
    Remove-Item $tmpTar -ErrorAction SilentlyContinue
    Write-Ok "WhatsApp service uploaded"
}

# ---------------------------------------------------------------
# Deploy helper
# ---------------------------------------------------------------
function Deploy-Service($svc, $deployMode) {
    $composeCmd = "docker compose -f docker-compose.yml"

    switch ($deployMode) {
        "quick" {
            Write-Info "Restarting $svc (no rebuild)..."
            ssh $VPS "cd $RemoteDir && $composeCmd restart $svc"
            Write-Ok "$svc restarted"
        }
        "build" {
            Write-Info "Rebuilding $svc (with cache)..."
            ssh $VPS "cd $RemoteDir && $composeCmd up -d --build $svc"
            Write-Ok "$svc rebuilt"
        }
        "full" {
            Write-Info "Rebuilding $svc (NO cache)..."
            ssh $VPS "cd $RemoteDir && $composeCmd build --no-cache $svc && $composeCmd up -d $svc"
            Write-Ok "$svc rebuilt from scratch"
        }
    }
}

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

# ---------------------------------------------------------------
# Single-file mode
# ---------------------------------------------------------------
if ($File -ne "") {
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "  Fast Deploy: $File (single file)" -ForegroundColor Cyan
    Write-Host "  Target: ${VPS}:${RemoteDir}" -ForegroundColor Cyan
    Write-Host "=============================================" -ForegroundColor Cyan

    Write-Step 1 2 "Uploading $File"
    $localPath = Join-Path $PSScriptRoot $File
    if (-not (Test-Path $localPath)) {
        Write-Host "  ERROR: File not found: $localPath" -ForegroundColor Red
        exit 1
    }
    $remoteParent = Split-Path $File -Parent
    if ($remoteParent) {
        ssh $VPS "mkdir -p $RemoteDir/$remoteParent"
    }
    scp $localPath "${VPS}:${RemoteDir}/${File}"
    Write-Ok "Uploaded"

    # Auto-detect which service to restart
    $restartTarget = ""
    if ($File -match "^orchestrator[/\\]") { $restartTarget = "orchestrator" }
    elseif ($File -match "^frontend[/\\]") { $restartTarget = "frontend" }
    elseif ($File -match "^whatsapp") { $restartTarget = "whatsapp" }

    if ($restartTarget) {
        $fileMode = if ($Mode) { $Mode } else { "quick" }
        # Frontend always uses local build + docker cp (avoids slow server-side npm ci)
        if ($restartTarget -eq "frontend") {
            Write-Step 2 2 "Deploying frontend (local build)"
            Deploy-Frontend-Local
        } else {
            Write-Step 2 2 "Deploying $restartTarget ($fileMode)"
            Deploy-Service $restartTarget $fileMode
        }
    }
}
# ---------------------------------------------------------------
# Service mode (single or all)
# ---------------------------------------------------------------
else {
    # Determine which services to deploy
    $services = @()
    switch ($Service) {
        "all"          { $services = @("orchestrator", "frontend", "whatsapp") }
        default        { $services = @($Service) }
    }

    $svcList = $services -join " + "
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "  Fast Deploy: $svcList" -ForegroundColor Cyan
    Write-Host "  Target: ${VPS}:${RemoteDir}" -ForegroundColor Cyan
    Write-Host "=============================================" -ForegroundColor Cyan

    $totalSteps = $services.Count * 2
    $step = 0

    foreach ($svc in $services) {
        # --- Upload ---
        $step++
        Write-Step $step $totalSteps "Upload $svc"

        switch ($svc) {
            "orchestrator" { Upload-Orchestrator }
            "frontend"     { Upload-Frontend }
            "whatsapp"     { Upload-Whatsapp }
        }

        # --- Deploy ---
        $step++

        # Smart mode per service:
        #   orchestrator → quick (volume-mounted, restart is enough)
        #   frontend     → local build + docker cp (avoids slow npm ci on VPS)
        #   whatsapp     → build (TypeScript needs compile)
        # User can override with -Mode
        if ($Mode) {
            $svcMode = $Mode
        } else {
            $svcMode = switch ($svc) {
                "orchestrator" { "quick" }
                "frontend"     { "local" }
                "whatsapp"     { "build" }
            }
        }

        Write-Step $step $totalSteps "Deploy $svc ($svcMode)"
        if ($svc -eq "frontend" -and $svcMode -eq "local") {
            Deploy-Frontend-Local
        } else {
            Deploy-Service $svc $svcMode
        }
    }
}

$stopwatch.Stop()
$elapsed = $stopwatch.Elapsed.TotalSeconds

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "  Deploy complete! ($([math]::Round($elapsed, 1))s)" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan

# Quick health check
Write-Host "`n  Checking health..." -ForegroundColor Gray
Start-Sleep -Seconds 3
$orchestratorHealth = ssh $VPS "curl -s http://localhost:8000/health 2>/dev/null | head -c 200"
$whatsappHealth = ssh $VPS "curl -s http://localhost:3110/status 2>/dev/null | head -c 200"
if ($orchestratorHealth -match '"status"' -and $whatsappHealth -match '"devices"') {
    Write-Ok "Orchestrator healthy: $orchestratorHealth"
    Write-Ok "WhatsApp healthy: $whatsappHealth"
} else {
    Write-Host "  Waiting for startup..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
    $orchestratorHealth = ssh $VPS "curl -s http://localhost:8000/health 2>/dev/null | head -c 200"
    $whatsappHealth = ssh $VPS "curl -s http://localhost:3110/status 2>/dev/null | head -c 200"
    if ($orchestratorHealth -match '"status"' -and $whatsappHealth -match '"devices"') {
        Write-Ok "Orchestrator healthy: $orchestratorHealth"
        Write-Ok "WhatsApp healthy: $whatsappHealth"
    } else {
        Write-Host "  WARNING: Health check failed. Check logs:" -ForegroundColor Red
        Write-Host "  ssh $VPS `"cd $RemoteDir && docker compose -f docker-compose.yml logs --tail=20 orchestrator frontend whatsapp`"" -ForegroundColor White
    }
}
