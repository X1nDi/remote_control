@echo off
setlocal
cd /d "%~dp0"
call py-auto-build.bat
exit /b %errorlevel%
