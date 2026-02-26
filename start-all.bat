@echo off
REM GetContact AI Agent - Start All Services
REM Opens 3 separate windows for each service

echo ========================================
echo GetContact AI Agent - Starting All Services
echo ========================================
echo.

echo [1/3] Starting WhatsApp Service (Port 3100)...
start "WhatsApp Service" cmd /k "cd /d F:\Programming\GetContactAIAgent\whatsapp-service && npm run dev"

timeout /t 3 /nobreak >nul

echo [2/3] Starting Orchestrator (Port 8000)...
start "Orchestrator" cmd /k "cd /d F:\Programming\GetContactAIAgent && python -m uvicorn orchestrator.main:app --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [3/3] Starting Frontend (Port 5173)...
start "Frontend" cmd /k "cd /d F:\Programming\GetContactAIAgent\frontend && npm run dev"

timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo All services started!
echo ========================================
echo.
echo Services:
echo   - WhatsApp Service: http://localhost:3100
echo   - Orchestrator:      http://localhost:8000
echo   - Frontend:          http://localhost:5173
echo.
echo Next steps:
echo   1. Scan QR code in "WhatsApp Service" window
echo   2. Open http://localhost:5173 in browser
echo.
pause
