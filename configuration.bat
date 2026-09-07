@echo off
setlocal
cd /d "%~dp0"
call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
set PYGAME_HIDE_SUPPORT_PROMPT=1
"%~dp0runtime\python.exe" -m combatai.configuration_ui %*
exit /b %ERRORLEVEL%
