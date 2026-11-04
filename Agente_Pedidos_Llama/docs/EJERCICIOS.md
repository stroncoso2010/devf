# Ejercicios — Integración Llama + WhatsApp (function calling)

Resolución de los 3 ejercicios del tema, con los datos reales de la prueba
ejecutada en este proyecto (ver `resultados/salida_consola.txt`).

---

## Ejercicio 1 — Descripción técnica de `consultar_clima(ciudad, fecha)`

**Contrato propuesto para el modelo:**

```json
{
  "type": "function",
  "name": "consultar_clima",
  "description": "Recibe una ciudad (texto) y una fecha (YYYY-MM-DD) y devuelve el pronóstico del tiempo para esa ciudad en esa fecha: temperatura mínima y máxima en °C, probabilidad de lluvia y condición general. Úsala EXCLUSIVAMENTE cuando el usuario pregunte por el clima o el tiempo de un lugar y día concretos; no la uses para reservar hoteles, consultar disponencia de alojamiento ni paquetes turísticos.",
  "parameters": {
    "type": "object",
    "properties": {
      "ciudad": {
        "type": "string",
        "description": "Nombre de la ciudad, por ejemplo 'Guadalajara'"
      },
      "fecha": {
        "type": "string",
        "description": "Fecha en formato YYYY-MM-DD, por ejemplo '2026-11-05'"
      }
    },
    "required": ["ciudad", "fecha"]
  }
}
```

**Por qué está escrita así:**

- **Tipos explícitos**: `ciudad` string, `fecha` string con formato `YYYY-MM-DD`
  (el modelo sabe rellenarlo; el servidor puede validar con regex antes de tocar la API).
