"""Cliente ligero para Ollama (API REST local, sin dependencias pesadas)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional


class OllamaClient:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        modelo: str = "llama3.2:latest",
        embed_model: str = "nomic-embed-text",
    ):
        self.host = host.rstrip("/")
        self.modelo = modelo
        self.embed_model = embed_model

    def _post(self, path: str, payload: dict, timeout: int = 120) -> dict:
        url = f"{self.host}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}

    def esta_disponible(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.host}/api/tags", timeout=5
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    def listar_modelos(self) -> List[str]:
        try:
            resp = self._post("/api/tags", {})
            return [m.get("name", "") for m in resp.get("models", [])]
        except Exception:
            return []

    def generar(
        self,
        prompt: str,
        temperatura: float = 0.2,
        num_predict: int = 512,
    ) -> str:
        payload = {
            "model": self.modelo,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperatura,
                "num_predict": num_predict,
            },
        }
        resp = self._post("/api/generate", payload)
        return resp.get("response", "")

    def embed(self, texto: str) -> List[float]:
        payload = {"model": self.embed_model, "prompt": texto}
        resp = self._post("/api/embeddings", payload)
        return resp.get("embedding", [])
