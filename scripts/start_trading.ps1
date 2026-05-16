# Start the Ultra Arb trading engine
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Starting Ultra AI Arbitrage Trading System..." -ForegroundColor Cyan

# Activate venv
& "$projectRoot\.venv\Scripts\Activate.ps1"

# Check Docker services
$dbRunning = docker ps --filter "name=ultra_arb_db" --format "{{.Status}}" 2>&1
$redisRunning = docker ps --filter "name=ultra_arb_redis" --format "{{.Status}}" 2>&1

if (-not $dbRunning -or -not $redisRunning) {
    Write-Host "Starting Docker services..." -ForegroundColor Yellow
    docker compose up -d
    Start-Sleep -Seconds 5
}

# Initialize database
Write-Host "Initializing database..." -ForegroundColor Yellow
python -c "import asyncio; from arb.infra.db import init_db; asyncio.run(init_db())"

# Start trading engine
Write-Host "Starting trading engine..." -ForegroundColor Green
python -m arb.main
