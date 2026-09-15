@echo off
setlocal

cd /d "%~dp0desktop"

if not exist "node_modules" (
    echo Desktop dependencies are missing.
    echo Installing dependencies...
    call npm.cmd install
    if errorlevel 1 (
        echo.
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

echo Starting LLMVoice Studio...
call npm.cmd run tauri dev

if errorlevel 1 (
    echo.
    echo LLMVoice Studio stopped with an error.
    pause
)

endlocal
