@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe --version >nul 2>&1
    if not errorlevel 1 set "PY=.venv\Scripts\python.exe"
)
if not defined PY if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe --version >nul 2>&1
    if not errorlevel 1 set "PY=venv\Scripts\python.exe"
)
if not defined PY set "PY=python"

echo [1/5] Using Python: %PY%
%PY% --version || goto :error

echo [2/5] Upgrading pip...
%PY% -m pip install --upgrade pip || goto :error

echo [3/5] Installing dependencies...
%PY% -m pip install -r requirements.txt || goto :error

echo [4/5] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist dist\PCController.exe (
    echo.
    echo Cannot clean old dist\PCController.exe because it is running or locked.
    echo Close PCController.exe and run py-auto-build again.
    exit /b 1
)

echo [5/5] Building one-file executable...
%PY% -m PyInstaller --noconfirm --clean PCController.spec || goto :error

if not exist dist\PCController.exe goto :error

if not exist output mkdir output
copy /Y dist\PCController.exe output\PCController.exe >nul

echo.
echo Build completed successfully.
echo EXE: dist\PCController.exe
echo Copy: output\PCController.exe
exit /b 0

:error
echo.
echo Build failed. See logs above.
exit /b 1
