# Proceso de construcción — decisiones y problemas resueltos

Registro de lo que se encontró y cómo se resolvió durante la construcción del
agente. Datos de la prueba real ejecutada el 2026-11-03.

## Decisiones de diseño

### 1. Reusar la arquitectura del challenge anterior (conversación + lock)
El challenge pide explícitamente "reutilizar la misma arquitectura de Llama Stack
(conversación + lock)". Se copiaron `memoria.py`, `reglas.py`, `normalizacion.py`,
`config.py` y `mock_meta.py` del proyecto de la veterinaria, y se escribieron
`herramientas.py` y `agente.py` desde cero para el loop de function calling.
El `.venv` se comparte por junction: mismas dependencias, cero reinstalación.

### 2. Separar CONTRATO de IMPLEMENTACIÓN (el tema lo exige explícitamente)
`herramientas.py` mantiene dos bloques claramente separados:

- `ESQUEMAS` → lo que el modelo **lee** (nombre, descripción, parámetros tipados).
- `consultar_pedido()` / `buscar_pregunta_frecuente()` → lo que **corre** en el
  servidor contra `configuracion/catalogo.json` (datos reales, no texto inventado).

Ambas descripciones dicen también **cuándo NO usarse**, para que el modelo no
confunda la consulta de estatus con las dudas generales.

### 3. Dos herramientas para cubrir las dos familias del reto
- `consultar_pedido(numero_pedido: int)` → el caso práctico del tema (pedido 4521).
- `buscar_pregunta_frecuente(tema: str)` → la FAQ como "RAG ligero": en vez de
  montar embeddings + recuperación aparte, la búsqueda se expone como función
  bajo el mismo mecanismo de function calling.

### 4. Reglas fijas ANTES del modelo, motor genérico
`reglas.py` evaluaba claves *hardcodeadas* del proyecto anterior
(`urgencia_medica`). Se reescribió `evaluar()` para recorrer **todas** las reglas
del JSON en orden: agregar una regla nueva ya no requiere tocar Python.
Resultado medido: la regla responde en **26–30 ms**; el modelo tarda 12–65 s.

### 5. Medir el ciclo completo por fases (el tema lo pide)
Cada traza de `/bitacora` registra `fases_ms.razonamiento` (llamadas al modelo),
`fases_ms.accion` (ejecución de herramientas) y `latencia_ms` (ciclo total, lo
único que percibe el usuario). El cronómetro corre **dentro del lock**, así que
el ciclo incluye también la espera de sucesión del mismo teléfono.

### 6. Mock local de Graph API
Se evita WhatsApp real + ngrok: `mock_meta.py` reproduce
`POST/GET/DELETE /v19.0/{phone_id}/messages` en 127.0.0.1:8890, suficiente para
ver handshake, idempotencia y mensajes salientes.

## Problemas encontrados y soluciones

### 1. La regla de urgencia no disparó (escenario 2 falló)
**Síntoma:** "Me cobraron dos veces… cargo duplicado" fue al modelo en 63 s.
**Causa:** `reglas.py` copiado traía `evaluar()` con las claves de la veterinaria
(`escalado_humano` + `urgencia_medica`); la clave nueva `urgencia_fraude` nunca se
evaluaba, y como el dict `reglas` sí existía, no había error.
**Solución:** `evaluar()` genérico por iteración sobre el config. Repetida la
prueba: **regla en 30 ms, sin llamada al modelo**.

### 2. Excepción de Llama Stack: el turno desaparecía (escenario 5)
**Síntoma:** el follow-up "¿Y en qué fecha llega?" no entraba a la bitácora;
`webhook.err` mostraba `APIConnectionError` propagado desde `responses.create`.
**Causa raíz:** error transitorio **Llama Stack ↔ Ollama** (500 en el servidor de
Llama Stack). El `except` no existía, la tarea en background moría y **el usuario
no recibía nada**.
**Solución (dos capas):**
1. **Reintento** en `_llamar_modelo` (2 intentos, espera de 2 s).
2. **Fallback**: el bloque del modelo quedó en `try/except`; si ambos intentos
   fallan, la traza se registra con `error` y el usuario recibe "problema temporal
   del servicio" en lugar de silencio. Esto es exactamente el "manejo de errores y
   timeouts" que pide el tema.

### 3. El veredicto dependía de la posición de los turnos
**Síntoma:** un turno de error o un reintento desplazaba los índices y el resumen
marcaba "FALLA" aunque el comportamiento fuera correcto.
**Solución:** `resumen()` ahora busca cada escenario **por el contenido del
mensaje** (`buscar("cargo duplicado")`, etc.) y valida el turno real.

### 4. Argumentos como string vs dict
El modelo devuelve `arguments` como string JSON (`'{"numero_pedido":9988}'`), no
como dict. `_ejecutar_herramienta` parsea ambos casos y captura
`JSONDecodeError` devolviendo `ok:false` — nunca excepción al modelo.

### 5. El modelo a veces tipa mal el número
En la práctica `numero_pedido` llegó a venir como `"9988"` (texto). La validación
convierte strings numéricos a entero y rechaza el resto (`RECHAZADA`) — así se
comprueba la validación de argumentos con el pedido 123456 inexistente: el modelo
la pidió, el servidor respondió con `ok:false` y la redacción final fue honesta
("no encontramos el pedido…"), sin inventar datos de otro pedido.

### 6. Recorte de historial intercalando function_call
Con function calling un turno mete **4 items** (user + function_call +
function_call_output + assistant), así que el límite de 8 se alcanza en dos
turnos. Se observó: `-4`, `-2` y `-6` items borrados. El recorte usa
`order="asc"` (Llama Stack lista los items por defecto del más nuevo al más
viejo; borrar "los primeros" de esa lista borraría los NUEVOS — bug ya sufrido en
el proyecto anterior).

### 7. Latencia alta del modelo en CPU
12–65 s por turno sin GPU. No es un defecto del diseño: es el hardware. Por eso
la arquitectura pone las reglas fijas y las FAQ *delante* del modelo grande, y
por eso se mide la latencia por fase para poder argumentar mejoras (ver
Ejercicio 3).

## Veredicto final de la prueba

```
[OK] 1 FAQ dispara buscar_pregunta_frecuente
[OK] 2 Cargo duplicado -> regla urgencia (sin Llama)
[OK] 3 Hablar con persona -> regla escalamiento (sin Llama)
[OK] 4 Pedido -> consultar_pedido ejecutada
[OK] 5 Memoria: follow-up sin repetir el numero
[OK] 6 Pedido inexistente -> respuesta honesta, sin inventar
TOTAL: TODOS LOS ESCENARIOS OK
```

- Handshake de Meta: **200** (`12345`).
- Sesiones Llama Stack: **1** teléfono · límite **8** items · **12** recortados.
- Mensajes salientes en el mock: **6 de 6**.
- Herramientas ejecutadas: `buscar_pregunta_frecuente` (0 ms), `consultar_pedido`
  (0 ms) y una `consultar_pedido` **rechazada** por validación (0 ms).
