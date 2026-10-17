"""Pruebas de estrategias de prompting con Ollama local (sin datos personales).

Cubre:
1. Zero-shot vs Few-shot (clasificación)
2. Chain-of-Thought (razonamiento paso a paso)
3. Límite del prompt (pregunta fuera del entrenamiento -> posible alucinación)
4. RAG (buscar antes de responder) con sentence-transformers + Ollama
5. Challenge: Asistente de políticas con RAG
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


# ---------------------------------------------------------------------------
# 1. ZERO-SHOT vs FEW-SHOT (clasificación)
# ---------------------------------------------------------------------------

def test_zero_shot_clasificacion(cliente):
    """Clasificar un texto sin ejemplos (zero-shot)."""
    prompt = (
        "Clasifica el siguiente texto en una de estas categorías: "
        "POSITIVO, NEGATIVO, NEUTRO.\n\n"
        "Texto: El servicio fue rápido y el personal muy amable.\n"
        "Categoría:"
    )
    respuesta = cliente.generar(prompt, temperatura=0.1, num_predict=30)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_zero_shot.txt").write_text(respuesta, encoding="utf-8")


def test_few_shot_clasificacion(cliente):
    """Clasificar un texto con ejemplos (few-shot)."""
    prompt = (
        "Clasifica el texto en POSITIVO, NEGATIVO o NEUTRO.\n\n"
        "Ejemplo 1: Me encantó el producto. -> POSITIVO\n"
        "Ejemplo 2: No funciona, pésimo servicio. -> NEGATIVO\n"
        "Ejemplo 3: Es aceptable, nada especial. -> NEUTRO\n\n"
        "Texto: El servicio fue rápido y el personal muy amable.\n"
        "Categoría:"
    )
    respuesta = cliente.generar(prompt, temperatura=0.1, num_predict=30)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_few_shot.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. CHAIN-OF-THOUGHT
# ---------------------------------------------------------------------------

def test_chain_of_thought(cliente):
    """Razonamiento paso a paso antes de la respuesta final."""
    prompt = (
        "Resuelve el siguiente problema paso a paso. "
        "Primero explica tu razonamiento y luego da la respuesta final.\n\n"
        "Problema: Si tengo 5 manzanas, regalo 2 y compro 4 más, "
        "¿cuántas manzanas tengo al final?\n\n"
        "Razonamiento:\nRespuesta final:"
    )
    respuesta = cliente.generar(prompt, temperatura=0.1, num_predict=150)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_chain_of_thought.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. LÍMITE DEL PROMPT (alucinación)
# ---------------------------------------------------------------------------

def test_limite_prompt_alucinacion(cliente):
    """Preguntar algo que el modelo no pudo haber visto en su entrenamiento."""
    prompt = (
        "Responde en español. "
        "¿Cuál fue el resultado del partido entre el Equipo X y el Equipo Y "
        "el 15 de marzo de 2025 en la ciudad ficticia de Novara?"
    )
    respuesta = cliente.generar(prompt, temperatura=0.2, num_predict=100)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_limite_prompt.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4. RAG (buscar antes de responder)
# ---------------------------------------------------------------------------

def test_rag_buscar_antes_de_responder(cliente, embed_model):
    """RAG: recuperar fragmento relevante y usarlo como contexto."""
    documentos = [
        "La política de reembolsos permite devolver productos dentro de los 30 días posteriores a la compra.",
        "El horario de atención al cliente es de lunes a viernes, de 9:00 a 18:00 horas.",
        "Los envíos estándar tardan entre 3 y 5 días hábiles en llegar.",
    ]
    pregunta = "¿Cuánto tiempo tengo para devolver un producto?"

    emb_doc = embed_model.encode(documentos, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]
    sims = (emb_doc @ emb_q) / (
        np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
    )
    idx = int(np.argmax(sims))
    fragmento = documentos[idx]

    prompt_rag = (
        "Eres un asistente de soporte. Responde usando solo el contexto proporcionado.\n\n"
        f"Contexto:\n- {fragmento}\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    respuesta_rag = cliente.generar(prompt_rag, temperatura=0.1, num_predict=100)
    assert isinstance(respuesta_rag, str)
    assert len(respuesta_rag.strip()) > 0
    Path("resultados_rag.txt").write_text(respuesta_rag, encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. CHALLENGE: ASISTENTE DE POLÍTICAS CON RAG
# ---------------------------------------------------------------------------

def test_challenge_asistente_politicas_rag(cliente, embed_model):
    """Asistente de políticas con RAG: zero-shot, few-shot, CoT, límite y RAG."""
    politicas = [
        "Los empleados pueden solicitar hasta 15 días de vacaciones al año.",
        "El reembolso de gastos de viaje requiere factura original y aprobación del gerente.",
        "El trabajo remoto se permite máximo dos días por semana con previa autorización.",
    ]
    pregunta = "¿Cuántos días de vacaciones puedo solicitar al año?"

    # 5a. Zero-shot
    prompt_zs = (
        "Responde en español de forma breve.\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    zs = cliente.generar(prompt_zs, temperatura=0.1, num_predict=80)

    # 5b. Few-shot
    prompt_fs = (
        "Responde en español de forma breve usando los ejemplos como guía.\n\n"
        "Ejemplo 1: Pregunta: ¿Puedo trabajar remoto? -> Respuesta: Sí, máximo dos días a la semana con autorización.\n"
        "Ejemplo 2: Pregunta: ¿Cómo solicito reembolso? -> Respuesta: Con factura original y aprobación del gerente.\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    fs = cliente.generar(prompt_fs, temperatura=0.1, num_predict=80)

    # 5c. Chain-of-thought
    prompt_cot = (
        "Razona paso a paso y luego responde en español de forma breve.\n\n"
        f"Pregunta: {pregunta}\nRazonamiento:\nRespuesta:"
    )
    cot = cliente.generar(prompt_cot, temperatura=0.1, num_predict=120)

    # 5d. RAG
    emb_doc = embed_model.encode(politicas, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]
    sims = (emb_doc @ emb_q) / (
        np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
    )
    idx = int(np.argmax(sims))
    fragmento = politicas[idx]

    prompt_rag = (
        "Eres un asistente de políticas internas. Usa solo el contexto proporcionado.\n\n"
        f"Contexto:\n- {fragmento}\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    rag = cliente.generar(prompt_rag, temperatura=0.1, num_predict=80)

    # Guardar resultados sin datos personales
    reporte = (
        "CHALLENGE: ASISTENTE DE POLÍTICAS CON RAG\n"
        "=" * 50 + "\n\n"
        f"Pregunta: {pregunta}\n\n"
        f"Fragmento recuperado (RAG): {fragmento}\n\n"
        f"--- ZERO-SHOT ---\n{zs}\n\n"
        f"--- FEW-SHOT ---\n{fs}\n\n"
        f"--- CHAIN-OF-THOUGHT ---\n{cot}\n\n"
        f"--- RAG ---\n{rag}\n\n"
        "Conclusión: RAG proporciona la respuesta más precisa y fundamentada "
        "en el documento de políticas.\n"
    )
    Path("resultados_challenge_politicas_rag.txt").write_text(
        reporte, encoding="utf-8"
    )

    assert isinstance(zs, str) and len(zs.strip()) > 0
    assert isinstance(fs, str) and len(fs.strip()) > 0
    assert isinstance(cot, str) and len(cot.strip()) > 0
    assert isinstance(rag, str) and len(rag.strip()) > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
