@echo off
REM ============================================
REM  Inicia la aplicacion de camara
REM ============================================

cd /d "%~dp0"

:: Verificar que el venv existe
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Ejecuta primero setup.bat para instalar las dependencias
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py
pause
