// Respuesta del asistente: con los parametros que saco el interprete (o la IA),
// elige versiones, calcula el costo con costo.js y arma el texto. Todo es
// codigo: la IA solo interpreta el pedido, nunca hace las cuentas.

import { calcular, componentes } from "./costo.js";

export const POR_DEFECTO = { provincia_id: "06", km_anio: 15000, anios: 5 };
// Para recomendar, solo versiones que se venden de verdad (ventas 0 km en 12 meses).
export const MIN_VENTAS = 100;
const CUANTAS = 5;
export const CARROCERIAS_AUTO = ["hatch", "sedan", "suv"];

const NOMBRE_COMPONENTE = {
  combustible_anual: "el combustible", service_anual: "el service", repuestos_anual: "los repuestos",
  patente_anual: "la patente", depreciacion_anual: "lo que pierde de valor", seguro_anual: "el seguro",
};

// "TOYOTA", "HILUX PICK - UP" -> "Toyota Hilux"; "PEUGEOT", "208" -> "Peugeot 208".
export function nombreFamilia(marca, familia) {
  const lindo = (t) => t.toLowerCase().replace(/(^|[\s-])([a-z])/g, (m, a, b) => a + b.toUpperCase());
  return `${lindo(marca)} ${lindo((familia || "").replace(/\s*PICK\s*-?\s*UP\b/i, "").trim())}`;
}

export function perfilDe(p) {
  return {
    km_anio: p.km_anio ?? POR_DEFECTO.km_anio,
    anios: p.anios ?? POR_DEFECTO.anios,
    seguro_mensual: p.seguro_mensual ?? 0,
    repuestos_originales: p.originales ?? false,
  };
}

// Filtros del pedido que aplican a una version.
function cumple(v, p) {
  if (p.combustible && !p.combustible.includes(v.combustible)) return false;
  if (p.automatica !== undefined && v.automatica !== p.automatica) return false;
  if (p.carroceria && !p.carroceria.includes(v.carroceria)) return false;
  if (p.presupuesto_max && !(v.valor_0km && v.valor_0km <= p.presupuesto_max)) return false;
  return true;
}

export function responder(p, versiones, precioLitro) {
  const provincia = p.provincia_id ?? POR_DEFECTO.provincia_id;
  const perfil = perfilDe(p);
  const costo = (v) => calcular(componentes(v, provincia, precioLitro), perfil);
  const filtros = ["combustible", "automatica", "carroceria", "presupuesto_max"].some((c) => p[c] !== undefined);

  if (p.modelos?.length) {
    const filas = p.modelos.map((clave) => {
      const delModelo = versiones.filter((v) => `${v.marca}|${v.familia}` === clave);
      const cumplen = delModelo.filter((v) => cumple(v, p));
      const pool = cumplen.length ? cumplen : delModelo;
      // La mas vendida con el costo completo; si ninguna lo tiene, la mas vendida.
      const ordenadas = pool.map((v) => ({ v, k: costo(v) }))
        .sort((a, b) => (b.k.completo - a.k.completo) || ((b.v.inscripciones_12m || 0) - (a.v.inscripciones_12m || 0)));
      const elegida = ordenadas[0];
      return elegida && { ...elegida, clave, nota: filtros && !cumplen.length ? "ninguna versión cumple lo que pediste: es la más vendida" : null };
    }).filter(Boolean);
    return { tipo: "comparar", provincia, perfil, filas: ordenar(filas) };
  }

  if (!filtros && p.km_anio === undefined && p.provincia_id === undefined) return { tipo: "nada", provincia, perfil, filas: [] };

  // Recomendar: la version mas barata de tener de cada familia, entre las que cumplen.
  // Sin carroceria pedida, solo autos: una pick-up o un utilitario no es lo que
  // busca quien no lo pidio, aunque salga barato.
  const pedido = p.carroceria ? p : { ...p, carroceria: CARROCERIAS_AUTO };
  const mejores = new Map();
  for (const v of versiones) {
    // Sin curva de depreciacion propia ni de la marca, el costo es una adivinanza:
    // no se recomienda (si el usuario lo nombra, se compara igual, con aviso).
    if ((v.inscripciones_12m || 0) < MIN_VENTAS || v.depreciacion_fuente === "mediana_general" || !cumple(v, pedido)) continue;
    const k = costo(v);
    if (!k.completo) continue;
    const clave = `${v.marca}|${v.familia}`;
    if (!mejores.has(clave) || k.mensual < mejores.get(clave).k.mensual) mejores.set(clave, { v, k, clave, nota: null });
  }
  return { tipo: "recomendar", provincia, perfil, filas: ordenar([...mejores.values()]).slice(0, CUANTAS) };
}

const ordenar = (filas) => filas.sort((a, b) => (b.k.completo - a.k.completo) || (a.k.mensual - b.k.mensual));

// El texto de la respuesta, con los numeros del calculo.
export function explicar(r, nombreProvincia, pesos) {
  if (r.tipo === "nada") return "No entendí el pedido. Probá nombrando modelos (\"cronos o polo\") o contando cómo lo vas a usar (\"hago 20.000 km por año en Córdoba, hasta 30 millones\").";
  const completas = r.filas.filter((f) => f.k.completo);
  const contexto = `Con ${r.perfil.km_anio.toLocaleString("es-AR")} km por año en ${nombreProvincia}, durante ${r.perfil.anios} ${r.perfil.anios === 1 ? "año" : "años"}`;
  if (!completas.length) return r.tipo === "recomendar"
    ? "No encontré 0 km que cumplan todo lo que pediste. Probá sacando alguna condición."
    : "No tengo el costo completo de esos modelos todavía.";
  const [primero, segundo] = completas;
  const nombre = (f) => nombreFamilia(f.v.marca, f.v.familia);
  let texto = r.tipo === "comparar"
    ? `${contexto}, el más barato de tener es el ${nombre(primero)}: ${pesos(primero.k.mensual)} por mes (${pesos(primero.k.por_km)} por km).`
    : `${contexto}, estos son los 0 km más baratos de tener entre los que cumplen lo que pediste. El primero es el ${nombre(primero)}: ${pesos(primero.k.mensual)} por mes.`;
  if (segundo && r.tipo === "comparar") {
    const dif = (c) => segundo.k[c] - primero.k[c];
    const principal = Object.keys(NOMBRE_COMPONENTE).sort((a, b) => dif(b) - dif(a))[0];
    texto += ` El ${nombre(segundo)} cuesta ${pesos(segundo.k.mensual - primero.k.mensual)} más por mes`;
    texto += dif(principal) > 0 ? `, sobre todo por ${NOMBRE_COMPONENTE[principal]}.` : ".";
  }
  const sinCosto = r.filas.filter((f) => !f.k.completo);
  if (sinCosto.length) texto += ` De ${sinCosto.map(nombre).join(", ")} me falta algún dato (${[...new Set(sinCosto.flatMap((f) => f.k.faltantes))].join(", ")}).`;
  return texto;
}
