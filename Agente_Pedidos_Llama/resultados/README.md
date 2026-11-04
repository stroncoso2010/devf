# Resultados — prueba ejecutada (2026-11-03)

Prueba local completa sobre servidor local: Ollama `gemma4:12b` + Llama Stack 0.7.3
(CPU, sin GPU). Servicios: Llama Stack `:8321`, webhook `:8030`, mock de Graph API `:8890`.

## Archivos

| Archivo | Contenido |
|---|---|
| `salida_consola.txt` | Salida íntegra de `python -X utf8 src\cliente_prueba.py` |
| `conversacion.json` | Bitácora de los 6 turnos: fuente, regla, herramientas, latencias por fase, recortes |
| `estado_sesiones.json` | Sesiones por teléfono, límite de historial y items borrados |
| `mensajes_salientes.json` | Los 6 mensajes entregados al endpoint de Graph API (mock) |

## Resumen numérico

**Veredicto: 6/6 escenarios OK.**

| # | Escenario | Fuente | Razonamiento | Acción | Ciclo total |
|---|---|---|---|---|---|
| 1 | ¿Qué formas de pago aceptan? | llama-stack + `buscar_pregunta_frecuente{"tema":"pagos"}` | 64 972 ms | 0 ms | **65 027 ms** |
| 2 | Cargo duplicado | **regla `urgencia_fraude`** | 0 | 0 | **30 ms** |
| 3 | Hablar con una persona | **regla `escalado_humano`** | 0 | 0 | **26 ms** |
| 4 | ¿Dónde está mi pedido 9988? | llama-stack + `consultar_pedido{"numero_pedido":9988}` | 28 499 ms | 0 ms | **28 590 ms** |
| 5 | ¿Y en qué fecha llega? | llama-stack (memoria: 05/11/2026 sin repetir el nº) | 12 507 ms | 0 ms | **12 570 ms** |
| 6 | Pedido 123456 | llama-stack + `consultar_pedido` **RECHAZADA** por validación | 22 482 ms | 0 ms | **22 596 ms** |

Promedio de los 4 turnos de modelo: **32 196 ms** · turnos de regla: **28 ms**
(diferencia de ~1 150×).

## Evidencias clave

- **Function calling**: en los turnos 1, 4 y 6 el `output_text` del modelo vino
  vacío y `respuesta.output` traía items `type == "function_call"` con
  `call_id` y `arguments` JSON.
- **Integración de resultados**: la respuesta final del turno 4 incluye datos que
  solo existen en `catalogo.json` (Estafeta, guía 7123456789, 05/11/2026): el
  modelo **no los inventó**, los redactó a partir del `function_call_output`.
- **Memoria**: turno 5 "¿Y en qué fecha llega?" → "05/11/2026" sin mencionar el
  número de pedido en el mensaje de entrada.
- **Límite de historial**: 8 items de techo; 12 borrados en 3 turnos
  (`-4`, `-2`, `-6`); al cierre, la sesión quedó en 8 items.
- **Reglas sin Llama**: turnos 2 y 3 con `fuente: "regla"` y `fases_ms.razonamiento: 0`.
- **Handshake**: `GET /webhook?hub.mode=subscribe&hub.verify_token=PEDIDOS_2026&hub.challenge=12345`
  → **200** con cuerpo `12345`.
- **Entrega**: 6/6 mensajes en el mock, todos con `context.message_id` del wamid entrante.

## Notas

- Las latencias varían entre corridas (CPU compartida): el primer turno del proceso
  es el más lento por la carga del modelo en Ollama.
- El escenario 6 muestra la validación de argumentos en acción: el modelo pidió un
  pedido inexistente, el servidor devolvió `ok:false` y la redacción final fue
  honesta, sin mezclar datos de otros pedidos.
- Para repetir: `POST /reiniciar` + `DELETE` del mock y volver a correr el cliente.
