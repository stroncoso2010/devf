# Agente de Atención a Pedidos — Llama Stack + Function Calling

Proyecto para el challenge **"Agente de Atención a Pedidos"** del curso *Diseño de
Agentes Conversacionales* (tema: **Integración Llama + WhatsApp**).

El agente recibe mensajes de WhatsApp a través de un webhook, mantiene una conversación
por número de teléfono en **Llama Stack** y, cuando el modelo lo pide, **ejecuta
funciones reales** (`consultar_pedido`, `buscar_pregunta_frecuente`) devolviendo los
datos al modelo para que redacte la respuesta final.

## Qué demuestra

| Requisito del challenge | Dónde está | Resultado de la prueba |
|---|---|---|
| Function calling con `consultar_pedido` | `src/herramientas.py` (contrato) + `src/agente.py` (loop) | El modelo la pidió con `{"numero_pedido":9988}` y el servidor la ejecutó contra datos reales |
| Integración de resultados de herramientas | `agente.py` → `function_call_output` → 2ª llamada | Guía, transportista y fechas reales en la respuesta final |
| Continuidad de la memoria (conversación + lock por teléfono) | `src/memoria.py` | Follow-up "¿Y en qué fecha llega?" respondió **05/11/2026** sin repetir el número |
| Regla fija de urgencia (cargo duplicado) sin pasar por Llama | `src/reglas.py` + config | 30 ms vs 65 s del modelo |
| Regla fija de escalamiento (hablar con persona) | `src/reglas.py` + config | 26 ms, sin llamada al modelo |
| Pregunta frecuente dispara `buscar_pregunta_frecuente` | `src/herramientas.py` | Tema `pagos` resuelto con la FAQ oficial |
| Límite de historial | `max_items_historial: 8` | 12 items recortados en 3 turnos |
| Webhook con verificación de Meta + `BackgroundTasks` | `src/servidor.py` | Handshake 200; responde 200 a Meta antes de procesar |
| Validación de argumentos y manejo de errores | `_validar_argumentos` + reintento + fallback | Pedido 123456 **rechazado** antes de tocar los datos |

## Arquitectura

```
WhatsApp (o el cliente de prueba)
        │  payload JSON estilo Graph API
        ▼
FastAPI  POST /webhook  ──► responde 200 a Meta de inmediato
        │                   BackgroundTasks (función síncrona)
        ▼
Lock por teléfono  ──►  Reglas fijas (urgencia / escalamiento)
        │                        │ si dispara → respuesta fija (30 ms)
        ▼ no dispara
Llama Stack  responses.create(tools=ESQUEMAS)     ◄── Ollama gemma4:12b
        │
        ├─ ¿items type == "function_call"? ──► valida argumentos ──►
        │        ejecuta la función real (timeout 3 s) ──► function_call_output
        │        ──► 2ª llamada al modelo ──► respuesta final
        └─ ¿texto libre? ──► respuesta directa
        ▼
Recorte de historial (límite 8 items)  ──►  envío por Graph API (mock local)
```

## Estructura

```
Agente_Pedidos_Llama/
├── configuracion/
│   ├── configuracion.json      # modelo, límites, reglas, tokens, instructions
│   └── catalogo.json           # datos reales: 5 pedidos + 6 preguntas frecuentes
├── llama_stack/run.yaml        # config de Llama Stack 0.7.3 (Ollama + responses)
├── src/
│   ├── agente.py               # ciclo completo + medición de fases + fallback
│   ├── herramientas.py         # CONTRATO (esquemas) + IMPLEMENTACIÓN (funciones)
│   ├── memoria.py              # conversación Llama Stack por teléfono + lock + recorte
│   ├── reglas.py               # motor genérico de reglas fijas (solo JSON)
│   ├── servidor.py             # webhook FastAPI (verificación, BackgroundTasks)
│   ├── normalizacion.py        # números de teléfono MX
│   ├── config.py               # carga de configuración
│   ├── mock_meta.py            # Graph API local (puerto 8890) para pruebas
│   └── cliente_prueba.py       # 6 escenarios + veredicto automático
├── resultados/                 # salida ejecutada de la prueba
├── docs/
│   ├── EJERCICIOS.md           # los 3 ejercicios del tema resueltos
│   └── PROCESO.md              # problemas encontrados y decisiones
├── colab/                      # notebook (opcional) con Llama 3.1
├── requirements.txt
└── iniciar.ps1 / iniciar.bat
```

## Puesta en marcha (prueba local)

```powershell
# 1. Ollama debe estar corriendo
Invoke-RestMethod http://127.0.0.1:11434/api/version

# 2. Llama Stack (puerto 8321)
.venv\Scripts\llama.exe stack run llama_stack\run.yaml --port 8321

# 3. Mock de Graph API (puerto 8890)
python src\mock_meta.py

# 4. Webhook (puerto 8030)
python src\servidor.py

# 5. Prueba completa (6 escenarios, ~4 min)
python -X utf8 src\cliente_prueba.py
```

O ejecuta `.\iniciar.ps1` para levantar los tres servicios de una vez.

## Resultado de la prueba ejecutada

```
[OK] 1 FAQ dispara buscar_pregunta_frecuente
[OK] 2 Cargo duplicado -> regla urgencia (sin Llama)
[OK] 3 Hablar con persona -> regla escalamiento (sin Llama)
[OK] 4 Pedido -> consultar_pedido ejecutada
[OK] 5 Memoria: follow-up sin repetir el numero
[OK] 6 Pedido inexistente -> respuesta honesta, sin inventar
TOTAL: TODOS LOS ESCENARIOS OK
```

Latencias del ciclo completo (lo que percibe el usuario):

| Escenario | Fase | Ciclo total |
|---|---|---|
| Pregunta frecuente | razonamiento 64 972 ms | 65 027 ms |
| Cargo duplicado | **regla 30 ms** | 30 ms |
| Hablar con persona | **regla 26 ms** | 26 ms |
| Consultar pedido 9988 | razonamiento 28 499 ms | 28 590 ms |
| Follow-up de memoria | razonamiento 12 507 ms | 12 570 ms |
| Pedido inexistente | razonamiento 22 482 ms | 22 596 ms |

Detalles en `resultados/` y en `docs/PROCESO.md`.

## Notas

- **No se usa WhatsApp real ni ngrok**: el mock local reproduce los endpoints de la
  Graph API (`POST/GET/DELETE /v19.0/{phone_id}/messages`). Para conectar a Meta basta
  cambiar `whatsapp.graph_api_base` a `https://graph.facebook.com` y completar el token.
- Todo corre en local: Llama Stack 0.7.3 + Ollama (`gemma4:12b`) sin GPU.
- La palabra "simulación" no se usa: es una **prueba local** sobre un **servidor local**.
