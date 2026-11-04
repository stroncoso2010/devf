"""
Herramientas (function calling): el contrato entre el modelo y tu codigo.

Este modulo mantiene SEPARADAS las dos piezas que exige el tema:

  1. El CONTRATO  -> `ESQUEMAS`: nombre, descripcion y parametros tipados que
     Llama lee para decidir cuando y como pedir la herramienta.
  2. La IMPLEMENTACION -> las funciones `consultar_pedido` y
     `buscar_pregunta_frecuente`: codigo comun de Python que corre en el
     servidor contra datos reales (configuracion/catalogo.json).

Si el modelo pide una herramienta con argumentos invalidos, la validacion
`_validar_argumentos` rechaza la ejecucion ANTES de tocar los datos.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CATALOGO = os.path.join(RAIZ, "configuracion", "catalogo.json")

# ---------------------------------------------------------------------------
# Datos reales (en produccion esto seria una base de datos o una API interna)
# ---------------------------------------------------------------------------
def _cargar_catalogo() -> Dict[str, Any]:
    with open(RUTA_CATALOGO, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


CATALOGO = _cargar_catalogo()

# ---------------------------------------------------------------------------
# 1. CONTRATO: esquemas que el modelo lee (function calling)
# ---------------------------------------------------------------------------
ESQUEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "consultar_pedido",
        "description": (
            "Recibe un numero_pedido entero y devuelve el estatus actual del "
            "pedido desde el sistema de logistica: estado, transportista, guia, "
            "fecha estimada de entrega y ultimo movimiento registrado. Usala "
            "EXCLUSIVAMENTE cuando el cliente pregunte por el estado, rastreo "
            "o ubicacion de un pedido concreto; no la uses para dudas generales "
            "de la tienda (horarios, garantias, pagos)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "numero_pedido": {
                    "type": "integer",
                    "description": "Numero de pedido entero, por ejemplo 4521",
                }
            },
            "required": ["numero_pedido"],
        },
    },
    {
        "type": "function",
        "name": "buscar_pregunta_frecuente",
        "description": (
            "Busca en la base de preguntas frecuentes de la tienda la respuesta "
            "oficial a dudas comunes del cliente (horarios de atencion, garantia, "
            "formas de pago, tiempos de envio, devoluciones, rastreo). Recibe un "
            "tema y devuelve la pregunta y la respuesta oficial. Usala antes de "
            "responder dudas generales; no la uses para consultar el estatus de "
            "un pedido especifico."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tema": {
                    "type": "string",
                    "description": (
                        "Tema corto en español: horarios, garantia, pagos, "
                        "envios, devoluciones o seguimiento"
                    ),
                }
            },
            "required": ["tema"],
        },
    },
]


# ---------------------------------------------------------------------------
# Validacion de argumentos propuestos por el modelo
# ---------------------------------------------------------------------------
def _validar_argumentos(nombre: str, argumentos: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Rechaza la ejecucion si los argumentos que pidio el modelo son invalidos
    (faltantes, mal tipados o fuera de rango). El servidor NUNCA toca los
    datos sin pasar por aqui.
    """
    esquema = next((e for e in ESQUEMAS if e["name"] == nombre), None)
    if esquema is None:
        return False, f"herramienta desconocida: {nombre}"

    requeridos = esquema["parameters"].get("required", [])
    for campo in requeridos:
        if campo not in argumentos or argumentos[campo] in (None, ""):
            return False, f"falta el parametro obligatorio '{campo}'"

    if nombre == "consultar_pedido":
        valor = argumentos["numero_pedido"]
        # El modelo a veces manda "9988" como texto con comillas
        if isinstance(valor, str) and valor.strip().isdigit():
            valor = int(valor.strip())
            argumentos["numero_pedido"] = valor
        if not isinstance(valor, int):
            return False, "numero_pedido debe ser un entero"
        if valor <= 0:
            return False, "numero_pedido debe ser positivo"

    if nombre == "buscar_pregunta_frecuente":
        tema = argumentos.get("tema", "")
        if not isinstance(tema, str) or not tema.strip():
            return False, "tema debe ser texto no vacio"

    return True, ""


