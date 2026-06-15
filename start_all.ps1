# TilinX — Start All Services
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   TilinX — Starting All Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$BASE = "C:\Users\Chichi\Downloads\TilinX"
$WIN  = "C:\Users\Chichi\Downloads\TilinX_Proxy_Windows"
$LOGS = "$WIN\logs"
$TEMP = $env:TEMP

# Ensure log dir
if (-not (Test-Path $LOGS)) { New-Item -ItemType Directory -Path $LOGS -Force | Out-Null }

# Kill old
Get-Process -Name "mitmweb", "python*", "bore" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "[1/3] Starting mitmweb proxy on :9999 ..." -ForegroundColor Yellow
$env:TilinX_BASE_DIR = $WIN
$env:TilinX_DB_PATH = "$WIN\uids.json"
$env:TilinX_LOG_DIR = $LOGS
$env:TilinX_DATA_DIR = "$WIN\data\HUNTER"
Start-Process -FilePath "mitmweb" -ArgumentList "--listen-port 9999 -s `"$WIN\tilinx_proxy.py`" --set block_global=false" -WindowStyle Hidden

Write-Host "[2/3] Starting web dashboard on :8080 HTTPS ..." -ForegroundColor Yellow
$env:TilinX_BASE_DIR = $BASE
$env:TilinX_DB_PATH = "$BASE\ips.json"
$env:TilinX_LOG_DIR = "$BASE\logs"
$env:TilinX_WEB_PORT = "8080"
Start-Process -FilePath "python" -ArgumentList "$BASE\website\app.py" -WorkingDirectory $BASE -WindowStyle Hidden

Write-Host "[3/3] Starting bore tunnel (proxy -> bore.pub) ..." -ForegroundColor Yellow
$boreExe = "$TEMP\bore\bore.exe"
if (Test-Path $boreExe) {
    Start-Process -FilePath $boreExe -ArgumentList "local 9999 --to bore.pub" -WindowStyle Hidden
} else {
    Write-Host "[!] bore.exe not found at $boreExe" -ForegroundColor Red
}

Start-Sleep -Seconds 8

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   TilinX RUNNING" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Proxy : http://localhost:9999" -ForegroundColor White
Write-Host "   Web   : https://localhost:8080" -ForegroundColor White
Write-Host "   Tunnel: bore.pub:31028 (proxy)" -ForegroundColor White
Write-Host ""
Write-Host "   Dashboard pass: (see .env TilinX_DASH_PASSWORD)" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Green

# Keep window open if double-clicked
if ($host.Name -like "*ISE*") { } else {
    Write-Host "`nPress any key to close..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
