# =============================================================
# Quick Deploy: tar + ssh (MUCH faster than scp -r)
# Usage: .\quick-deploy.ps1
# =============================================================

param(
    [string]$User = "root",
    [string]$VPSHost = "103.253.145.84",
    [string]$RemoteDir = "/opt/getcontact-ai-agent"
)

$VPS = "${User}@${VPSHost}"
$ProjectRoot = $PSScriptRoot
$TarFile = Join-Path $env:TEMP "getcontact-deploy.tar.gz"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Quick Deploy to ${VPS}:${RemoteDir}" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# Step 1: Create tar.gz locally (exclude junk)
Write-Host "`n[1/4] Creating archive..." -ForegroundColor Yellow

Push-Location $ProjectRoot
try {
    tar -czf $TarFile `
        --exclude="node_modules" `
        --exclude=".git" `
        --exclude="__pycache__" `
        --exclude="*.pyc" `
        --exclude=".env" `
        --exclude="data/getcontact.db" `
        --exclude="whatsapp-service/auth_store" `
        --exclude="frontend/dist" `
        --exclude=".superdesign" `
        --exclude=".claude" `
        --exclude="=2.1.2" `
        docker-compose.yml `
        Dockerfile.orchestrator `
        Dockerfile.whatsapp `
        Dockerfile.frontend `
        .dockerignore `
        .env.production.example `
        deploy.sh `
        requirements.txt `
        nginx `
        orchestrator `
        scripts `
        frontend/index.html `
        frontend/package.json `
        frontend/package-lock.json `
        frontend/postcss.config.js `
        frontend/tailwind.config.ts `
        frontend/tsconfig.json `
        frontend/vite.config.ts `
        frontend/src `
        whatsapp-service/package.json `
        whatsapp-service/package-lock.json `
        whatsapp-service/tsconfig.json `
        whatsapp-service/src

    $size = [math]::Round((Get-Item $TarFile).Length / 1MB, 2)
    Write-Host "  Archive created: $size MB" -ForegroundColor Green
} finally {
    Pop-Location
}

# Step 2: Create remote dir & upload
Write-Host "`n[2/4] Uploading to VPS..." -ForegroundColor Yellow
ssh $VPS "mkdir -p $RemoteDir"
scp $TarFile "${VPS}:${RemoteDir}/deploy.tar.gz"
Write-Host "  Upload complete" -ForegroundColor Green

# Step 3: Extract on server
Write-Host "`n[3/4] Extracting on server..." -ForegroundColor Yellow
ssh $VPS "cd $RemoteDir && tar -xzf deploy.tar.gz && rm deploy.tar.gz"
Write-Host "  Extracted" -ForegroundColor Green

# Step 4: Rebuild & restart Docker containers
Write-Host "`n[4/4] Rebuilding Docker containers..." -ForegroundColor Yellow
ssh $VPS "cd $RemoteDir && docker compose up -d --build"

# Cleanup local tar
Remove-Item $TarFile -ErrorAction SilentlyContinue

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "  Deploy complete!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Check status:" -ForegroundColor Yellow
Write-Host "  ssh ${VPS} 'cd ${RemoteDir} && docker compose ps'" -ForegroundColor White
Write-Host "  ssh ${VPS} 'cd ${RemoteDir} && docker compose logs -f --tail=50'" -ForegroundColor White
Write-Host ""
