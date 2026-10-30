

### Paso 1. Verificar Ollama

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/version
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```


### Paso 2. Dependencias

```powershell
python -m pip install -r requirements.txt
```

### Paso 3. Levantar los dos servidores

```powershell
python src/servidor.py
```

Salida esperada:

```
[SERVIDOR-META] arrancando en http://127.0.0.1:8899
[ASISTENTE] arrancando en http://127.0.0.1:8000
```

### Paso 4. Comprobar que todo responde

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8899/estado
```

### Paso 5. Prueba extremo a extremo

```powershell
python src/cliente_prueba.py
```

Genera `resultados/`.

### Paso 6. Detener

`Ctrl+C` en la terminal del servidor, o:

```powershell
Get-Process python | Where-Object { $_.Path -like "*pythoncore*" } | Stop-Process -Force
```

---

## Pruebas manuales (copiar y pegar)

### Verificación de credenciales (lo que hace Meta)

```powershell
Invoke-WebRequest "http://127.0.0.1:8000/webhook?hub.mode=subscribe&hub.verify_token=HANDS_ON_2026&hub.challenge=12345"
```

Debe devolver `12345` en texto plano.

### Mensaje entrante (como si lo enviara Meta)

```powershell
$payload = @{
  object = "whatsapp_business_account"
  entry = @(@{ changes = @(@{ value = @{
    messaging_product = "whatsapp"
    messages = @(@{ from = "5215512345678"; type = "text"; text = @{ body = "Hola" } })
  } }) })
} | ConvertTo-Json -Depth 10

Invoke-RestMethod http://127.0.0.1:8000/webhook -Method Post -Body $payload -ContentType "application/json"
Start-Sleep 3
Invoke-RestMethod http://127.0.0.1:8899/mensajes
```

### Cambiar de modelo

```powershell
# temporal
$env:OLLAMA_MODELO = "gemma4:12b"
python src/servidor.py
```

O de forma permanente en `configuracion/configuracion.json` → `ollama.modelo`.

### Reiniciar el estado entre pruebas

```powershell
Invoke-RestMethod http://127.0.0.1:8000/admin/reiniciar -Method Post
Invoke-RestMethod http://127.0.0.1:8899/mensajes -Method Delete
```

---

## De prueba local a producción

1. `.env` con `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `VERIFY_TOKEN`.
2. `GRAPH_API_BASE=https://graph.facebook.com`.
3. `ngrok http 8000` → URL pública.
4. Meta for Developers → WhatsApp → Configuration → Callback URL = `<url>/webhook`.
5. `python src/servidor.py --solo-asistente`.
