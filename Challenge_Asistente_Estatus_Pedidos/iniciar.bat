@echo off
REM ===============================================================
REM  Challenge: Asistente de Estatus de Pedidos
REM  Servidor local local: Ollama (PC) + WhatsApp Cloud API (servidor local)
REM ===============================================================
setlocal

cd /d "%~dp0"

echo ==============================================================
echo  Iniciando prueba local completa...
echo ==============================================================

REM 1. Verificar Ollama
echo [1/4] Verificando Ollama...
powershell -NoProfile -Command "try { $v = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 5; Write-Host ('      Ollama OK - version ' + $v.version) } catch { Write-Host '      ERROR: Ollama no responde en 127.0.0.1:11434' -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo.
    echo Arranca Ollama antes de continuar.
    exit /b 1
)

REM 2. Instalar dependencias
echo [2/4] Instalando dependencias...
python -m pip install --disable-pip-version-check -q -r requirements.txt

REM 3. Levantar los dos servidores
echo [3/4] Levantando servidor del asistente y servidor local de Meta...
start "Asistente-Pedidos" /min python src\servidor.py
timeout /t 6 /nobreak >nul

REM 4. Prueba extremo a extremo
echo [4/4] Ejecutando prueba extremo a extremo...
python src\cliente_prueba.py

echo.
echo Resultados en: resultados\
echo Para detener los servidores: cierra la ventana "Asistente-Pedidos"

endlocal
