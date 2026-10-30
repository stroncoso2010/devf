"""
Servidor FastAPI del Asistente de Estatus de Pedidos.

Implementa los dos endpoints que exige WhatsApp Cloud API:
  - GET  /webhook  -> verificación de credenciales (hub.mode / hub.verify_token / hub.challenge)
  - POST /webhook  -> recepción de mensajes entrantes

El trabajo pesado (Llamada a Ollama + envío) se delega a `BackgroundTasks`
para responderle a Meta de inmediato: si Meta espera, reintenta la entrega
y se duplican las respuestas.
"""

import sys
from pathlib import Path
from typing import Any, Dict

import requests
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asistente import AsistentePedidos  # noqa: E402
from config import cargar_config  # noqa: E402
from normalizacion import normalizar_numero_mx  # noqa: E402
from ollama import ClienteOllama  # noqa: E402

config = cargar_config()

cliente_ollama = ClienteOllama(
    url=config["ollama"]["url"],
    modelo=config["ollama"]["modelo"],
    num_predict=config["ollama"]["num_predict"],
    temperature=config["ollama"]["temperature"],
    think=config["ollama"]["think"],
    timeout=config["ollama"]["timeout_segundos"],
)

asistente = AsistentePedidos(config, cliente_ollama)

app = FastAPI(
    title=config["servidor"]["titulo"],
    description="Webhook de WhatsApp Cloud API con Ollama local (PC)",
    version="1.0.0",
)

WA = config["whatsapp"]
GRAPH_VERSION = config["servidor_meta"]["graph_api_version"]


# ---------------------------------------------------------------------------
# Envío hacia WhatsApp (real o servidor local)
# ---------------------------------------------------------------------------
def enviar_mensaje_whatsapp(destinatario: str, mensaje: str) -> Dict[str, Any]:
    """Envía el mensaje por Graph API. En modo local apunta al servidor local."""
    url = f"{WA['graph_api_base']}/{GRAPH_VERSION}/{WA['phone_id']}/messages"
    headers = {
        "Authorization": f"Bearer {WA['token'] or 'LOCAL'}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destinatario,
        "type": "text",
        "text": {"preview_url": False, "body": mensaje},
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        return {
            "ok": r.status_code == 200,
            "http": r.status_code,
            "respuesta": r.text[:500],
        }
    except requests.RequestException as exc:
        return {"ok": False, "http": 0, "respuesta": str(exc)}


# ---------------------------------------------------------------------------
# Procesamiento (se ejecuta en segundo plano)
# ---------------------------------------------------------------------------
async def procesar_mensaje(telefono: str, texto: str) -> None:
    """Decide qué responder (saludo / catálogo / LLM) y lo envía."""
    resultado = asistente.responder(telefono, texto)
    envio = enviar_mensaje_whatsapp(telefono, resultado["respuesta"])
    resultado["envio"] = envio
    asistente.bitacora[-1]["envio"] = envio


# ---------------------------------------------------------------------------
# Endpoints del webhook
# ---------------------------------------------------------------------------
@app.get("/webhook")
async def verificar_webhook(request: Request):
    """Verificación de credenciales que Meta ejecuta al configurar el webhook."""
    params = request.query_params
    modo = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if modo == "subscribe" and token == WA["verify_token"]:
        # Meta espera el challenge en texto plano, sin JSON.
        return PlainTextResponse(content=challenge or "", status_code=200)
    return JSONResponse(
        content={"error": "Token de verificación incorrecto"},
        status_code=403,
    )


@app.post("/webhook")
async def recibir_mensajes(request: Request, background_tasks: BackgroundTasks):
    """Recibe un mensaje entrante de WhatsApp y agenda el procesamiento."""
    body = await request.json()
    asistente.mensajes_recibidos.append(body)

    try:
        entry = body["entry"][0]
        value = entry["changes"][0]["value"]
        mensajes = value.get("messages", [])
    except (KeyError, IndexError, TypeError):
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    if not mensajes:
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    mensaje = mensajes[0]
    telefono = normalizar_numero_mx(mensaje.get("from", ""))
    texto = (mensaje.get("text") or {}).get("body", "")

    # Respuesta inmediata a Meta; el resto va en segundo plano.
    background_tasks.add_task(procesar_mensaje, telefono, texto)
    return JSONResponse(content={"status": "received"}, status_code=200)


# ---------------------------------------------------------------------------
# Endpoints auxiliares (diagnóstico / panel / pruebas)
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Estado del servidor, del servidor local de Meta y de Ollama."""
    meta_ok = False
    try:
        r = requests.get(f"{WA['graph_api_base']}/estado", timeout=5)
        meta_ok = r.status_code == 200
    except requests.RequestException:
        meta_ok = False

    return {
        "servidor": "activo",
        "modo_whatsapp": WA.get("modo", "real"),
        "servidor_meta": meta_ok,
        "ollama": {
            "disponible": cliente_ollama.disponible(),
            "modelo": cliente_ollama.modelo,
            "url": cliente_ollama.url,
        },
    }


@app.get("/stats")
async def stats():
    """Métricas en vivo del asistente."""
    return {
        "usuarios_conocidos": len(asistente.usuarios_conocidos),
        "mensajes_recibidos": len(asistente.mensajes_recibidos),
        "pedidos_en_catalogo": len(asistente.pedidos),
        "modelo_ollama": cliente_ollama.modelo,
        "ultima_metrica_llm": cliente_ollama.ultima_metrica,
    }


@app.get("/pedidos")
async def listar_pedidos():
    """Catálogo de pedidos disponible en el entorno local."""
    return {"pedidos": asistente.pedidos}


@app.get("/bitacora")
async def bitacora():
    """Historial de la conversación (entradas y respuestas)."""
    return {"registros": asistente.bitacora}


@app.post("/admin/reiniciar")
async def reiniciar():
    """Limpia usuarios conocidos y bitácora (para repetir la prueba)."""
    asistente.reiniciar_estado()
    return {"status": "reiniciado"}
