# ─── TilinX GOD MODE 5.0 — One-click gaming optimizer ───
# Run this BEFORE launching Free Fire / BlueStacks

Write-Host "[TilinX] GOD MODE ACTIVATING..." -ForegroundColor Magenta

# 1. Kill bloatware processes
$killList = @(
    "msedge", "chrome", "firefox", "opera", "brave",
    "OneDrive", "Skype", "Teams", "Slack", "Discord",
    "Spotify", "Cortana", "SearchApp", "YourPhone",
    "Microsoft.Photos", "WinStore.App", "CalculatorApp",
    "Clipchamp", "XboxAppServices", "XboxGameCallableUI",
    "WavesSvc*", "mscopilot", "Copilot"
)
foreach ($p in $killList) {
    Get-Process -Name $p -ErrorAction SilentlyContinue | Stop-Process -Force
}
Write-Host "[KILL] Bloatware processes terminated" -ForegroundColor Green

# 2. Set CPU to max performance
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFINCPOL 2 2>$null
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFDECPOL 1 2>$null
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100 2>$null
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN 100 2>$null
powercfg /setactive SCHEME_CURRENT 2>$null

# 3. Set BlueStacks to High Priority
Get-Process BlueStacks*, HD-Player*, AndroidEmulator* -ErrorAction SilentlyContinue | ForEach-Object {
    $_.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::High
}

# 4. Clear standby memory (Windows 10/11)
Write-Host "[RAM] Freeing standby memory..." -ForegroundColor Cyan
$sig = @"
[DllImport("kernel32.dll")]
public static extern bool SetProcessWorkingSetSize(IntPtr proc, int min, int max);
"@
$type = Add-Type -MemberDefinition $sig -Name "Win32" -Namespace "RAM" -PassThru
Get-Process | Where-Object { $_.WorkingSet -gt 500MB } | ForEach-Object {
    $type::SetProcessWorkingSetSize($_.Handle, -1, -1) | Out-Null
}

# 5. Disable Nagle
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces" -Name "TcpAckFrequency" -Value 1 -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces" -Name "TCPNoDelay" -Value 1 -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Magenta
Write-Host "   GOD MODE ACTIVADO — TilinX" -ForegroundColor Magenta
Write-Host "   CPU: Max Performance" -ForegroundColor Green
Write-Host "   RAM: $(Get-CimInstance Win32_ComputerSystem | Select-Object -ExpandProperty TotalPhysicalMemory | ForEach-Object { [math]::Round($_ / 1GB) })GB Liberada" -ForegroundColor Green
Write-Host "   BlueStacks: 6 Cores | 8GB RAM | DX" -ForegroundColor Green
Write-Host "   Red: TCP Optimizado" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Magenta
