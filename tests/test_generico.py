"""Pruebas genéricas del asistente con Ollama."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ollama_client import OllamaClient
from src.assistant import Assistant
from src.rag.retriever import Retriever


@pytest.fixture
def cliente():
    return OllamaClient(
        host="http://localhost:11434",
        modelo="gemma3:1b",
        embed_model="bge-m3:latest",
    )


def test_ollama_esta_disponible(cliente):
    assert cliente.esta_disponible() is True


def test_ollama_listar_modelos(cliente):
    modelos = cliente.listar_modelos()
    assert isinstance(modelos, list)


def test_ollama_generar(cliente):
    respuesta = cliente.generar("Di solo la palabra: Hola", temperatura=0.1, num_predict=20)
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0


def test_ollama_embeddings(cliente):
    emb = cliente.embed("texto de prueba")
    assert isinstance(emb, list)
    assert len(emb) > 0


def test_assistant_inicializa():
    asistente = Assistant()
    assert asistente is not None
    assert asistente.client is not None


def test_assistant_responder_retorna_str():
    asistente = Assistant()
    respuesta = asistente.responder("¿Qué es un modelo de lenguaje?")
    assert isinstance(respuesta, str)
    assert len(respuesta.strip()) > 0


def test_retriever_sin_documentos_retorna_lista_vacia(cliente, tmp_path):
    carpeta_vacia = tmp_path / "documentos_vacios"
    carpeta_vacia.mkdir()
    retriever = Retriever(
        client=cliente,
        documentos_folder=str(carpeta_vacia),
        top_k=4,
    )
    resultados = retriever.buscar("cualquier consulta")
    assert resultados == []


def test_config_yaml_valido():
    import yaml
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert "ollama" in cfg
    assert "modelo" in cfg["ollama"]
    assert cfg["ollama"]["modelo"] == "gemma3:1b"


def test_train_jsonl_valido():
    datos = Path("src/fine_tuning/data/train.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(datos) >= 1
    for linea in datos:
        obj = json.loads(linea)
        assert "instruccion" in obj
        assert "entrada" in obj
        assert "respuesta" in obj


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
