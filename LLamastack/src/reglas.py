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
        Evalua las reglas en orden de prioridad.

        1. Escalado a persona.
        2. Urgencia medica.
        """
        escalado = self.reglas.get("escalado_humano", {})
        if escalado and self._coincide(escalado.get("patrones", []), texto):
            return ResultadoRegla(
                disparo=True,
                nombre="escalado_humano",
                respuesta=escalado.get("mensaje"),
                motivo="El usuario pide hablar con una persona: regla fija.",
            )

        urgencia = self.reglas.get("urgencia_medica", {})
        if urgencia and self._coincide(urgencia.get("patrones", []), texto):
            return ResultadoRegla(
                disparo=True,
                nombre="urgencia_medica",
                respuesta=urgencia.get("mensaje"),
                motivo="Se detectan palabras de urgencia medica: regla fija.",
            )

        return ResultadoRegla(disparo=False)
