"""Pruebas de estrategias de prompting y RAG con tema científico (fotosíntesis).

Cubre los puntos del challenge:
- Prompt de clasificación en modo zero-shot
- Prompt de clasificación en modo few-shot
- Razonamiento paso a paso (chain-of-thought)
- Pregunta fuera del entrenamiento (límite del prompt / posible alucinación)
- Instalación y uso de sentence-transformers para embeddings
- RAG: buscar antes de responder sobre base de conocimiento científica
- Challenge: asistente de políticas científicas con RAG
"""

from __future__ import annotations

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
# 1. Prompt de clasificación en modo zero-shot
# ---------------------------------------------------------------------------

def test_prompt_clasificacion_zero_shot(cliente):
    """Clasificar un texto científico sin ejemplos previos."""
    prompt = (
        "Clasifica el siguiente enunciado en una de estas categorías: "
        "BIOLOGÍA, QUÍMICA, FÍSICA.\n\n"
        "Enunciado: La clorofila absorbe luz solar para producir glucosa y oxígeno.\n"
        "Categoría:"
    )
    respuesta = cliente.generar(prompt, temperatura=0.1, num_predict=30)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_zero_shot.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. Prompt de clasificación en modo few-shot
# ---------------------------------------------------------------------------

def test_prompt_clasificacion_few_shot(cliente):
    """Clasificar un texto científico con ejemplos (few-shot)."""
    prompt = (
        "Clasifica el enunciado en BIOLOGÍA, QUÍMICA o FÍSICA.\n\n"
        "Ejemplo 1: El corazón bombea sangre a todo el cuerpo. -> BIOLOGÍA\n"
        "Ejemplo 2: El agua hierve a 100 °C al nivel del mar. -> QUÍMICA\n"
        "Ejemplo 3: La gravedad mantiene a los planetas en órbita. -> FÍSICA\n\n"
        "Enunciado: La clorofila absorbe luz solar para producir glucosa y oxígeno.\n"
        "Categoría:"
    )
    respuesta = cliente.generar(prompt, temperatura=0.1, num_predict=30)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_few_shot.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. Razonamiento paso a paso (chain-of-thought)
# ---------------------------------------------------------------------------

def test_reasoning_chain_of_thought(cliente):
    """Resolver un problema científico mostrando el razonamiento paso a paso."""
    prompt = (
        "Resuelve el siguiente problema paso a paso. Explica el razonamiento "
        "antes de dar la respuesta final.\n\n"
        "Problema: Una planta realiza fotosíntesis y produce 6 moléculas de "
        "glucosa. Cada molécula de glucosa tiene 6 átomos de carbono. "
        "¿Cuántos átomos de carbono se fijan en total?\n\n"
        "Razonamiento:\nRespuesta final:"
    )
    respuesta = cliente.generar(prompt, temperatura=0.1, num_predict=150)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_chain_of_thought.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4. El límite del prompt: información que el modelo nunca vio
# ---------------------------------------------------------------------------

def test_limite_prompt_sin_informacion(cliente):
    """Preguntar sobre un evento futuro o ficticio para observar comportamiento."""
    prompt = (
        "Responde en español de forma breve. "
        "¿Cuál fue el hallazgo principal del informe científico sobre "
        "fotosíntesis en Marte publicado el 20 de enero de 2026?"
    )
    respuesta = cliente.generar(prompt, temperatura=0.2, num_predict=100)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_limite_prompt.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. RAG: buscar antes de responder (sentence-transformers + similitud coseno)
# ---------------------------------------------------------------------------

