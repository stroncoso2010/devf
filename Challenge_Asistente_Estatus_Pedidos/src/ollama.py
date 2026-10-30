"""
Cliente de Ollama (PC local).

Reglas de operación (ver AGENTS.md sección 5):
  - `think = false` por defecto: los modelos de la familia qwen/gemma devuelven
    el contenido en `thinking` y dejan `content` vacío si no se desactiva.
  - `num_predict` explícito para evitar bucles de repetición.
  - `temperature` baja (0.1–0.4) para un tono controlado.
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests


class ClienteOllama:
    """Envoltorio mínimo sobre la API HTTP de Ollama."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        modelo: str = "qwen3.5:0.8b",
        num_predict: int = 200,
        temperature: float = 0.3,
        think: bool = False,
        timeout: int = 45,
    ) -> None:
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.num_predict = num_predict
        self.temperature = temperature
        self.think = think
        self.timeout = timeout
        self.ultima_metrica: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def disponible(self) -> bool:
        """True si el servidor de Ollama responde."""
        try:
            r = requests.get(f"{self.url}/api/version", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def listar_modelos(self) -> List[str]:
        """Modelos instalados en el PC."""
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=10)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except requests.RequestException:
            return []

    def _construir_payload(self, sistema: str, usuario: str) -> Dict[str, Any]:
        return {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "stream": False,
            "think": self.think,
            "options": {
                "num_predict": self.num_predict,
                "temperature": self.temperature,
            },
        }

    # ------------------------------------------------------------------
    # Generación
    # ------------------------------------------------------------------
    def chat(self, sistema: str, usuario: str) -> str:
        """
        Genera una respuesta. Devuelve texto plano (nunca vacío; si el modelo
        no dice nada, devuelve un mensaje de respaldo controlado).
        """
        inicio = time.perf_counter()
        payload = self._construir_payload(sistema, usuario)
        respuesta = ""
        thinking = ""
        error = ""

        try:
            r = requests.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            mensaje = data.get("message", {}) or {}
            respuesta = (mensaje.get("content") or "").strip()
            thinking = (mensaje.get("thinking") or "").strip()
        except requests.RequestException as exc:
            error = str(exc)

        # Fallback: algunos modelos solo contestan por /api/generate
        if not respuesta and not error:
            try:
                r = requests.post(
                    f"{self.url}/api/generate",
                    json={
                        "model": self.modelo,
                        "prompt": f"{sistema}\n\n{usuario}",
                        "stream": False,
                        "think": self.think,
                        "options": {
                            "num_predict": self.num_predict,
                            "temperature": self.temperature,
                        },
                    },
                    timeout=self.timeout,
                )
                r.raise_for_status()
                respuesta = (r.json().get("response") or "").strip()
            except requests.RequestException as exc:
                error = str(exc)

        duracion_ms = int((time.perf_counter() - inicio) * 1000)
        self.ultima_metrica = {
            "modelo": self.modelo,
            "duracion_ms": duracion_ms,
            "chars_respuesta": len(respuesta),
            "chars_thinking": len(thinking),
            "error": error,
        }

        if error:
            return (
                "⚠️ No pude conectarme con el motor de lenguaje en este momento. "
                "Intenta de nuevo en unos segundos."
            )
        if not respuesta:
            return (
                "Gracias por tu mensaje. 🙌 Para darte el estatus exacto necesito "
                "el número de pedido (por ejemplo: PED-1001)."
            )
        return respuesta

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------
    def informacion_modelo(self) -> Dict[str, Any]:
        """Metadatos del modelo activo (para el panel /stats)."""
        try:
            r = requests.post(
                f"{self.url}/api/show",
                json={"model": self.modelo},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "modelo": data.get("details", {}).get("family", self.modelo),
                "parametros": data.get("details", {}).get("parameter_size", "n/a"),
                "capacidades": data.get("capabilities", []),
            }
        except requests.RequestException:
            return {"modelo": self.modelo, "parametros": "n/a", "capacidades": []}
