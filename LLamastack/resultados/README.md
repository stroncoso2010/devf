# Resultados de la prueba local

Salidas ejecutadas con:

```bash
python src/cliente_prueba.py
```

| Archivo | Contenido |
|---|---|
| `salida_consola.txt` | Salida completa de la prueba (4 escenarios) |
| `conversacion.json` | Trazas de los 8 turnos: fuente (modelo/regla), latencia, items antes/después, recorte |
| `estado_sesiones.json` | Sesiones de Llama Stack por teléfono: conversation_id, turnos, items borrados |
| `mensajes_salientes.json` | Los 8 mensajes que el webhook envió al API de Meta (mock) |

## Resumen medido

```
turnos totales  : 8   (6 con modelo, 2 con regla fija)
latencia modelo : 19,342 – 40,817 ms  (promedio 32,126 ms)
latencia reglas : 27 y 28 ms
items borrados  : 2  (recorte al superar max_items_historial=8)
handshake       : 200 OK
envíos a Meta   : 8/8
```

## Escenarios cubiertos

1. **Memoria** — 5 mensajes del mismo teléfono; el turno 5 responde
   correctamente "¿qué servicio pedí al inicio?" (turno 1) y aplica el
   recorte de historial.
2. **Escalamiento** — "quiero hablar con una persona" → regla fija en 27 ms.
3. **Urgencia médica** — "está sangrando, es una urgencia" → regla fija en
   28 ms.
4. **Memoria aislada** — segundo teléfono con su propia conversación.
