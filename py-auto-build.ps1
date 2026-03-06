$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$python = "python"
if (Test-Path ".venv\Scripts\python.exe") {
    try {
        & ".venv\Scripts\python.exe" --version *> $null
        $python = ".venv\Scripts\python.exe"
    }
    catch {
    }
}

if ($python -eq "python" -and (Test-Path "venv\Scripts\python.exe")) {
    try {
        & "venv\Scripts\python.exe" --version *> $null
        $python = "venv\Scripts\python.exe"
    }
    catch {
    }
}

Write-Host "[1/5] Using Python: $python"
& $python --version

Write-Host "[2/5] Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "[3/5] Installing dependencies..."
& $python -m pip install -r requirements.txt

Write-Host "[4/5] Cleaning previous build artifacts..."
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path "dist\\PCController.exe") {
    throw "Cannot clean dist\\PCController.exe because it is running or locked. Close app and retry."
}

Write-Host "[5/5] Building one-file executable..."
& $python -m PyInstaller --noconfirm --clean PCController.spec

if (-not (Test-Path "dist\PCController.exe")) {
    throw "dist\PCController.exe was not created"
}

if (-not (Test-Path output)) { New-Item -Path output -ItemType Directory | Out-Null }
Copy-Item -Path "dist\PCController.exe" -Destination "output\PCController.exe" -Force

Write-Host ""
Write-Host "Build completed successfully."
Write-Host "EXE: dist\PCController.exe"
Write-Host "Copy: output\PCController.exe"
