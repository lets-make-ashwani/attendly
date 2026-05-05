@echo off
echo =========================================
echo Starting Attendly Development Server
echo =========================================

:: Automatically switch to the exact folder where this script is located
cd /d "%~dp0"

:: Automatically activate the virtual environment
if exist "venv\Scripts\activate.bat" (
    echo Activating Virtual Environment...
    call venv\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment 'venv' not found. Ensure it is created in this folder.
)

echo Starting server...
python manage.py runserver 0.0.0.0:8000
pause