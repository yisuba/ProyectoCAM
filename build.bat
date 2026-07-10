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

for /f %%i in (VERSION) do set VER=%%i
echo.
echo === Version del proyecto: %VER% ===

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
    echo === Copiando a portable ===
    if not exist "portable" mkdir "portable"
    copy /y "dist\VisorCamara.exe" "portable\VisorCamara v%VER%.exe" >nul
    copy /y "dist\VisorCamara.exe" "portable\VisorCamara.exe" >nul
    echo.
    echo === Listo! ===
    echo.
    echo   - Version: %VER%
    echo   - Ejecutable: dist\VisorCamara.exe
    echo   - Portable:   portable\VisorCamara.exe
    echo                portable\VisorCamara v%VER%.exe
    echo.
    echo Tamanio:
    dir "dist\VisorCamara.exe"
) else (
    echo.
    echo ERROR: fallo la compilacion
)

pause
