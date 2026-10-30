# Challenge: Asistente de Estatus de Pedidos

**WhatsApp Cloud API + Ollama (Llama 3.1)** — Hands-On de la clase, con las dos mejoras del reto:

1. **Mensaje de bienvenida** para usuarios nuevos.
2. **Tono de respuesta controlado** (máximo 2-3 líneas, amable).

El asistente recibe mensajes de WhatsApp por webhook, consulta el estatus de un pedido y
responde usando un modelo de lenguaje servido por **Ollama**.

---

## Arquitectura

```
┌──────────────┐   webhook POST   ┌───────────────────────────┐
│  Meta / Local│ ───────────────► │  Servidor FastAPI         │
│  (WhatsApp)  │                  │  src/app.py                │
└──────────────┘                  │   • GET  /webhook  (verify)│
                                  │   • POST /webhook  (recibe)│
                                  │   • BackgroundTasks        │
                                  └────────────┬──────────────┘
                                               │
                        ┌──────────────────────┼──────────────────────┐
                        ▼                      ▼                      ▼
              ┌──────────────────┐  ┌───────────────────┐  ┌────────────────────┐
              │ Lógica negocio   │  │  Catálogo pedidos │  │  Ollama (PC local) │
              │ src/asistente.py │  │ pedidos.json      │  │  127.0.0.1:11434   │
              │  • saludo        │  │  (datos duros)    │  │  qwen3.5:0.8b      │
              │  • reglas        │  └───────────────────┘  │  gemma4:12b        │
              │  • LLM           │                         └────────────────────┘
              └──────────────────┘
                        │
                        ▼  Graph API (real o servidor local)
              ┌──────────────────┐
              │ src/servidor_meta.py  (servidor local, puerto 8899) │
              └──────────────────┘
```

### Tres rutas de respuesta (sin alucinaciones)

| Fuente | Cuándo | LLM |
|---|---|---|
| `saludo` | Primer mensaje de un usuario nuevo | No |
| `catalogo` | El mensaje trae un folio `PED-####` (o no existe) | No |
| `regla` | Pide estatus **sin** folio → se le pide el folio | No |
| `llm` | Conversación general | Sí |

Los datos duros (estado, fecha, rastreo) **nunca** los inventa el modelo: salen del catálogo.
El LLM solo entra en la conversación libre, y el prompt incluye el catálogo vigente.

---

## Requisitos

- Python 3.10+ (probado en 3.14)
- [Ollama](https://ollama.com) ejecutándose en el PC (`http://127.0.0.1:11434`)
- Un modelo local. En esta máquina: `qwen3.5:0.8b` (rápido), `gemma4:12b` (mejor calidad),
  `granite4.2:8b` (JSON), `gpt-oss:20b` (razonamiento). El challenge original usa `llama3.1:8b`:
  ```bash
  ollama pull llama3.1:8b
  ```

## Instalación

```bash
git clone <tu-repo>
cd Challenge_Asistente_Estatus_Pedidos
python -m pip install -r requirements.txt
```



## Configuración

Todo vive en `configuracion/configuracion.json` y se puede sobrescribir con variables
de entorno (ver `.env.example`):

| Variable | Por defecto | Para qué |
|---|---|---|
| `OLLAMA_MODELO` | `qwen3.5:0.8b` | Modelo local que responde |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Servidor Ollama |
| `GRAPH_API_BASE` | `http://127.0.0.1:8899` | `https://graph.facebook.com` en producción |
| `WHATSAPP_TOKEN` | vacío | Token de Meta |
| `WHATSAPP_PHONE_ID` | `LOCAL_...` | Phone number id |
| `VERIFY_TOKEN` | `HANDS_ON_2026` | Token de verificación del webhook |

> `think=false` y `num_predict` explícito: es lo que evita que qwen/gemma devuelvan la
> respuesta dentro de `thinking` y dejen `content` vacío.

## Pasarlo a WhatsApp real

1. Copia `.env.example` a `.env` y rellena `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `VERIFY_TOKEN`.
2. Pon `GRAPH_API_BASE=https://graph.facebook.com`.
3. Expón el webhook con ngrok:
   ```bash
   ngrok http 8000
   ```
4. En **Meta for Developers → WhatsApp → Configuration**, pega la URL pública + `/webhook`
   y el mismo `VERIFY_TOKEN`.
5. Ejecuta `python src/servidor.py --solo-asistente` y manda un mensaje al número de prueba.

El notebook `colab/Challenge_Asistente_Estatus_Pedidos.ipynb` replica el flujo completo
en Google Colab (instalación de Ollama, Secrets, ngrok y pruebas).

## Resultados de la prueba

En `resultados/`:

| Archivo | Contenido |
|---|---|
| `CONVERSACION.md` | La conversación completa, legible |
| `conversacion.json` | La misma conversación en JSON |
| `bitacora.json` | Cada paso de la prueba con su respuesta |
| `metricas.json` | Tiempos, conteos y modelo usado |

Ejemplo real (Ollama local, `qwen3.5:0.8b`):

| Caso | Entrada | Respuesta | Fuente |
|---|---|---|---|
| Usuario nuevo | "Hola, buenas tardes" | Saludo de bienvenida | `saludo` |
| Estatus con folio | "¿Cuál es el estatus de mi pedido PED-1002?" | Estado + entrega + rastreo | `catalogo` |
| Estatus sin folio | "Oye, ¿ya llegó mi compra?" | "¿Me compartes el número de pedido?" | `regla` |
| Pedido inexistente | "Revisa el pedido PED-9999" | "No encuentro el pedido…" | `catalogo` |
| Conversación | "¿Puedo comprar sin pasar a la tienda?" | Respuesta del modelo, 2-3 líneas | `llm` (0.9-3.1 s) |

## Estructura del proyecto

```
.
├── configuracion/
│   ├── configuracion.json     # servidor, Ollama, WhatsApp, asistente
│   └── pedidos.json           # catálogo de pedidos (datos duros)
├── src/
│   ├── app.py                 # servidor FastAPI + webhook
│   ├── asistente.py           # lógica de negocio (saludo, reglas, catálogo, LLM)
│   ├── ollama.py              # cliente Ollama (think=false, métricas)
│   ├── normalizacion.py       # normalización de números mexicanos
│   ├── servidor_meta.py      # servidor local de la Graph API de Meta
│   ├── cliente_prueba.py      # prueba extremo a extremo -> resultados/
│   ├── servidor.py            # lanza los dos servidores
│   └── config.py              # carga de configuración
├── 
├── resultados/                # salidas de la prueba local
├── docs/PROCESO.md            # el proceso paso a paso
├── INSTRUCCIONES.md           # guía de ejecución
├── iniciar_prueba local.ps1
├── iniciar_prueba local.bat
├── requirements.txt
└── LICENSE
```