# ---------------------------------------------------------------------------
# 2. IMPLEMENTACION: las funciones reales del servidor
# ---------------------------------------------------------------------------
def consultar_pedido(numero_pedido: int) -> Dict[str, Any]:
    """
    Consulta el estatus real de un pedido en el catalogo interno.
    Devuelve un dict con ok/datos o ok/error (nunca lanza excepcion al modelo).
    """
    pedido = CATALOGO["pedidos"].get(str(int(numero_pedido)))
    if pedido is None:
        return {
            "ok": False,
            "error": f"No existe el pedido {numero_pedido} en el sistema.",
        }
    return {
        "ok": True,
        "numero_pedido": pedido["numero_pedido"],
        "estado": pedido["estado"],
        "transportista": pedido["transportista"] or "no asignado",
        "guia": pedido["guia"] or "sin guia aun",
        "fecha_pedido": pedido["fecha_pedido"],
        "fecha_estimada": pedido["fecha_estimada"] or "sin fecha estimada",
        "ultimo_movimiento": pedido["ultimo_movimiento"],
        "total": pedido["total"],
        "moneda": pedido["moneda"],
        "pagado": pedido["pagado"],
    }


def buscar_pregunta_frecuente(tema: str) -> Dict[str, Any]:
    """
    Busca la respuesta oficial en la base de preguntas frecuentes.
    Coincide por palabra clave del tema (sin acentos ni puntuacion).
    """
    limpio = re.sub(r"[^a-z0-9\s]", " ", tema.lower()).strip()
    # sinonimos minimos para que el modelo encuentre la entrada correcta
    sinoni = {
        "horario": "horarios",
        "atencion": "horarios",
        "garantia": "garantia",
        "garantías": "garantia",
        "pago": "pagos",
        "pagar": "pagos",
        "envio": "envios",
        "envíos": "envios",
        "entrega": "envios",
        "devolucion": "devoluciones",
        "reembolso": "devoluciones",
        "rastreo": "seguimiento",
        "rastrear": "seguimiento",
        "guia": "seguimiento",
        "tracking": "seguimiento",
    }
    claves = limpio.split()
    for clave in claves:
        clave = sinoni.get(clave, clave)
        entrada = CATALOGO["preguntas_frecuentes"].get(clave)
        if entrada:
            return {"ok": True, "tema": clave, **entrada}

    # Busqueda parcial sobre las preguntas
    for clave, entrada in CATALOGO["preguntas_frecuentes"].items():
        if any(c in limpio for c in clave.split("_")):
            return {"ok": True, "tema": clave, **entrada}

    return {
        "ok": False,
        "error": (
            f"No hay pregunta frecuente para '{tema}'. Temas disponibles: "
            + ", ".join(sorted(CATALOGO["preguntas_frecuentes"]))
        ),
    }


# ---------------------------------------------------------------------------
# Ejecucion dirigida por el modelo (el servidor valida y luego corre)
# ---------------------------------------------------------------------------
def ejecutar(nombre: str, argumentos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Punto de entrada que usa el agente: valida los argumentos que pidio el
    modelo y, solo si son validos, ejecuta la funcion real.
    """
    valido, motivo = _validar_argumentos(nombre, argumentos)
    if not valido:
        return {"ok": False, "error": f"argumentos invalidos: {motivo}"}

    if nombre == "consultar_pedido":
        return consultar_pedido(argumentos["numero_pedido"])
    if nombre == "buscar_pregunta_frecuente":
        return buscar_pregunta_frecuente(argumentos["tema"])
    return {"ok": False, "error": f"herramienta no implementada: {nombre}"}
