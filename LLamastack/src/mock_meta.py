"""
Mock local de la API de Graph de Meta (WhatsApp).

Sustituye a la API real en las pruebas locales: acepta los POST de envio del
webhook, guarda los mensajes salientes y los sirve por GET para verificarlos.

  POST /v19.0/{phone_id}/messages  -> guarda y responde con un wamid ficticio
  GET  /v19.0/{phone_id}/messages  -> lista de mensajes enviados
  DELETE /v19.0/{phone_id}/messages -> limpia (reiniciar prueba)

No requiere token de Meta: el webhook apunta aqui con graph_api_base local.
"""

import time
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock API Graph (Meta) - pruebas locales")

# Mensajes enviados por el webhook, en orden de llegada.
ENVIADOS: List[Dict[str, Any]] = []
_CONTADOR = [0]


@app.post("/v19.0/{phone_id}/messages")
async def enviar(phone_id: str, request: Request):
    cuerpo: Dict[str, Any] = await request.json()
    _CONTADOR[0] += 1
    registro = {
        "wamid": f"mock_wamid_{_CONTADOR[0]:04d}",
        "phone_id": phone_id,
        "to": cuerpo.get("to", ""),
        "texto": cuerpo.get("text", {}).get("body", ""),
        "context": cuerpo.get("context"),
        "recibido_en": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    ENVIADOS.append(registro)
    return {
        "messaging_product": "whatsapp",
        "messages": [{"id": registro["wamid"]}],
    }


@app.get("/v19.0/{phone_id}/messages")
async def listar(phone_id: str):
    return {"phone_id": phone_id, "total": len(ENVIADOS), "mensajes": ENVIADOS}


@app.delete("/v19.0/{phone_id}/messages")
async def limpiar(phone_id: str):
    total = len(ENVIADOS)
    ENVIADOS.clear()
    _CONTADOR[0] = 0
    return {"status": "limpio", "borrados": total}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mock_meta:app", host="127.0.0.1", port=8890, log_level="warning")
