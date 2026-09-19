# dev.ps1 - start API (:8000) + dashboard (:3000) in one terminal.
# Usage: .\dev.ps1     Stop: Ctrl+C (kills both process trees)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Kill-Tree([int]$rootPid) {
    $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $rootPid" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty ProcessId)
    foreach ($k in $kids) { Kill-Tree $k }
    Stop-Process -Id $rootPid -Force -ErrorAction SilentlyContinue
}

foreach ($port in 8000, 3000) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "Port $port already in use - stop the old process first" -ForegroundColor Red
        exit 1
    }
}

Write-Host "API -> http://localhost:8000   dashboard -> http://localhost:3000   (Ctrl+C to stop)" -ForegroundColor Cyan

$api = Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "api:app", "--port", "8000", "--reload" `
    -NoNewWindow -PassThru
$web = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory "dashboard" -NoNewWindow -PassThru

$stopped = $false
trap {
    if (-not $stopped) {
        $stopped = $true
        Kill-Tree $api.Id
        Kill-Tree $web.Id
        Write-Host "Stopped" -ForegroundColor Yellow
    }
    exit 1
}

while (-not $api.HasExited -and -not $web.HasExited) {
    Start-Sleep -Milliseconds 500
}

if (-not $stopped) {
    $stopped = $true
    if ($api.HasExited) { Write-Host "API exited (code $($api.ExitCode))" -ForegroundColor Red }
    if ($web.HasExited) { Write-Host "Dashboard exited (code $($web.ExitCode))" -ForegroundColor Red }
    Kill-Tree $api.Id
    Kill-Tree $web.Id
}
exit 1
