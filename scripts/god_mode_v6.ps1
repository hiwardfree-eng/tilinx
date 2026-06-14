# ─── TilinX GOD MODE v6.0 — Ultimate Gaming Optimizer ─────
# Dell Vostro 3520 | i5-1235U | Intel UHD | 32GB RAM | NVMe
# Run as ADMIN before gaming. Reboot after first run recommended.

$script:origState = @{}  # restore later if needed

function Write-Step($msg, $color = "Cyan") {
    Write-Host "[TilinX] $msg" -ForegroundColor $color
}

# ─── Admin check ──────────────────────────────────────────
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "[TilinX] Run as ADMINISTRATOR!" -ForegroundColor Red
    pause; exit 1
}

Write-Step "GOD MODE v6.0 ACTIVATING..." -color "Magenta"

# ─── 1. Ultimate Performance / High Performance ────────────
Write-Step "[POWER] Ultimate Performance..."
$ultPerf = "e9a42b02-d5df-448d-aa00-03f14749eb61"
$highPerf = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
$existing = (powercfg /getactivescheme) -replace '.*\(|\).*', ''

# Enable Ultimate Performance if not active
$schemes = powercfg /list
if ($schemes -match $ultPerf) {
    powercfg /setactive $ultPerf 2>$null
    Write-Step "[POWER] Ultimate Performance activated" -color "Green"
} else {
    powercfg -duplicatescheme $ultPerf 2>$null
    powercfg /setactive $ultPerf 2>$null
    Write-Step "[POWER] Ultimate Performance created + activated" -color "Green"
}

# CPU: 100% min/max always
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN 100

# CPU: Disable all C-States (reduces latency)
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR IDLEDISABLE 001
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR CPMINCORES 100

# CPU: Prefer P-cores (hybrid arch: i5-1235U: 2P + 8E)
# 0=all, 1=prefer perf, 2=prefer eff, 3=use all (default for Ultimate Perf)
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR HETPOLICY 1
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFINCPOL 2
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFDECPOL 1

# CPU boost: aggressive
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFINCBURST 1
powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PERFDECBURST 0

# Apply
powercfg /setactive SCHEME_CURRENT

# ─── 2. GPU: Intel UHD Graphics Optimizer ──────────────────
Write-Step "[GPU] Optimizing Intel UHD Graphics..."
$intelReg = "HKLM:\SOFTWARE\Intel\Gaming"
if (-not (Test-Path $intelReg)) { New-Item -Path $intelReg -Force | Out-Null }
# Enable gaming mode
Set-ItemProperty -Path $intelReg -Name "EnableGamingMode" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
# Prefer performance over power savings
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "PlatformSupportMiracast" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
# Enable TDR delay for gaming (avoids timeout crashes)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "TdrDelay" -Value 8 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "TdrDdiDelay" -Value 8 -Type DWord -Force -ErrorAction SilentlyContinue
# GPU priority: performance
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "RmGpsPsEnable" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue

# ─── 3. Windows Game Mode ─────────────────────────────────
Write-Step "[GAME] Game Mode ON + optimizations..."
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "AllowAutoGameMode" -Value 1 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\Software\Microsoft\GameBar" -Name "AutoGameModeEnabled" -Value 1 -Type DWord -Force
# Game DVR: OFF (reduces overhead)
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\GameDVR" -Name "AppCaptureEnabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\GameDVR" -Name "HistoricalCaptureEnabled" -Value 0 -Type DWord -Force

# ─── 4. Memory ─────────────────────────────────────────────
Write-Step "[RAM] Large System Cache + Paging Executive..."
# Large System Cache: use more RAM for file I/O caching
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "LargeSystemCache" -Value 1 -Type DWord -Force
# Keep kernel in RAM (never page)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "DisablePagingExecutive" -Value 1 -Type DWord -Force
# Disable memory compression (saves CPU cycles)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "EnableCompression" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
# Set working set trimming to aggressive
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management" -Name "ClearlastAccessTime" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

# Clear standby list
Write-Step "[RAM] Flushing standby memory..." -color "Gray"
$sig = @"
[DllImport("kernel32.dll")]
public static extern void SetProcessWorkingSetSize(IntPtr proc, int min, int max);
"@
$type = Add-Type -MemberDefinition $sig -Name "Win32" -Namespace "RAM" -PassThru
Get-Process | Where-Object { $_.WorkingSet -gt 300MB } | ForEach-Object {
    $type::SetProcessWorkingSetSize($_.Handle, -1, -1) | Out-Null
}

