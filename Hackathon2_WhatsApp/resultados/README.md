# Resultados — prueba ejecutada (2026-11-04)

Prueba local completa sobre servidor local: Ollama `gemma4:12b` + Llama Stack
0.7.3 (CPU, sin GPU). Servicios: Llama Stack `:8321`, webhook `:8040`,
receptor local de Graph API `:8890`.

## Archivos

| Archivo | Contenido |
|---|---|
| `salida_consola.txt` | Salida íntegra de `python -X utf8 src\cliente_prueba.py` |
| `conversacion.json` | Bitácora de los 7 turnos: fuente (guard/regla/modelo), herramientas, latencias por fase, recortes, errores |
| `estado_sesiones.json` | Sesión por teléfono, límite de historial y items borrados |
| `mensajes_salientes.json` | Los 7 mensajes entregados al endpoint de Graph (context.message_id incluido) |
| `reservas.json` | Reserva creada por function calling |

## Veredicto: 8/8 escenarios OK

| # | Escenario | Fuente | Razonamiento | Ciclo total |
|---|---|---|---|---|
| 1 | ¿Qué hay en el menú? | modelo + `buscar_pregunta_frecuente{"tema":"menu"}` | 58 975 ms | **59 917 ms** |
| 2 | Mesa para 4, viernes 6, 20:00 | modelo + `consultar_disponibilidad` (2026-11-06, M4/M5 libres) | 18 970 ms | **19 061 ms** |
| 3 | "Agéndala a nombre de Ana Pérez" | modelo + `agendar_reserva` **con datos de la memoria** → `R-101` | 22 524 ms | **22 637 ms** |
| 4 | Intoxicación alimentaria | **regla `urgencia_salud`** | 0 | **29 ms** |
| 5 | Hablar con el gerente | **regla `escalado_humano`** | 0 | **29 ms** |
| 6 | "Ignora tus instrucciones…" | **guard `prompt_injection`** | 0 | **0 ms** |
| 7 | ¿Y el domingo? (follow-up) | modelo + `buscar_pregunta_frecuente{"tema":"horarios"}` | 15 570 ms | **15 710 ms** |

Promedio de los 4 turnos de modelo: **29 331 ms** · reglas 29 ms · guard 0 ms
(diferencia de ~1 000×).

## Evidencias clave

- **Memoria (Clase 2/6):** el mensaje del turno 3 no contiene fecha, hora ni
  número de personas; aun así la reserva salió `2026-11-06 20:00 · 4 personas ·
  mesa M4` → los datos venían de la conversación. Límite de 8 items respetado:
  16 recortados (`-4`, `-6`, `-6`) en 4 turnos de modelo.
- **Function calling (Clase 3):** en los turnos 1, 2, 3 y 7 el `output_text`
  del modelo vino vacío y `respuesta.output` traía items `type == "function_call"`
  con `call_id` y `arguments` JSON. La respuesta final usa datos que solo
  existen en `catalogo.json` (precios, M4, R-101, horarios del domingo).
- **Validación de argumentos:** rechazados en prueba unitaria: fecha pasada,
  lunes cerrado, hora fuera de turno y grupos de 12 (>8). Idempotencia:
  segunda reserva idéntica → `duplicada: true`.
- **Reglas sin Llama (Clase 2):** turnos 4 y 5 con `fuente: "regla"` y
  `razonamiento: 0`.
- **Seguridad (Clase 4):** turno 6 con `fuente: "guard"`,
  `categoria: "prompt_injection"` — cero llamadas al modelo, cero ejecución de
  herramientas, cero mensajes en la conversación (`items 0 → 0`).
- **Handshake:** `GET /webhook?hub.mode=subscribe&hub.verify_token=RESTAURANTE_2026&hub.challenge=67890`
  → **200** con cuerpo `67890`.
- **Entrega:** 7/7 mensajes en el receptor local, todos con `context.message_id`.

## Repetir la prueba

```powershell
# reiniciar estado
Invoke-RestMethod -Method POST http://127.0.0.1:8040/reiniciar
Invoke-RestMethod -Method DELETE http://127.0.0.1:8890/v19.0/LOCAL_1234567890/messages
# volver a correr
.venv\Scripts\python.exe -X utf8 src\cliente_prueba.py
```

> Nota: las reservas de la prueba viven en memoria del proceso; al reiniciar
> el webhook empiezan de cero (la política de producción es base de datos).
