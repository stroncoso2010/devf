"""Challenge 2: RAG con Ollama — pruebas genéricas.

Implementa los pasos del challenge:
1. Configura entorno Ollama (cliente local).
2. Base de conocimiento con 3 fragmentos y embeddings (sentence-transformers + numpy).
3. buscar_fragmento(pregunta) con similitud coseno.
4. Respuesta sin RAG (respuesta_sin_rag).
5. Respuesta con RAG (respuesta_con_rag).
6. Comparación e impresión de ambas respuestas.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sentence_transformers import SentenceTransformer

from src.ollama_client import OllamaClient


@pytest.fixture
def cliente():
    return OllamaClient(
        host="http://localhost:11434",
        modelo="gemma3:1b",
        embed_model="bge-m3:latest",
    )


@pytest.fixture
def embed_model():
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture
def documentos():
    """3 fragmentos de un reglamento interno de uso de asistentes de IA."""
    return [
        "El asistente inteligente solo puede usarse para consultas internas de la empresa y no para compartir datos personales de clientes.",
        "Está prohibido cargar código fuente confidencial al modelo; solo se permiten fragmentos públicos o desidentificados.",
        "Toda respuesta generada por el asistente debe ser revisada por un humano antes de ser enviada a un cliente externo.",
    ]


@pytest.fixture
def pregunta():
    return "¿Puedo cargar código fuente confidencial al asistente?"


def test_challenge2_configura_ollama(cliente):
    """Paso 1: Verificar que el cliente Ollama esté disponible."""
    assert cliente.esta_disponible() is True


def test_challenge2_genera_embeddings(documentos, embed_model):
    """Paso 2: Generar embeddings de los documentos con sentence-transformers."""
    embeddings = embed_model.encode(documentos, convert_to_numpy=True)
    assert embeddings.shape[0] == len(documentos)
    assert embeddings.shape[1] > 0


def test_challenge2_buscar_fragmento(documentos, embed_model, pregunta):
    """Paso 2b y 3: Definir buscar_fragmento con similitud coseno."""
    emb_doc = embed_model.encode(documentos, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]

    def buscar_fragmento(pregunta: str, documentos: list, emb_doc: np.ndarray, model) -> str:
        emb_q = model.encode([pregunta], convert_to_numpy=True)[0]
        sims = (emb_doc @ emb_q) / (
            np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
        )
        idx = int(np.argmax(sims))
        return documentos[idx]

    resultado = buscar_fragmento(pregunta, documentos, emb_doc, embed_model)
    assert isinstance(resultado, str)
    assert len(resultado) > 0


def test_challenge2_respuesta_sin_rag(cliente, pregunta):
    """Paso 3: Respuesta sin contexto RAG."""
    prompt_sin_rag = (
        "Eres un asistente basado en Llama. Responde en español de forma clara y breve.\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    respuesta_sin_rag = cliente.generar(
        prompt_sin_rag, temperatura=0.2, num_predict=200
    )
    assert isinstance(respuesta_sin_rag, str)
    assert len(respuesta_sin_rag.strip()) > 0

    # Guardar para inspección manual si se ejecuta directo
    Path("respuesta_sin_rag.txt").write_text(
        respuesta_sin_rag, encoding="utf-8"
    )


def test_challenge2_respuesta_con_rag(cliente, documentos, embed_model, pregunta):
    """Paso 4: Respuesta con contexto RAG."""
    emb_doc = embed_model.encode(documentos, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]
    sims = (emb_doc @ emb_q) / (
        np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
    )
    idx = int(np.argmax(sims))
    fragmento = documentos[idx]

    prompt_con_rag = (
        "Eres un asistente basado en Llama. Responde en español de forma clara y breve. "
        "Usa exclusivamente el contexto proporcionado para fundamentar tu respuesta.\n\n"
        f"Contexto relevante:\n- {fragmento}\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    respuesta_con_rag = cliente.generar(
        prompt_con_rag, temperatura=0.2, num_predict=200
    )
    assert isinstance(respuesta_con_rag, str)
    assert len(respuesta_con_rag.strip()) > 0

    Path("respuesta_con_rag.txt").write_text(
        respuesta_con_rag, encoding="utf-8"
    )


def test_challenge2_compara_y_concluye(cliente, documentos, embed_model, pregunta):
    """Paso 5: Comparar ambas respuestas e imprimir conclusión."""
    emb_doc = embed_model.encode(documentos, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]
    sims = (emb_doc @ emb_q) / (
        np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
    )
    idx = int(np.argmax(sims))
    fragmento = documentos[idx]

    prompt_sin_rag = (
        "Eres un asistente basado en Llama. Responde en español de forma clara y breve.\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    respuesta_sin_rag = cliente.generar(
        prompt_sin_rag, temperatura=0.2, num_predict=200
    )

    prompt_con_rag = (
        "Eres un asistente basado en Llama. Responde en español de forma clara y breve. "
        "Usa exclusivamente el contexto proporcionado para fundamentar tu respuesta.\n\n"
        f"Contexto relevante:\n- {fragmento}\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    respuesta_con_rag = cliente.generar(
        prompt_con_rag, temperatura=0.2, num_predict=200
    )

    print("\n" + "=" * 60)
    print("CHALLENGE 2 — COMPARACIÓN RAG vs SIN RAG")
    print("=" * 60)
    print(f"\nPregunta: {pregunta}")
    print(f"\nFragmento recuperado (RAG): {fragmento}")
    print(f"\n--- RESPUESTA SIN RAG ---\n{respuesta_sin_rag}")
    print(f"\n--- RESPUESTA CON RAG ---\n{respuesta_con_rag}")
    print("\nConclusión:")
    print(
        "- La respuesta SIN RAG puede alucinar o ser imprecisa porque el modelo "
        "no conoce el reglamento interno.\n"
        "- La respuesta CON RAG usa el fragmento real del documento, por lo que "
        "es más precisa y reduce alucinaciones.\n"
    )
    print("=" * 60 + "\n")

    assert isinstance(respuesta_sin_rag, str)
    assert isinstance(respuesta_con_rag, str)
    assert len(respuesta_con_rag.strip()) > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
