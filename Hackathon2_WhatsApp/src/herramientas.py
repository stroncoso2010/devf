"""
Herramientas (function calling) del agente de restaurante.

Este modulo mantiene SEPARADAS las dos piezas que exige el tema:

  1. El CONTRATO  -> `ESQUEMAS`: nombre, descripcion y parametros tipados que
     Llama lee para decidir cuando y como pedir la herramienta.
  2. La IMPLEMENTACION -> `consultar_disponibilidad`, `agendar_reserva` y
     `buscar_pregunta_frecuente`: codigo comun de Python que corre en el
     servidor contra datos reales (configuracion/catalogo.json) y contra el
     estado de reservas del proceso.

Reglas de negocio reales aplicadas aqui (no en el modelo):
  * Valida fecha, hora y personas ANTES de tocar la disponibilidad.
  * Rechaza grupos de mas de 8 (politica del restaurante).
  * Rechaza dias cerrado (lunes y martes) y horas fuera de turno.
  * Idempotencia: mismo telefono + fecha + hora => la misma reserva, sin duplicar.
"""

import datetime
import json
import os
import re
from typing import Any, Dict, List, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CATALOGO = os.path.join(RAIZ, "configuracion", "catalogo.json")

MAX_PERSONAS = 8


def _cargar_catalogo() -> Dict[str, Any]:
    with open(RUTA_CATALOGO, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


CATALOGO = _cargar_catalogo()

# Reservas creadas en runtime (en produccion seria una base de datos).
RESERVAS: Dict[str, Dict[str, Any]] = {}
_CONTADOR_RESERVA = [100]


# ---------------------------------------------------------------------------
# 1. CONTRATO: esquemas que el modelo lee (function calling)
# ---------------------------------------------------------------------------
ESQUEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "consultar_disponibilidad",
        "description": (
            "Recibe fecha (YYYY-MM-DD), hora (HH:MM) y personas (entero 1 a 8) "
            "y devuelve si hay mesa libre en el restaurante para ese horario, "
            "con las mesas disponibles y su capacidad. Usala ANTES de ofrecer "
            "una reserva cuando el cliente pregunte por disponibilidad; no la "
            "uses para consultar el menu ni los horarios de apertura."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD, por ejemplo 2026-11-06",
                },
                "hora": {
                    "type": "string",
                    "description": "Hora en formato HH:MM dentro de un turno, por ejemplo 20:00",
                },
                "personas": {
                    "type": "integer",
                    "description": "Numero de personas, entre 1 y 8",
                },
            },
            "required": ["fecha", "hora", "personas"],
        },
    },
    {
        "type": "function",
        "name": "agendar_reserva",
        "description": (
            "Crea una reserva de mesa con fecha (YYYY-MM-DD), hora (HH:MM), "
            "personas (entero 1 a 8) y nombre del titular. Devuelve el id de "
            "reserva, la mesa asignada y la politica de gracia de 15 minutos. "
            "Usala SOLO cuando el cliente confirme que quiere apartar la mesa "
            "y ya se haya verificado la disponibilidad; si falta fecha, hora o "
            "personas, pidelas antes de llamar. Si la reserva ya existe para "
            "ese telefono y horario, devuelve la existente sin duplicarla."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD",
                },
                "hora": {
                    "type": "string",
                    "description": "Hora en formato HH:MM",
                },
                "personas": {
                    "type": "integer",
                    "description": "Numero de personas, entre 1 y 8",
                },
                "nombre": {
                    "type": "string",
                    "description": "Nombre de quien reserva, por ejemplo Ana Perez",
                },
            },
            "required": ["fecha", "hora", "personas", "nombre"],
        },
    },
    {
        "type": "function",
        "name": "buscar_pregunta_frecuente",
        "description": (
            "Busca en la base de preguntas frecuentes del restaurante la "
            "respuesta oficial a dudas generales: menu, horarios, ubicacion, "
            "alergenos, reservas, estacionamiento, pagos o grupos. Devuelve la "
            "pregunta y la respuesta oficial. Usala antes de responder dudas "
            "generales; no la uses para disponibilidad ni para agendar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tema": {
                    "type": "string",
                    "description": (
                        "Tema corto en español: menu, horarios, ubicacion, "
                        "alergenos, reservas, estacionamiento, pagos o grupos"
                    ),
                }
            },
            "required": ["tema"],
        },
    },
]


