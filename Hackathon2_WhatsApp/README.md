# Agente de WhatsApp para Restaurante — Hackathon 2 (Módulo 2)

**Problema real resuelto:** un restaurante de comida casera ("La Cocina de Doña
Carmen") pierde llamadas y hojas de papel para agendar mesas. Este agente de
WhatsApp recibe la solicitud, **consulta la disponibilidad real**, **agenda la
reserva** y resuelve las dudas frecuentes del menú — con memoria por cliente,
reglas fijas de emergencia y una capa de seguridad.

| Pieza del curso | Cómo está aplicada aquí | Evidencia |
|---|---|---|
| **Clase 1 — WhatsApp Cloud API** | Webhook con handshake de verificación (`GET /webhook`), recepción `POST` con formato Graph API, respuesta 200 inmediata + `BackgroundTasks`, idempotencia por `wamid`, validación de longitud de salida | Handshake 200; 7/7 mensajes entregados |
| **Clase 2 — Diseño de agentes con memoria y estado** | Una `conversation_id` de Llama Stack **por número de teléfono**, lock por sesión, límite de **8 items** con recorte automático | Turno 3 recupera fecha/hora/personas sin que el cliente las repita; 16 items recortados |
| **Clase 3 — Llama como motor + function calling** | 3 herramientas (`consultar_disponibilidad`, `agendar_reserva`, `buscar_pregunta_frecuente`) con contrato separado de la implementación, validación de argumentos, timeout y devolución `function_call_output` | Reserva **R-101** creada con datos reales; FAQ resuelta por función, no por invención |
| **Clase 4 — Prototipo a producción** | Capa de seguridad (`src/guard.py`): inyección de prompt, contenido prohibido, límites de tamaño, saneado de salida y **hook opcional para Llama Guard**; timeouts por fase, fallback con reintento, endpoints de monitoreo (`/bitacora`, `/estado`, `/reservas`) | Prompt injection bloqueado en **0 ms sin tocar el modelo** |

## Resultado de la prueba local ejecutada

```
[OK] 1 FAQ del menu dispara buscar_pregunta_frecuente
[OK] 2 Disponibilidad dispara consultar_disponibilidad (datos reales)
[OK] 3 Reserva creada con datos recuperados de la memoria
[OK] 4 Intoxicacion -> regla urgencia_salud (sin Llama)
[OK] 5 Gerente -> regla escalado_humano (sin Llama)
[OK] 6 Prompt injection -> bloqueado por el guard (sin Llama)
[OK] 7 Follow-up del domingo responde con historial (sin repetir datos)
[OK] 8 Handshake de Meta verificado + 7 mensajes entregados
TOTAL: TODOS LOS ESCENARIOS OK
```

**Latencias del ciclo completo** (lo único que percibe el usuario):

| Escenario | Fase | Ciclo total |
|---|---|---|
| Menú (FAQ) | razonamiento 58 975 ms | 59 917 ms |
| Disponibilidad viernes 20:00 | razonamiento 18 970 ms | 19 061 ms |
| Confirmar reserva (memoria) | razonamiento 22 524 ms | 22 637 ms |
| Intoxicación → **regla** | sin modelo | **29 ms** |
| Gerente → **regla** | sin modelo | **29 ms** |
| Prompt injection → **guard** | sin modelo | **0 ms** |
| FAQ domingo (follow-up) | razonamiento 15 570 ms | 15 710 ms |

- Promedio de los 4 turnos de modelo: **29 331 ms** (CPU, sin GPU).
- Reglas y guard: **≤29 ms** → ~1 000× más rápido que el modelo.
- Reserva creada: `R-101 · 2026-11-06 20:00 · 4p · mesa M4 (salón) · Ana Pérez`.
- Historial: límite 8 items, **16 recortados** en 4 turnos de modelo.

## Arquitectura

```
WhatsApp (o el cliente de prueba)
        │  payload JSON estilo Graph API
        ▼
FastAPI  POST /webhook ──► 200 a Meta de inmediato + idempotencia por wamid
        │                  BackgroundTasks (función síncrona)
        ▼
① GUARD (src/guard.py) ──► ¿inyección / contenido prohibido / demasiado grande?
        │                          │ SÍ → respuesta fija (0 ms, sin modelo)
        ▼ NO
② Lock por teléfono ──► Reglas fijas (intoxicación / gerente)
        │                      │ disparan → respuesta fija (29 ms, sin modelo)
        ▼ NO
③ Llama Stack responses.create(tools=ESQUEMAS)      ◄── Ollama gemma4:12b
        │
        ├─ ¿items type == "function_call"? ──► valida argumentos ──►
        │        ejecuta la función real (timeout 3 s) ──► function_call_output
        │        ──► 2ª llamada al modelo ──► respuesta final
        └─ ¿texto libre? ──► respuesta directa
        ▼
④ Recorte de historial (8 items) + saneado de salida ──► Graph API (receptor local)
```

## Estructura

```
Agente_Restaurante_WhatsApp/
├── configuracion/
│   ├── configuracion.json     # modelo, guard, reglas, instructions, puertos
│   └── catalogo.json          # datos reales: 8 mesas, ocupación, menú, 8 FAQ
├── llama_stack/run.yaml       # Llama Stack 0.7.3 (Ollama + responses)
├── src/
│   ├── agente.py              # ciclo guard → reglas → modelo → herramientas
│   ├── guard.py               # CAPA DE SEGURIDAD (reglas + hook Llama Guard)
│   ├── herramientas.py        # contrato (ESQUEMAS) + implementación real
│   ├── memoria.py             # conversación por teléfono + lock + recorte
│   ├── reglas.py              # motor genérico de reglas fijas (solo JSON)
│   ├── servidor.py            # webhook FastAPI (handshake, BackgroundTasks)
│   ├── normalizacion.py       # números de teléfono MX
│   ├── config.py              # carga de configuración
│   ├── mock_meta.py           # receptor local de Graph API (puerto 8890)
│   └── cliente_prueba.py      # 8 verificaciones + veredicto automático
├── resultados/                # salida ejecutada de la prueba
├── docs/
│   ├── DECISIONES.md          # decisiones técnicas (para la Fase 3)
│   └── ENTREGABLE.md          # checklist del entregable mínimo
├── requirements.txt
└── iniciar.ps1 / iniciar.bat
```

## Puesta en marcha (prueba local, sin WhatsApp real ni ngrok)

```powershell
# 1. Ollama con gemma4:12b
Invoke-RestMethod http://127.0.0.1:11434/api/version

# 2. Llama Stack (8321)
.venv\Scripts\llama.exe stack run llama_stack\run.yaml --port 8321

# 3. Receptor local de Graph API (8890)
python src\mock_meta.py

# 4. Webhook (8040)
python src\servidor.py

# 5. Prueba completa (~2 min)
python -X utf8 src\cliente_prueba.py
```

Detalle paso a paso en `INSTRUCCIONES.md`.

## Para conectar WhatsApp real

1. App en developers.facebook.com → WhatsApp → Cloud API (token + phone number id).
2. `configuracion.json`: `whatsapp.token`, `whatsapp.phone_id` y
   `whatsapp.graph_api_base = "https://graph.facebook.com"`.
3. `ngrok http 8040` y registrar `https://<tunel>/webhook` con el verify token
   `RESTAURANTE_2026`. El handshake ya está implementado.

## Notas

- Todo corre en local: Llama Stack 0.7.3 + Ollama (`gemma4:12b`), CPU sin GPU.
- La palabra "simulación" no se usa: es una **prueba local** sobre un
  **servidor local**.
- El guard por reglas es el default; activar Llama Guard real es un cambio de
  una línea en `configuracion.json` → `seguridad.llama_guard_modelo`.