def test_rag_buscar_antes_de_responder(cliente, embed_model):
    """Recuperar el fragmento científico más relevante y usarlo como contexto."""
    documentos = [
        "La fotosíntesis convierte dióxido de carbono y agua en glucosa y oxígeno usando energía lumínica.",
        "El ciclo de Calvin ocurre en el estroma del cloroplasto y fija el CO₂ en moléculas orgánicas.",
        "La luz solar es absorbida por la clorofila en los tilacoides durante las reacciones luminosas.",
    ]
    pregunta = "¿En qué parte del cloroplasto ocurre el ciclo de Calvin?"

    emb_doc = embed_model.encode(documentos, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]
    sims = (emb_doc @ emb_q) / (
        np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
    )
    idx = int(np.argmax(sims))
    fragmento = documentos[idx]

    prompt_rag = (
        "Eres un asistente científico. Responde usando únicamente el contexto proporcionado.\n\n"
        f"Contexto:\n- {fragmento}\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    respuesta = cliente.generar(prompt_rag, temperatura=0.1, num_predict=100)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0
    Path("resultados_rag.txt").write_text(respuesta, encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. Challenge: Asistente de políticas científicas con RAG
# ---------------------------------------------------------------------------

def test_challenge_asistente_cientifico_rag(cliente, embed_model):
    """Asistente científico con RAG: zero-shot, few-shot, CoT, límite y RAG."""
    politicas = [
        "Los experimentos de laboratorio requieren equipo de protección personal en todo momento.",
        "El uso de reactivos químicos peligrosos debe estar autorizado por el responsable de seguridad.",
        "Los datos de investigación deben registrarse en cuaderno de bitácora con fecha y firma.",
    ]
    pregunta = "¿Qué se requiere para manipular reactivos químicos peligrosos?"

    # 6a. Zero-shot
    prompt_zs = (
        "Responde en español de forma breve.\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    zs = cliente.generar(prompt_zs, temperatura=0.1, num_predict=80)

    # 6b. Few-shot
    prompt_fs = (
        "Responde en español de forma breve siguiendo los ejemplos.\n\n"
        "Ejemplo 1: Pregunta: ¿Se requiere equipo de protección? -> Respuesta: Sí, en todo momento en el laboratorio.\n"
        "Ejemplo 2: Pregunta: ¿Cómo se registran los datos? -> Respuesta: En cuaderno de bitácora con fecha y firma.\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    fs = cliente.generar(prompt_fs, temperatura=0.1, num_predict=80)

    # 6c. Chain-of-thought
    prompt_cot = (
        "Razona paso a paso y luego responde en español de forma breve.\n\n"
        f"Pregunta: {pregunta}\nRazonamiento:\nRespuesta:"
    )
    cot = cliente.generar(prompt_cot, temperatura=0.1, num_predict=120)

    # 6d. RAG
    emb_doc = embed_model.encode(politicas, convert_to_numpy=True)
    emb_q = embed_model.encode([pregunta], convert_to_numpy=True)[0]
    sims = (emb_doc @ emb_q) / (
        np.linalg.norm(emb_doc, axis=1) * np.linalg.norm(emb_q)
    )
    idx = int(np.argmax(sims))
    fragmento = politicas[idx]

    prompt_rag = (
        "Eres un asistente de políticas de laboratorio. Usa únicamente el contexto proporcionado.\n\n"
        f"Contexto:\n- {fragmento}\n\n"
        f"Pregunta: {pregunta}\nRespuesta:"
    )
    rag = cliente.generar(prompt_rag, temperatura=0.1, num_predict=80)

    reporte = (
        "CHALLENGE: ASISTENTE CIENTÍFICO CON RAG\n"
        "=" * 50 + "\n\n"
        f"Pregunta: {pregunta}\n\n"
        f"Fragmento recuperado (RAG): {fragmento}\n\n"
        f"--- ZERO-SHOT ---\n{zs}\n\n"
        f"--- FEW-SHOT ---\n{fs}\n\n"
        f"--- CHAIN-OF-THOUGHT ---\n{cot}\n\n"
        f"--- RAG ---\n{rag}\n\n"
        "Conclusión: RAG proporciona la respuesta más precisa y fundamentada "
        "en el documento de políticas del laboratorio.\n"
    )
    Path("resultados_challenge_cientifico_rag.txt").write_text(
        reporte, encoding="utf-8"
    )

    assert isinstance(zs, str) and len(zs.strip()) > 0
    assert isinstance(fs, str) and len(fs.strip()) > 0
    assert isinstance(cot, str) and len(cot.strip()) > 0
    assert isinstance(rag, str) and len(rag.strip()) > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
