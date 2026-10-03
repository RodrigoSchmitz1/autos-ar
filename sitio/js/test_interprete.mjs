// Mide el interprete contra los pedidos de prueba: cuantos salen exactos y,
// por campo, aciertos, faltantes (no lo saco) e inventados (saco algo que no
// estaba o distinto). Uso: node sitio/js/test_interprete.mjs [casos.json] [--detalle]

import { readFileSync } from "node:fs";
import { interpretar, prepararCatalogo } from "./interprete.js";

const costo = JSON.parse(readFileSync("sitio/datos/costo.json", "utf8"));
const i = Object.fromEntries(costo.columnas.map((c, n) => [c, n]));
const ventas = new Map();
for (const v of costo.versiones) {
  const k = `${v[i.marca]}|${v[i.familia]}`;
  ventas.set(k, (ventas.get(k) || 0) + (v[i.inscripciones_12m] || 0));
}
const catalogo = prepararCatalogo([...ventas].map(([k, n]) => {
  const [marca, familia] = k.split("|");
  return { marca, familia, inscripciones: n };
}));

const archivo = process.argv.find((a) => a.endsWith(".json")) || "asistente/casos_interprete.json";
const { casos } = JSON.parse(readFileSync(archivo, "utf8"));
const igual = (a, b) => JSON.stringify(Array.isArray(a) ? [...a].sort() : a) === JSON.stringify(Array.isArray(b) ? [...b].sort() : b);
const campos = {};
let exactos = 0;
const detalle = process.argv.includes("--detalle");
for (const { texto, esperado } of casos) {
  const obtenido = interpretar(texto, catalogo);
  let ok = true;
  for (const c of new Set([...Object.keys(esperado), ...Object.keys(obtenido)])) {
    const e = (campos[c] ??= { aciertos: 0, faltantes: 0, inventados: 0 });
    if (igual(esperado[c], obtenido[c])) e.aciertos++;
    else {
      ok = false;
      if (obtenido[c] === undefined) e.faltantes++; else e.inventados++;
    }
  }
  if (ok) exactos++;
  else if (detalle) console.log(`MAL: ${texto}\n  esperado ${JSON.stringify(esperado)}\n  obtenido ${JSON.stringify(obtenido)}`);
}
console.log(`${exactos}/${casos.length} pedidos exactos`);
for (const [c, e] of Object.entries(campos)) console.log(`  ${c.padEnd(16)} ${e.aciertos} bien, ${e.faltantes} faltantes, ${e.inventados} inventados`);
// --estricto (lo usa el pipeline con casos_interprete.json): falla si algun
// pedido no sale exacto, para que un cambio de reglas no rompa lo que andaba.
if (process.argv.includes("--estricto") && exactos < casos.length) process.exit(1);
