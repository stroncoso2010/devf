"""
Prueba extremo a extremo del flujo completo (local).

Replica la entrega de Meta entregando mensajes al webhook y verifica la respuesta del
asistente en el buzón del servidor local. Genera los resultados en `resultados/`.

Ejecución:
    python src/cliente_prueba.py
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

# La consola de Windows usa cp1252: forzamos UTF-8 para no romper con acentos/emoji.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from config import cargar_config  # noqa: E402

config = cargar_config()
PUERTO = config["servidor"]["puerto"]
PUERTO_META = config["servidor_meta"]["puerto"]
BASE = f"http://127.0.0.1:{PUERTO}"
BASE_META = f"http://127.0.0.1:{PUERTO_META}"
VERIFY_TOKEN = config["whatsapp"]["verify_token"]

RUTA_RESULTADOS = RAIZ / "resultados"


def payload_whatsapp(telefono: str, texto: str) -> Dict[str, Any]:
    """Construye un payload con la misma forma que envía Meta."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID_LOCAL",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": config["whatsapp"]["phone_id"],
                            },
                            "contacts": [
                                {"profile": {"name": "Cliente Demo"}, "wa_id": telefono}
                            ],
                            "messages": [
                                {
                                    "from": telefono,
                                    "id": f"wamid.TEST{int(time.time() * 1000)}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def enviar_mensaje_entrante(telefono: str, texto: str) -> Dict[str, Any]:
    """Entrega el mensaje al webhook, como haría Meta."""
    inicio = time.perf_counter()
    r = requests.post(f"{BASE}/webhook", json=payload_whatsapp(telefono, texto), timeout=30)
    duracion = int((time.perf_counter() - inicio) * 1000)
    return {
        "telefono": telefono,
        "texto": texto,
        "http_webhook": r.status_code,
        "respuesta_webhook": r.json() if r.content else {},
        "ms_respuesta_webhook": duracion,
    }


def leer_buzon() -> List[Dict[str, Any]]:
    r = requests.get(f"{BASE_META}/mensajes", timeout=10)
    return r.json().get("mensajes", [])


def ultimo_registro() -> Dict[str, Any]:
    """Última entrada de la bitácora del asistente (fuente, modelo, folio)."""
    try:
        r = requests.get(f"{BASE}/bitacora", timeout=10)
        registros = r.json().get("registros", [])
        return registros[-1] if registros else {}
    except requests.RequestException:
        return {}


def esperar_respuesta(buzon_previo: int, segundos: int = 90) -> Dict[str, Any]:
    """Espera a que el asistente envíe su respuesta (BackgroundTasks)."""
    limite = time.time() + segundos
    while time.time() < limite:
        buzon = leer_buzon()
        if len(buzon) > buzon_previo:
            return buzon[-1]
        time.sleep(0.6)
    return {"error": "timeout esperando respuesta", "cuerpo": ""}


def verificar_webhook() -> Dict[str, Any]:
    """Meta verifica las credenciales del webhook."""
    r = requests.get(
        f"{BASE}/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "CHALLENGE_12345",
        },
        timeout=10,
    )
    return {
        "http": r.status_code,
        "cuerpo": r.text,
        "correcto": r.status_code == 200 and r.text == "CHALLENGE_12345",
    }


def main() -> None:
    RUTA_RESULTADOS.mkdir(exist_ok=True)
    inicio_total = time.perf_counter()
    pasos: List[Dict[str, Any]] = []
    transcript: List[Dict[str, Any]] = []

    print("=" * 72)
    print("  PRUEBA COMPLETA - Asistente de Estatus de Pedidos")
    print("=" * 72)

    # 0. Limpieza de estado
    requests.post(f"{BASE}/admin/reiniciar", timeout=10)
    requests.delete(f"{BASE_META}/mensajes", timeout=10)

    # 1. Salud de los servicios
    salud = requests.get(f"{BASE}/health", timeout=20).json()
    pasos.append({"paso": "1. Health check", "resultado": salud})
    print(f"\n[1] Health -> {json.dumps(salud, ensure_ascii=False)}")

    # 2. Verificacion de credenciales del webhook
    verif = verificar_webhook()
    pasos.append({"paso": "2. Verificacion del webhook (GET)", "resultado": verif})
    print(f"[2] Verificacion webhook -> HTTP {verif['http']} '{verif['cuerpo']}'")

    # 3. Usuario NUEVO: mensaje de saludo
    caso1 = enviar_mensaje_entrante("5215512345678", "Hola, buenas tardes")
    r1 = esperar_respuesta(0)
    pasos.append({"paso": "3. Usuario nuevo saluda", "entrada": caso1, "salida": r1})
    transcript.append({"caso": "Usuario nuevo (saludo)", **caso1, "respuesta": r1.get("cuerpo", ""), "fuente": ultimo_registro().get("fuente", "")})
    print(f"[3] Usuario nuevo -> {r1.get('cuerpo', '')[:120]}")

    # 4. Usuario conocido: consulta de estatus con folio
    caso2 = enviar_mensaje_entrante("5215512345678", "¿Cuál es el estatus de mi pedido PED-1002?")
    r2 = esperar_respuesta(1)
    pasos.append({"paso": "4. Usuario conocido pide estatus con folio", "entrada": caso2, "salida": r2})
    transcript.append({"caso": "Estatus con folio", **caso2, "respuesta": r2.get("cuerpo", ""), "fuente": ultimo_registro().get("fuente", "")})
    print(f"[4] Estatus PED-1002 -> {r2.get('cuerpo', '')[:160]}")

    # 5. Usuario conocido: pregunta sin folio (responde el LLM)
    caso3 = enviar_mensaje_entrante("5215512345678", "Oye, ¿ya llegó mi compra?")
    r3 = esperar_respuesta(2)
    pasos.append({"paso": "5. Pregunta sin folio (LLM)", "entrada": caso3, "salida": r3})
    transcript.append({"caso": "Estatus sin folio (regla)", **caso3, "respuesta": r3.get("cuerpo", ""), "fuente": ultimo_registro().get("fuente", "")})
    print(f"[5] Pregunta sin folio -> {r3.get('cuerpo', '')[:160]}")

    # 6. Usuario nuevo con pedido inexistente
    caso4 = enviar_mensaje_entrante("5215599998888", "Revisa el pedido PED-9999 por favor")
    r4 = esperar_respuesta(3)
    pasos.append({"paso": "6. Pedido inexistente", "entrada": caso4, "salida": r4})
    transcript.append({"caso": "Pedido inexistente", **caso4, "respuesta": r4.get("cuerpo", ""), "fuente": ultimo_registro().get("fuente", "")})
    print(f"[6] PED-9999 -> {r4.get('cuerpo', '')[:160]}")

    # 7. Usuario conocido: conversacion general -> responde el LLM con tono controlado
    caso5 = enviar_mensaje_entrante("5215512345678", "¿Puedo comprar sin pasar a la tienda?")
    r5 = esperar_respuesta(4)
    pasos.append({"paso": "7. Conversacion general (LLM, tono controlado)", "entrada": caso5, "salida": r5})
    transcript.append({"caso": "Conversacion general (LLM)", **caso5, "respuesta": r5.get("cuerpo", ""), "fuente": ultimo_registro().get("fuente", "")})
    print(f"[7] Metodos de pago -> {r5.get('cuerpo', '')[:200]}")

    # 8. Estadisticas finales
    stats = requests.get(f"{BASE}/stats", timeout=20).json()
    pasos.append({"paso": "8. Estadisticas finales", "resultado": stats})
    print(f"[8] Stats -> {json.dumps(stats, ensure_ascii=False)}")

    duracion_total = int((time.perf_counter() - inicio_total) * 1000)

    # ---------------------------------------------------------------
    # Persistencia de resultados
    # ---------------------------------------------------------------
    metricas = {
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duracion_total_ms": duracion_total,
        "pasos": len(pasos),
        "mensajes_entrantes": len(transcript),
        "respuestas_generadas": len(leer_buzon()),
        "modelo_ollama": config["ollama"]["modelo"],
        "url_ollama": config["ollama"]["url"],
        "usuarios_conocidos": stats.get("usuarios_conocidos"),
        "servidor": f"http://127.0.0.1:{PUERTO}",
        "servidor_meta": f"http://127.0.0.1:{PUERTO_META}",
    }

    (RUTA_RESULTADOS / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RUTA_RESULTADOS / "bitacora.json").write_text(
        json.dumps(pasos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RUTA_RESULTADOS / "conversacion.json").write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Conversacion legible en Markdown
    lineas = [
        "# Conversacion de la prueba - Asistente de Estatus de Pedidos",
        "",
        f"**Fecha:** {metricas['fecha']}  ",
        f"**Modelo:** `{config['ollama']['modelo']}` (Ollama local del PC)  ",
        f"**Duracion de la prueba local:** {duracion_total} ms",
        "",
    ]
    for item in transcript:
        lineas.append(f"### {item['caso']}")
        lineas.append("")
        lineas.append(f"**Telefono:** `{item['telefono']}`")
        lineas.append("")
        lineas.append(f"**Usuario:** {item['texto']}")
        lineas.append("")
        lineas.append(f"**Bot** (`fuente: {item.get('fuente', '-')}`):")
        lineas.append("")
        lineas.append("```")
        lineas.append(item["respuesta"])
        lineas.append("```")
        lineas.append("")
    (RUTA_RESULTADOS / "CONVERSACION.md").write_text("\n".join(lineas), encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"  PRUEBA COMPLETADA en {duracion_total} ms")
    print(f"  Resultados en: {RUTA_RESULTADOS}")
    print("=" * 72)


if __name__ == "__main__":
    main()
