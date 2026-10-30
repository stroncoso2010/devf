# Conversacion de la prueba - Asistente de Estatus de Pedidos

**Fecha:** 2026-10-30 13:22:21  
**Modelo:** `qwen3.5:0.8b` (Ollama local del PC)  
**Duracion de la prueba local:** 1022 ms

### Usuario nuevo (saludo)

**Telefono:** `5215512345678`

**Usuario:** Hola, buenas tardes

**Bot** (`fuente: saludo`):

```
¡Hola! 👋 Bienvenido/a al Asistente de Estatus de Pedidos. Soy tu asistente virtual y te ayudo a consultar el estado de tus compras. Dime el número de pedido (ejemplo: PED-1001) y te doy la información al instante. 🌎
```

### Estatus con folio

**Telefono:** `5215512345678`

**Usuario:** ¿Cuál es el estatus de mi pedido PED-1002?

**Bot** (`fuente: catalogo`):

```
📦 *PED-1002* — Mochila urbana waterproof 30L (x2)
Estado: *En camino*
Entrega estimada: 2026-10-30
Rastreo: MX-TRACK-771044 (Envíos Andes)
¿Necesitas algo más sobre este pedido?
```

### Estatus sin folio (regla)

**Telefono:** `5215512345678`

**Usuario:** Oye, ¿ya llegó mi compra?

**Bot** (`fuente: regla`):

```
Claro, con gusto te ayudo. 📦 ¿Me compartes el número de pedido? Se ve algo como PED-1001.
```

### Pedido inexistente

**Telefono:** `5215599998888`

**Usuario:** Revisa el pedido PED-9999 por favor

**Bot** (`fuente: catalogo`):

```
No encuentro el pedido *PED-9999* en el sistema. 🤔 Revisa el número e inténtalo de nuevo, o escríbeme para ayuda.
```

### Conversacion general (LLM)

**Telefono:** `5215512345678`

**Usuario:** ¿Puedo comprar sin pasar a la tienda?

**Bot** (`fuente: llm`):

```
¡Sí, puedes realizar tu pedido directamente desde tu navegador! Solo tienes que seleccionar los productos y pagar con tarjeta o efectivo. 🛒✨
```