# ---------------------------------------------------------------------------
# Validacion de argumentos propuestos por el modelo (antes de tocar datos)
# ---------------------------------------------------------------------------
def _validar_argumentos(nombre: str, argumentos: Dict[str, Any]) -> Tuple[bool, str]:
    esquema = next((e for e in ESQUEMAS if e["name"] == nombre), None)
    if esquema is None:
        return False, f"herramienta desconocida: {nombre}"

    for campo in esquema["parameters"].get("required", []):
        if campo not in argumentos or argumentos[campo] in (None, ""):
            return False, f"falta el parametro obligatorio '{campo}'"

    if nombre in ("consultar_disponibilidad", "agendar_reserva"):
        ok, motivo = _validar_fecha_hora_personas(argumentos)
        if not ok:
            return False, motivo

    if nombre == "agendar_reserva":
        nombre_titular = argumentos.get("nombre")
        if not isinstance(nombre_titular, str) or len(nombre_titular.strip()) < 3:
            return False, "nombre del titular invalido"

    if nombre == "buscar_pregunta_frecuente":
        tema = argumentos.get("tema", "")
        if not isinstance(tema, str) or not tema.strip():
            return False, "tema debe ser texto no vacio"
        if tema.lower() not in CATALOGO["preguntas_frecuentes"]:
            # Se normaliza; si aun asi no existe, se responde con los temas validos
            pass

    return True, ""


