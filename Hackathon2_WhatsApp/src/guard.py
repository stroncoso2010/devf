"""
Capa de seguridad del agente (Llama Guard / Prompt Guard, Masterclass 4).

Implementacion por REGLAS con hook opcional para un modelo real de guard:

  1. Validacion de entrada: longitud maxima y saneamiento de caracteres.
  2. Deteccion de prompt injection / fuga de instrucciones (Patron de
     Prompt Guard: clasificar la INTENCION del texto, no solo palabras sueltas).
  3. Deteccion de contenido prohibido (violencia, autolesiones).
  4. Hook opcional `llama_guard_modelo`: si se configura en
     configuracion.json (por ejemplo "llama-guard3"), cada entrada se
     clasifica ademas con el modelo de seguridad via Ollama /api/generate.
     Asi el mismo codigo pasa de guard por reglas a guard real sin tocar
     el flujo del agente.
  5. Saneamiento de SALIDA antes de enviar a la Cloud API (limite de
     caracteres y eliminacion de caracteres de control).

El guard se ejecuta ANTES que las reglas fijas y antes del modelo: si
bloquea, no hay llamada al modelo ni ejecucion de herramientas.
"""

import json
import re
import urllib.request
from typing import Any, Dict, List, Optional

import config as config_mod

# Patrones de bloqueo por categoria (se compilan desde el config)
_INYECCION = [
    "ignora (todas )?las instrucciones",
    "ignora tus instrucciones",
    "ignora lo anterior",
    "olvida lo que te dijeron",
    "olvida tus instrucciones",
    "instrucciones del sistema",
    "prompt del sistema",
    "system prompt",
    "modo developer",
    "modo dios",
    "jailbreak",
    "actua como otro",
    "eres otro asistente",
    "no eres un asistente",
    "haz lo que te diga sin preguntar",
]

_CONTENIDO_PROHIBIDO = [
    "mata a",
    "como matar",
    "arma para",
    "drogas ilegales",
    "suicid",
]

# Plantilla para el hook opcional con llama-guard3
_PROMPT_GUARD = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>

[INST] Task: Check if the user message violates the safety policy.
Categories: S1 Safe, S2 Unsafe.
User message: "{texto}"

Is the message safe or unsafe? Answer Safe or Unsafe. <|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni puntuacion, espacios simples."""
    t = texto.lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"), ("ü", "u")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _coincide(texto_normalizado: str, patrones: List[str]) -> List[str]:
    encontrados = []
    for patron in patrones:
        p = _normalizar(patron)
        if p and p in texto_normalizado:
            encontrados.append(patron)
    return encontrados


def evaluar_entrada(texto: str) -> Dict[str, Any]:
    """
    Evalua un mensaje entrante. Devuelve:
      {"permitido": bool, "categoria": str|None, "motivo": str|None,
       "coincidencias": [...], "guard_modelo": ...}
    """
    cfg = config_mod.cargar_configuracion().get("seguridad", {})

    # 1) Longitud y saneamiento
    max_entrada = int(cfg.get("max_caracteres_entrada", 600))
    if not texto or not texto.strip():
        return {"permitido": False, "categoria": "vacio", "motivo": "mensaje vacio",
                "coincidencias": []}
    if len(texto) > max_entrada:
        return {
            "permitido": False,
            "categoria": "longitud",
            "motivo": f"mensaje de {len(texto)} caracteres; maximo {max_entrada}",
            "coincidencias": [],
        }

    normalizado = _normalizar(texto)

    # 2) Prompt injection / fuga de instrucciones
    patrones_cfg = [p for p in cfg.get("patrones_bloqueo", [])]
    inyeccion = _coincide(normalizado, _INYECCION + patrones_cfg)
    if inyeccion:
        return {
            "permitido": False,
            "categoria": "prompt_injection",
            "motivo": "intento de inyeccion o fuga de instrucciones",
            "coincidencias": inyeccion,
        }

    # 3) Contenido prohibido
    prohibido = _coincide(normalizado, _CONTENIDO_PROHIBIDO)
    if prohibido:
        return {
            "permitido": False,
            "categoria": "contenido_prohibido",
            "motivo": "contenido fuera de politica",
            "coincidencias": prohibido,
        }

    # 4) Hook opcional: modelo real de seguridad (llama-guard3)
    modelo_guard = cfg.get("llama_guard_modelo")
    guard_modelo: Optional[Dict[str, Any]] = None
    if modelo_guard:
        guard_modelo = _clasificar_con_modelo(texto, modelo_guard, cfg)
        if guard_modelo and guard_modelo.get("unsafe"):
            return {
                "permitido": False,
                "categoria": "llama_guard",
                "motivo": f"modelo {modelo_guard} marco la entrada como unsafe",
                "coincidencias": [guard_modelo.get("respuesta", "")],
                "guard_modelo": guard_modelo,
            }

    return {"permitido": True, "categoria": None, "motivo": None,
            "coincidencias": [], "guard_modelo": guard_modelo}


def _clasificar_con_modelo(texto: str, modelo: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Hook opcional hacia Ollama con un modelo de seguridad."""
    url = cfg.get("llama_guard_url", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": modelo,
        "prompt": _PROMPT_GUARD.format(texto=texto.replace('"', "'")[:400]),
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 10},
    }
    try:
        req = urllib.request.Request(
            f"{url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            salida = json.loads(resp.read().decode("utf-8")).get("response", "")
        return {
            "modelo": modelo,
            "respuesta": salida.strip()[:80],
            "unsafe": "unsafe" in salida.lower(),
        }
    except Exception as exc:  # noqa: BLE001
        # Si el modelo de seguridad no esta disponible, se registra pero no
        # bloquea el flujo (el guard por reglas ya cubrio la entrada).
        return {"modelo": modelo, "error": str(exc), "unsafe": False}


def sane_salida(texto: str) -> str:
    """Valida y sanea la respuesta antes de llamar al endpoint de envio."""
    cfg = config_mod.cargar_configuracion().get("seguridad", {})
    max_salida = int(cfg.get("max_caracteres_salida", 1200))
    if not texto:
        return ""
    # Elimina caracteres de control (no imprimibles) que la Cloud API rechaza
    limpio = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", texto)
    if len(limpio) > max_salida:
        limpio = limpio[:max_salida] + "…"
    return limpio
