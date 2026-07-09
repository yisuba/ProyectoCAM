@echo off
REM ============================================
REM  Configura el entorno virtual e instala
REM  dependencias para ProyectoPDI
REM ============================================

cd /d "%~dp0"
echo.
echo === Instalando entorno virtual ===

:: Crear entorno virtual si no existe
if not exist "venv\Scripts\python.exe" (
    echo Creando venv...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: No se encuentra Python. Instalalo desde python.org
        pause
        exit /b 1
    )
) else (
    echo venv ya existe
)

:: Activar e instalar dependencias
call venv\Scripts\activate.bat
echo Actualizando pip...
python -m pip install --upgrade pip >nul
echo Instalando dependencias...
pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo.
    echo === Listo! Ejecuta run.bat para iniciar ===
) else (
    echo.
    echo ERROR: fallo la instalacion de dependencias
)

pause
