@echo off
REM ============================================================
REM  Build a standalone .exe with PyInstaller
REM ============================================================
REM  Requires: pyinstaller  (pip install pyinstaller)
REM ============================================================

cd /d "%~dp0"

echo === Verificando PyInstaller ===
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo PyInstaller no esta instalado.
    echo Ejecuta:  pip install pyinstaller
    echo.
    pause
    exit /b 1
)

echo === Limpiando builds anteriores ===
if exist "dist"  rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo === Compilando .exe ===
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "VisorCamara" ^
    --manifest "visor-camara.manifest" ^
    --add-data "visor-camara.manifest;." ^
    --hidden-import "PIL" ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "camara" ^
    --hidden-import "camara.device" ^
    --hidden-import "camara.stream" ^
    --hidden-import "interfaz" ^
    --hidden-import "interfaz.app" ^
    --hidden-import "interfaz.viewer" ^
    --collect-submodules "camara" ^
    --collect-submodules "interfaz" ^
    main.py

if %errorlevel% equ 0 (
    echo.
    echo === Copiando a portable\VisorCamara.exe ===
    if not exist "portable" mkdir "portable"
    copy /y "dist\VisorCamara.exe" "portable\VisorCamara.exe" >nul
    echo.
    echo === Listo! ===
    echo.
    echo   - Ejecutable: dist\VisorCamara.exe
    echo   - Portable:   portable\VisorCamara.exe
    echo.
    echo Tamanio:
    dir "dist\VisorCamara.exe"
) else (
    echo.
    echo ERROR: fallo la compilacion
)

pause
