// Utilidades compartidas: carga de datos, formato y tablas compactas.

const cache = {};

export async function cargar(nombre) {
  if (!cache[nombre]) {
    cache[nombre] = fetch(`datos/${nombre}`).then((r) => {
      if (!r.ok) throw new Error(`no se pudo cargar ${nombre} (${r.status})`);
      return r.json();
    });
  }
  return cache[nombre];
}

// Las listas del JSON vienen como filas + "columnas": las paso a objetos.
export function objetos(columnas, filas) {
  return filas.map((f) => Object.fromEntries(columnas.map((c, i) => [c, f[i]])));
}

const pesosFmt = new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 });
const numFmt = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const decFmt = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const pesos = (x) => (x === null || x === undefined ? "s/d" : pesosFmt.format(x));
export const numero = (x) => (x === null || x === undefined ? "s/d" : numFmt.format(x));
export const decimal = (x) => (x === null || x === undefined ? "s/d" : decFmt.format(x));
export const millones = (x) => (x === null || x === undefined ? "s/d" : `$${decFmt.format(x / 1e6)} M`);

export function fecha(iso) {
  if (!iso) return "s/d";
  const [a, m, d] = iso.split("-");
  const meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  return d ? `${Number(d)} ${meses[Number(m) - 1]} ${a}` : `${meses[Number(m) - 1]} ${a}`;
}

export function el(tag, atributos = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(atributos)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v);
  }
  for (const h of hijos.flat()) if (h !== null && h !== undefined) e.append(h);
  return e;
}

// Busqueda tolerante: todas las palabras, sin tildes ni mayusculas.
export function normalizar(t) {
  return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
}
export function coincide(texto, consulta) {
  const t = normalizar(texto);
  return normalizar(consulta).split(/\s+/).filter(Boolean).every((p) => t.includes(p));
}

export async function pie() {
  const meta = await cargar("meta.json").catch(() => null);
  const f = document.querySelector("footer");
  if (!f || !meta) return;
  f.append(el("p", {},
    `Datos actualizados el ${fecha(meta.generado)}. Combustible: ${fecha(meta.periodos.combustible.slice(0, 7))}; `,
    `mercado: ${fecha(meta.periodos.mercado.slice(0, 7))}; guía de precios: ${fecha(meta.periodos.guia_cca.slice(0, 7))}. `,
    el("a", { href: "https://github.com/RodrigoSchmitz1/autos-ar", text: "Código y metodología" }), " · ",
    el("a", { href: "creditos.html", text: "Créditos de las fotos" }), "."));
}
