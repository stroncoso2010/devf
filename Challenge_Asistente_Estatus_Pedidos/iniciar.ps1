# Inicia la prueba local completa: Ollama (PC) + servidor del asistente + servidor local de Meta
# Uso:  powershell -ExecutionPolicy Bypass -File .\iniciar_prueba local.ps1

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Raiz

Write-Host "=" -NoNewline -ForegroundColor Cyan | Out-Null
Write-Host ("=" * 64) -ForegroundColor Cyan
Write-Host "  Challenge: Asistente de Estatus de Pedidos" -ForegroundColor Cyan
Write-Host ("=" * 64) -ForegroundColor Cyan

# 1. Ollama
Write-Host "`n[1/4] Verificando Ollama en el PC..." -ForegroundColor Yellow
try {
    $v = Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 5
    Write-Host "      Ollama OK - version $($v.version)" -ForegroundColor Green
    $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
    Write-Host "      Modelos: $(($tags.models | ForEach-Object { $_.name }) -join ', ')" -ForegroundColor DarkGray
}
catch {
    Write-Host "      ERROR: Ollama no responde en 127.0.0.1:11434" -ForegroundColor Red
    Write-Host "      Ejecuta: powershell -File F:\ai\opencode\scripts\ensure-ollama.ps1" -ForegroundColor Yellow
    exit 1
}

# 2. Dependencias
Write-Host "`n[2/4] Instalando dependencias..." -ForegroundColor Yellow
python -m pip install --disable-pip-version-check -q -r requirements.txt

# 3. Servidores
Write-Host "`n[3/4] Levantando servidores..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*pythoncore*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$log = Join-Path $Raiz "log_servidor.log"
$err = Join-Path $Raiz "log_servidor.err"
Start-Process -FilePath "python" -ArgumentList "src/servidor.py" -WorkingDirectory $Raiz `
    -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden
Start-Sleep -Seconds 6

try {
    $health = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 15
    Write-Host "      Servidor OK: $($health.servidor) | meta=$($health.servidor_meta) | ollama=$($health.ollama.modelo)" -ForegroundColor Green
}
catch {
    Write-Host "      ERROR: el servidor no respondio. Revisa log_servidor.err" -ForegroundColor Red
    exit 1
}

# 4. Prueba
Write-Host "`n[4/4] Ejecutando prueba extremo a extremo..." -ForegroundColor Yellow
python src/cliente_prueba.py

Write-Host "`nResultados guardados en: $(Join-Path $Raiz 'resultados')" -ForegroundColor Cyan
