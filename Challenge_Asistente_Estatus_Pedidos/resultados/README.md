# Resultados de la prueba local

Salidas de `python src/cliente_prueba.py` contra el **Ollama del PC** y el servidor local de Meta.

| Archivo | Contenido |
|---|---|
| `CONVERSACION.md` | La conversación completa, legible, con la fuente de cada respuesta |
| `conversacion.json` | La misma conversación en JSON |
| `bitacora.json` | Los 8 pasos de la prueba con entradas y salidas |
| `metricas.json` | Tiempos, conteos y modelo usado |
| `salida_consola.txt` | Salida de consola de la corrida |
| `servidor.log` | Log del servidor (envíos al servidor local de Meta) |

## Última corrida

| Métrica | Valor |
|---|---|
| Fecha | 2026-10-30 13:02 |
| Duración total | ~1.0 s |
| Modelo | `qwen3.5:0.8b` (Ollama local, `127.0.0.1:11434`) |
| `think` | 0 (desactivado) |
| Escenarios | 8/8 OK |
| Latencia de la ruta LLM | 0.9 – 3.1 s |
| Mensajes enviados por el bot | 5 |

## Escenarios cubiertos

1. Health check (servidor + servidor local + Ollama)
2. Verificación de credenciales del webhook (`hub.challenge` en texto plano)
3. Usuario nuevo → saludo de bienvenida
4. Usuario conocido con folio → datos del catálogo
5. Consulta de estatus sin folio → regla determinista (pide el folio)
6. Folio inexistente → "no encontrado"
7. Conversación general → ruta LLM, máximo 3 líneas
8. Estadísticas finales del asistente

## Cómo regenerarlos

```powershell
.\iniciar_prueba local.ps1
```

Los archivos se sobrescriben en cada corrida.
