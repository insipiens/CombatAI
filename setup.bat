@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Setting up CombatAI private Python and SDL support...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [2/3] Setting up local Whisper speech recognition...
call "%~dp0setup-stt.bat"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [3/3] Setting up Piper speech output...
call "%~dp0setup-tts.bat"
if errorlevel 1 exit /b %ERRORLEVEL%

echo CombatAI setup is complete.
exit /b 0
