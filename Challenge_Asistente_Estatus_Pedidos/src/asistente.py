"""
Lógica de negocio del Asistente de Estatus de Pedidos.

Dos rutas de respuesta:
  1. `catalogo`  -> el mensaje trae un folio (PED-####) y se responde con los
                    datos del pedido. Determinista, sin LLM: es el dato duro.
  2. `llm`       -> conversación libre. Llama 3.1 (o el modelo local activo)
                    responde con tono amable y máximo 2-3 líneas.
"""

import re
from typing import Any, Dict, List, Optional

from config import cargar_pedidos
from ollama import ClienteOllama

PATRON_FOLIO = re.compile(r"\bPED[\s\-_]?(\d{3,6})\b", re.IGNORECASE)

# Intención de consulta de estatus sin folio: aquí NO dejamos que el LLM invente.
# Solo palabras que hablan del ESTADO o la ENTREGA (no "pedido" suelto, que
# aparece en casi cualquier frase y dejaría al LLM sin oportunidades).
PATRON_INTENCION_ESTATUS = re.compile(
    r"\b(estatus|estado|status|lleg[oó]|llega|llegar|entregad[oa]|entrega|"
    r"enviad[oa]|envi[oó]|rastreo|seguimiento|cu[aá]ndo llega|qu[eé] tal)\b",
    re.IGNORECASE,
)

PROMPT_BASE = """Eres el Asistente de Estatus de Pedidos de una tienda en línea.
Reglas de tono (obligatorias):
- Responde en ESPAÑOL, con AMABILIDAD y en un máximo de 2-3 líneas.
- Ve directo al grano: nada de preámbulos largos ni frases de relleno.
- Si te preguntan por el estatus de un pedido y NO te dan el número, pídelo
  con un ejemplo: "Dame el número de pedido (ejemplo: PED-1001)".
- Si te preguntan por algo que no es de pedidos (clima, política, etc.), indica
  con cortesía que solo atiendes consultas de pedidos.
- No inventes estados de pedido, fechas ni números de rastreo.
- Usa emojis con moderación (máximo uno por respuesta)."""