- **Una sola oración de descripción** que delimita el alcance: dice *qué devuelve*
  (temperatura, lluvia, condición) y, sobre todo, **cuándo NO usarla** ("no la uses
  para reservar hoteles…"). La ambigüedad clásica con `consultar_hotel` es que ambas
  reciben ciudad y fecha: la separación segura es por *acción de retorno*
  (pronóstico vs. disponibilidad), no por los parámetros.
- **Ejemplo en cada parámetro**: reduce los argumentos inventados.
- Si se describiera solo como "obtiene información del clima", el modelo podría
  confundirla con una herramienta de disponibilidad turística cuando el usuario
  diga algo como "¿qué clima hay en Cancún el 15 para mi viaje?".

> Aplicado en este proyecto: `consultar_pedido` lleva la misma estructura
> ("…Usala EXCLUSIVAMENTE cuando el cliente pregunte por el estado…; no la uses
> para dudas generales") y `buscar_pregunta_frecuente` dice lo contrario. Por eso
> el modelo elige bien: en la prueba, "¿qué formas de pago aceptan?" llamó a la FAQ
> y "¿dónde está mi pedido 9988?" llamó a `consultar_pedido`.

---

## Ejercicio 2 — Ciclo completo de "Quiero mi factura del pedido 9988"

| # | Paso | Qué ocurre exactamente | Dónde en este proyecto |
|---|---|---|---|
| 1 | **Webhook recibe el mensaje** | Meta envía el evento HTTP; el servidor valida `hub.mode`/token en el GET, y en el POST parsea el payload, extrae `from` (teléfono), `text.body` y `id` (wamid). Respeta la **idempotencia**: si el wamid ya se procesó, lo ignora (Meta reintenta entregas). | `src/servidor.py` → `recibir_mensaje()` + `_mensajes_procesados` |
| 2 | **Respuesta inmediata a Meta + BackgroundTasks** | Responde `{"status":"received"}` 200 de inmediato y delega el proceso pesado a una tarea en threadpool (función **síncrona**, para no congelar el event loop). | `background.add_task(_procesar_y_responder, …)` |
| 3 | **Lock por teléfono + reglas fijas** | Se serializan los mensajes del mismo número. Se evalúan primero las reglas de urgencia y escalamiento: "factura del pedido 9988" **no** dispara ninguna, así que se continúa. | `src/memoria.py`, `src/reglas.py` |
| 4 | **Servidor arma el contexto** | Recupera la conversación de ese teléfono (`conversation_id` de Llama Stack), manda el mensaje del usuario con las *instructions* del sistema y el catálogo de herramientas. | `src/agente.py` → `procesar()` |
| 5 | **Llama procesa y decide** ← **aquí ocurre el function calling** | El modelo devuelve items con `type == "function_call"`, por ejemplo `consultar_pedido({"numero_pedido": 9988})`, y **no** texto libre (`output_text` vacío). | `agente.py` → detecta `llamadas` en `respuesta.output` |
| 6 | **Validación ANTES de ejecutar** | `_validar_argumentos` comprueba: la herramienta existe, `numero_pedido` está presente, es entero y positivo. Si el modelo pidiera `{"numero_pedido": null}` o `"abc"`, se rechaza aquí **sin tocar los datos**. (Nota: el endpoint de facturas suele requerir además permiso/propiedad del pedido — en producción se valida el teléfono contra el pedido antes de consultar.) | `src/herramientas.py` → `_validar_argumentos()` |
| 7 | **Ejecución real + timeout** | La función corre contra `configuracion/catalogo.json` dentro de un `ThreadPoolExecutor` con timeout de 3 s; devuelve `{"ok": true, …}` o `{"ok": false, "error": …}` sin lanzar excepciones. | `agente.py` → `_ejecutar_herramienta()` |
| 8 | **Devolución del resultado al modelo** | Se arma el par `function_call` + `function_call_output` con el resultado en JSON. | `agente.py` → `entradas.append(…)` |
| 9 | **Segunda llamada: redacción final** | Llama recibe el dato crudo y redacta la respuesta en lenguaje natural, en español y máximo 3 líneas, con los datos del sistema (nunca inventa). | 2ª iteración del loop en `agente.py` |
| 10 | **Recorte de historial** | Se aplica el límite de 8 items a la conversación (`order="asc"` para borrar los más viejos). | `memoria.py` → `recortar()` |
| 11 | **Envío al usuario** | Se valida la longitud (máx. 1500 caracteres) y se llama al endpoint de la Graph API con `context.message_id` para responder en el mismo hilo. | `servidor.py` → `_procesar_y_responder()` |

**Tipo de respuesta esperada de regreso (paso 7):** un JSON estructurado, no
prosa, por ejemplo:

```json
{
  "ok": true,
  "numero_pedido": 9988,
  "estado": "en_tránsito",
  "transportista": "Estafeta",
  "guia": "7123456789",
  "fecha_estimada": "2026-11-05",
  "ultimo_movimiento": "2026-11-01: paquete en centro de distribución Guadalajara",
  "total": 1249.0,
  "moneda": "MXN",
  "pagado": true
}
```

Con `ok: false, "error": "No existe el pedido …"` cuando no existe. El JSON
estructurado es lo que permite al modelo redactar el cierre sin perder datos.

**Respuesta final observada en la prueba real:**

> Tu pedido 9988 está en tránsito con Estafeta (guía: 7123456789).
> La fecha estimada de entrega es el 05/11/2026.
> Último movimiento: Paquete en centro de distribución Guadalajara el 01/11/2026.

---

## Ejercicio 3 — Dos cambios para reducir la latencia percibida (mismo hardware)

**Cambio 1: separar la *decisión* de la *redacción* con un modelo pequeño de
triage (dos velocidades).**

En este equipo, `gemma4:12b` tardó **65 s** en el primer turno y 12–28 s en los
demás. El costo no está solo en "generar tokens": está en que el modelo grande
hace a la vez *clasificar intención + decidir herramienta + redactar*. Si un
modelo pequeño (`qwen3.5:0.8b`, ~1–2 s en CPU) decide **si hace falta llamar a
una herramienta y con qué argumentos**, y solo el modelo grande redacta cuando
hay dato real que comunicar, el 70 % de los mensajes (saludos, dudas simples con
FAQ ya resueltas, agradecimientos) se resuelven en segundos. Mismo hardware,
misma calidad donde importa, cola de espera mucho menor.

*Evidencia en este proyecto:* las **reglas fijas** aplican exactamente esta
idea y responden en **26–30 ms** frente a los 12 570–65 027 ms del modelo.
Mover la clasificación a un componente barato (modelo pequeño o regex) antes
del modelo grande es el mismo principio, aplicado al resto de mensajes.

**Cambio 2: respuesta optimista + procesamiento asíncrono con "escribiendo…"
y streaming parcial.**

El usuario no percibe el tiempo del webhook ni el de la validación: percibe el
silencio. Dos medidas concretas:

1. **Mensaje de cortesía inmediato** ("Recibí tu consulta, un momento…") apenas
   llega el wamid — cuesta milisegundos — y luego el mensaje final en el mismo
   hilo (`context.message_id`). El tiempo *percibido* baja de 65 s a <1 s,
   aunque el tiempo total de ciclo no cambie.
2. **Cancelar el trabajo muerto**: el webhook ya responde 200 a Meta de
   inmediato (lo implementado en `servidor.py`) y, además, se puede:
   - cachear respuestas de FAQ por tema (la misma pregunta frecuente no debe
     volver a pasar por el modelo: 65 s → 0 ms);
   - descartar turnos obsoletos del mismo teléfono (si llega un mensaje nuevo
     mientras se procesa el anterior, el anterior ya no se envía);
   - reducir `max_output_tokens` (aquí 220): el usuario pide 3 líneas, no un
     ensayo.

> Otros candidatos válidos (no elegidos por ir más allá del alcance): modelo
> cuantizado más liviano, cuartear la respuesta con *streaming* para que el
> indicador "escribiendo…" se convierta en texto visible, o precarga del
> catálogo de pedidos en memoria.

---

## Glosario del tema aplicado

| Término | Definición | Ejemplo aquí |
|---|---|---|
| Function calling | Capacidad de indicar que debe ejecutarse una función con argumentos, en vez de responder solo texto | `consultar_pedido({"numero_pedido":9988})` |
| Herramienta (tool) | Función real expuesta al modelo con descripción y parámetros | `ESQUEMAS` en `src/herramientas.py` |
| Motor de rol / de razonamiento | Rol de Llama: interpretar, elegir estrategia y sintetizar la salida | `AgentePedidos.procesar()` |
| Latencia del ciclo | Tiempo total desde que llega el mensaje hasta que se envía la respuesta | columna `latencia_ms` en `/bitacora` |
| Idempotencia | Ejecutar dos veces la misma entrega no duplica efectos | `_mensajes_procesados` con el wamid |
| Tool output | Resultado devuelto al modelo para que redacte la respuesta final | `function_call_output` |
