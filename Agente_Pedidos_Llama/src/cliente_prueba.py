"""
Cliente de prueba local: envia los mensajes al webhook tal como lo haria
Meta, y verifica las respuestas en el mock de Graph + el historial en
Llama Stack + el disparo de herramientas y reglas.

No requiere WhatsApp real ni ngrok: todo corre en 127.0.0.1.

    python src/cliente_prueba.py

Escenarios del challenge:
  1. Pregunta frecuente  -> debe disparar buscar_pregunta_frecuente
  2. Cargo duplicado     -> regla de urgencia SIN pasar por Llama
  3. Hablar con persona  -> regla de escalamiento SIN pasar por Llama
  4. Estado de pedido    -> consultar_pedido (function calling)
  5. Memoria + follow-up -> continuidad de la conversacion (mismo telefono)
  6. Pedido inexistente  -> validacion de argumentos del modelo
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

BASE = "http://127.0.0.1:8030"
GRAPH = "http://127.0.0.1:8890/v19.0/LOCAL_1234567890/messages"
RAIZ = os.path.join(os.path.dirname(__file__), "..")
VERIFY_TOKEN = json.load(
    open(os.path.join(RAIZ, "configuracion", "configuracion.json"), encoding="utf-8")
)["whatsapp"]["verify_token"]

CONTADOR = [0]
_VISTOS = [0]


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


def mostrar_turno(t: dict) -> None:
    origen = t["fuente"].upper()
    fases = t.get("fases_ms", {})
    print(f"\n  TURNO {origen} | ciclo {t['latencia_ms']} ms "
          f"(razonamiento {fases.get('razonamiento', 0)} ms | "
          f"accion {fases.get('accion', 0)} ms) | "
          f"items {t.get('items_antes')} -> {t.get('items_despues')}")
    print(f"    usuario : {t['mensaje']}")
    print(f"    agente  : {(t['respuesta'] or '')[:150]}")
    if t.get("regla"):
        print(f"    regla   : {t['regla']} (sin llamada al modelo)")
    if t.get("error"):
        print(f"    error   : {t['error']} -> fallback enviado")
    for h in t.get("herramientas_llamadas", []):
        estado = "OK" if h.get("ok") else "RECHAZADA"
        print(f"    tool    : {h['nombre']}({h.get('argumentos')}) "
              f"[{estado}, {h.get('duracion_ms')} ms]")
    rec = t.get("recorte", {})
    if rec.get("items_borrados"):
        print(f"    recorte : -{rec['items_borrados']} items (limite de historial)")


def esperar_turnos(cantidad: int, tiempo_max: int = 180) -> list:
    """Espera hasta que /bitacora tenga `cantidad` turnos, imprimiendo los nuevos."""
    inicio = time.time()
    while time.time() - inicio < tiempo_max:
        turnos = requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]
        for t in turnos[_VISTOS[0]:]:
            mostrar_turno(t)
        _VISTOS[0] = len(turnos)
        if len(turnos) >= cantidad:
            return turnos
        time.sleep(3)
    return requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]


def escenario_1_faq() -> None:
    """Pregunta frecuente: debe disparar buscar_pregunta_frecuente."""
    print("\n=== ESCENARIO 1: pregunta frecuente (function calling) ===")
    mandar("5215511110009", "Hola, ¿qué formas de pago aceptan?")
    print("  -> enviado: ¿qué formas de pago aceptan?")
    esperar_turnos(1, 240)


def escenario_2_cargo_duplicado() -> None:
    """Cargo duplicado: regla de urgencia, sin modelo."""
    print("\n=== ESCENARIO 2: cargo duplicado (regla de urgencia) ===")
    mandar("5215511110009", "Me cobraron dos veces el pedido, hay un cargo duplicado!")
    print("  -> enviado: Me cobraron dos veces el pedido, hay un cargo duplicado!")
    esperar_turnos(2, 120)


def escenario_3_escalado() -> None:
    """Hablar con una persona: regla de escalamiento, sin modelo."""
    print("\n=== ESCENARIO 3: hablar con persona (regla de escalamiento) ===")
    mandar("5215511110009", "Quiero hablar con una persona, por favor")
    print("  -> enviado: Quiero hablar con una persona, por favor")
    esperar_turnos(3, 120)


def escenario_4_pedido() -> None:
    """Estado de un pedido: consultar_pedido (el caso practico del tema)."""
    print("\n=== ESCENARIO 4: consultar pedido (function calling) ===")
    mandar("5215511110009", "¿Dónde está mi pedido 9988?")
    print("  -> enviado: ¿Dónde está mi pedido 9988?")
    esperar_turnos(4, 300)


def escenario_5_memoria() -> None:
    """Follow-up que depende del turno anterior (continuidad de memoria)."""
    print("\n=== ESCENARIO 5: memoria (follow-up del pedido) ===")
    mandar("5215511110009", "¿Y en qué fecha llega?")
    print("  -> enviado: ¿Y en qué fecha llega?")
    esperar_turnos(5, 300)


def escenario_6_pedido_inexistente() -> None:
    """Pedido inexistente: el modelo pide la herramienta, la validacion responde."""
    print("\n=== ESCENARIO 6: pedido inexistente (validacion) ===")
    mandar("5215511110009", "Necesito el status del pedido 123456")
    print("  -> enviado: Necesito el status del pedido 123456")
    esperar_turnos(6, 300)


def verificar_llama_stack() -> None:
    print("\n=== VERIFICACION EN LLAMA STACK ===")
    estado = requests.get(f"{BASE}/estado", timeout=10).json()
    print(f"  sesiones: {estado['total_sesiones']} | limite items: {estado['max_items_historial']}")
    for sesion in estado["sesiones"]:
        print(f"    {sesion['telefono']}: turnos={sesion['turnos']} "
              f"borrados={sesion['items_borrados']}")
    hist = requests.get(f"{BASE}/historial/5215511110009", timeout=10).json()
    print(f"  items guardados: {len(hist['items'])}")
    for item in hist["items"][-4:]:
        print(f"    [{item['rol'] or item['tipo']}] {item['texto'][:75]}")


def verificar_mensajes_salientes() -> None:
    print("\n=== MENSAJES SALIENTES (mock de Meta) ===")
    r = requests.get(GRAPH, timeout=10).json()
    print(f"  total enviados: {r['total']}")
    for m in r["mensajes"]:
        print(f"    -> {m['to']}: {m['texto'][:95]}")


def resumen() -> None:
    """Veredicto por escenario contra lo que exige el challenge.

    Se busca cada turno por su CONTENIDO (no por posicion) para que el
    veredicto sea robusto ante reintentos o turnos de error.
    """
    print("\n" + "=" * 78)
    print("VEREDICTO POR ESCENARIO")
    print("=" * 78)
    turnos = requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]

    def buscar(fragmento):
        for t in turnos:
            if fragmento in t["mensaje"]:
                return t
        return None

    def tuvo_tool(t, nombre):
        return t is not None and any(
            h["nombre"] == nombre for h in t.get("herramientas_llamadas", [])
        )

    t_faq = buscar("formas de pago")
    t_dup = buscar("cargo duplicado")
    t_esc = buscar("hablar con una persona")
    t_ped = buscar("pedido 9988")
    t_fup = buscar("fecha llega")
    t_no = buscar("123456")

    checks = [
        ("1 FAQ dispara buscar_pregunta_frecuente",
         tuvo_tool(t_faq, "buscar_pregunta_frecuente")),
        ("2 Cargo duplicado -> regla urgencia (sin Llama)",
         t_dup is not None and t_dup["fuente"] == "regla"
         and t_dup["regla"] == "urgencia_fraude"),
        ("3 Hablar con persona -> regla escalamiento (sin Llama)",
         t_esc is not None and t_esc["fuente"] == "regla"
         and t_esc["regla"] == "escalado_humano"),
        ("4 Pedido -> consultar_pedido ejecutada",
         tuvo_tool(t_ped, "consultar_pedido")),
        ("5 Memoria: follow-up sin repetir el numero",
         t_fup is not None and t_fup["fuente"] == "llama-stack"
         and "9988" not in t_fup["mensaje"]),
        ("6 Pedido inexistente -> respuesta honesta, sin inventar",
         t_no is not None and t_no["fuente"] == "llama-stack"
         and "9988" not in t_no["respuesta"]
         and "Estafeta" not in t_no["respuesta"]),
    ]
    todos = True
    for nombre, ok in checks:
        marca = "OK   " if ok else "FALLA"
        todos = todos and ok
        print(f"  [{marca}] {nombre}")
    print(f"\n  TOTAL: {'TODOS LOS ESCENARIOS OK' if todos else 'HAY FALLOS'}")


def main() -> None:
    print("=" * 78)
    print("PRUEBA LOCAL: AGENTE DE ATENCION A PEDIDOS (function calling)")
    print("=" * 78)

    requests.post(f"{BASE}/reiniciar", timeout=10)
    requests.delete(GRAPH, timeout=10)

    if not verificar_handshake():
        print("El handshake fallo: revisa el servidor del webhook.")
        sys.exit(1)

    escenario_1_faq()
    escenario_2_cargo_duplicado()
    escenario_3_escalado()
    escenario_4_pedido()
    escenario_5_memoria()
    escenario_6_pedido_inexistente()
    verificar_llama_stack()
    verificar_mensajes_salientes()
    resumen()

    # Persistir resultados
    os.makedirs(os.path.join(RAIZ, "resultados"), exist_ok=True)
    turnos = requests.get(f"{BASE}/bitacora", timeout=10).json()["turnos"]
    with open(os.path.join(RAIZ, "resultados", "conversacion.json"), "w", encoding="utf-8") as f:
        json.dump(turnos, f, ensure_ascii=False, indent=2)
    estado = requests.get(f"{BASE}/estado", timeout=10).json()
    with open(os.path.join(RAIZ, "resultados", "estado_sesiones.json"), "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    salientes = requests.get(GRAPH, timeout=10).json()
    with open(os.path.join(RAIZ, "resultados", "mensajes_salientes.json"), "w", encoding="utf-8") as f:
        json.dump(salientes, f, ensure_ascii=False, indent=2)
    print("\n[resultados] conversacion.json, estado_sesiones.json, mensajes_salientes.json")


if __name__ == "__main__":
    main()
