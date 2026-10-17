"""Utilidades para ajustar un modelo Llama en Ollama mediante Modelfile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict


def cargar_datos(ruta: str) -> List[Dict[str, str]]:
    """Carga ejemplos de entrenamiento en formato JSONL (una línea por objeto)."""
    datos: List[Dict[str, str]] = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                datos.append(json.loads(linea))
    return datos


def generar_modelfile(
    modelo_base: str,
    datos: List[Dict[str, str]],
    salida: str = "Modelfile",
    sistema: str = "Eres un asistente basado en Llama ajustado para responder en español de forma clara y breve.",
) -> None:
    """Genera un Modelfile de Ollama con ejemplos few-shot incrustados."""
    ejemplos = "\n\n".join(
        f"### Instrucción:\n{e.get('instruccion', '')}\n"
        f"### Entrada:\n{e.get('entrada', '')}\n"
        f"### Respuesta:\n{e.get('respuesta', '')}"
        for e in datos
    )
    contenido = f"""FROM {modelo_base}

PARAMETER temperature 0.2
PARAMETER num_predict 512

SYSTEM {sistema}

# Ejemplos de ajuste few-shot
{ejemplos}
"""
    Path(salida).write_text(contenido, encoding="utf-8")
    print(f"Modelfile generado en {salida}")
    print(
        "Para crear el modelo personalizado en Ollama ejecuta:\n"
        f"  ollama create mi-asistente -f {salida}"
    )


if __name__ == "__main__":
    print(
        "Ajusta los datos en src/fine_tuning/data/train.jsonl y ejecuta este script "
        "para generar el Modelfile de Ollama."
    )
