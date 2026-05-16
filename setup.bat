@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc >nul 2>nul

echo Character Card Forge - Windows setup

echo Checking for Python...
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
    ) else (
        echo Python 3.10 or newer was not found.
        echo Install Python from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

if not exist ".venv" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo Setup failed while installing dependencies.
    pause
    exit /b 1
)

echo.
echo Setup complete.
echo Run start.bat to launch Character Card Forge.
pause
