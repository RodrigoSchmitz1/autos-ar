// Cloudflare Worker: intermediario entre el sitio y Gemini. Existe para que la
// clave no viaje al navegador (cualquiera podria copiarla de una pagina
// estatica). Recibe {texto} y devuelve los parametros interpretados.
//
// Costo cero: la clave es de un proyecto de AI Studio SIN facturacion
// habilitada; si se agota la cuota gratis, Gemini responde 429 y el sitio sigue
// con las reglas. El plan gratis de Workers da 100.000 pedidos por dia.

import { interpretarConGemini, MAX_CARACTERES } from "./pedido.js";

function respuesta(cuerpo, estado, origen) {
  // Un 204 (respuesta al preflight de CORS) no puede llevar cuerpo.
  return new Response(cuerpo === null ? null : JSON.stringify(cuerpo), {
    status: estado,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": origen,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      Vary: "Origin",
    },
  });
}

export default {
  async fetch(pedido, env) {
    const origen = pedido.headers.get("Origin") || "";
    // Solo el sitio (y el servidor local de desarrollo) puede usarlo.
    if (!env.ORIGENES.split(",").includes(origen)) return new Response("origen no permitido", { status: 403 });
    if (pedido.method === "OPTIONS") return respuesta(null, 204, origen);
    if (pedido.method !== "POST") return respuesta({ error: "usar POST" }, 405, origen);

    let texto;
    try {
      ({ texto } = await pedido.json());
    } catch {
      return respuesta({ error: "se esperaba JSON con 'texto'" }, 400, origen);
    }
    if (typeof texto !== "string" || !texto.trim() || texto.length > MAX_CARACTERES) {
      return respuesta({ error: `'texto' tiene que tener entre 1 y ${MAX_CARACTERES} caracteres` }, 400, origen);
    }
    try {
      return respuesta(await interpretarConGemini(texto, env.GEMINI_API_KEY, env.GEMINI_MODELO), 200, origen);
    } catch (e) {
      // 429: se agoto la cuota gratis del dia. Otro error de Gemini: 502.
      return respuesta({ error: e.message }, e.status === 429 ? 429 : 502, origen);
    }
  },
};
