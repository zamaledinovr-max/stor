@echo off
setlocal EnableExtensions

rem Run from the project root regardless of where the file is double-clicked.
cd /d "%~dp0.."

set "REMOTE_URL=%~1"
if "%REMOTE_URL%"=="" (
    set /p "REMOTE_URL=Repository URL (https://github.com/user/repo.git), or leave empty for local git: "
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\init_git.ps1" "%REMOTE_URL%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo Git setup failed with exit code %EXIT_CODE%.
) else (
    echo Git setup finished.
)
pause
exit /b %EXIT_CODE%
