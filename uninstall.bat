@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0runtime\python.exe" (
  echo CombatAI uninstall failed: the private runtime is missing, so the DCS hook cannot be verified and restored safely. 1>&2
  exit /b 1
)

"%~dp0runtime\python.exe" "%~dp0tools\install.py" uninstall --purge %*
if errorlevel 1 exit /b %ERRORLEVEL%

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\purge-local.ps1" -ProjectRoot "%~dp0."
if errorlevel 1 exit /b %ERRORLEVEL%

echo CombatAI uninstall is complete. The source folder can now be deleted.
exit /b 0
