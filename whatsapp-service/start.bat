@echo off
REM WhatsApp Service Startup Script
REM Auto-restart on exit

:loop
echo Starting WhatsApp Service...
echo Press CTRL+C to stop
echo.

npm run dev

echo.
echo WhatsApp Service stopped. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul

goto loop
