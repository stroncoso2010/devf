"""Recuperador de fragmentos relevantes para RAG usando embeddings de Ollama."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import numpy as np

try:
    import faiss
except Exception:  # pragma: no cover
    faiss = None

from src.ollama_client import OllamaClient


class Retriever:
    def __init__(
        self,
        client: OllamaClient,
        documentos_folder: str,
        top_k: int = 4,
        indice_path: str = "src/rag/indice.json",
    ):
        self.client = client
        self.documentos_folder = Path(documentos_folder)
        self.top_k = top_k
        self.indice_path = Path(indice_path)
        self.textos: List[str] = []
        self.embeddings: Optional[np.ndarray] = None
        self.index = None
        self._cargar_o_indexar()

    def _cargar_documentos(self) -> List[str]:
        textos: List[str] = []
        if not self.documentos_folder.exists():
            return textos
        for archivo in sorted(self.documentos_folder.rglob("*")):
            if archivo.is_file() and archivo.suffix.lower() in {
                ".txt",
                ".md",
                ".pdf",
            }:
                try:
                    textos.append(archivo.read_text(encoding="utf-8"))
                except Exception:
                    continue
        return textos

    def _cargar_o_indexar(self) -> None:
        self.textos = self._cargar_documentos()
        if not self.textos:
            return
        embeddings = [self.client.embed(t) for t in self.textos]
        self.embeddings = np.array(embeddings, dtype="float32")

        if faiss is not None:
            dim = self.embeddings.shape[1]
            self.index = faiss.IndexFlatL2(dim)
            self.index.add(self.embeddings)

        self.indice_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"textos": self.textos, "embeddings": self.embeddings.tolist()}
        self.indice_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def buscar(self, consulta: str) -> List[str]:
        if not self.textos or self.embeddings is None:
            return []
        q_emb = np.array([self.client.embed(consulta)], dtype="float32")

        if faiss is not None and self.index is not None:
            _, ids = self.index.search(q_emb, self.top_k)
            return [
                self.textos[i]
                for i in ids[0]
                if 0 <= i < len(self.textos)
            ]

        # Fallback: similitud del coseno con numpy
        sims = (self.embeddings @ q_emb.T).flatten()
        norms = np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb)
        if norms.any():
            sims = sims / norms
        top_ids = np.argsort(-sims)[: self.top_k]
        return [self.textos[i] for i in top_ids]
