"""Asistente inteligente basado en Llama ejecutado localmente con Ollama."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional

from src.ollama_client import OllamaClient
from src.rag.retriever import Retriever


class Assistant:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        oll = self.config.get("ollama", {})

        self.client = OllamaClient(
            host=oll.get("host", "http://localhost:11434"),
            modelo=oll.get("modelo", "llama3.2:latest"),
            embed_model=oll.get("embed_model", "nomic-embed-text"),
        )
        self.temperatura = float(oll.get("temperatura", 0.2))
        self.num_predict = int(oll.get("num_predict", 512))

        self.retriever: Optional[Retriever] = None
        if self.config.get("rag", {}).get("habilitado", False):
            self.retriever = Retriever(
                client=self.client,
                documentos_folder=self.config["rag"].get(
                    "carpeta_documentos", "src/rag/documentos"
                ),
                top_k=self.config["rag"].get("top_k", 4),
                indice_path=self.config["rag"].get(
                    "indice", "src/rag/indice.json"
                ),
            )

    def responder(self, pregunta: str) -> str:
        contexto = ""
        if self.retriever:
            fragmentos = self.retriever.buscar(pregunta)
            if fragmentos:
                contexto = "\n".join(f"- {f[:500]}" for f in fragmentos)

        prompt = self._construir_prompt(pregunta, contexto)
        return self.client.generar(
            prompt,
            temperatura=self.temperatura,
            num_predict=self.num_predict,
        )

    def _construir_prompt(self, pregunta: str, contexto: str) -> str:
        sistema = (
            "Eres un asistente inteligente basado en Llama ejecutado localmente con Ollama. "
            "Responde de forma clara, concisa y en español. "
            "Si el contexto proporcionado es relevante, úsalo para fundamentar la respuesta."
        )
        if contexto:
            return (
                f"{sistema}\n\nContexto relevante:\n{contexto}\n\n"
                f"Pregunta: {pregunta}\nRespuesta:"
            )
        return f"{sistema}\n\nPregunta: {pregunta}\nRespuesta:"


def main() -> None:
    asistente = Assistant()
    if not asistente.client.esta_disponible():
        print(
            "Ollama no está disponible en http://localhost:11434. "
            "Ejecuta 'ollama serve' y asegúrate de tener el modelo instalado."
        )
        return
    print("Asistente listo (Ollama). Escribe 'salir' para terminar.")
    while True:
        try:
            pregunta = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n¡Hasta luego!")
            break
        if pregunta.lower() in {"salir", "exit", "quit"}:
            print("¡Hasta luego!")
            break
        if not pregunta:
            continue
        try:
            respuesta = asistente.responder(pregunta)
        except Exception as e:
            respuesta = (
                f"Error al consultar Ollama: {e}\n"
                "Verifica que Ollama esté corriendo y que el modelo esté instalado."
            )
        print(f"\nAsistente: {respuesta}")


if __name__ == "__main__":
    main()
