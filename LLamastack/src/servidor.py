"""
Servidor del webhook de WhatsApp (FastAPI).

Endpoints:
  GET  /webhook       -> verificacion inicial de Meta
  POST /webhook       -> mensaje entrante; responde a Meta de inmediato y
                         delega el trabajo pesado a BackgroundTasks
  GET  /estado        -> sesiones y limites de historial
  GET  /historial/{tel} -> items guardados en Llama Stack para ese telefono
  GET  /bitacora      -> trazas de los turnos procesados
  POST /reiniciar     -> borra las conversaciones para repetir la prueba

El endpoint de recepcion usa BackgroundTasks: primero se responde 200 a Meta
(con el id de mensaje) y despues se procesa el mensaje con el agente. Asi Meta
no reintenta la entrega ni se duplican las respuestas.
"""

import logging
import os
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from agente import AgenteVeterinario
from config import cargar_configuracion
from normalizacion import normalizar_numero_mx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("webhook")

config = cargar_configuracion()
agente = AgenteVeterinario(config)

app = FastAPI(title=config["servidor"].get("titulo", "Agente veterinario"))

# Mensajes ya procesados: Meta puede reintentar la entrega; el id del mensaje
# evita contestar dos veces lo mismo.
_mensajes_procesados: set = set()


# ---------------------------------------------------------------------------
# Verificacion del webhook (handshake inicial de Meta)
# ---------------------------------------------------------------------------
@app.get("/webhook")
async def verificar_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == config["whatsapp"]["verify_token"]:
        log.info("Webhook verificado correctamente")
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
    return JSONResponse(status_code=403, content={"error": "token de verificacion invalido"})


# ---------------------------------------------------------------------------
# Recepcion de mensajes
# ---------------------------------------------------------------------------
def _procesar_y_responder(wamid: str, telefono: str, texto: str) -> None:
    """
    Procesa el mensaje con el agente y 'envia' la respuesta a Meta.

    Se define como funcion SINCRONA a proposito: FastAPI/Starlette ejecuta las
    tareas sincronas en un threadpool, de modo que las llamadas bloqueantes a
    Llama Stack y Ollama no congelan el event loop (mientras el modelo genera,
    el webhook sigue respondiendo a Meta).
    """
    traza = agente.procesar(telefono, texto)
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": traza["respuesta"]},
        "context": {"message_id": wamid},
    }
    # Envio a la API de Graph (en esta configuracion: el mock local).
    import requests

    url = (
        f"{config['whatsapp']['graph_api_base']}/{config['whatsapp']['graph_api_version']}"
        f"/{config['whatsapp']['phone_id']}/messages"
    )
    try:
        respuesta = requests.post(url, json=payload, timeout=10)
        traza["envio"] = {"status": respuesta.status_code, "body": respuesta.text[:300]}
    except Exception as exc:  # noqa: BLE001
        traza["envio"] = {"status": "error", "detalle": str(exc)}
    log.info(
        "TURNOS tel=%s fuente=%s lat=%sms | respuesta=%s",
        telefono, traza["fuente"], traza["latencia_ms"], traza["respuesta"][:80],
    )


@app.post("/webhook")
async def recibir_mensaje(request: Request, background: BackgroundTasks):
    cuerpo: Dict[str, Any] = await request.json()

    for entrada in cuerpo.get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value", {})
            for mensaje in valor.get("messages", []) or []:
                wamid = mensaje.get("id", "")
                telefono = normalizar_numero_mx(mensaje.get("from", ""))
                texto = (
                    mensaje.get("text", {}).get("body", "")
                    if mensaje.get("type") == "text"
                    else ""
                )
                if not wamid or not telefono or not texto:
                    continue
                if wamid in _mensajes_procesados:
                    log.info("Mensaje repetido ignorado: %s", wamid)
                    continue
                _mensajes_procesados.add(wamid)
                background.add_task(_procesar_y_responder, wamid, telefono, texto)

    # Se responde a Meta de inmediato (sin esperar al modelo).
    return {"status": "received"}


# ---------------------------------------------------------------------------
# Endpoints de inspeccion / control
# ---------------------------------------------------------------------------
@app.get("/estado")
async def estado():
    return agente.estado()


@app.get("/historial/{telefono}")
async def historial(telefono: str):
    tel = normalizar_numero_mx(telefono)
    return {"telefono": tel, "items": agente.historial(tel)}


@app.get("/bitacora")
async def bitacora():
    return {"turnos": agente.trazabilidad}


@app.post("/reiniciar")
async def reiniciar():
    agente.memoria.reiniciar()
    _mensajes_procesados.clear()
    agente.trazabilidad.clear()
    return {"status": "reiniciado", "en": time.strftime("%Y-%m-%d %H:%M:%S")}


if __name__ == "__main__":
    import uvicorn

    servidor = config["servidor"]
    uvicorn.run(
        "servidor:app",
        host=servidor.get("host", "127.0.0.1"),
        port=int(servidor.get("puerto", 8020)),
        log_level="info",
    )