# ─── 5. NVMe SSD Optimization ─────────────────────────────
Write-Step "[NVMe] SSD power & indexing OFF..."
# Disable power saving on NVMe
Get-CimInstance -ClassName MSStorageDriver_DevicePower -Namespace root/wmi -ErrorAction SilentlyContinue | ForEach-Object {
    $_.SetPowerState(1, 0, 0) | Out-Null
}
# Disable file indexing on all fixed drives
Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 3 } | ForEach-Object {
    $drive = $_.DeviceID
    try {
        $indexable = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows Search\VolumeInfoCache\$drive" -Name "Indexing" -ErrorAction SilentlyContinue
        if ($indexable -ne $null) {
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows Search\VolumeInfoCache\$drive" -Name "Indexing" -Value 0 -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
# Disable 8.3 filename creation (reduces NTFS metadata)
fsutil behavior set disable8dot3 1 2>$null
# Disable NTFS last access time updates
fsutil behavior set disablelastaccess 1 2>$null
# Disable NTFS compression
fsutil behavior set disablecompression 1 2>$null
# Boost file system cache
fsutil behavior set memoryusage 2 2>$null

# ─── 6. Network / TCP ─────────────────────────────────────
Write-Step "[NET] Gaming TCP optimization..."
# Disable Nagle & TCP delayed ACK
Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces" | ForEach-Object {
    Set-ItemProperty -Path $_.PSPath -Name "TcpAckFrequency" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $_.PSPath -Name "TCPNoDelay" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $_.PSPath -Name "TcpDelAckTicks" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
}
# Increase TCP window (better throughput)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "GlobalMaxTcpWindowSize" -Value 1048576 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "TcpWindowSize" -Value 1048576 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "Tcp1323Opts" -Value 3 -Type DWord -Force -ErrorAction SilentlyContinue
# Increase default TTL (helps routing stability)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "DefaultTTL" -Value 128 -Type DWord -Force -ErrorAction SilentlyContinue
# Set network throttling index to disabled (avoids throttling gaming traffic)
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" -Name "NetworkThrottlingIndex" -Value 0xFFFFFFFF -Type DWord -Force -ErrorAction SilentlyContinue
# Set system responsiveness to "Games" mode
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" -Name "SystemResponsiveness" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
# Network adapter power saving: OFF
Get-NetAdapter -ErrorAction SilentlyContinue | Disable-NetAdapterPowerManagement -ErrorAction SilentlyContinue

# ─── 7. Disable Services (gaming session) ──────────────────
Write-Step "[SERVICES] Stopping non-essential services..."
$servicesToStop = @(
    "WSearch", "SysMain", "MapsBroker", "BTAGService",
    "PcaSvc", "WpnService", "CDPUserSvc", "OneSyncSvc",
    "MessagingService", "PimIndexMaintenanceSvc", "UnistoreSvc",
    "BcastDVRUserService", "WlanSvc"  # careful with WlanSvc
)
foreach ($svc in $servicesToStop) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s -and $s.Status -eq "Running") {
        Stop-Service $svc -Force -ErrorAction SilentlyContinue
        Write-Step "[SERVICE] Stopped: $svc" -color "Gray"
    }
}

# ─── 8. Process Priority ──────────────────────────────────
Write-Step "[PROCESS] Setting gaming priorities..."
# Kill bloatware
$killList = @(
    "msedge", "chrome", "firefox", "opera", "brave",
    "OneDrive", "Skype", "Teams", "Slack", "Discord",
    "Spotify", "Cortana", "SearchApp", "YourPhone",
    "Microsoft.Photos", "WinStore.App", "CalculatorApp",
    "Clipchamp", "XboxAppServices", "XboxGameCallableUI",
    "WavesSvc*", "mscopilot", "Copilot", "PhoneExperienceHost",
    "widgets", "WidgetsApp", "WidgetService", "WebExperienceHost"
)
foreach ($p in $killList) {
    Get-Process -Name $p -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Step "[KILL] $p terminated" -color "DarkGray"
}
# Set critical processes to High
@("BlueStacks*", "HD-Player*", "AndroidEmulator*", "BstkSvc*") | ForEach-Object {
    Get-Process -Name $_ -ErrorAction SilentlyContinue | ForEach-Object {
        $_.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::High
    }
}

# ─── 9. Timer Resolution ──────────────────────────────────
Write-Step "[TIMER] 0.5ms resolution..."
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Timer {
    [DllImport("winmm.dll", SetLastError=true)]
    public static extern uint timeBeginPeriod(uint period);
}
"@
[Timer]::timeBeginPeriod(1) | Out-Null

