@echo off
chcp 65001 >nul
title USTAD GOZCU
cd /d "%~dp0"

echo.
echo   ==================================================
echo       U S T A D   G O Z C U     ~~~ o ~~~
echo           Gozcu hic kirpmaz.
echo   ==================================================
echo.
echo   Giris ekrani birazdan tarayicida acilacak. (Harita icin HARITA.bat)
echo   Bu pencereyi KAPATMAYIN - panel bu sunucudan besleniyor.
echo   Kapatmak icin: Ctrl + C  veya  bu pencereyi kapat.
echo.

start "" /b cmd /c "%SystemRoot%\System32\timeout.exe /t 3 /nobreak >nul & start http://127.0.0.1:8811/giris.html"

python sunucu.py 8811

echo.
echo   Sunucu kapandi.
pause
