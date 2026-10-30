"""
Servidor local de la Graph API de Meta (WhatsApp Cloud API).

Permite ejecutar TODO el challenge sin credenciales reales de Meta:

  POST /v19.0/{phone_id}/messages  -> recibe lo que el asistente "envía"
  GET  /mensajes                   -> lista los mensajes enviados
  DELETE /mensajes                 -> limpia el buzón
  GET  /estado                     -> estado (latido) del servidor local

Es un servidor FastAPI independiente que corre en otro puerto.
"""

import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import cargar_config  # noqa: E402

config = cargar_config()

app = FastAPI(
    title="Servidor local Graph API (WhatsApp Cloud API)",
    description="Sustituye a Meta for Developers en el entorno local",
    version="1.0.0",
)

buzon: List[Dict[str, Any]] = []


@app.get("/estado")
async def estado():
    """Latido del servidor local."""
    return {
        "servidor": "servidor-meta",
        "activo": True,
        "mensajes_recibidos": len(buzon),
        "hora": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/{version}/{phone_id}/messages")
async def enviar_mensaje(version: str, phone_id: str, request: Request):
    """Recibe el envío que el asistente hace a WhatsApp y lo archiva."""
    body = await request.json()
    registro = {
        "id": f"wamid.{uuid.uuid4().hex[:24]}",
        "version_api": version,
        "phone_id": phone_id,
        "para": body.get("to"),
        "tipo": body.get("type"),
        "cuerpo": (body.get("text") or {}).get("body", ""),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    buzon.append(registro)
    print(f"[SERVIDOR-META] -> {registro['para']}: {registro['cuerpo'][:90]}")

    # Respuesta con la misma forma que la Graph API real
    return JSONResponse(
        content={
            "messaging_product": "whatsapp",
            "contacts": [{"input": registro["para"], "wa_id": registro["para"]}],
            "messages": [{"id": registro["id"], "message_status": "accepted"}],
        },
        status_code=200,
    )


@app.get("/mensajes")
async def listar_mensajes():
    """Buzón: todo lo que el asistente ha enviado."""
    return {"total": len(buzon), "mensajes": buzon}


@app.delete("/mensajes")
async def limpiar_mensajes():
    buzon.clear()
    return {"status": "buzon_limpio"}
