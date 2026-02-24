# =============================================================
# Quick helper: sync project files to VPS (PowerShell / Windows)
# Usage: .\sync-to-vps.ps1 [-User "root"] [-Host "103.253.145.84"]
# =============================================================

param(
    [string]$User = "root",
    [string]$VPSHost = "103.253.145.84",
    [string]$RemoteDir = "/opt/getcontact-ai-agent"
)

$VPS = "${User}@${VPSHost}"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Sync to VPS: ${VPS}:${RemoteDir}" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# Step 1: Create remote directory
Write-Host "`n[1/4] Creating remote directory..." -ForegroundColor Yellow
ssh $VPS "mkdir -p $RemoteDir"

# Step 2: Sync project files with scp (exclude large/unnecessary dirs)
Write-Host "`n[2/4] Syncing project files..." -ForegroundColor Yellow

# Files/directories to copy
$items = @(
    "docker-compose.yml",
    "Dockerfile.orchestrator",
    "Dockerfile.whatsapp",
    "Dockerfile.frontend",
    ".dockerignore",
    ".env.production.example",
    "deploy.sh",
    "requirements.txt",
    "nginx",
    "orchestrator",
    "scripts",
    "frontend",
    "whatsapp-service/package.json",
    "whatsapp-service/package-lock.json",
    "whatsapp-service/tsconfig.json",
    "whatsapp-service/src"
)

foreach ($item in $items) {
    $localPath = Join-Path $PSScriptRoot $item
    if (Test-Path $localPath) {
        $isDir = (Get-Item $localPath).PSIsContainer
        if ($isDir) {
            Write-Host "  Copying directory: $item" -ForegroundColor Gray
            scp -r $localPath "${VPS}:${RemoteDir}/${item}"
        } else {
            # Ensure parent directory exists
            $parentDir = Split-Path $item -Parent
            if ($parentDir) {
                ssh $VPS "mkdir -p $RemoteDir/$parentDir"
            }
            Write-Host "  Copying file: $item" -ForegroundColor Gray
            scp $localPath "${VPS}:${RemoteDir}/${item}"
        }
    } else {
        Write-Host "  SKIP (not found): $item" -ForegroundColor DarkGray
    }
}

# Step 3: Copy database if exists
$dbPath = Join-Path $PSScriptRoot "data\getcontact.db"
if (Test-Path $dbPath) {
    Write-Host "`n[3/4] Copying database (getcontact.db)..." -ForegroundColor Yellow
    ssh $VPS "mkdir -p $RemoteDir/data"
    scp $dbPath "${VPS}:${RemoteDir}/data/getcontact.db"
    $dbSize = [math]::Round((Get-Item $dbPath).Length / 1MB, 2)
    Write-Host "  Database copied ($dbSize MB)" -ForegroundColor Green
} else {
    Write-Host "`n[3/4] No local database found - will create fresh on first run" -ForegroundColor DarkGray
}

# Step 4: Copy WhatsApp auth store if exists
$authPath = Join-Path $PSScriptRoot "whatsapp-service\auth_store"
if (Test-Path $authPath) {
    $authFiles = Get-ChildItem $authPath -File
    if ($authFiles.Count -gt 0) {
        $fileCount = $authFiles.Count
        Write-Host "`n[4/4] Copying WhatsApp session - $fileCount files..." -ForegroundColor Yellow
        ssh $VPS "mkdir -p $RemoteDir/whatsapp-service/auth_store"
        scp -r "$authPath\*" "${VPS}:${RemoteDir}/whatsapp-service/auth_store/"
        Write-Host "  WhatsApp session copied" -ForegroundColor Green
    } else {
        Write-Host "`n[4/4] WhatsApp auth_store is empty - need to scan QR after deploy" -ForegroundColor DarkGray
    }
} else {
    Write-Host "`n[4/4] No WhatsApp auth_store - need to scan QR after deploy" -ForegroundColor DarkGray
}

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "  Sync complete!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "  1. ssh $VPS" -ForegroundColor White
Write-Host "  2. cd $RemoteDir" -ForegroundColor White
Write-Host "  3. cp .env.production.example .env.production" -ForegroundColor White
Write-Host "  4. nano .env.production  # Isi OPENAI_API_KEY & SERPER_API_KEY" -ForegroundColor White
Write-Host "  5. bash deploy.sh" -ForegroundColor White
Write-Host ""
