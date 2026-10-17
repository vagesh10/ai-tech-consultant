$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$python = Join-Path $root "task1-knowledge-brain\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python environment not found: $python"
}

$task1 = Join-Path $root "task1-knowledge-brain"
$task2 = Join-Path $root "task2-inbox-agent"
$task3 = Join-Path $root "task3-meeting-to-sow"

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$task1'; & '$python' -m uvicorn app.api.server:app --reload --port 8000"
)

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$task2'; npm run dev"
)

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$task3'; & '$python' -m uvicorn app.main:app --reload --port 8002"
)

Write-Host "Started the three API processes."
Write-Host "Task 1: http://127.0.0.1:8000/health"
Write-Host "Task 2: http://127.0.0.1:3001/health"
Write-Host "Task 3: http://127.0.0.1:8002/health"
