$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Write-Host '=== TradingAgents-CN ===' -ForegroundColor Cyan

$nodeModules = Join-Path $root 'frontend\node_modules'
if (-not (Test-Path $nodeModules)) {
    Write-Host '[0/2] Installing frontend deps...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'frontend')
    yarn install
    Pop-Location
}

Write-Host '[1/2] Starting backend (port 8010)...' -ForegroundColor Yellow
$backend = Start-Process -FilePath 'python' -ArgumentList '-m app' -WorkingDirectory $root -PassThru

Write-Host 'Waiting for backend...' -ForegroundColor Gray
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri 'http://localhost:8010/api/health' -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            Write-Host 'Backend ready!' -ForegroundColor Green
            $ready = $true
            break
        }
    } catch { }
}
if (-not $ready) {
    Write-Host 'Backend timeout, check logs\webapi.log' -ForegroundColor Red
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    exit 1
}

Write-Host '[2/2] Starting frontend (port 3010)...' -ForegroundColor Yellow
$frontendDir = Join-Path $root 'frontend'
$frontend = Start-Process -FilePath 'cmd' -ArgumentList '/c yarn dev' -WorkingDirectory $frontendDir -PassThru

Start-Sleep -Seconds 3
Write-Host ''
Write-Host '=== Ready ===' -ForegroundColor Green
Write-Host '  Backend:  http://localhost:8010' -ForegroundColor Cyan
Write-Host '  Frontend: http://localhost:3010' -ForegroundColor Cyan
Write-Host '  API Docs: http://localhost:8010/docs' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Press Ctrl+C to stop' -ForegroundColor Gray

function Stop-ChildProcesses {
    param([int]$ProcessId)
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId } | ForEach-Object {
        Stop-ChildProcesses -ProcessId $_.ProcessId
        Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    }
}

while ($true) {
    Start-Sleep -Seconds 5
    $bAlive = Get-Process -Id $backend.Id -ErrorAction SilentlyContinue
    $fAlive = Get-Process -Id $frontend.Id -ErrorAction SilentlyContinue
    if (-not $bAlive -and -not $fAlive) { break }
    if (-not $bAlive) {
        Write-Host 'Backend exited, stopping frontend...' -ForegroundColor Yellow
        Stop-ChildProcesses -ProcessId $frontend.Id
        Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue
        break
    }
    if (-not $fAlive) {
        Write-Host 'Frontend exited, stopping backend...' -ForegroundColor Yellow
        Stop-ChildProcesses -ProcessId $backend.Id
        Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
        break
    }
}
Write-Host 'Stopped' -ForegroundColor Yellow
