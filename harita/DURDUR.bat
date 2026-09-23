@echo off
chcp 65001 >nul
title USTAD GOZCU - durdur
powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue).OwningProcess; if($p){Stop-Process -Id $p -Force -ErrorAction SilentlyContinue; Write-Host '  Gozcu durduruldu.'} else {Write-Host '  Calisan Gozcu sunucusu yok.'}"
%SystemRoot%\System32\timeout.exe /t 3 /nobreak >nul
