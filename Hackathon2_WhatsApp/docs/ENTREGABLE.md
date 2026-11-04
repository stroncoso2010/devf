# Entregable mínimo — Hackathon 2

Checklist de evidencia que el equipo presenta para acreditar el Hackathon.
Todo está ejecutado y guardado en este repositorio.

## 1. El agente funcionando sobre WhatsApp

| Evidencia | Estado | Dónde |
|---|---|---|
| Webhook con verificación de Meta (handshake `hub.verify_token` + `hub.challenge`) | ✅ 200 con challenge `67890` | `resultados/salida_consola.txt` → `[HANDSHAKE] OK` |
| Recepción de mensajes con el formato real de la Cloud API (`entry/changes/value/messages`) | ✅ | `src/servidor.py` + `src/cliente_prueba.py` |
| Respuesta entregada al canal (7/7 mensajes) | ✅ | `resultados/mensajes_salientes.json` |
| Idempotencia ante reintentos de Meta (por `wamid`) | ✅ | `servidor._mensajes_procesados` |
| Demo en vivo (Fase 3) con `iniciar.ps1` + `cliente_prueba.py` | ✅ reproducible | `INSTRUCCIONES.md` |

> En el repositorio se corre contra un receptor local de Graph API en
> `127.0.0.1:8890` (mismo formato que Meta). Para la demo con WhatsApp real solo
> hay que cambiar `graph_api_base` a `https://graph.facebook.com` y usar ngrok.

## 2. Decisiones técnicas explicadas

| Tema | Dónde está la explicación |
|---|---|
| Estado de la conversación (conversation por teléfono + lock + límite de 8) | `docs/DECISIONES.md` §1 |
| Function calling (contrato vs. implementación, validación, idempotencia) | `docs/DECISIONES.md` §2 |
| Capa de seguridad (guard + hook Llama Guard) | `docs/DECISIONES.md` §3 |
| Reglas fijas antes del modelo | `docs/DECISIONES.md` §4 |
| Confiabilidad (timeouts, reintento, fallback, saneado) | `docs/DECISIONES.md` §5 |
| Monitoreo y medición por fases | `docs/DECISIONES.md` §6 |
| Estrategia de prueba | `docs/DECISIONES.md` §7 |

## 3. Las cuatro piezas del Módulo 2 presentes

1. **Cloud API** — webhook handshake + formato Graph + BackgroundTasks + idempotencia.
2. **Agente con memoria y estado** — conversation por teléfono, lock, recorte.
3. **Llama como motor + function calling** — 3 herramientas, loop de dos llamadas.
4. **Producción** — guard de entrada/salida, timeouts, fallback, endpoints de
   monitoreo (`/estado`, `/bitacora`, `/historial`, `/reservas`, `/reiniciar`).

## 4. Resultado de la prueba ejecutada (veredicto 8/8)

```
[OK] 1 FAQ del menu dispara buscar_pregunta_frecuente
[OK] 2 Disponibilidad dispara consultar_disponibilidad (datos reales)
[OK] 3 Reserva creada con datos recuperados de la memoria
[OK] 4 Intoxicacion -> regla urgencia_salud (sin Llama)
[OK] 5 Gerente -> regla escalado_humano (sin Llama)
[OK] 6 Prompt injection -> bloqueado por el guard (sin Llama)
[OK] 7 Follow-up del domingo responde con historial (sin repetir datos)
[OK] 8 Handshake de Meta verificado + 7 mensajes entregados
TOTAL: TODOS LOS ESCENARIOS OK
```

Artefactos en `resultados/`:

| Archivo | Contenido |
|---|---|
| `salida_consola.txt` | salida íntegra de la prueba (7 escenarios + verificaciones) |
| `conversacion.json` | bitácora: fuente (guard/regla/modelo), herramientas, latencias por fase, recortes |
| `estado_sesiones.json` | sesión por teléfono, límite e items borrados |
| `mensajes_salientes.json` | los 7 mensajes entregados al canal |
| `reservas.json` | reserva creada por function calling (R-101) |

## 5. Criterios típicos de un Hackathon (autoevaluación)

| Criterio | Cumplimiento |
|---|---|
| Resuelve un problema real (reservas + FAQ de un restaurante) | ✅ con datos y políticas reales (días cerrados, máximo 8, gracia de 15 min) |
| Memoria/estado por usuario | ✅ reserva creada sin repetir datos |
| Function calling con datos reales | ✅ 3 herramientas, validación y timeout |
| Capa de seguridad | ✅ guard por reglas + hook Llama Guard + saneado de salida |
| Prueba demostrable y reproducible | ✅ veredicto 8/8 con un solo comando |
| Código ordenado y documentado | ✅ README, instrucciones, decisiones, proceso |

## 6. Limites conocidos (honestidad técnica)

- Las reservas viven en memoria del proceso: para producción, base de datos.
- El guard por reglas cubre inyección y contenidos groseros; el modelo real de
  seguridad (llama-guard3) está enchufado pero **desactivado** por defecto.
- Latencia de15–60 s por turno del modelo grande en CPU; las capas baratas
  (guard, reglas, FAQ) están delante para que la mayoría de mensajes responda
  en milisegundos.
- Sin WhatsApp real en el repo (se usa receptor local): la conexión real es un
  cambio de configuración, no de código.
