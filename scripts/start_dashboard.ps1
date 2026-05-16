# Start the Ultra Arb dashboard (API + frontend)
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Starting Ultra AI Arbitrage Dashboard..." -ForegroundColor Cyan

# Activate venv for API
& "$projectRoot\.venv\Scripts\Activate.ps1"

# Start FastAPI backend in background
Write-Host "Starting API server on http://localhost:8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; .\.venv\Scripts\Activate.ps1; uvicorn arb.dashboard.api.main:app --reload --port 8000" -WindowStyle Normal

Start-Sleep -Seconds 2

# Start Next.js frontend
$frontendPath = Join-Path $projectRoot "arb\dashboard\frontend"
if (Test-Path $frontendPath) {
    Write-Host "Starting frontend on http://localhost:3000..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; npm run dev" -WindowStyle Normal
} else {
    Write-Host "Frontend not yet initialized. Run: cd arb/dashboard/frontend && npx create-next-app@latest . --typescript --tailwind --app --yes" -ForegroundColor Red
}

Write-Host "`nDashboard URLs:" -ForegroundColor Green
Write-Host "  API:      http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
