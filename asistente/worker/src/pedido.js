// Instrucciones y formato de respuesta para Gemini. Lo usan el Worker (en
// produccion) y asistente/medir_gemini.mjs (para medirlo contra los mismos
// pedidos de prueba que las reglas): un solo lugar, para que lo medido sea lo
// que corre.

export const PROVINCIAS = {
  "02": "Ciudad Autonoma de Buenos Aires", "06": "Buenos Aires", "10": "Catamarca", "14": "Cordoba",
  "18": "Corrientes", "22": "Chaco", "26": "Chubut", "30": "Entre Rios", "34": "Formosa", "38": "Jujuy",
  "42": "La Pampa", "46": "La Rioja", "50": "Mendoza", "54": "Misiones", "58": "Neuquen", "62": "Rio Negro",
  "66": "Salta", "70": "San Juan", "74": "San Luis", "78": "Santa Cruz", "82": "Santa Fe",
  "86": "Santiago del Estero", "90": "Tucuman", "94": "Tierra del Fuego",
};

// ASCII plano a proposito (convencion del proyecto para textos generados).
export const INSTRUCCIONES = `Sos el interprete de un sitio argentino que calcula cuanto cuesta tener un auto 0 km.
Recibis el pedido de una persona y devolves SOLO los parametros que el pedido dice. No calculas nada y no recomendas nada: el sitio hace las cuentas.

Reglas:
- Lo que el pedido no dice, va en null (o lista vacia). No inventes ni supongas valores por defecto.
- modelos: los modelos de auto que nombra, copiados TAL CUAL los escribio, con la marca si la dijo, aunque tengan errores de tipeo o no conozcas el modelo (hay modelos nuevos que no conoces, como el Tera). No los cambies por otro modelo: el sitio los busca en su catalogo. Ej: "la hillux y la amarok" -> ["hillux", "amarok"]. Una marca sola ("algo de Toyota") no es un modelo.
- km_anio: kilometros por anio. Converti: por dia x365, por semana x52, por mes x12. "voy y vuelvo, 40 km en total por dia" -> 14600. Si no dice cuantos km, null.
- provincia_id: el codigo de la provincia donde vive o usa el auto, de esta lista: ${Object.entries(PROVINCIAS).map(([id, n]) => `${id}=${n}`).join(", ")}. Una ciudad cuenta por su provincia (Rosario -> 82, Mar del Plata -> 06, Bariloche -> 62). "Capital federal" o CABA -> 02.
- anios: cuantos anios piensa tener el auto.
- presupuesto_max: precio maximo del auto, en pesos argentinos. "30 palos" o "30 millones" -> 30000000. Si es un monto en dolares o un gasto por mes, null.
- seguro_mensual: cuota mensual del seguro en pesos, si la dice. "85 lucas" -> 85000.
- carroceria: tipos de auto que pide con palabras, de: hatch, sedan, suv, pickup, utilitario. "camioneta" o "chata" -> pickup; "rural" -> suv; "4 puertas" -> sedan; "furgon" -> utilitario; "auto chico" -> hatch. No la deduzcas de los modelos ni del uso: si nombra una Kangoo o dice "para reparto" pero no pide un tipo, va vacia.
- combustible: de: nafta, diesel, hibrido, electrico. "gasolero" -> diesel.
- automatica: true si pide caja automatica, false si pide manual, null si no dice.
- originales: true si pide repuestos originales, false si alternativos, null si no dice.`;

// Formato de salida (responseSchema de Gemini: un subconjunto de OpenAPI).
export const FORMATO = {
  type: "OBJECT",
  properties: {
    modelos: { type: "ARRAY", items: { type: "STRING" } },
    km_anio: { type: "INTEGER", nullable: true },
    provincia_id: { type: "STRING", enum: Object.keys(PROVINCIAS), nullable: true },
    anios: { type: "INTEGER", nullable: true },
    presupuesto_max: { type: "INTEGER", nullable: true },
    seguro_mensual: { type: "INTEGER", nullable: true },
    carroceria: { type: "ARRAY", items: { type: "STRING", enum: ["hatch", "sedan", "suv", "pickup", "utilitario"] } },
    combustible: { type: "ARRAY", items: { type: "STRING", enum: ["nafta", "diesel", "hibrido", "electrico"] } },
    automatica: { type: "BOOLEAN", nullable: true },
    originales: { type: "BOOLEAN", nullable: true },
  },
  required: ["modelos", "carroceria", "combustible"],
};

export const MAX_CARACTERES = 300;

// Llama a Gemini y devuelve los parametros sin nulos ni listas vacias.
export async function interpretarConGemini(texto, clave, modelo, fetchFn = fetch) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelo}:generateContent`;
  const r = await fetchFn(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": clave },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: INSTRUCCIONES }] },
      contents: [{ role: "user", parts: [{ text: texto.slice(0, MAX_CARACTERES) }] }],
      generationConfig: { temperature: 0, responseMimeType: "application/json", responseSchema: FORMATO },
    }),
  });
  if (!r.ok) {
    // El mensaje de Gemini ("API key not valid", cuota, etc.) sirve para diagnosticar; nunca incluye la clave.
    const crudo = await r.text().catch(() => "");
    let detalle;
    try { detalle = JSON.parse(crudo).error?.message; } catch { detalle = crudo.replace(/\s+/g, " ").trim(); }
    const error = new Error(`Gemini respondio ${r.status}${detalle ? `: ${detalle.slice(0, 200)}` : ""}`);
    error.status = r.status;
    throw error;
  }
  const datos = await r.json();
  const salida = JSON.parse(datos.candidates[0].content.parts[0].text);
  return Object.fromEntries(Object.entries(salida)
    .filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)));
}