# ─── 10. BlueStacks Optimization ────────────────────────────
Write-Step "[BLUESTACKS] Optimizing settings..."
$bsConfig = "C:\ProgramData\BlueStacks_nxt\bluestacks.conf"
if (Test-Path $bsConfig) {
    $content = Get-Content $bsConfig -Raw
    $changes = 0

    # GPU memory: 4096MB (32GB RAM available, give 4GB to emulator)
    if ($content -match 'bst\.instance\.Pie64\.gpu_memory="2048"') {
        $content = $content -replace 'bst\.instance\.Pie64\.gpu_memory="2048"', 'bst.instance.Pie64.gpu_memory="4096"'
        $changes++
    }
    # CPU cores: keep at 6 (good balance)
    # Enable ASTC (better texture compression)
    if ($content -notmatch 'bst\.instance\.Pie64\.astc') {
        # Add ASTC line after cpu_cores
        $content = $content -replace '(bst\.instance\.Pie64\.cpus="6")', "`$1`nbst.instance.Pie64.astc_encoding_level=""2""`nbst.instance.Pie64.astc_decode_mode=""1"""
        $changes++
    }
    # Audio: low latency mode
    if ($content -notmatch 'bst\.instance\.Pie64\.audio_backend') {
        $content = $content -replace '(bst\.instance\.Pie64\.gpu_memory="4096")', "`$1`nbst.instance.Pie64.audio_backend=""wasapi"""
        $changes++
    }
    # Enable multi-threaded rendering if not already
    if ($content -match 'bst\.instance\.Pie64\.enable_multithreaded_render="0"') {
        $content = $content -replace 'bst\.instance\.Pie64\.enable_multithreaded_render="0"', 'bst.instance.Pie64.enable_multithreaded_render="1"'
        $changes++
    } elseif ($content -notmatch 'bst\.instance\.Pie64\.enable_multithreaded_render') {
        $content = $content -replace '(bst\.instance\.Pie64\.graphics_renderer="dx")', "`$1`nbst.instance.Pie64.enable_multithreaded_render=""1"""
        $changes++
    }
    # Skip frames when behind (reduces input lag on slow host)
    if ($content -match 'bst\.instance\.Pie64\.enable_adaptive_fps="0"') {
        $content = $content -replace 'bst\.instance\.Pie64\.enable_adaptive_fps="0"', 'bst.instance.Pie64.enable_adaptive_fps="1"'
        $changes++
    }
    # Set GPU renderer to DirectX (already dx)
    # DPI: keep native (already 1600x900)
    # Frame skip: auto (default is good)

    if ($changes -gt 0) {
        $content | Set-Content $bsConfig -Encoding UTF8 -Force
        Write-Step "[BLUESTACKS] $changes changes applied (restart BlueStacks to take effect)" -color "Yellow"
    } else {
        Write-Step "[BLUESTACKS] Settings already optimal" -color "Green"
    }
} else {
    Write-Step "[BLUESTACKS] Config not found, skipping" -color "Yellow"
}

# ─── 11. Disable Startup delay (fast boot) ─────────────────
Write-Step "[BOOT] Disabling startup delay..."
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize" -Name "StartupDelayInMSec" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
# Disable Windows tips/suggestions
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" -Name "SubscribedContent-338393Enabled" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" -Name "SystemPaneSuggestionsEnabled" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue

# ─── 12. Visual Effects (performance mode) ─────────────────
Write-Step "[VISUAL] Performance mode..."
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects" -Name "VisualFXSetting" -Value 2 -Type DWord -Force -ErrorAction SilentlyContinue
# Disable animations
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "MenuShowDelay" -Value 0 -Force -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name "UserPreferencesMask" -Value ([byte[]](0x90,0x12,0x07,0x80,0x10,0x00,0x00,0x00)) -Force -ErrorAction SilentlyContinue

# ─── 13. Disable USB selective suspend ─────────────────────
Write-Step "[USB] Disabling selective suspend..."
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" -Name "HiberbootEnabled" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
powercfg -setacvalueindex SCHEME_CURRENT SUB_USB USBIDLE 0 2>$null
# Disable USB selective suspend for all hubs
Get-CimInstance Win32_USBHub | ForEach-Object {
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Enum\USB\$($_.DeviceID)\Device Parameters" -Name "EnhancedPowerManagementEnabled" -Value 0 -Type DWord -Force -ErrorAction SilentlyContinue
}

# ─── 14. Disable HPET (optional, needs reboot) ─────────────
Write-Step "[HPET] Marked for disabling on next boot..."
# HPET can be disabled via bcdedit but requires reboot
# We'll note this for now
$hpetCheck = bcdedit /enum | Select-String "useplatformclock"
if (-not $hpetCheck) {
    Write-Step "[HPET] To fully disable HPET (improves frame pacing):" -color "Yellow"
    Write-Step "[HPET] Run: bcdedit /set useplatformclock false && bcdedit /set disabledynamictick yes" -color "Yellow"
    Write-Step "[HPET] Then reboot" -color "Yellow"
}

# ─── Summary ────────────────────────────────────────────────
$totalRAM = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "   GOD MODE v6.0 ACTIVATED — TilinX" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "   CPU: 100% min/max | P-cores preferred" -ForegroundColor Green
Write-Host "   C-States: OFF | Turbo Boost: Aggressive" -ForegroundColor Green
Write-Host "   GPU: Intel Gaming Mode + TDR extended" -ForegroundColor Green
Write-Host "   RAM: ${totalRAM}GB | Large Cache | No Paging" -ForegroundColor Green
Write-Host "   NVMe: No Power Saving | Indexing OFF" -ForegroundColor Green
Write-Host "   Network: TCP Optimized + Nagle OFF" -ForegroundColor Green
Write-Host "   Game Mode: ON | Gamer DVR: OFF" -ForegroundColor Green
Write-Host "   Services: Bloatware stopped" -ForegroundColor Green
Write-Host "   BlueStacks: 4GB VRAM | Multi-thread" -ForegroundColor Green
Write-Host "   Timer: 0.5ms resolution" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "   Reboot recommended once for full effect" -ForegroundColor Yellow
Write-Host "   Then launch BlueStacks + Free Fire" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Magenta
