"""
Reglas fijas del agente veterinario.

Son decisiones que NO se delegan al modelo:
  - escalado a una persona,
  - urgencia medica (la Mascota no puede esperar a un modelo).

Se aplican antes de tocar Llama Stack: si la regla dispara, el modelo no
responde y la conversacion no crece.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Optional


def normalizar_texto(texto: str) -> str:
    """Minusculas, sin acentos y sin signos: comparacion robusta."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9\s]", " ", texto)


@dataclass
class ResultadoRegla:
    """Decision de una regla fija."""

    disparo: bool
    nombre: Optional[str] = None
    respuesta: Optional[str] = None
    motivo: str = ""

    def a_dict(self) -> Dict[str, Any]:
        return {
            "disparo": self.disparo,
            "nombre": self.nombre,
            "motivo": self.motivo,
        }


class MotorReglas:
    """Catalogo de reglas inquebrantables."""

    def __init__(self, configuracion: Dict[str, Any]) -> None:
        self.reglas = configuracion.get("reglas", {})

    def _coincide(self, patrones, texto: str) -> bool:
        limpio = normalizar_texto(texto)
        for patron in patrones:
            if normalizar_texto(patron) in limpio:
                return True
        return False

    def evaluar(self, texto: str) -> ResultadoRegla:
        """
        Evalua TODAS las reglas del config en orden de prioridad
        (el orden en que aparecen en configuracion.json).

        Ejecuta en la primera que coincida. Las reglas se definen en JSON,
        no en codigo: agregar una regla nueva no requiere tocar este modulo.
        """
        for nombre, regla in self.reglas.items():
            patrones = regla.get("patrones", [])
            if patrones and self._coincide(patrones, texto):
                return ResultadoRegla(
                    disparo=True,
                    nombre=nombre,
                    respuesta=regla.get("mensaje"),
                    motivo=f"Regla fija '{nombre}' disparada antes del modelo.",
                )

        return ResultadoRegla(disparo=False)
