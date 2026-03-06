# =============================================================
# Fast Deploy to VPS
# Usage:
#   .\deploy-fast.ps1                    # Deploy ALL (orchestrator + frontend)
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
function Upload-Orchestrator {
    Write-Info "Uploading orchestrator files..."
    foreach ($f in @("requirements.txt", "Dockerfile.orchestrator", "docker-compose.yml", "docker-compose.override.yml")) {
        $localPath = Join-Path $PSScriptRoot $f
        if (Test-Path $localPath) {
            scp $localPath "${VPS}:${RemoteDir}/${f}" 2>$null
        }
    }
    $tarFile = Join-Path $env:TEMP "orchestrator_deploy.tar.gz"
    $projectDir = $PSScriptRoot -replace '\\', '/'
    tar.exe -czf $tarFile -C $projectDir --exclude='__pycache__' --exclude='*.pyc' orchestrator scripts
    $tarSize = [math]::Round((Get-Item $tarFile).Length / 1KB, 1)
    Write-Info "Uploading orchestrator archive ($tarSize KB)..."
    scp $tarFile "${VPS}:${RemoteDir}/orchestrator_deploy.tar.gz"
    ssh $VPS "cd $RemoteDir && tar -xzf orchestrator_deploy.tar.gz && rm orchestrator_deploy.tar.gz"
    Remove-Item $tarFile -ErrorAction SilentlyContinue
    Write-Ok "Orchestrator uploaded"
}

function Upload-Frontend {
    Write-Info "Uploading frontend files..."
    foreach ($f in @("Dockerfile.frontend", "docker-compose.yml", "docker-compose.override.yml")) {
        $localPath = Join-Path $PSScriptRoot $f
        if (Test-Path $localPath) { scp $localPath "${VPS}:${RemoteDir}/${f}" 2>$null }
    }
    $tarFile = Join-Path $env:TEMP "frontend_deploy.tar.gz"
    $projectDir = $PSScriptRoot -replace '\\', '/'
    tar.exe -czf $tarFile -C $projectDir --exclude='node_modules' --exclude='dist' frontend nginx
    $tarSize = [math]::Round((Get-Item $tarFile).Length / 1KB, 1)
    Write-Info "Uploading frontend archive ($tarSize KB)..."
    scp $tarFile "${VPS}:${RemoteDir}/frontend_deploy.tar.gz"
    ssh $VPS "cd $RemoteDir && tar -xzf frontend_deploy.tar.gz && rm frontend_deploy.tar.gz"
    Remove-Item $tarFile -ErrorAction SilentlyContinue
    Write-Ok "Frontend uploaded"
}

function Upload-Whatsapp {
    Write-Info "Uploading whatsapp-service files..."
    foreach ($f in @("Dockerfile.whatsapp", "docker-compose.yml", "docker-compose.override.yml")) {
        $localPath = Join-Path $PSScriptRoot $f
        if (Test-Path $localPath) { scp $localPath "${VPS}:${RemoteDir}/${f}" 2>$null }
    }
    $tarFile = Join-Path $env:TEMP "whatsapp_deploy.tar.gz"
    $projectDir = $PSScriptRoot -replace '\\', '/'
    tar.exe -czf $tarFile -C $projectDir --exclude='node_modules' --exclude='dist' --exclude='auth_store' whatsapp-service
    $tarSize = [math]::Round((Get-Item $tarFile).Length / 1KB, 1)
    Write-Info "Uploading whatsapp archive ($tarSize KB)..."
    scp $tarFile "${VPS}:${RemoteDir}/whatsapp_deploy.tar.gz"
    ssh $VPS "cd $RemoteDir && tar -xzf whatsapp_deploy.tar.gz && rm whatsapp_deploy.tar.gz"
    Remove-Item $tarFile -ErrorAction SilentlyContinue
    Write-Ok "WhatsApp service uploaded"
}

# ---------------------------------------------------------------
# Deploy helper
# ---------------------------------------------------------------
function Deploy-Service($svc, $deployMode) {
    switch ($deployMode) {
        "quick" {
            Write-Info "Restarting $svc (no rebuild)..."
            ssh $VPS "cd $RemoteDir && docker compose restart $svc"
            Write-Ok "$svc restarted"
        }
        "build" {
            Write-Info "Rebuilding $svc (with cache)..."
            ssh $VPS "cd $RemoteDir && docker compose up -d --build $svc"
            Write-Ok "$svc rebuilt"
        }
        "full" {
            Write-Info "Rebuilding $svc (NO cache)..."
            ssh $VPS "cd $RemoteDir && docker compose build --no-cache $svc && docker compose up -d $svc"
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
        # Frontend always needs build (React must compile)
        if ($restartTarget -eq "frontend") { $fileMode = "build" }
        Write-Step 2 2 "Deploying $restartTarget ($fileMode)"
        Deploy-Service $restartTarget $fileMode
    }
}
# ---------------------------------------------------------------
# Service mode (single or all)
# ---------------------------------------------------------------
else {
    # Determine which services to deploy
    $services = @()
    switch ($Service) {
        "all"          { $services = @("orchestrator", "frontend") }
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
        #   frontend     → build (React needs compile inside Docker)
        #   whatsapp     → build (TypeScript needs compile)
        # User can override with -Mode
        if ($Mode) {
            $svcMode = $Mode
        } else {
            $svcMode = switch ($svc) {
                "orchestrator" { "quick" }
                "frontend"     { "build" }
                "whatsapp"     { "build" }
            }
        }

        Write-Step $step $totalSteps "Deploy $svc ($svcMode)"
        Deploy-Service $svc $svcMode
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
$health = ssh $VPS "curl -s http://localhost:8000/health 2>/dev/null | head -c 200"
if ($health -match '"status"') {
    Write-Ok "API healthy: $health"
} else {
    Write-Host "  Waiting for startup..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
    $health = ssh $VPS "curl -s http://localhost:8000/health 2>/dev/null | head -c 200"
    if ($health -match '"status"') {
        Write-Ok "API healthy: $health"
    } else {
        Write-Host "  WARNING: Health check failed. Check logs:" -ForegroundColor Red
        Write-Host "  ssh $VPS `"docker compose -f $RemoteDir/docker-compose.yml logs --tail=20`"" -ForegroundColor White
    }
}
