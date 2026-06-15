Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   TilinX Proxy + Web Dashboard" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$BASE = "C:\Users\Chichi\Downloads\TilinX"
$WIN = "C:\Users\Chichi\Downloads\TilinX_Proxy_Windows"
$LOGS = "$WIN\logs"

if (-not (Test-Path $LOGS)) { New-Item -ItemType Directory -Path $LOGS -Force | Out-Null }

# Kill old processes
Get-Process -Name "mitmweb", "mitmproxy", "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "mitmweb|8884|app.py" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# ─── 1. Proxy (mitmweb on 8884) ───
Write-Host "[1/2] Starting mitmweb proxy on :8884 ..." -ForegroundColor Yellow
$env:TilinX_BASE_DIR = $WIN
$env:TilinX_DB_PATH = "$WIN\uids.json"
$env:TilinX_LOG_DIR = $LOGS
$env:TilinX_DATA_DIR = "$WIN\data\HUNTER"
$env:TilinX_ENV = "development"

$proxyJob = Start-Job -ScriptBlock {
    param($win)
    $env:TilinX_BASE_DIR = $win
    $env:TilinX_DB_PATH = "$win\uids.json"
    $env:TilinX_LOG_DIR = "$win\logs"
    $env:TilinX_DATA_DIR = "$win\data\HUNTER"
    mitmweb --listen-port 9999 -s "$win\tilinx_proxy.py" --set block_global=false 2>&1
} -ArgumentList $WIN

# ─── 2. Web Dashboard (Flask on 8080) ───
Write-Host "[2/2] Starting web dashboard on :8080 ..." -ForegroundColor Yellow
$env:TilinX_BASE_DIR = $BASE
$env:TilinX_DB_PATH = "$BASE\ips.json"
$env:TilinX_LOG_DIR = "$BASE\logs"
$env:TilinX_WEB_PORT = "8080"

$webJob = Start-Job -ScriptBlock {
    param($base)
    Set-Location -LiteralPath $base
    $env:TilinX_BASE_DIR = $base
    $env:TilinX_DB_PATH = "$base\ips.json"
    $env:TilinX_LOG_DIR = "$base\logs"
    $env:TilinX_WEB_PORT = "8080"
    python "$base\website\app.py" 2>&1
} -ArgumentList $BASE

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   TilinX RUNNING" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Proxy : http://localhost:9999" -ForegroundColor White
Write-Host "   Web   : https://localhost:8080" -ForegroundColor White
Write-Host "   Web   : https://localhost:8080 (LAN)" -ForegroundColor White
Write-Host "   Tunnel: bore.pub:31028 (proxy)" -ForegroundColor White
Write-Host ""
Write-Host "   mitmweb UI: http://localhost:9999" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Stop: Get-Job | Stop-Job; Get-Process mitmweb | Stop-Process" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Green

while ($true) {
    $proxyRunning = Get-Job -Id $proxyJob.Id -ErrorAction SilentlyContinue | Where-Object State -eq "Running"
    $webRunning = Get-Job -Id $webJob.Id -ErrorAction SilentlyContinue | Where-Object State -eq "Running"
    
    if (-not $proxyRunning) { Write-Host "[!] Proxy stopped!" -ForegroundColor Red }
    if (-not $webRunning) { Write-Host "[!] Web dashboard stopped!" -ForegroundColor Red }
    if (-not $proxyRunning -and -not $webRunning) { break }
    
    Start-Sleep -Seconds 10
}
