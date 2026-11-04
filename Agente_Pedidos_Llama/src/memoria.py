"""
Memoria de la conversacion sobre Llama Stack.

Cada numero de telefono tiene:
  - una conversacion propia en Llama Stack (client.conversations.create),
  - un lock propio para serializar sus mensajes (dos mensajes seguidos del
    mismo usuario no disparan dos llamadas en paralelo sobre la misma
    conversacion),
  - un limite de items conservados: cuando se supera, se borran los mas
    antiguos de la conversacion.

El modelo no recuerda nada entre llamadas: toda la memoria vive en la
conversacion de Llama Stack y se le reenvia en cada turno.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from llama_stack_client import LlamaStackClient


class SesionUsuario:
    """Estado de un usuario: conversion de Llama Stack + lock + contadores."""

    def __init__(self, telefono: str, conversation_id: str) -> None:
        self.telefono = telefono
        self.conversation_id = conversation_id
        self.lock = threading.Lock()
        self.turnos = 0
        self.items_borrados = 0
        self.creada_en = time.strftime("%Y-%m-%d %H:%M:%S")

    def a_dict(self) -> Dict[str, Any]:
        return {
            "telefono": self.telefono,
            "conversation_id": self.conversation_id,
            "turnos": self.turnos,
            "items_borrados": self.items_borrados,
            "creada_en": self.creada_en,
        }


class MemoriaConversaciones:
    """Gestiona una conversacion de Llama Stack por numero de telefono."""

    def __init__(self, cliente: LlamaStackClient, config: Dict[str, Any]) -> None:
        self.cliente = cliente
        self.config = config
        self.max_items = int(config.get("max_items_historial", 8))
        self.sesiones: Dict[str, SesionUsuario] = {}
        self._lock_global = threading.Lock()

    # ------------------------------------------------------------------
    # Sesiones
    # ------------------------------------------------------------------
    def sesion(self, telefono: str) -> SesionUsuario:
        """Devuelve (o crea) la conversacion del telefono."""
        with self._lock_global:
            if telefono not in self.sesiones:
                conversacion = self.cliente.conversations.create(
                    metadata={
                        "telefono": telefono,
                        "session_id": f"vet-{telefono}",
                        "proyecto": "agente-veterinaria",
                    }
                )
                self.sesiones[telefono] = SesionUsuario(telefono, conversacion.id)
            return self.sesiones[telefono]

    # ------------------------------------------------------------------
    # Historial
    # ------------------------------------------------------------------
    def items(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Historial de la conversacion en Llama Stack.

        Nota: Llama Stack devuelve `content` como LISTA de partes para los
        mensajes del asistente, pero como STRING directo para los del usuario.
        Se normalizan los dos casos a texto plano. Se pide order="asc" para
        que el historial salga en orden cronologico.
        """
        pagina = self.cliente.conversations.items.list(
            conversation_id=conversation_id, order="asc"
        )
        salida = []
        for item in getattr(pagina, "data", []) or []:
            contenido = getattr(item, "content", None)
            texto = ""
            if isinstance(contenido, str):
                texto = contenido
            elif isinstance(contenido, list):
                for parte in contenido:
                    valor = getattr(parte, "text", None)
                    if valor:
                        texto = valor
                        break
                    # fallback: algunos tipos exponen model_dump()
                    if hasattr(parte, "model_dump"):
                        texto = parte.model_dump().get("text", "") or texto
                        if texto:
                            break
            salida.append(
                {
                    "id": getattr(item, "id", ""),
                    "tipo": getattr(item, "type", ""),
                    "rol": getattr(item, "role", ""),
                    "texto": texto,
                }
            )
        return salida

    def recortar(self, sesion: SesionUsuario) -> Dict[str, Any]:
        """
        Aplica el limite de historial: conserva solo los `max_items` items
        mas recientes de la conversacion de Llama Stack.

        Importante: items.list devuelve los items del MAS RECIENTE al MAS
        ANTIGUO por defecto (order=desc). Para borrar los antiguos hay que
        pedirlos en orden ascendente (`order="asc"`) y recortar la cabeza.
        """
        pagina = self.cliente.conversations.items.list(
            conversation_id=sesion.conversation_id, order="asc"
        )
        items = [
            {"id": getattr(it, "id", ""), "texto": ""}
            for it in getattr(pagina, "data", []) or []
        ]
        excedente = len(items) - self.max_items
        borrados = []
        if excedente > 0:
            for item in items[:excedente]:  # los mas antiguos
                try:
                    self.cliente.conversations.items.delete(
                        item_id=item["id"], conversation_id=sesion.conversation_id
                    )
                    borrados.append(item["id"])
                except Exception as exc:  # noqa: BLE001
                    print(f"[MEMORIA] no se pudo borrar {item['id']}: {exc}")
            sesion.items_borrados += len(borrados)
        return {
            "items_antes": len(items),
            "items_borrados": len(borrados),
            "items_despues": len(items) - len(borrados),
            "max_items": self.max_items,
        }

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def estado(self) -> Dict[str, Any]:
        return {
            "total_sesiones": len(self.sesiones),
            "max_items_historial": self.max_items,
            "sesiones": [s.a_dict() for s in self.sesiones.values()],
        }

    def reiniciar(self) -> None:
        """Borra las conversaciones creadas (para repetir la prueba)."""
        for sesion in list(self.sesiones.values()):
            try:
                self.cliente.conversations.delete(conversation_id=sesion.conversation_id)
            except Exception:  # noqa: BLE001
                pass
        with self._lock_global:
            self.sesiones.clear()
