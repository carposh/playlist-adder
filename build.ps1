# Builds dist\PlaylistAdder\ (PyInstaller) and dist\PlaylistAdder-Setup.exe (Inno Setup).
# Needs: .venv with requirements.txt + pyinstaller, and Inno Setup 6.
# Not "Stop": Windows PowerShell 5.1 treats PyInstaller's progress output on stderr as an error.
# Each tool's exit code is checked instead.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$pyiArgs = @("--noconfirm", "--clean", "--windowed", "--name", "PlaylistAdder",
             "--icon", "icon.ico", "--add-data", "icon.ico;.")
# Ship the pictures captured on this PC as the installed app's starting set.
if (Test-Path "templates\*") { $pyiArgs += @("--add-data", "templates;default_templates") }
& .\.venv\Scripts\pyinstaller @pyiArgs app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }
# Inno Setup can't read files past the 260-character path limit, so stage the app in a short path.
$stage = Join-Path $env:TEMP "PlaylistAdderStage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
Copy-Item -Recurse "dist\PlaylistAdder" $stage
& $iscc /Q "/DSourceDir=$stage" installer.iss
Remove-Item -Recurse -Force $stage
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Built dist\PlaylistAdder-Setup.exe"
