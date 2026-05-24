$ErrorActionPreference = 'SilentlyContinue'

Write-Host '=== Stopping TradingAgents-CN ===' -ForegroundColor Cyan

$stopped = 0

# Kill backend: python -m app
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'python.*-m\s+app' } | ForEach-Object {
    Write-Host "Stopping backend (PID $($_.ProcessId))..." -ForegroundColor Yellow
    # Kill children first (uvicorn workers)
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $_.ProcessId } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }
    Stop-Process -Id $_.ProcessId -Force
    $stopped++
}

# Kill frontend: cmd /c yarn dev -> node (vite)
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'yarn\s+dev' } | ForEach-Object {
    $cmdPid = $_.ProcessId
    Write-Host "Stopping frontend cmd (PID $cmdPid)..." -ForegroundColor Yellow
    # Kill child node processes spawned by yarn
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $cmdPid } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }
    Stop-Process -Id $cmdPid -Force
    $stopped++
}

# Also catch orphan node processes with vite in their command line
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite'
} | ForEach-Object {
    Write-Host "Stopping orphan vite process (PID $($_.ProcessId))..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force
    $stopped++
}

if ($stopped -eq 0) {
    Write-Host 'No running TradingAgents services found.' -ForegroundColor Gray
} else {
    Write-Host "Stopped $stopped process group(s)." -ForegroundColor Green
}
