# El proceso, paso a paso

Cómo se construyó y se verificó el **Challenge: Asistente de Estatus de Pedidos**.

---

## Fase 1 — Requisitos del challenge

De la masterclass "Hands-On: WhatsApp Cloud API" el reto pide:

1. Entorno con Ollama instalado y arrancado en segundo plano, modelo **Llama 3.1 8B**.
2. Servidor FastAPI con `mensajes_recibidos` (bitácora) y `usuarios_conocidos` (`set`).
3. `normalizar_numero_mx` para dejar el número en formato que acepta la API de envío.
4. Prompt ajustado: respuestas de **máximo 2-3 líneas** y tono amable.
5. Endpoints `GET /webhook` (verificación) y `POST /webhook` (recepción) con `BackgroundTasks`.
6. Saludo fijo para usuarios nuevos + envío de la respuesta.
7. Túnel ngrok y prueba del flujo completo.

## Fase 2 — Decisiones de diseño

| Decisión | Motivo |
|---|---|
| **Servidor local de la Graph API de Meta** en lugar de credenciales reales | El reto debe poder revisarse sin tokens de Meta; además el servidor nunca sale de localhost. |
| **Ollama del PC** (`127.0.0.1:11434`) | El enunciado pide Colab, pero la máquina ya tiene Ollama y varios modelos: la prueba local es reproducible y offline. `llama3.1:8b` queda documentado como alternativa (`ollama pull llama3.1:8b`). |
| **`think=false`** | Medido en esta máquina: con `think` activo, `qwen3.5` y `gemma4` devuelven `content` vacío y dejan todo el texto en `thinking`. |
| **Datos duros fuera del LLM** | Un modelo pequeño inventó *"tu pedido ha sido enviado"* en la primera corrida. Los estados, fechas y rastreos salen del catálogo; el LLM solo conversa. |
| **Regla para "estatus sin folio"** | Si el usuario pregunta por su compra sin dar el folio, la respuesta es fija: *"¿Me compartes el número de pedido?"*. Nunca una suposición. |
| **`BackgroundTasks`** | Meta debe recibir el `200` de inmediato; si espera, reintenta y se duplican las respuestas. |
| **Normalización a 13 dígitos** | La API de envío exige E.164. WhatsApp entrega `5215512345678` (12) y México usa `52` + `1` + 10 dígitos; el prefijo válido es `55`. |

## Fase 3 — Construcción

```
src/config.py           Configuración + variables de entorno
src/normalizacion.py    normalizar_numero_mx + formatear_legible
src/ollama.py           Cliente Ollama (chat, fallback a generate, métricas)
src/asistente.py        Lógica: saludo, folio, reglas, catálogo, LLM
src/app.py              FastAPI: webhook, health, stats, pedidos, bitácora
src/servidor_meta.py   Servidor local de la Graph API (buzón de mensajes enviados)
src/servidor.py         Levanta los dos servidores en hilos
src/cliente_prueba.py   Prueba extremo a extremo -> resultados/
```

## Fase 4 — Verificación

La prueba replica la entrega de Meta entregando mensajes y comprueba la respuesta en el buzón.

| # | Escenario | Verificación |
|---|---|---|
| 1 | Health check | Servidor + servidor local + Ollama activos |
| 2 | `GET /webhook` con token | Devuelve el `hub.challenge` en texto plano (200) |
| 3 | Usuario nuevo saluda | Se envía el saludo de bienvenida |
| 4 | Usuario conocido con folio | Respuesta con estado, entrega y rastreo del catálogo |
| 5 | Pregunta de estatus sin folio | Se pide el folio (sin inventar estado) |
| 6 | Folio inexistente | Mensaje de "no encontrado" |
| 7 | Conversación general | Respuesta del LLM en 2-3 líneas, ~1 s |
| 8 | `/stats` | 2 usuarios conocidos, 5 mensajes, métricas del LLM |

### Hallazgo de la primera corrida

En el escenario 5, `qwen3.5:0.8b` respondió *"tu pedido ha sido procesado y enviado a la
puerta"*: una alucinación (no había pedido). Corrección: se añadió la regla determinista
`PATRON_INTENCION_ESTATUS` y el catálogo real al prompt del sistema.

## Fase 5 — Cierre

- 8/8 escenarios OK.
- Respuestas del LLM: ≤3 líneas (recorte determinista), 0.9-3.1 s, `think` 0.
- Configuración en un solo archivo (`configuracion/configuracion.json`), con overrides por
  variables de entorno para el paso a producción.
- Notebook de Colab incluido para replicar el flujo original.
