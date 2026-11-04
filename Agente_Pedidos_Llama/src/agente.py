"""
Agente de atencion a pedidos: Llama Stack (memoria) + function calling.

Flujo de un mensaje (el ciclo completo del tema):
  1. Lock del telefono (serializa mensajes del mismo usuario).
  2. Reglas fijas: cargo duplicado (urgencia) / hablar con persona.
     Si disparan, NO hay llamada al modelo.
  3. Modelo con memoria (conversation de Llama Stack) Y herramientas.
     Si el modelo devuelve items type == "function_call":
  4. Validacion de argumentos + ejecucion real de la funcion
     (con timeout) y devolucion del resultado como tool output.
  5. Segunda llamada al modelo: redaccion final en lenguaje natural.

Cada turno registra la latencia POR FASE (razonamiento / accion) mas la
latencia total del ciclo, que es la unica que percibe el usuario.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional

from llama_stack_client import LlamaStackClient

import herramientas
from memoria import MemoriaConversaciones
from reglas import MotorReglas, ResultadoRegla

# Maximo de idas y vueltas modelo -> herramienta -> modelo en un turno.
MAX_ITERACIONES_HERRAMIENTA = 2


class AgentePedidos:
    """Agente conversacional de atencion a pedidos con function calling."""

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
                    max_output_tokens=self.config["llama_stack"].get("max_output_tokens", 220),
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
    def _ejecutar_herramienta(self, nombre: str, argumentos_crudos: Any) -> Dict[str, Any]:
        # Los argumentos llegan como string JSON o como dict
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
            # Timeout real aunque la funcion sea local: el patron es el mismo
            # que para una API externa (en produccion, requests con timeout).
            with ThreadPoolExecutor(max_workers=1) as pool:
                futuro = pool.submit(herramientas.ejecutar, nombre, argumentos)
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
    # Turno completo con function calling
    # ------------------------------------------------------------------
    def procesar(self, telefono: str, mensaje: str) -> Dict[str, Any]:
        sesion = self.memoria.sesion(telefono)

        with sesion.lock:
            inicio_ciclo = time.perf_counter()

            # --- 1. Reglas fijas antes del modelo ---
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
                    "herramientas_llamadas": [],
                    "fases_ms": {"razonamiento": 0, "accion": 0},
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

                    # Items de salida: texto libre o peticion de funcion
                    llamadas = [i for i in respuesta.output if i.type == "function_call"]
                    if not llamadas:
                        texto_final = (respuesta.output_text or "").strip()
                        break

                    # --- 3-4. Ejecutar cada herramienta pedida ---
                    for llamada in llamadas:
                        dump = llamada.model_dump()
                        nombre = dump.get("name", "")
                        t1 = time.perf_counter()
                        resultado = self._ejecutar_herramienta(nombre, dump.get("arguments"))
                        ms_accion += int((time.perf_counter() - t1) * 1000)
                        herramientas_llamadas.append(
                            {
                                "nombre": nombre,
                                "argumentos": dump.get("arguments"),
                                "ok": resultado.get("ok"),
                                "duracion_ms": resultado.get("duracion_ms"),
                            }
                        )
                        # Se devuelve el resultado al modelo (function_call_output)
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

            # --- 5. Recorte del limite de historial ---
            recorte = self.memoria.recortar(sesion)
            items_despues = len(self.memoria.items(sesion.conversation_id))
            sesion.turnos += 1

            traza = {
                "telefono": telefono,
                "mensaje": mensaje,
                "respuesta": texto_final,
                "fuente": "llama-stack",
                "regla": None,
                "conversation_id": sesion.conversation_id,
                "response_id": response_id,
                "items_antes": items_antes,
                "items_despues": items_despues,
                "recorte": recorte,
                "herramientas_llamadas": herramientas_llamadas,
                "error": error_turno,
                "fases_ms": {
                    "razonamiento": ms_razonamiento,
                    "accion": ms_accion,
                },
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
