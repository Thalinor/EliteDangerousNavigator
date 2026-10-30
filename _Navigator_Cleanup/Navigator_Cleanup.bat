@echo off
rem Navigator suite: one-time cleanup of the plugin folders used before 30 October 2026.
rem Double-click with EDMC closed. Moves old folders to plugins\_Navigator_old_backup; deletes nothing.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Navigator_Cleanup.ps1" %*
echo.
pause
