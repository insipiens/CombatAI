@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
"%~dp0runtime\python.exe" "%~dp0tools\install.py" install %*
exit /b %ERRORLEVEL%
