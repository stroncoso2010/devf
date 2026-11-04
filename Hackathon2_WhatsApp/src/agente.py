"""
Agente de WhatsApp del restaurante: guard + reglas fijas + Llama Stack
(memoria por telefono) + function calling.

Flujo de un mensaje (el ciclo completo del tema):
  1. CAPA DE SEGURIDAD (src/guard.py): validacion de entrada, deteccion de
     prompt injection / contenido prohibido y hook opcional de Llama Guard.
     Si bloquea, NO hay llamada al modelo ni ejecucion de herramientas.
  2. Lock del telefono (serializa mensajes del mismo usuario).
  3. Reglas fijas: urgencia de salud / escalamiento a persona.
     Si disparan, tampoco hay llamada al modelo.
  4. Modelo con memoria (conversation de Llama Stack) Y herramientas.
     Si el modelo devuelve items type == "function_call":
  5. Validacion de argumentos + ejecucion real de la funcion
     (con timeout) y devolucion del resultado como tool output.
  6. Segunda llamada al modelo: redaccion final en lenguaje natural.
  7. Recorte del limite de historial y saneado de la salida.

Cada turno registra la latencia POR FASE (guard / razonamiento / accion) mas
la latencia total del ciclo, que es la unica que percibe el usuario.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional

from llama_stack_client import LlamaStackClient

import guard
import herramientas
from memoria import MemoriaConversaciones
from reglas import MotorReglas, ResultadoRegla

# Maximo de idas y vueltas modelo -> herramienta -> modelo en un turno.
MAX_ITERACIONES_HERRAMIENTA = 2


class AgenteRestaurante:
    """Agente conversacional de reservas y FAQ con function calling."""

    def __init__(self, configuracion: Dict[str, Any]) -> None:
        self.config = configuracion
        self.cliente = LlamaStackClient(
            base_url=self.config["llama_stack"]["base_url"],
            timeout=self.config["llama_stack"].get("timeout_modelo_ms", 90000) / 1000,
        )
        self.memoria = MemoriaConversaciones(self.cliente, self.config["llama_stack"])
        self.reglas = MotorReglas(configuracion)
        self.instrucciones = configuracion["agente"]["instructions"]
        self.timeout_tool_s = (
            self.config["llama_stack"].get("timeout_herramienta_ms", 3000) / 1000
        )
        self.trazabilidad: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Llamada al modelo con herramientas
    # ------------------------------------------------------------------
    def _llamar_modelo(
        self, conversation_id: str, entradas: List[Dict[str, Any]]
    ) -> Any:
        """
        Llamada al modelo con 1 reintento ante errores transitorios
        (500 de Llama Stack / conexion con Ollama caida). Si ambos
        intentos fallan, propaga la excepcion para que el turno se
        registre como error y se envie el fallback.
        """
        ultimo_error: Optional[Exception] = None
        for intento in range(2):
            try:
                return self.cliente.responses.create(
                    model=self.config["llama_stack"]["modelo"],
                    conversation=conversation_id,
                    instructions=self.instrucciones,
                    input=entradas,
                    tools=herramientas.ESQUEMAS,
                    max_output_tokens=self.config["llama_stack"].get("max_output_tokens", 240),
                    temperature=self.config["llama_stack"].get("temperatura", 0.3),
                )
            except Exception as exc:  # noqa: BLE001
                ultimo_error = exc
                if intento == 0:
                    time.sleep(2)  # espera antes del reintento
        raise ultimo_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Ejecucion de la herramienta pedida por el modelo (validada + timeout)
    # ------------------------------------------------------------------
    def _ejecutar_herramienta(
        self, nombre: str, argumentos_crudos: Any, telefono: str
    ) -> Dict[str, Any]:
        if isinstance(argumentos_crudos, str):
            try:
                argumentos = json.loads(argumentos_crudos or "{}")
            except json.JSONDecodeError:
                return {"ok": False, "error": "argumentos no son JSON valido"}
        elif isinstance(argumentos_crudos, dict):
            argumentos = argumentos_crudos
        else:
            return {"ok": False, "error": "argumentos con tipo inesperado"}

        inicio = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                futuro = pool.submit(
                    herramientas.ejecutar, nombre, argumentos, telefono
                )
                resultado = futuro.result(timeout=self.timeout_tool_s)
        except FuturesTimeout:
            resultado = {
                "ok": False,
                "error": f"la herramienta '{nombre}' excedio {self.timeout_tool_s:.1f}s",
            }
        except Exception as exc:  # noqa: BLE001
            resultado = {"ok": False, "error": f"error interno: {exc}"}
        resultado["duracion_ms"] = int((time.perf_counter() - inicio) * 1000)
        return resultado

    # ------------------------------------------------------------------
    # Turno completo
    # ------------------------------------------------------------------
    def procesar(self, telefono: str, mensaje: str) -> Dict[str, Any]:
        inicio_ciclo = time.perf_counter()

        # --- 0. Capa de seguridad (antes que todo) ---
        veredicto = guard.evaluar_entrada(mensaje)
        if not veredicto["permitido"]:
            respuesta = guard.sane_salida(
                self.config["seguridad"].get(
                    "respuesta_bloqueo",
                    "No puedo procesar ese mensaje. Puedo ayudarte con reservas y dudas del restaurante.",
                )
            )
            traza = {
                "telefono": telefono,
                "mensaje": mensaje[:200],
                "respuesta": respuesta,
                "fuente": "guard",
                "regla": None,
                "guard": veredicto,
                "conversation_id": None,
                "items_antes": 0,
                "items_despues": 0,
                "recorte": {"items_borrados": 0, "motivo": "bloqueado por seguridad"},
                "herramientas_llamadas": [],
                "error": None,
                "fases_ms": {"guard": int((time.perf_counter() - inicio_ciclo) * 1000),
                             "razonamiento": 0, "accion": 0},
                "latencia_ms": int((time.perf_counter() - inicio_ciclo) * 1000),
                "response_id": None,
            }
            self.trazabilidad.append(traza)
            return traza

        sesion = self.memoria.sesion(telefono)

        with sesion.lock:
            # --- 1. Reglas fijas antes del modelo ---
            regla: ResultadoRegla = self.reglas.evaluar(mensaje)
            if regla.disparo:
                traza = {
                    "telefono": telefono,
                    "mensaje": mensaje,
                    "respuesta": regla.respuesta,
                    "fuente": "regla",
                    "regla": regla.nombre,
                    "guard": veredicto,
                    "conversation_id": sesion.conversation_id,
                    "items_antes": len(self.memoria.items(sesion.conversation_id)),
                    "items_despues": len(self.memoria.items(sesion.conversation_id)),
                    "recorte": {"items_borrados": 0, "motivo": "regla fija: no entra al modelo"},
                    "herramientas_llamadas": [],
                    "error": None,
                    "fases_ms": {"guard": 0, "razonamiento": 0, "accion": 0},
                    "latencia_ms": int((time.perf_counter() - inicio_ciclo) * 1000),
                    "response_id": None,
                }
                self.trazabilidad.append(traza)
                return traza

            # --- 2. Modelo con herramientas (con manejo de error) ---
            items_antes = len(self.memoria.items(sesion.conversation_id))
            entradas: List[Dict[str, Any]] = [
                {"role": "user", "content": mensaje}
            ]
            herramientas_llamadas: List[Dict[str, Any]] = []
            ms_razonamiento = 0
            ms_accion = 0
            texto_final = ""
            response_id = None
            error_turno: Optional[str] = None

            try:
                for _iteracion in range(MAX_ITERACIONES_HERRAMIENTA):
                    t0 = time.perf_counter()
                    respuesta = self._llamar_modelo(sesion.conversation_id, entradas)
                    ms_razonamiento += int((time.perf_counter() - t0) * 1000)
                    response_id = respuesta.id

                    llamadas = [i for i in respuesta.output if i.type == "function_call"]
                    if not llamadas:
                        texto_final = (respuesta.output_text or "").strip()
                        break

                    # --- 3-4. Ejecutar cada herramienta pedida ---
                    for llamada in llamadas:
                        dump = llamada.model_dump()
                        nombre = dump.get("name", "")
                        t1 = time.perf_counter()
                        resultado = self._ejecutar_herramienta(
                            nombre, dump.get("arguments"), telefono
                        )
                        ms_accion += int((time.perf_counter() - t1) * 1000)
                        herramientas_llamadas.append(
                            {
                                "nombre": nombre,
                                "argumentos": dump.get("arguments"),
                                "ok": resultado.get("ok"),
                                "duracion_ms": resultado.get("duracion_ms"),
                                "detalle": {
                                    k: resultado.get(k)
                                    for k in (
                                        "id_reserva", "mesa", "hay_mesa",
                                        "mesa_recomendada", "tema", "error",
                                    )
                                    if k in resultado
                                },
                            }
                        )
                        entradas.append(
                            {
                                "type": "function_call",
                                "call_id": dump.get("call_id"),
                                "name": nombre,
                                "arguments": dump.get("arguments"),
                            }
                        )
                        entradas.append(
                            {
                                "type": "function_call_output",
                                "call_id": dump.get("call_id"),
                                "output": json.dumps(resultado, ensure_ascii=False),
                            }
                        )
            except Exception as exc:  # noqa: BLE001
                # Fallback: el usuario SIEMPRE recibe respuesta; el error queda
                # registrado en la bitacora para diagnostico.
                error_turno = f"{type(exc).__name__}: {exc}"
                texto_final = (
                    "No pude procesar tu mensaje en este momento (problema "
                    "temporal del servicio). Por favor intenta de nuevo en "
                    "unos segundos."
                )

            # --- 5. Recorte del limite de historial + saneado de salida ---
            recorte = self.memoria.recortar(sesion)
            items_despues = len(self.memoria.items(sesion.conversation_id))
            sesion.turnos += 1
            texto_final = guard.sane_salida(texto_final)

            traza = {
                "telefono": telefono,
                "mensaje": mensaje,
                "respuesta": texto_final,
                "fuente": "llama-stack",
                "regla": None,
                "guard": veredicto,
                "conversation_id": sesion.conversation_id,
                "response_id": response_id,
                "items_antes": items_antes,
                "items_despues": items_despues,
                "recorte": recorte,
                "herramientas_llamadas": herramientas_llamadas,
                "error": error_turno,
                "fases_ms": {"guard": 0, "razonamiento": ms_razonamiento, "accion": ms_accion},
                "turno": sesion.turnos,
                "latencia_ms": int((time.perf_counter() - inicio_ciclo) * 1000),
            }
            self.trazabilidad.append(traza)
            return traza

    # ------------------------------------------------------------------
    # Inspeccion
    # ------------------------------------------------------------------
    def historial(self, telefono: str) -> List[Dict[str, Any]]:
        sesion = self.memoria.sesion(telefono)
        return self.memoria.items(sesion.conversation_id)

    def estado(self) -> Dict[str, Any]:
        return self.memoria.estado()

    def reservas(self) -> Dict[str, Any]:
        return {"total": len(herramientas.RESERVAS),
                "reservas": list(herramientas.RESERVAS.values())}
