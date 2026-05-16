@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc >nul 2>nul

if not exist ".venv\Scripts\python.exe" (
    echo No virtual environment found. Running setup first...
    call setup.bat
    if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat

set "DEP_CHECK=%TEMP%\ccf_dep_check_%RANDOM%.py"
> "%DEP_CHECK%" echo import importlib.util
>> "%DEP_CHECK%" echo import subprocess
>> "%DEP_CHECK%" echo import sys
>> "%DEP_CHECK%" echo required = {"webview": "pywebview", "qtpy": "qtpy", "PyQt6": "PyQt6", "PIL": "Pillow"}
>> "%DEP_CHECK%" echo missing = [pkg for module, pkg in required.items() if importlib.util.find_spec(module) is None]
>> "%DEP_CHECK%" echo if missing:
>> "%DEP_CHECK%" echo     print("Installing missing dependencies:", ", ".join(missing))
>> "%DEP_CHECK%" echo     subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"])

python "%DEP_CHECK%"
set "DEP_STATUS=%ERRORLEVEL%"
del "%DEP_CHECK%" >nul 2>nul
if not "%DEP_STATUS%"=="0" (
    echo Dependency check failed.
    pause
    exit /b %DEP_STATUS%
)

python app.py
if errorlevel 1 (
    echo.
    echo Character Card Forge closed with an error.
    pause
)
