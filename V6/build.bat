@echo off
echo ======================================
echo   Gerando executavel - Second Screen
echo ======================================
echo.

echo [1/3] Instalando dependencias...
pip install pillow av sounddevice numpy pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ERRO: Falha ao instalar dependencias!
    pause
    exit /b 1
)

echo [2/3] Criando executavel...
pyinstaller --noconfirm --onefile --windowed ^
    --name "SecondScreen" ^
    --strip ^
    --collect-all av ^
    --collect-all sounddevice ^
    second_screen_controller.py

if %errorlevel% neq 0 (
    echo ERRO: Falha ao criar executavel!
    pause
    exit /b 1
)

echo [3/3] Limpeza...
rmdir /s /q build 2>nul
del /q *.spec 2>nul

echo.
echo ======================================
echo   Pronto! Executavel em: dist\SecondScreen.exe
echo ======================================
echo   Copie o arquivo para o PC de destino
echo   Nao e necessario instalar o VLC
echo ======================================
echo.
pause
