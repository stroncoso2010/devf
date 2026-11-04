# Instrucciones — Agente de WhatsApp para Restaurante

Guía paso a paso para reproducir la prueba local desde cero.

## 0. Requisitos

- Python 3.12 con el `.venv` del proyecto (o `uv venv` + `pip install -r requirements.txt`)
- Ollama con `gemma4:12b` descargado (`ollama list`)
- Llama Stack 0.7.3 (ya instalado en el venv)

Si Ollama no responde:

```powershell
powershell -File F:\ai\opencode\scripts\ensure-ollama.ps1
```

## 1. Levantar los servicios (3 procesos)

O ejecuta todo de una vez con `.\iniciar.ps1`.

**Terminal A — Llama Stack (8321):**

```powershell
cd F:\tarea\Agente_Restaurante_WhatsApp
.venv\Scripts\llama.exe stack run llama_stack\run.yaml --port 8321
```

**Terminal B — Receptor local de Graph API (8890):**

```powershell
.venv\Scripts\python.exe src\mock_meta.py
```

**Terminal C — Webhook (8040):**

```powershell
.venv\Scripts\python.exe src\servidor.py
```

Verificación:

```powershell
Invoke-WebRequest http://127.0.0.1:8321/v1/health                          # 200
Invoke-WebRequest http://127.0.0.1:8890/v19.0/LOCAL_1234567890/messages     # 200
Invoke-WebRequest http://127.0.0.1:8040/estado                              # JSON
```

## 2. Ejecutar la prueba completa (7 escenarios, ~2 min)

```powershell
.venv\Scripts\python.exe -X utf8 src\cliente_prueba.py
```

Imprime cada turno con su latencia por fase, las herramientas llamadas, los
recortes de historial y el **veredicto 8/8**. La salida queda en
`resultados/salida_consola.txt`.

`-X utf8` es obligatorio en Windows (la consola es cp1252).

## 3. Verificar por HTTP a mano

```powershell
# Handshake de Meta
Invoke-WebRequest "http://127.0.0.1:8040/webhook?hub.mode=subscribe&hub.verify_token=RESTAURANTE_2026&hub.challenge=12345"

# Sesiones, historial y bitácora
Invoke-WebRequest http://127.0.0.1:8040/estado
Invoke-WebRequest http://127.0.0.1:8040/historial/5215511110015
Invoke-WebRequest http://127.0.0.1:8040/bitacora

# Reservas creadas por function calling
Invoke-WebRequest http://127.0.0.1:8040/reservas

# Mensajes entregados al canal
Invoke-WebRequest http://127.0.0.1:8890/v19.0/LOCAL_1234567890/messages

# Reiniciar para repetir la prueba
Invoke-WebRequest -Method POST http://127.0.0.1:8040/reiniciar
Invoke-WebRequest -Method DELETE http://127.0.0.1:8890/v19.0/LOCAL_1234567890/messages
```

## 4. Enviar un mensaje manual (formato de Meta)

```powershell
$body = @{
  entry = @(@{ changes = @(@{ value = @{ messages = @(@{
    id = "wamid.MANUAL01"
    from = "5215511110015"
    type = "text"
    text = @{ body = "¿Tienen mesa para 2 el sábado 7 a las 14:00?" }
  }) } }) }) })
} | ConvertTo-Json -Depth 10

Invoke-WebRequest -Method POST http://127.0.0.1:8040/webhook -Body $body -ContentType "application/json"
```

Después consulta `/bitacora`, `/reservas` y el receptor de Graph.

## 5. Puntos de configuración

| Qué | Dónde |
|---|---|
| Modelo, límite de historial, timeouts, temperatura | `configuracion.json` → `llama_stack` |
| **Capa de seguridad** (patrones, límites, `llama_guard_modelo`) | `configuracion.json` → `seguridad` |
| Reglas fijas (patrones + mensaje) | `configuracion.json` → `reglas` |
| Instructions del agente y fecha de referencia | `configuracion.json` → `agente` |
| Mesas, ocupación, menú, FAQ, días cerrados | `configuracion/catalogo.json` |
| Puerto del webhook (8040) y verify token | `configuracion.json` → `servidor` / `whatsapp` |

## 6. Activar Llama Guard real (opcional)

1. `ollama pull llama-guard3`
2. En `configuracion.json`:
   ```json
   "seguridad": { "llama_guard_modelo": "llama-guard3" }
   ```
3. Reiniciar el webhook. Cada entrada pasará además por el modelo de
   seguridad vía `/api/generate`; si no responde, el guard por reglas sigue
   cubriendo (queda registrado en `guard_modelo`).

## 7. Conectar WhatsApp real

1. App en developers.facebook.com → WhatsApp → Cloud API (token + phone number id).
2. `configuracion.json`:
   - `whatsapp.token` → tu token
   - `whatsapp.phone_id` → tu phone number id
   - `whatsapp.graph_api_base` → `https://graph.facebook.com`
3. `ngrok http 8040` y registrar `https://<tunel>/webhook` en Meta con el
   verify token `RESTAURANTE_2026`.

## 8. Apagar los servicios

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*src\servidor.py*" -or $_.CommandLine -like "*src\mock_meta.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-Process llama -ErrorAction SilentlyContinue | Stop-Process -Force
```

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `webhook CAIDO` | error al importar | revisa `webhook.err` |
| Turno con `error` y mensaje de servicio temporal | Llama Stack ↔ Ollama caído | verifica Ollama y `/v1/health`; el agente reintenta 1 vez solo |
| Reserva rechazada "argumentos invalidos" | fecha pasada, día cerrado, hora fuera de turno o >8 personas | es la validación funcionando; mira `detalle.error` en `/bitacora` |
| Entrada bloqueada por el guard | patrón de inyección o mensaje >600 caracteres | revisa `guard.categoria` en `/bitacora` |
| Respuestas lentas (15–60 s) | modelo grande en CPU | normal; reglas y guard responden ≤29 ms |
