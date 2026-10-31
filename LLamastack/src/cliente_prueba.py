"""
Cliente de prueba local: envia una conversacion al webhook tal como lo haria
Meta, y verifica las respuestas en el mock de Graph + el historial en
Llama Stack.

No requiere WhatsApp real ni ngrok: todo corre en 127.0.0.1.

    python src/cliente_prueba.py

Escenarios:
  A) 5 mensajes del mismo telefono: el 3ro y 4to dependen del primero (historial)
     y el recorte de items se dispara al superar el limite (8 items).
  B) Mensaje de escalado: regla fija, sin llamada al modelo.
  C) Mensaje de urgencia medica: regla fija, sin llamada al modelo.
  D) Segundo telefono: memoria aislada por numero.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

BASE = "http://127.0.0.1:8020"
GRAPH = "http://127.0.0.1:8890/v19.0/LOCAL_1234567890/messages"
VERIFY_TOKEN = json.load(
    open(os.path.join(os.path.dirname(__file__), "..", "configuracion", "configuracion.json"), encoding="utf-8")
)["whatsapp"]["verify_token"]

CONTADOR = [0]


def mensaje(telefono: str, texto: str) -> dict:
    """Arma el payload de mensaje entrante con el formato de Meta."""
    CONTADOR[0] += 1
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": f"wamid.TEST{CONTADOR[0]:03d}",
                                    "from": telefono,
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def mandar(telefono: str, texto: str) -> dict:
    r = requests.post(f"{BASE}/webhook", json=mensaje(telefono, texto), timeout=10)
    return r.json()


def verificar_handshake() -> bool:
    r = requests.get(
        f"{BASE}/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "12345"},
        timeout=10,
    )
    ok = r.status_code == 200 and "12345" in r.text
    print(f"[HANDSHAKE] {'OK' if ok else 'FALLO'} -> {r.status_code} {r.text[:50]}")
    return ok


# Ultimo turno ya impreso por esperar_turnos (contador entre llamadas).
_VISTOS = [0]


def esperar_turnos(cantidad: int, tiempo_max: int = 90, imprimir: bool = False) -> list:
    """
    Espera hasta que /bitacora tenga `cantidad` turnos, imprimiendo los nuevos
    a medida que llegan (en local cada turno del modelo puede tardar varios
    minutos, asi se ve el avance en vivo).
    """
    inicio = time.time()
    while time.time() - inicio < tiempo_max:
        turnos = requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]
        if imprimir:
            for t in turnos[_VISTOS[0]:]:
                mostrar_turno(t)
            _VISTOS[0] = len(turnos)
        if len(turnos) >= cantidad:
            return turnos
        time.sleep(3)
    return requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]


def mostrar_turno(t: dict) -> None:
    origen = t["fuente"].upper()
    lat = t["latencia_ms"]
    print(f"\n  TURNO {origen} | {lat} ms | items {t.get('items_antes')} -> {t.get('items_despues')}")
    print(f"    usuario : {t['mensaje']}")
    print(f"    agente  : {t['respuesta'][:140]}")
    if t.get("regla"):
        print(f"    regla   : {t['regla']}")
    rec = t.get("recorte", {})
    if rec.get("items_borrados"):
        print(f"    recorte : -{rec['items_borrados']} items (limite de historial aplicado)")


def escenario_a() -> None:
    """Conversacion de 5 mensajes: memoria, referencia y recorte de historial."""
    print("\n=== ESCENARIO A: conversacion con memoria (5 mensajes) ===")
    tel = "5215511110009"
    mensajes = [
        "Hola, quiero una cita dental para mi perrito Max",
        "El martes me queda mejor",
        "Son las 10 de la manana?",
        "Perfecto, agendala",
        "Cual fue el servicio que pedi al inicio?",
    ]
    for texto in mensajes:
        mandar(tel, texto)
        print(f"  -> enviado: {texto}")
        time.sleep(1)
    # En local cada turno del modelo puede tardar 40-140 s: se espera hasta
    # 12 minutos para los 5 turnos, imprimiendo cada uno al llegar.
    turnos = esperar_turnos(5, 720, imprimir=True)
    if len(turnos) < 5:
        print(f"  [AVISO] solo llegaron {len(turnos)} de 5 turnos")


def escenario_b() -> None:
    """Escalado a persona: regla fija, sin modelo."""
    print("\n=== ESCENARIO B: escalado a humano (regla fija) ===")
    tel = "5215511110009"
    mandar(tel, "Quiero hablar con una persona, por favor")
    print("  -> enviado: Quiero hablar con una persona, por favor")
    esperar_turnos(6, 300, imprimir=True)


def escenario_c() -> None:
    """Urgencia medica: regla fija, sin modelo."""
    print("\n=== ESCENARIO C: urgencia medica (regla fija) ===")
    tel = "5215511110009"
    mandar(tel, "Mi perrito esta sangrando mucho, es una urgencia!")
    print("  -> enviado: Mi perrito esta sangrando mucho, es una urgencia!")
    esperar_turnos(7, 300, imprimir=True)


def escenario_d() -> None:
    """Segundo telefono: la memoria es por numero, no global."""
    print("\n=== ESCENARIO D: segundo telefono (memoria aislada) ===")
    tel2 = "5215522220001"
    mandar(tel2, "Hola, es para mi gata")
    print("  -> enviado: Hola, es para mi gata")
    esperar_turnos(8, 300, imprimir=True)
    hist = requests.get(f"{BASE}/historial/{tel2}", timeout=10).json()
    print(f"  historial Llama Stack de {tel2}: {len(hist['items'])} items")


def verificar_llama_stack() -> None:
    """Confirma que la memoria vive en Llama Stack y esta recortada."""
    print("\n=== VERIFICACION EN LLAMA STACK ===")
    estado = requests.get(f"{BASE}/estado", timeout=10).json()
    print(f"  sesiones: {estado['total_sesiones']} | limite items: {estado['max_items_historial']}")
    for sesion in estado["sesiones"]:
        print(f"    {sesion['telefono']}: conv={sesion['conversation_id'][:22]}... "
              f"turnos={sesion['turnos']} borrados={sesion['items_borrados']}")
    hist = requests.get(f"{BASE}/historial/5215511110009", timeout=10).json()
    print(f"  items guardados (tel principal): {len(hist['items'])}")
    for item in hist["items"][-4:]:
        print(f"    [{item['rol'] or item['tipo']}] {item['texto'][:70]}")


def verificar_mensajes_salientes() -> None:
    """Los mensajes que el webhook envio al mock de Graph de Meta."""
    print("\n=== MENSAJES SALIENTES (mock de Meta) ===")
    r = requests.get(GRAPH, timeout=10).json()
    print(f"  total enviados: {r['total']}")
    for m in r["mensajes"]:
        print(f"    -> {m['to']}: {m['texto'][:90]}")


def main() -> None:
    print("=" * 78)
    print("PRUEBA LOCAL DEL AGENTE DE LA VETERINARIA (Llama Stack + Ollama)")
    print("=" * 78)

    # Limpieza inicial
    requests.post(f"{BASE}/reiniciar", timeout=10)
    requests.delete(GRAPH, timeout=10)

    if not verificar_handshake():
        print("El handshake fallo: revisa el servidor del webhook.")
        sys.exit(1)

    escenario_a()
    escenario_b()
    escenario_c()
    escenario_d()
    verificar_llama_stack()
    verificar_mensajes_salientes()

    # Persistir los resultados para el reporte
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "resultados"), exist_ok=True)
    turnos = requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]
    with open(os.path.join(os.path.dirname(__file__), "..", "resultados", "conversacion.json"), "w", encoding="utf-8") as f:
        json.dump(turnos, f, ensure_ascii=False, indent=2)
    estado = requests.get(f"{BASE}/estado", timeout=10).json()
    with open(os.path.join(os.path.dirname(__file__), "..", "resultados", "estado_sesiones.json"), "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    salientes = requests.get(GRAPH, timeout=10).json()
    with open(os.path.join(os.path.dirname(__file__), "..", "resultados", "mensajes_salientes.json"), "w", encoding="utf-8") as f:
        json.dump(salientes, f, ensure_ascii=False, indent=2)
    print("\n[resultados] conversacion.json, estado_sesiones.json, mensajes_salientes.json")


if __name__ == "__main__":
    main()
