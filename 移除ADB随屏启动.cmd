@echo off
chcp 65001 >nul
set PYTHONUTF8=1
"%~dp0tools\python\python.exe" "%~dp0scripts\adb_autostart.py" remove
pause
