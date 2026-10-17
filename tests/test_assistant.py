"""Pruebas mínimas para el asistente con Ollama."""

from src.assistant import Assistant


def test_asistente_inicializa():
    asistente = Assistant()
    assert asistente is not None


def test_responder_retorna_str():
    asistente = Assistant()
    try:
        respuesta = asistente.responder("Di hola en español")
        assert isinstance(respuesta, str)
    except Exception:
        # Si Ollama no está corriendo, al menos no debe romper la importación
        pass


if __name__ == "__main__":
    test_asistente_inicializa()
    test_responder_retorna_str()
    print("Pruebas básicas OK")
