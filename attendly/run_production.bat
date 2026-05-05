@echo off
echo =========================================
echo Preparing Attendly for Production Server
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

echo Collecting static files...
python manage.py collectstatic --noinput
echo Applying database migrations...
python manage.py migrate
echo Starting Waitress Production Server on all network interfaces (port 8000)...
waitress-serve --listen=0.0.0.0:8000 attendly.wsgi:application
pause