"""
Agente de la veterinaria: Llama Stack (memoria) + Ollama (inferencia).

Flujo de un mensaje:
  1. Lock del telefono (no dos llamadas en paralelo sobre la misma sesion).
  2. Reglas fijas: escalado / urgencia. Si disparan, no hay llamada al modelo.
  3. Si no: se responde con Llama Stack usando la conversacion del telefono
     (ahi esta la memoria) y se recorta el historial al limite configurado.
"""

import time
from typing import Any, Dict, List, Optional

from llama_stack_client import LlamaStackClient

from memoria import MemoriaConversaciones
from reglas import MotorReglas, ResultadoRegla


class AgenteVeterinario:
    """Agente conversacional de la clinica veterinaria."""

    def __init__(self, configuracion: Dict[str, Any]) -> None:
        self.config = configuracion
        self.cliente = LlamaStackClient(base_url=self.config["llama_stack"]["base_url"])
        self.memoria = MemoriaConversaciones(self.cliente, self.config["llama_stack"])
        self.reglas = MotorReglas(configuracion)
        self.instrucciones = configuracion["agente"]["instructions"]
        self.trazabilidad: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Llamada al modelo (a traves de Llama Stack)
    # ------------------------------------------------------------------
    def _responder_con_llama_stack(
        self, conversation_id: str, mensaje: str
    ) -> Dict[str, Any]:
        inicio = time.perf_counter()
        respuesta = self.cliente.responses.create(
            model=self.config["llama_stack"]["modelo"],
            conversation=conversation_id,
            instructions=self.instrucciones,
            input=[{"role": "user", "content": mensaje}],
            max_output_tokens=self.config["llama_stack"].get("max_output_tokens", 220),
            temperature=self.config["llama_stack"].get("temperatura", 0.3),
        )
        latencia = int((time.perf_counter() - inicio) * 1000)
        return {
            "texto": (respuesta.output_text or "").strip(),
            "response_id": respuesta.id,
            "latencia_ms": latencia,
        }

    # ------------------------------------------------------------------
    # Turno completo
    # ------------------------------------------------------------------
    def procesar(self, telefono: str, mensaje: str) -> Dict[str, Any]:
        """Procesa un mensaje de usuario y devuelve la respuesta + la traza."""
        sesion = self.memoria.sesion(telefono)

        with sesion.lock:  # serializa los mensajes del mismo telefono
            # El cronometro arranca DENTRO del lock: la latencia reportada debe
            # ser la del propio turno, no el tiempo de espera en cola.
            inicio = time.perf_counter()

            # 1. Reglas fijas antes del modelo
            regla: ResultadoRegla = self.reglas.evaluar(mensaje)
            if regla.disparo:
                traza = {
                    "telefono": telefono,
                    "mensaje": mensaje,
                    "respuesta": regla.respuesta,
                    "fuente": "regla",
                    "regla": regla.nombre,
                    "conversation_id": sesion.conversation_id,
                    "items_antes": len(self.memoria.items(sesion.conversation_id)),
                    "items_despues": len(self.memoria.items(sesion.conversation_id)),
                    "recorte": {"items_borrados": 0, "motivo": "regla fija: no entra al modelo"},
                    "latencia_ms": int((time.perf_counter() - inicio) * 1000),
                    "response_id": None,
                }
                self.trazabilidad.append(traza)
                return traza

            # 2. Modelo con memoria (la conversacion de Llama Stack)
            items_antes = len(self.memoria.items(sesion.conversation_id))
            resultado = self._responder_con_llama_stack(sesion.conversation_id, mensaje)

            # 3. Limite de historial sobre la conversacion de Llama Stack
            recorte = self.memoria.recortar(sesion)
            items_despues = len(self.memoria.items(sesion.conversation_id))

            sesion.turnos += 1
            traza = {
                "telefono": telefono,
                "mensaje": mensaje,
                "respuesta": resultado["texto"],
                "fuente": "llama-stack",
                "regla": None,
                "conversation_id": sesion.conversation_id,
                "response_id": resultado["response_id"],
                "items_antes": items_antes,
                "items_despues": items_despues,
                "recorte": recorte,
                "turno": sesion.turnos,
                "latencia_ms": int((time.perf_counter() - inicio) * 1000),
            }
            self.trazabilidad.append(traza)
            return traza

    # ------------------------------------------------------------------
    # Inspeccion
    # ------------------------------------------------------------------
    def historial(self, telefono: str) -> List[Dict[str, Any]]:
        """Historial guardado en Llama Stack para ese telefono."""
        sesion = self.memoria.sesion(telefono)
        return self.memoria.items(sesion.conversation_id)

    def estado(self) -> Dict[str, Any]:
        return self.memoria.estado()
