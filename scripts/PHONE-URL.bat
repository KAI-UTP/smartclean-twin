@echo off
title SmartClean Twin - Phone Address
color 0B

REM Address discovery is done in PowerShell because parsing ipconfig picks up
REM virtual adapters (WSL, Docker, Mobile Hotspot) that a phone cannot reach,
REM and the order they appear in is not stable.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "Write-Host '';" ^
  "Write-Host '============================================================';" ^
  "Write-Host '   Open the operator console on your phone';" ^
  "Write-Host '============================================================';" ^
  "Write-Host '';" ^
  "$addrs = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' };" ^
  "$best = $null;" ^
  "foreach ($a in $addrs) {" ^
  "  $alias = $a.InterfaceAlias;" ^
  "  $kind = 'other';" ^
  "  if ($alias -like '*Wi-Fi*' -and $alias -notlike '*Direct*') { $kind = 'wifi' }" ^
  "  elseif ($alias -like '*Local Area Connection*' -or $a.IPAddress -eq '192.168.137.1') { $kind = 'hosted' }" ^
  "  elseif ($alias -like '*vEthernet*' -or $alias -like '*WSL*' -or $alias -like '*Docker*') { $kind = 'virtual' }" ^
  "  elseif ($alias -like '*Ethernet*') { $kind = 'lan' }" ^
  "  $label = switch ($kind) {" ^
  "    'wifi'    { 'WiFi or phone hotspot the laptop joined  <== USE THIS' }" ^
  "    'hosted'  { 'this laptop is sharing its own hotspot' }" ^
  "    'lan'     { 'wired network' }" ^
  "    'virtual' { 'virtual adapter, a phone cannot reach this' }" ^
  "    default   { '' } };" ^
  "  if ($kind -eq 'virtual') { continue }" ^
  "  Write-Host ('   http://' + $a.IPAddress + ':8005') -NoNewline;" ^
  "  Write-Host ('   ' + $label);" ^
  "  if ($kind -eq 'wifi' -and -not $wifi) { $wifi = $a.IPAddress }" ^
  "  if ($kind -eq 'hosted' -and -not $hosted) { $hosted = $a.IPAddress }" ^
  "  if ($kind -eq 'lan' -and -not $lan) { $lan = $a.IPAddress } };" ^
  "if ($wifi) { $best = $wifi } elseif ($hosted) { $best = $hosted } else { $best = $lan };" ^
  "Write-Host '';" ^
  "if (-not $best) { Write-Host '   No usable address found. Is WiFi connected?'; exit }" ^
  "Write-Host '------------------------------------------------------------';" ^
  "try { $h = Invoke-WebRequest ('http://' + $best + ':8005/health') -UseBasicParsing -TimeoutSec 8;" ^
  "      Write-Host ('   console reachable on ' + $best + '  (HTTP ' + $h.StatusCode + ')') }" ^
  "catch { Write-Host '   The console did NOT answer on that address.';" ^
  "        Write-Host '   Usually the Windows firewall treating the network as Public.';" ^
  "        Write-Host '   Settings > Network > WiFi > (network) > Private' };" ^
  "$code = 0;" ^
  "try { Invoke-WebRequest ('http://' + $best + ':8005/api/state') -UseBasicParsing -TimeoutSec 8 | Out-Null; $code = 200 }" ^
  "catch { $code = [int]$_.Exception.Response.StatusCode };" ^
  "Write-Host '';" ^
  "if ($code -eq 401) {" ^
  "  Write-Host '   A PASSWORD IS SET. Sign in on the phone as: operator';" ^
  "  Write-Host '   To remove it, run in the smartclean-twin folder:';" ^
  "  Write-Host '      docker compose up -d --force-recreate web-control' }" ^
  "else { Write-Host '   No password set. The console opens straight away.' };" ^
  "Write-Host '';"

echo  Using a phone hotspot:
echo    1. Phone: turn on Personal Hotspot
echo    2. Laptop: connect to it in the WiFi menu
echo    3. Run this file again, the address will have changed
echo.
echo  No mobile data is used. Everything runs on this laptop, the
echo  hotspot is only being used as a local network.
echo.
echo ============================================================
pause
