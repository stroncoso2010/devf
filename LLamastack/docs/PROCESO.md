# Proceso de construcción — Agente de la Veterinaria con Llama Stack

Registro técnico de cómo se construyó el agente, las decisiones tomadas y los
problemas resueltos durante la práctica local.

---

## 1. Objetivo

Replicar el flujo del hands-on de la masterclass **Diseño de Agentes
Conversacionales** — memoria por número de teléfono, regla fija de
escalamiento — y resolver el **Challenge: agente de una veterinaria**, con:

- memoria de conversación en **Llama Stack** (`client.conversations`),
- **regla fija adicional** de urgencia médica,
- **límite al historial** conservado en la conversación,
- **lock por número** para serializar mensajes del mismo usuario,
- webhook con `BackgroundTasks` y verificación de Meta,
- ejecución **local en PC** con Ollama (en Colab solo está el notebook).

---

## 2. Entorno

| Componente | Versión / valor |
|---|---|
| Python | 3.12.16 (venv con `uv`) |
| llama-stack | 0.7.3 |
| llama-stack-client | 0.7.5 |
| fastapi + uvicorn | 0.162.0 / 0.54.0 |
| Ollama (PC) | `http://127.0.0.1:11434` |
| Modelo | `gemma4:12b` (Q4_K_M, 11.9B) |
| Llama Stack | `http://127.0.0.1:8321` |
| Webhook local | `http://127.0.0.1:8020` |
| Mock de Meta | `http://127.0.0.1:8890` |

---

## 3. Decisiones de diseño

### 3.1 Memoria = conversación de Llama Stack, no diccionario propio

El hands-on original guarda el historial en un `dict` por número. Aquí se usa
la API de conversaciones de Llama Stack (`/v1/conversations`), que es lo que el
Tema 11 (Llama Stack) estandariza:

```python
conv = client.conversations.create(metadata={"telefono": tel})   # por usuario
client.responses.create(conversation=conv.id, ...)               # con memoria
client.conversations.items.list(conversation_id=conv.id)         # historial
client.conversations.items.delete(...)                           # recorte
```

### 3.2 Reglas fijas ANTES del modelo

Las dos decisiones que no se delegan (escalamiento y urgencia médica) se
evalúan con coincidencia de patrones (normalizados sin acentos) antes de tocar
Llama Stack. Si la regla dispara, el modelo no se invoca y la conversación no
crece.

### 3.3 Lock por teléfono

Cada sesión (`SesionUsuario`) lleva su propio `threading.Lock`: dos mensajes
seguidos del mismo número se procesan **en serie** sobre la misma conversación
(paralelismo entre usuarios, serialización dentro del usuario).

### 3.4 Respuesta inmediata a Meta con `BackgroundTasks`

El endpoint `POST /webhook` responde `200 {"status":"received"}` de inmediato
y delega el procesamiento real a una tarea de fondo; así Meta no reintenta la
entrega ni se duplican las respuestas. Además, los IDs de mensaje ya procesados
se guardan en un conjunto para ignorar reintentos.

### 3.5 Mock local de la API de Meta

Para probar sin WhatsApp real ni ngrok, `src/mock_meta.py` imita los endpoints
`/v19.0/{phone_id}/messages` (POST guarda + GET lista + DELETE limpia). El
webhook apunta ahí con `whatsapp.graph_api_base`.

---

## 4. Problemas resueltos durante la construcción

| # | Problema | Causa | Solución |
|---|---|---|---|
| 1 | `llama stack serve` no existe | En 0.7.3 el CLI es `llama stack run <config>` | Usar `llama.exe stack run llama_stack/run.yaml` |
| 2 | Error de validación del YAML | El formato 0.7.3 exige `apis:` + `providers:` por API | Escribir el `run.yaml` con el formato nuevo (`providers.inference`, `responses`, `vector_io`, `tool_runtime`, `files`) |
| 3 | `ImportError: mcp / pydantic` | Dependencias desalineadas | Fijar `mcp<1.13` y `pydantic<2.12` |
| 4 | `ModuleNotFoundError: ollama / chardet / pypdf / sqlite-vec` | Dependencias no empaquetadas | Instalarlas aparte |
| 5 | `required dependency 'tool_runtime'/'files' no disponible` | El proveedor `builtin` de responses las exige | Agregar `tool_runtime` y `files` al YAML |
| 6 | `NameError: config is not defined` | Referencias a `config` en vez de `self.config` | Corregir en `agente.py` |
| 7 | Webhook no respondía (timeout) | La tarea de fondo era `async` pero llamaba código síncrono bloqueante, **congelando el event loop** | Cambiar `_procesar_y_responder` a función **sincrónica** (Starlette la corre en threadpool) |
| 8 | `content` de items `user` vacío | Llama Stack devuelve `content` como **string** en usuario y como **lista de partes** en asistente | Normalizar los dos casos en `memoria.items()` |
| 9 | Recorte borraba los turnos **nuevos** | `items.list` ordena por defecto de lo **más reciente** a lo más antiguo (`desc`) | Pedir `order="asc"` antes de recortar (y para mostrar el historial) |
| 10 | Latencia del turno incluía espera en cola | El cronómetro arrancaba antes del `lock` | Mover `inicio` **dentro** del lock |

---

## 5. Prueba ejecutada

Comando:

```
python src/cliente_prueba.py
```

Escenarios (8 mensajes, 2 teléfonos):

| Escenario | Qué verifica | Resultado |
|---|---|---|
| A | 5 mensajes con memoria + recorte al llegar a 8 items | ✅ el turno 5 recuerda el servicio del turno 1; -2 items borrados |
| B | Escalado a humano | ✅ regla fija, 27 ms, sin modelo |
| C | Urgencia médica | ✅ regla fija, 28 ms, sin modelo |
| D | Segundo teléfono | ✅ memoria aislada: 2 items propios, 0 ajenos |
| — | Handshake del webhook | ✅ 200 + challenge |
| — | Mensajes salientes al "API de Meta" | ✅ 8/8 en el mock |

Métricas (`resultados/conversacion.json`):

```
turnos totales        : 8   (6 con modelo, 2 con regla fija)
latencia modelo       : 19,342 – 40,817 ms (promedio 32,126 ms)
latencia reglas       : 27 y 28 ms
items borrados        : 2 (recorte de historial aplicado 1 vez)
```

---

## 6. Estructura final

```
Agente_Veterinaria_LlamaStack/
├── configuracion/
│   └── configuracion.json      # modelo, límites, reglas, puertos, WhatsApp
├── llama_stack/
│   ├── run.yaml                # distribución Llama Stack con Ollama
│   └── data/                   # almacenamiento (kv/sqlite) — no se versiona
├── src/
│   ├── config.py               # carga de configuración + variables de entorno
│   ├── reglas.py               # reglas fijas (escalamiento, urgencia)
│   ├── memoria.py              # conversación por teléfono + recorte + lock
│   ├── agente.py               # pipeline: lock → reglas → modelo → recorte
│   ├── servidor.py             # webhook FastAPI (BackgroundTasks)
│   ├── mock_meta.py            # mock local de la API de Graph de Meta
│   ├── normalizacion.py        # normalización E.164 de números MX
│   └── cliente_prueba.py       # cliente que dispara los 4 escenarios
├── docs/
│   ├── EJERCICIOS.md           # ejercicios resueltos con datos reales
│   └── PROCESO.md              # este documento
├── resultados/                 # salidas de la prueba local
└── colab/                      # notebook para Colab (Llama 3.1 + Llama Stack)
```
