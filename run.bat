@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
"%~dp0runtime\python.exe" -m combatai.launcher %*
exit /b %ERRORLEVEL%
