"""Construye el índice vectorial de documentos para RAG con Ollama."""

from __future__ import annotations

import yaml
from pathlib import Path

from src.ollama_client import OllamaClient
from src.rag.retriever import Retriever


def indexar(config_path: str = "config.yaml") -> None:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    oll = cfg.get("ollama", {})
    client = OllamaClient(
        host=oll.get("host", "http://localhost:11434"),
        modelo=oll.get("modelo", "llama3.2:latest"),
        embed_model=oll.get("embed_model", "nomic-embed-text"),
    )
    rag = cfg.get("rag", {})
    retriever = Retriever(
        client=client,
        documentos_folder=rag.get("carpeta_documentos", "src/rag/documentos"),
        top_k=rag.get("top_k", 4),
        indice_path=rag.get("indice", "src/rag/indice.json"),
    )
    print(f"Documentos indexados: {len(retriever.textos)}")


if __name__ == "__main__":
    indexar()
