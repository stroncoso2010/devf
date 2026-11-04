"""
Carga de la configuracion del agente.

Todo se lee de `configuracion/configuracion.json` para que los valores
(modelo, puerto, reglas, limites) se puedan cambiar sin tocar codigo.
"""

import json
import os
from typing import Any, Dict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CONFIG = os.path.join(RAIZ, "configuracion", "configuracion.json")


def cargar_configuracion(ruta: str = RUTA_CONFIG) -> Dict[str, Any]:
    """Lee el JSON de configuracion y aplica los valores por entorno."""
    with open(ruta, "r", encoding="utf-8") as archivo:
        config = json.load(archivo)

    # Variables de entorno: tienen prioridad sobre el JSON (nunca se versionan
    # credenciales reales en el repositorio).
    servidor = config.get("servidor", {})
    puerto = os.environ.get("VET_PUERTO")
    if puerto:
        servidor["puerto"] = int(puerto)

    base = os.environ.get("LLAMA_STACK_BASE_URL")
    if base:
        config["llama_stack"]["base_url"] = base

    token = os.environ.get("WHATSAPP_TOKEN")
    if token:
        config["whatsapp"]["token"] = token

    verify = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    if verify:
        config["whatsapp"]["verify_token"] = verify

    return config
