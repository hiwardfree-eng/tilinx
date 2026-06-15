$token = "247fe09b-4be4-4d21-be9f-9b6cd1ee356a"
$domain = "tilinxproxy"
$log = "$PSScriptRoot\..\logs\duckdns.log"

try {
    $ip = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing).Content
    $url = "https://duckdns.org/update/$domain/$token/$ip"
    $r = (Invoke-WebRequest -Uri $url -UseBasicParsing).Content
    $msg = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') IP=$ip DuckDNS=$r"
    Write-Output $msg
    Add-Content -Path $log -Value $msg
} catch {
    $err = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ERROR: $_"
    Write-Output $err
    Add-Content -Path $log -Value $err
}
