"""
Lanzador: levanta los DOS servidores del entorno local.

  1. Servidor local de la Graph API de Meta  -> 127.0.0.1:8899
  2. Servidor del asistente (webhook)    -> 127.0.0.1:8000

Uso:
    python src/servidor.py
    python src/servidor.py --solo-asistente
"""

import argparse
import sys
import threading
import time
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import cargar_config  # noqa: E402

config = cargar_config()


def _servidor(nombre: str, app_import: str, host: str, puerto: int, log_level: str = "info") -> None:
    import importlib

    modulo = importlib.import_module(app_import)
    print(f"[{nombre}] arrancando en http://{host}:{puerto}")
    uvicorn.run(modulo.app, host=host, port=puerto, log_level=log_level)


def main() -> None:
    parser = argparse.ArgumentParser(description="Arranca el entorno local completo")
    parser.add_argument("--solo-asistente", action="store_true")
    parser.add_argument("--solo-meta", action="store_true")
    args = parser.parse_args()

    host_meta = config["servidor_meta"]["host"]
    puerto_meta = config["servidor_meta"]["puerto"]
    host_app = config["servidor"]["host"]
    puerto_app = config["servidor"]["puerto"]

    hilos = []

    if not args.solo_asistente:
        hilos.append(
            threading.Thread(
                target=_servidor,
                args=("SERVIDOR-META", "servidor_meta", host_meta, puerto_meta),
                daemon=True,
            )
        )
    if not args.solo_meta:
        hilos.append(
            threading.Thread(
                target=_servidor,
                args=("ASISTENTE", "app", host_app, puerto_app),
                daemon=True,
            )
        )

    for hilo in hilos:
        hilo.start()

    print("")
    print("=" * 70)
    print("  ENTORNO ACTIVO")
    print(f"  Webhook del asistente : http://{host_app}:{puerto_app}/webhook")
    print(f"  Servidor local de Meta     : http://{host_meta}:{puerto_meta}")
    print(f"  Modelo Ollama         : {config['ollama']['modelo']} ({config['ollama']['url']})")
    print("  Ctrl+C para detener")
    print("=" * 70)
    print("")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo servidores...")


if __name__ == "__main__":
    main()
