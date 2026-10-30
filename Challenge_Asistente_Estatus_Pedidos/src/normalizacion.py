"""
Normalización de números telefónicos.

WhatsApp entrega los números en formato internacional sin `+`
(ej. `5215512345678`). La API de envío exige E.164 (`+5215512345678`),
por lo que hay que normalizar antes de mandar.
"""

import re

PREFIJO_MX = "55"


def normalizar_numero_mx(telefono: str) -> str:
    """
    Normaliza un número de WhatsApp al formato E.164 con prefijo de México.

    Reglas:
      - Elimina espacios, guiones y paréntesis.
      - Si empieza con `00`, lo traduce a `+`.
      - Si ya trae `+`, se conserva.
      - Si empieza con `0` (formato nacional), se reemplaza por `55`.
      - Si tiene 10 dígitos, se asume nacional y se prefija con `55`.
      - Si tiene 12 dígitos y empieza con `52` (México móvil), se corrige a `55`.

    >>> normalizar_numero_mx("+52 1 55 1234 5678")
    '5215512345678'
    >>> normalizar_numero_mx("5512345678")
    '525512345678'
    >>> normalizar_numero_mx("1234567890")
    '551234567890'
    """
    if telefono is None:
        return ""

    numero = re.sub(r"[^0-9+]", "", str(telefono).strip())

    if numero.startswith("00"):
        numero = "+" + numero[2:]

    if numero.startswith("+"):
        numero = numero[1:]

    # Formato nacional con cero inicial -> prefijo internacional
    if numero.startswith("0"):
        numero = PREFIJO_MX + numero[1:]

    # 12 dígitos empezando por 52 (prefijo viejo de móvil en México)
    if len(numero) == 12 and numero.startswith("52"):
        numero = PREFIJO_MX + numero[2:]

    # 10 dígitos -> número nacional mexicano
    if len(numero) == 10 and numero.isdigit():
        numero = PREFIJO_MX + numero

    return numero


def formatear_legible(numero: str) -> str:
    """Formato para mostrar al usuario: +55 1 55 1234 5678."""
    if len(numero) == 13 and numero.startswith("521"):
        return f"+52 1 {numero[3:5]} {numero[5:9]} {numero[9:13]}"
    if len(numero) == 12 and numero.startswith("52"):
        return f"+52 {numero[2:4]} {numero[4:8]} {numero[8:12]}"
    return f"+{numero}"
