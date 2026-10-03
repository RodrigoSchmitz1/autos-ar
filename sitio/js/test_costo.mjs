// Prueba que el calculo en JavaScript (costo.js) da lo mismo que Python,
// usando los casos que genera costo/generar_casos.py.
//
// Uso (desde la raiz del repo): node sitio/js/test_costo.mjs

import { readFileSync } from "node:fs";
import { calcular, proporcionConservada, validarPerfil } from "./costo.js";

const casos = JSON.parse(readFileSync("costo/casos_prueba.json", "utf-8"));
const errores = [];
const campos = ["anual", "combustible_anual", "service_anual", "repuestos_anual",
                "patente_anual", "depreciacion_anual", "seguro_anual"];

for (const caso of casos) {
  const r = calcular(caso.componentes, caso.perfil);
  for (const campo of campos) {
    if (Math.abs(r[campo] - caso.esperado[campo]) > 1e-6 * Math.max(1, Math.abs(caso.esperado[campo]))) {
      errores.push(`${caso.nombre} ${JSON.stringify(caso.perfil)} ${campo}: ${r[campo]} en vez de ${caso.esperado[campo]}`);
    }
  }
  if (JSON.stringify(r.faltantes) !== JSON.stringify(caso.esperado.faltantes)) {
    errores.push(`${caso.nombre} faltantes: ${r.faltantes} en vez de ${caso.esperado.faltantes}`);
  }
}

// Perfil invalido: tiene que fallar igual que en Python.
for (const malo of [{ km_anio: 0 }, { anios: -1 }, { seguro_mensual: -5 }]) {
  try { validarPerfil(malo); errores.push(`perfil invalido aceptado: ${JSON.stringify(malo)}`); } catch { /* bien */ }
}
if (proporcionConservada({}, 5) !== null) errores.push("curva vacia deberia ser null");

if (errores.length) {
  console.log(`${errores.length} casos fallaron`);
  errores.slice(0, 20).forEach((e) => console.log("MAL", e));
  process.exit(1);
}
console.log(`OK: ${casos.length} casos iguales a Python`);
