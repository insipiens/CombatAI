@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
rem START /WAIT keeps cmd.exe from treating the handled Ctrl+C as an aborted
rem batch file and asking "Terminate batch job (Y/N)?" afterwards.
start "" /b /wait "%~dp0runtime\python.exe" -m dcs_radio_voice_control.launcher %*
exit /b %ERRORLEVEL%
