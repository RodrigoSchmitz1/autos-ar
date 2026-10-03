# Asistente

- `casos_interprete.json`: pedidos con los que se armaron las reglas (test de regresion en el pipeline: tienen que salir todos exactos).
- `casos_validacion.json`, `casos_validacion_2.json`: pedidos escritos aparte para medir. Una vez usados para mejorar reglas dejan de medir: para una medicion nueva, escribir un set nuevo.
- `medir_gemini.mjs`: mide a Gemini con los mismos pedidos y las mismas instrucciones que el Worker.
- `worker/`: Cloudflare Worker que guarda la clave de Gemini y la usa por el sitio.

Medir las reglas:

```bash
node sitio/js/test_interprete.mjs asistente/casos_validacion_2.json --detalle
```

## Poner en marcha el Worker (una vez)

1. Clave de Gemini: https://aistudio.google.com/apikey -> Create API key, en un proyecto **sin facturacion** (asi no puede cobrar: al agotar la cuota gratis responde 429). Guardarla en `.env` (no se versiona) como `GEMINI_API_KEY=...` para medir local.
2. Cuenta gratis en https://dash.cloudflare.com/sign-up.
3. Desde `asistente/worker/`:

```bash
npx wrangler login
npx wrangler secret put GEMINI_API_KEY
npx wrangler deploy
```

4. Poner la URL que devuelve `deploy` (https://autos-ar-asistente.<cuenta>.workers.dev) en `IA_URL` de `sitio/js/asistente.js`.
