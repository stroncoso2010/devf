"""
Normalizacion de numeros de WhatsApp (formato E.164, prefijo de Mexico).

WhatsApp entrega el numero sin '+' (ej. 5215512345678). La API de envio exige
E.164. Mexico usa 55 + 10 digitos (moviles con 1 inicial: 13 digitos).
"""

import re

PREFIJO_MX = "55"


def normalizar_numero_mx(telefono: str) -> str:
    """
    Normaliza a E.164 numerico.

      +52 1 55 1234 5678  ->  5215512345678
      5512345678          ->  525512345678
      1234567890          ->  551234567890
      044 55 1234 5678   ->  551234567890
    """
    if telefono is None:
        return ""

    numero = re.sub(r"[^0-9+]", "", str(telefono).strip())

    if numero.startswith("00"):
        numero = "+" + numero[2:]
    if numero.startswith("+"):
        numero = numero[1:]

    # Prefijo de larga distancia nacional (044 / 045)
    if numero.startswith("044") or numero.startswith("045"):
        numero = numero[3:]

    if numero.startswith("0"):
        numero = PREFIJO_MX + numero[1:]

    # 12 digitos con prefijo 52 (moviles antiguos de Mexico)
    if len(numero) == 12 and numero.startswith("52"):
        numero = PREFIJO_MX + numero[2:]

    # 10 digitos -> numero nacional
    if len(numero) == 10 and numero.isdigit():
        numero = PREFIJO_MX + numero

    return numero
