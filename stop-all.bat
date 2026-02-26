@echo off
REM GetContact AI Agent - Stop All Services

echo ========================================
echo GetContact AI Agent - Stopping All Services
echo ========================================
echo.

echo [1/3] Stopping WhatsApp Service (Port 3100)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3100') do (
    taskkill /F /PID %%a 2>nul
    if not errorlevel 1 (
        echo Killed process %%a
    )
)

echo [2/3] Stopping Orchestrator (Port 8000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    taskkill /F /PID %%a 2>nul
    if not errorlevel 1 (
        echo Killed process %%a
    )
)

echo [3/3] Stopping Frontend (Port 5173)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173') do (
    taskkill /F /PID %%a 2>nul
    if not errorlevel 1 (
        echo Killed process %%a
    )
)

echo.
echo ========================================
echo All services stopped!
echo ========================================
pause
