# Asistente Inteligente con Llama - Hackathon 1 (DevF)

Asistente funcional basado en **Llama ejecutado localmente con Ollama**.  
Combina **prompting**, **RAG** (búsqueda semántica sobre documentos) y **ajuste con Modelfile de Ollama** para responder preguntas reales.

## Estructura

```
ia/
├── .gitignore
├── README.md
├── requirements.txt
├── config.yaml
├── Modelfile
├── run.ps1
├── src/
│   ├── ollama_client.py      # Cliente REST de Ollama
│   ├── assistant.py          # Punto de entrada del asistente
│   ├── rag/
│   │   ├── index.py          # Construcción del índice vectorial
│   │   ├── retriever.py      # Recuperación semántica con Ollama embeddings
│   │   └── documentos/       # Documentos fuente para RAG
│   └── fine_tuning/
│       ├── train_lora.py     # Generador de Modelfile (ajuste Ollama)
│       └── data/
│           └── train.jsonl   # Ejemplos de entrenamiento
├── tests/
│   └── test_assistant.py     # Pruebas mínimas
└── notebooks/                # Demostración interactiva (demo.ipynb)
```

## Requisitos previos

1. **Instala Ollama**: https://ollama.com  
2. Descarga el modelo (ejemplo):  
   ```powershell
   ollama pull llama3.2:latest
   ollama pull nomic-embed-text
   ```
3. Instala dependencias de Python:  
   ```powershell
   pip install -r requirements.txt
   ```

## Uso

### 1. Arrancar Ollama
```powershell
ollama serve
```

### 2. Indexar documentos (RAG)
```powershell
python src\rag\index.py
```

### 3. Ejecutar el asistente
```powershell
python src\assistant.py
```
O usa el script incluido:
```powershell
.\run.ps1
```

### 4. Ejecutar pruebas
```powershell
pytest tests\test_assistant.py
```

## Ajuste del modelo con Modelfile

Ollama no usa LoRA tradicional, pero permite crear modelos personalizados con un **Modelfile**.

1. Edita los ejemplos en `src/fine_tuning/data/train.jsonl`.
2. Genera el Modelfile:
   ```powershell
   python src\fine_tuning\train_lora.py
   ```
3. Crea el modelo en Ollama:
   ```powershell
   ollama create mi-asistente -f Modelfile
   ```
4. Cambia `config.yaml` para usar `mi-asistente` como modelo.

## Estrategia técnica

- **Prompting**: plantilla de sistema en `assistant.py`.
- **RAG**: embeddings con `nomic-embed-text` vía Ollama + búsqueda semántica (FAISS o coseno con NumPy).
- **Ajuste**: Modelfile de Ollama con ejemplos few-shot.
- **Evaluación**: pruebas en `tests/`.

## Entrega en GitHub

```powershell
git init
git add .
git commit -m "Entrega Hackathon 1: Asistente con Ollama"
git branch -M main
git remote add origin https://github.com/stroncoso2010/devf.git
git push -u origin main
```

Luego entrega la URL del repositorio en el campus de DevF:
`https://edu.devf.la/campus/program/module/ia-aplicada-con-modelos-abiertos/asistente-inteligente-con-llama/project/hackathon-1`
