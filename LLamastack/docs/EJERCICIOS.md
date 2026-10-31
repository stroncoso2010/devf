# Ejercicios resueltos — Agente de la Veterinaria con Llama Stack

Cada ejercicio se resuelve con **datos reales de la prueba local** ejecutada en
`resultados/` (ver `resultados/salida_consola.txt`).

---

## Ejercicio 1: La memoria paso a paso

**Pregunta.** Sigue el escenario A (5 mensajes del mismo teléfono) y responde:

1. ¿Qué identificador de conversación de Llama Stack recibe el teléfono
   `5215511110009`?
2. ¿Cuántos items hay en la conversación tras cada turno?
3. ¿Qué items se borran y en qué turno?

**Respuesta (datos reales de `resultados/conversacion.json` y
`estado_sesiones.json`):**

| Turno | Mensaje | Items antes → después | Detalle |
|---|---|---|---|
| 1 | "Hola, quiero una cita dental para mi perrito Max" | 0 → 2 | Se crea la conversación `conv_290e16fcf1dc55b15…` con `client.conversations.create()` |
| 2 | "El martes me queda mejor" | 2 → 4 | El modelo responde "…cita dental para Max el martes" (recuerda el servicio del turno 1) |
| 3 | "Son las 10 de la manana?" | 4 → 6 | Sigue la conversación sin repetir datos |
| 4 | "Perfecto, agendala" | 6 → 8 | Llega al límite (`max_items_historial: 8`) |
| 5 | "Cual fue el servicio que pedi al inicio?" | 8 → 8 | **Recorte**: se borran los 2 items más antiguos (turno 1) y se responden los 2 nuevos |

**Clave:** el límite no corta la respuesta — primero el modelo responde con el
historial completo y **después** se recortan los items más antiguos
(`memoria.recortar`, `order="asc"`). El turno 5 responde "Solicitaste una cita
dental…": el modelo recuperó el dato del turno 1 **antes** de que ese turno se
borrara.

---

## Ejercicio 2: ¿Regla fija o modelo?

**Pregunta.** Para cada intención del usuario, decide si la responde una
**regla fija** (código) o el **modelo**, y justifica:

| Intención | Respuesta | Justificación |
|---|---|---|
| "Quiero hablar con una persona" | **Regla fija** (`escalado_humano`) | Decisión de negocio: no se delega al modelo. Medido: 27 ms vs 32 s promedio del modelo |
| "Mi perrito está sangrando mucho, ¡es una urgencia!" | **Regla fija** (`urgencia_medica`) | Una urgencia médica no puede esperar a que el modelo decida. Medido: 28 ms |
| "¿Qué servicio le puedo agendar a mi gato?" | **Modelo** (Llama Stack + Ollama) | Consulta abierta que requiere lenguaje natural |
| "¿Cuál fue el servicio que pedí al inicio?" | **Modelo** con memoria | Resolución de referencia a mensajes anteriores: solo el modelo con historial lo resuelve |

**Regla de decisión:** si la respuesta es **siempre la misma** o **no puede
esperar** → regla fija. Si requiere **comprensión o generación de lenguaje** →
modelo.

**Evidencia del costo** (`resultados/conversacion.json`):

```
latencia modelo: 19,342 – 40,817 ms  (promedio 32,126 ms)
latencia reglas: 27 y 28 ms          (~1,190× más rápido)
```

---

## Ejercicio 3: El límite de historial

**Pregunta.** Con `max_items_historial: 8`:

1. ¿Cuántos intercambios (turnos) caben antes del primer recorte?
2. Después del recorte del turno 5, ¿qué conversación "ve" el modelo en el
   turno 6?
3. ¿Qué pasaría si el usuario pregunta en el turno 6 por su teléfono dado en
   el turno 1?

**Respuesta:**

1. Cada turno agrega **2 items** (mensaje usuario + respuesta asistente):
   `8 ÷ 2 = 4` intercambios completos. El recorte ocurre al **5º turno**.

2. Tras el recorte la conversación conserva los **8 items más recientes**
   (turnos 2 a 5). Verificado en la prueba: los items restantes empiezan en
   `"Perfecto, agendala"` y terminan en `"Solicitaste una cita dental…"`.

3. **El dato se habría perdido** — es la limitación conocida de una ventana
   fija: los datos duros del turno 1 ya no están en el historial. En este
   proyecto ese problema lo cubre el patrón de la clase: para datos que
   **deben persistir** (citas, folios, datos del cliente) se usa almacenamiento
   externo (base de datos), no el historial de conversación. El historial de
   Llama Stack sirve para **coherencia conversacional**, no como base de datos.

**Extra:** ¿por qué dos teléfonos no se mezclan? Porque cada número recibe su
propia conversación:

```
5215511110009 → conv_290e16fcf1dc55b15…  (5 turnos, 2 borrados)
5215522220001 → conv_87bcb807b546dadf7…  (1 turno, 0 borrados)
```

La memoria se aísla por `telefono`, no es global.

---

## Ejercicio 4 (opcional): Verificar el handshake del webhook

**Pregunta.** Meta verifica el webhook con `hub.mode`, `hub.verify_token` y
`hub.challenge`. ¿Qué responde el servidor si el token no coincide?

**Respuesta:** `403` con `{"error": "token de verificacion invalido"}`. Si
coincide, devuelve el `hub.challenge` como entero. Verificado en la prueba:

```
[HANDSHAKE] OK -> 200 12345
```
