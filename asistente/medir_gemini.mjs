// Mide a Gemini contra los mismos pedidos de prueba que las reglas, con las
// mismas instrucciones que usa el Worker. Los modelos que devuelve se validan
// contra el catalogo igual que en el sitio.
//
// La clave se lee de la variable GEMINI_API_KEY o del archivo .env (que no se
// versiona). Respeta la cuota gratis: un pedido cada 5 segundos.
// Uso: node asistente/medir_gemini.mjs [casos.json ...] [--detalle]

import { existsSync, readFileSync } from "node:fs";
import { interpretar, prepararCatalogo } from "../sitio/js/interprete.js";
import { interpretarConGemini } from "./worker/src/pedido.js";

const clave = process.env.GEMINI_API_KEY
  || (existsSync(".env") && readFileSync(".env", "utf8").match(/^GEMINI_API_KEY=(.+)$/m)?.[1].trim());
if (!clave) throw new Error("falta GEMINI_API_KEY (variable de entorno o archivo .env)");
const modelo = readFileSync("asistente/worker/wrangler.toml", "utf8").match(/GEMINI_MODELO = "(.+)"/)[1];

const costo = JSON.parse(readFileSync("sitio/datos/costo.json", "utf8"));
const i = Object.fromEntries(costo.columnas.map((c, n) => [c, n]));
const ventas = new Map();
for (const v of costo.versiones) {
  const k = `${v[i.marca]}|${v[i.familia]}`;
  ventas.set(k, (ventas.get(k) || 0) + (v[i.inscripciones_12m] || 0));
}
const catalogo = prepararCatalogo([...ventas].map(([k, n]) => ({ marca: k.split("|")[0], familia: k.split("|")[1], inscripciones: n })));

const archivos = process.argv.filter((a) => a.endsWith(".json"));
const detalle = process.argv.includes("--detalle");
const igual = (a, b) => JSON.stringify(Array.isArray(a) ? [...a].sort() : a) === JSON.stringify(Array.isArray(b) ? [...b].sort() : b);
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

for (const archivo of archivos.length ? archivos : ["asistente/casos_interprete.json", "asistente/casos_validacion.json", "asistente/casos_validacion_2.json"]) {
  const { casos } = JSON.parse(readFileSync(archivo, "utf8"));
  let exactos = 0, errores = 0;
  for (const { texto, esperado } of casos) {
    let obtenido;
    try {
      const ia = await interpretarConGemini(texto, clave, modelo);
      if (ia.modelos) {
        const resueltos = interpretar(ia.modelos.join(" o "), catalogo).modelos;
        if (resueltos) ia.modelos = resueltos; else delete ia.modelos;
      }
      obtenido = ia;
    } catch (e) {
      errores++;
      console.log(`ERROR (${e.message}): ${texto}`);
      if (e.status === 429) { console.log("cuota agotada: corto la medicion"); process.exit(1); }
      await pausa(5000);
      continue;
    }
    const claves = new Set([...Object.keys(esperado), ...Object.keys(obtenido)]);
    const ok = [...claves].every((c) => igual(esperado[c], obtenido[c]));
    if (ok) exactos++;
    else if (detalle) console.log(`MAL: ${texto}\n  esperado ${JSON.stringify(esperado)}\n  obtenido ${JSON.stringify(obtenido)}`);
    await pausa(5000);
  }
  console.log(`${archivo}: ${exactos}/${casos.length} exactos (${modelo})${errores ? `, ${errores} errores` : ""}`);
}