def _validar_fecha_hora_personas(argumentos: Dict[str, Any]) -> Tuple[bool, str]:
    # personas: puede llegar como texto
    personas = argumentos.get("personas")
    if isinstance(personas, str) and personas.strip().isdigit():
        personas = int(personas.strip())
        argumentos["personas"] = personas
    if not isinstance(personas, int):
        return False, "personas debe ser un entero"
    if personas < 1:
        return False, "personas debe ser mayor a 0"
    if personas > MAX_PERSONAS:
        return False, (
            f"para grupos de mas de {MAX_PERSONAS} personas se requiere "
            "evento previo con el gerente"
        )

    fecha = argumentos.get("fecha", "")
    if not isinstance(fecha, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
        return False, "fecha debe tener formato YYYY-MM-DD"
    try:
        fecha_dt = datetime.date.fromisoformat(fecha)
    except ValueError:
        return False, "fecha invalida"
    if fecha_dt < datetime.date.today():
        return False, "la fecha ya paso"
    if fecha_dt.weekday() in CATALOGO["dias_cerrado"]:
        return False, "el restaurante ese dia esta cerrado (lunes y martes)"

    hora = argumentos.get("hora", "")
    if not isinstance(hora, str) or not re.match(r"^\d{2}:\d{2}$", hora):
        return False, "hora debe tener formato HH:MM"
    todas = CATALOGO["horas"]["almuerzo"] + CATALOGO["horas"]["cena"]
    if hora not in todas:
        return False, "hora fuera de los turnos de servicio"

    # Domingo solo turno de almuerzo
    if fecha_dt.weekday() == 6 and hora in CATALOGO["horas"]["cena"]:
        return False, "los domingos solo hay servicio de almuerzo (13:00 a 17:00)"

    return True, ""


# ---------------------------------------------------------------------------
# 2. IMPLEMENTACION: las funciones reales del servidor
# ---------------------------------------------------------------------------
def _mesas_ocupadas(fecha: str, hora: str) -> set:
    ocupadas = set(CATALOGO["ocupacion_previa"].get(fecha, {}).get(hora, []))
    for reserva in RESERVAS.values():
        if reserva["fecha"] == fecha and reserva["hora"] == hora:
            ocupadas.add(reserva["mesa"])
    return ocupadas


def consultar_disponibilidad(fecha: str, hora: str, personas: int) -> Dict[str, Any]:
    ocupadas = _mesas_ocupadas(fecha, hora)
    libres = [
        m for m in CATALOGO["mesas"]
        if m["id"] not in ocupadas and m["capacidad"] >= personas
    ]
    libres.sort(key=lambda m: m["capacidad"])
    return {
        "ok": True,
        "fecha": fecha,
        "hora": hora,
        "personas": personas,
        "hay_mesa": len(libres) > 0,
        "mesas_libres": [
            {"mesa": m["id"], "capacidad": m["capacidad"], "zona": m["zona"]}
            for m in libres
        ],
        "mesa_recomendada": libres[0]["id"] if libres else None,
        "politica": CATALOGO["restaurante"]["politica_reserva"],
    }


def agendar_reserva(
    fecha: str, hora: str, personas: int, nombre: str, telefono: str = "desconocido"
) -> Dict[str, Any]:
    # Idempotencia: mismo telefono + fecha + hora => no se duplica
    for reserva in RESERVAS.values():
        if (
            reserva["telefono"] == telefono
            and reserva["fecha"] == fecha
            and reserva["hora"] == hora
        ):
            return {"ok": True, "duplicada": True, **reserva}

    disponibilidad = consultar_disponibilidad(fecha, hora, personas)
    if not disponibilidad["hay_mesa"]:
        return {
            "ok": False,
            "error": (
                f"No hay mesa para {personas} el {fecha} a las {hora}. "
                "Sugerencia: elige otra hora del mismo dia."
            ),
            "horas_con_mesa": _horas_libres(fecha, personas),
        }

    mesa = disponibilidad["mesa_recomendada"]
    _CONTADOR_RESERVA[0] += 1
    id_reserva = f"R-{_CONTADOR_RESERVA[0]}"
    reserva = {
        "id_reserva": id_reserva,
        "fecha": fecha,
        "hora": hora,
        "personas": personas,
        "nombre": nombre.strip(),
        "telefono": telefono,
        "mesa": mesa,
        "zona": next(m["zona"] for m in CATALOGO["mesas"] if m["id"] == mesa),
        "politica": "La mesa se reserva 15 minutos; pasado ese tiempo se libera.",
        "estado": "confirmada",
    }
    RESERVAS[id_reserva] = reserva
    return {"ok": True, "duplicada": False, **reserva}


def _horas_libres(fecha: str, personas: int) -> List[str]:
    todas = CATALOGO["horas"]["almuerzo"] + CATALOGO["horas"]["cena"]
    return [
        h for h in todas
        if any(
            m["id"] not in _mesas_ocupadas(fecha, h) and m["capacidad"] >= personas
            for m in CATALOGO["mesas"]
        )
    ]


def buscar_pregunta_frecuente(tema: str) -> Dict[str, Any]:
    limpio = re.sub(r"[^a-z0-9\s]", " ", tema.lower()).strip()
    sinoni = {
        "comida": "menu",
        "comer": "menu",
        "ordenar": "menu",
        "platillo": "menu",
        "platos": "menu",
        "carta": "menu",
        "abierto": "horarios",
        "abren": "horarios",
        "horario": "horarios",
        "donde": "ubicacion",
        "direccion": "ubicacion",
        "ubicacion": "ubicacion",
        "alergia": "alergenos",
        "alergias": "alergenos",
        "reserva": "reservas",
        "reservacion": "reservas",
        "estacionamiento": "estacionamiento",
        "parking": "estacionamiento",
        "pago": "pagos",
        "pagar": "pagos",
        "grupo": "grupos",
        "grupos": "grupos",
    }
    for clave in limpio.split():
        clave = sinoni.get(clave, clave)
        entrada = CATALOGO["preguntas_frecuentes"].get(clave)
        if entrada:
            return {"ok": True, "tema": clave, **entrada}

    for clave, entrada in CATALOGO["preguntas_frecuentes"].items():
        if any(c in limpio for c in clave.split("_")):
            return {"ok": True, "tema": clave, **entrada}

    return {
        "ok": False,
        "error": f"No hay pregunta frecuente para '{tema}'.",
        "temas_disponibles": sorted(CATALOGO["preguntas_frecuentes"]),
    }


# ---------------------------------------------------------------------------
# Ejecucion dirigida por el modelo (el servidor valida y luego corre)
# ---------------------------------------------------------------------------
def ejecutar(nombre: str, argumentos: Dict[str, Any], telefono: str = "") -> Dict[str, Any]:
    """
    Punto de entrada que usa el agente: valida los argumentos que pidio el
    modelo y, solo si son validos, ejecuta la funcion real.
    """
    valido, motivo = _validar_argumentos(nombre, argumentos)
    if not valido:
        return {"ok": False, "error": f"argumentos invalidos: {motivo}"}

    if nombre == "consultar_disponibilidad":
        return consultar_disponibilidad(
            argumentos["fecha"], argumentos["hora"], argumentos["personas"]
        )
    if nombre == "agendar_reserva":
        return agendar_reserva(
            argumentos["fecha"],
            argumentos["hora"],
            argumentos["personas"],
            argumentos["nombre"],
            telefono=telefono or "desconocido",
        )
    if nombre == "buscar_pregunta_frecuente":
        return buscar_pregunta_frecuente(argumentos["tema"])
    return {"ok": False, "error": f"herramienta no implementada: {nombre}"}
