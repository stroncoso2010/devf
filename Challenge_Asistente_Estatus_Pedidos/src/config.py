"""
Carga centralizada de configuración del proyecto.

Lee `configuracion/configuracion.json` y permite sobrescribir valores con
variables de entorno (para Colab, GitHub Actions o despliegue real).
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "configuracion" / "configuracion.json"
RUTA_PEDIDOS = RAIZ / "configuracion" / "pedidos.json"

# Variables de entorno -> ruta en la configuración (formato: SECCION.clave)
SOBRESCRITURAS = {
    "WHATSAPP_TOKEN": "whatsapp.token",
    "WHATSAPP_PHONE_ID": "whatsapp.phone_id",
    "VERIFY_TOKEN": "whatsapp.verify_token",
    "GRAPH_API_BASE": "whatsapp.graph_api_base",
    "OLLAMA_URL": "ollama.url",
    "OLLAMA_MODELO": "ollama.modelo",
    "PUERTO_SERVIDOR": "servidor.puerto",
    "PUERTO_LOCALR": "servidor_meta.puerto",
}


def _aplicar_sobreescrituras(config: Dict[str, Any]) -> Dict[str, Any]:
    for var, ruta in SOBRESCRITURAS.items():
        valor = os.getenv(var)
        if valor is None or valor == "":
            continue
        partes = ruta.split(".")
        destino = config
        for parte in partes[:-1]:
            destino = destino.setdefault(parte, {})
        destino[partes[-1]] = valor
    return config


def cargar_config() -> Dict[str, Any]:
    """Carga la configuración del proyecto aplicando variables de entorno."""
    with open(RUTA_CONFIG, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    return _aplicar_sobreescrituras(config)


def cargar_pedidos() -> List[Dict[str, Any]]:
    """Carga el catálogo local de pedidos."""
    with open(RUTA_PEDIDOS, "r", encoding="utf-8") as fh:
        return json.load(fh)["pedidos"]
