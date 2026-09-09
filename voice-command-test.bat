@echo off
setlocal
cd /d "%~dp0"
call "%~dp0setup.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
call "%~dp0setup-stt.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
"%~dp0runtime\python.exe" -m dcs_radio_voice_control.voice_command_test %*
exit /b %ERRORLEVEL%
