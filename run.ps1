# Verifica que Ollama esté corriendo
$resp = $null
try { $resp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 } catch { }

if (-not $resp) {
    Write-Host "Ollama no está corriendo. Ejecuta: ollama serve" -ForegroundColor Red
    exit 1
}

# Verifica que el modelo exista, si no, lo descarga
$modelo = "llama3.2:latest"
if (-not ($resp.models | Where-Object { $_.name -eq $modelo })) {
    Write-Host "Descargando modelo $modelo ..." -ForegroundColor Cyan
    ollama pull $modelo
}

# Ejecuta el asistente
Write-Host "Iniciando asistente..." -ForegroundColor Green
python src\assistant.py