class AsistentePedidos:
    """Orquesta catálogo + LLM + memoria de usuarios conocidos."""

    def __init__(self, config: Dict[str, Any], cliente_ollama: ClienteOllama) -> None:
        self.config = config
        self.cliente = cliente_ollama
        self.pedidos: List[Dict[str, Any]] = cargar_pedidos()
        self.usuarios_conocidos: set[str] = set()
        self.mensajes_recibidos: List[Dict[str, Any]] = []
        self.bitacora: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    def extraer_folio(self, texto: str) -> Optional[str]:
        """Detecta un folio tipo PED-1001 en el texto."""
        match = PATRON_FOLIO.search(texto or "")
        if not match:
            return None
        return f"PED-{match.group(1)}"

    def buscar_pedido(self, folio: str) -> Optional[Dict[str, Any]]:
        folio = (folio or "").upper().strip()
        for pedido in self.pedidos:
            if pedido["folio"].upper() == folio:
                return pedido
        return None

    def _recortar(self, respuesta: str) -> str:
        """Control de tono: maximo N lineas (requisito del challenge)."""
        max_lineas = int(self.config["asistente"].get("max_lineas", 3))
        terminadores = (".", "!", "?", ":", ")", "…")
        lineas = [ln.strip() for ln in (respuesta or "").splitlines() if ln.strip()]
        lineas = lineas[:max_lineas]
        # Si la ultima linea quedo cortada (el modelo no la termino), se descarta.
        if len(lineas) == max_lineas and not lineas[-1].endswith(terminadores):
            lineas = lineas[:-1]
        if len(lineas) == 1 and len(lineas[0]) > 280:
            lineas[0] = lineas[0][:277].rstrip() + "..."
        elif lineas and lineas[-1][-1].isalnum():
            # Frase cortada por el limite de generacion: se cierra con puntos suspensivos.
            lineas[-1] = lineas[-1].rstrip() + "..."
        return "\n".join(lineas)

    def _prompt_sistema(self) -> str:
        """Prompt con el catálogo real: el modelo no puede inventar pedidos."""
        resumen = "; ".join(
            f"{p['folio']} ({p['estado']})" for p in self.pedidos
        )
        return (
            f"{PROMPT_BASE}\n"
            f"Pedidos existentes en el sistema: {resumen}.\n"
            f"Si te piden un estatus y no das folio, NO supongas ninguno."
        )

    def _respuesta_de_catalogo(self, pedido: Dict[str, Any]) -> str:
        """Respuesta determinista con los datos duros del pedido."""
        partes = [
            f"📦 *{pedido['folio']}* — {pedido['producto']} (x{pedido['cantidad']})",
            f"Estado: *{pedido['estado']}*",
        ]
        if pedido.get("fecha_estimada_entrega"):
            partes.append(f"Entrega estimada: {pedido['fecha_estimada_entrega']}")
        if pedido.get("rastreo") and pedido["rastreo"] != "Pendiente de asignación":
            partes.append(f"Rastreo: {pedido['rastreo']} ({pedido['transportista']})")
        if pedido.get("motivo_cancelacion"):
            partes.append(f"Motivo: {pedido['motivo_cancelacion']}")
        partes.append("¿Necesitas algo más sobre este pedido?")
        return "\n".join(partes)

    # ------------------------------------------------------------------
    # Memoria de conversación
    # ------------------------------------------------------------------
    def registrar_usuario(self, telefono: str) -> bool:
        """Agrega el usuario al registro. True si es nuevo."""
        if telefono in self.usuarios_conocidos:
            return False
        self.usuarios_conocidos.add(telefono)
        return True

    def reiniciar_estado(self) -> None:
        self.usuarios_conocidos.clear()
        self.mensajes_recibidos.clear()
        self.bitacora.clear()

    # ------------------------------------------------------------------
    # Respuesta
    # ------------------------------------------------------------------
    def responder(self, telefono: str, texto: str) -> Dict[str, Any]:
        """
        Devuelve el dict de la respuesta:
          {telefono, texto_usuario, respuesta, fuente, modelo, duracion_ms, folio}
        """
        es_nuevo = self.registrar_usuario(telefono)
        folio = self.extraer_folio(texto)

        # Saludo de bienvenida para usuarios nuevos (sinfolio, primer contacto)
        if es_nuevo and folio is None:
            respuesta = self.config["asistente"]["saludo_bienvenida"]
            fuente = "saludo"
            modelo = None
            duracion_ms = 0
        elif folio:
            pedido = self.buscar_pedido(folio)
            if pedido:
                respuesta = self._respuesta_de_catalogo(pedido)
                fuente = "catalogo"
            else:
                respuesta = (
                    f"No encuentro el pedido *{folio}* en el sistema. 🤔 "
                    "Revisa el número e inténtalo de nuevo, o escríbeme para ayuda."
                )
                fuente = "catalogo"
            modelo = None
            duracion_ms = 0
        else:
            # Consulta de estatus SIN folio -> regla determinista (evita alucinaciones)
            if PATRON_INTENCION_ESTATUS.search(texto or ""):
                respuesta = self.config["asistente"]["sin_folio"]
                fuente = "regla"
            else:
                respuesta = self._recortar(self.cliente.chat(self._prompt_sistema(), texto))
                fuente = "llm"
            modelo = None if fuente != "llm" else self.cliente.modelo
            duracion_ms = 0 if fuente != "llm" else self.cliente.ultima_metrica.get("duracion_ms", 0)

        registro = {
            "telefono": telefono,
            "texto_usuario": texto,
            "respuesta": respuesta,
            "fuente": fuente,
            "modelo": modelo,
            "duracion_ms": duracion_ms,
            "folio": folio,
            "usuario_nuevo": es_nuevo,
        }
        self.bitacora.append(registro)
        return registro
