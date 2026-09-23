@echo off
chcp 65001 >nul
title USTAD GOZCU - harita
cd /d "%~dp0"

echo.
echo   ==================================================
echo       U S T A D   G O Z C U     ~~~ o ~~~
echo                H A R I T A
echo   ==================================================
echo.
echo   Bu kisayol HARITAYI acar (dokuz canli katman).
echo   Giris ekranini acmak icin:  GIRIS.bat
echo.

rem Sunucu calisiyor mu diye bak (port 8811)
powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue).OwningProcess; if($p){exit 0} else {exit 1}"
if errorlevel 1 goto SUNUCU_KAPALI

echo   Sunucu zaten calisiyor, harita aciliyor.
start "" "http://127.0.0.1:8811/index.html"
exit /b 0

:SUNUCU_KAPALI
echo   Sunucu kapali, baslatiliyor...
echo   Bu pencereyi KAPATMAYIN - panel bu sunucudan besleniyor.
echo   Kapatmak icin: Ctrl + C  veya  bu pencereyi kapat.
echo.

start "" /b cmd /c "%SystemRoot%\System32\timeout.exe /t 3 /nobreak >nul & start http://127.0.0.1:8811/index.html"

python sunucu.py 8811

echo.
echo   Sunucu kapandi.
pause
