# Starts the backend (FastAPI, port 8000) and the frontend (Next.js, port 3000) in two windows.
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; node node_modules\next\dist\bin\next dev -p 3000"
Write-Host "Backend : http://localhost:8000/docs  |  Frontend : http://localhost:3000"
