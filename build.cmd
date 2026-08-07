@echo off
REM Build a standalone PDFImageMerger.exe for Windows via PyInstaller.
REM Run this from a plain Windows cmd.exe / PowerShell prompt -- no Git Bash,
REM no WSL needed (build.sh is the Linux/AppImage counterpart of this file;
REM PyInstaller does not cross-compile, so each OS builds its own artifact).
REM
REM Usage:  build.cmd

setlocal enabledelayedexpansion
cd /d "%~dp0"

set APP_NAME=PDFImageMerger

echo.
echo ==^> Cerco un interprete Python
where python >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON=py
    ) else (
        echo ERRORE: nessun python/py trovato nel PATH. Installa Python da https://python.org e riprova.
        exit /b 1
    )
)
echo Uso: %PYTHON%

echo.
echo ==^> Installo le dipendenze (pip install -r requirements.txt + pyinstaller)
%PYTHON% -m pip install --quiet --upgrade pip
if errorlevel 1 goto :pip_error
%PYTHON% -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :pip_error
%PYTHON% -m pip install --quiet pyinstaller
if errorlevel 1 goto :pip_error
goto :deps_ok

:pip_error
echo ERRORE: installazione delle dipendenze fallita. Controlla la connessione e riprova.
exit /b 1

:deps_ok
echo.
echo ==^> Rigenero l'icona (assets\icon.png + assets\icon.ico)
%PYTHON% assets\generate_icon.py
if errorlevel 1 (
    echo ERRORE: generazione icona fallita.
    exit /b 1
)

echo.
echo ==^> Eseguo PyInstaller (build monolitica, puo' richiedere qualche minuto)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PYTHON% -m PyInstaller --noconfirm --clean pdfimagemerger.spec
if errorlevel 1 (
    echo ERRORE: PyInstaller ha fallito.
    exit /b 1
)

if not exist "dist\%APP_NAME%.exe" (
    echo ERRORE: build completata ma dist\%APP_NAME%.exe non e' stato trovato.
    exit /b 1
)

echo.
echo ==^> Fatto: dist\%APP_NAME%.exe
for %%F in ("dist\%APP_NAME%.exe") do echo     Dimensione: %%~zF byte

echo.
echo NOTA: pywebview usa qui il backend nativo WebView2 (nessun Qt incluso).
echo Se al primo avvio manca una DLL, vedi il README (sezione Build) per la
echo procedura di ripristino manuale di WebView2Loader.dll.

endlocal
