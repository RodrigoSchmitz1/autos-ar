// Fotos de los modelos: de Wikimedia Commons, con licencia libre, elegidas a
// mano para que sean la generacion que se vende en Argentina (ver
// exportar/fotos.py). Los modelos sin foto muestran una tarjeta con la marca.

import { el } from "./comun.js";

const PALETA = ["#e63946", "#f4a261", "#2a9d8f", "#3a86ff", "#9b5de5", "#f15bb5",
                "#00b4d8", "#fb8500", "#06a77d", "#ef476f", "#ffbe0b", "#8338ec"];

let fotos = {};

export async function cargarFotos() {
  try {
    const r = await fetch("img/autos/fotos.json");
    if (r.ok) fotos = await r.json();
  } catch { /* sin fotos el sitio sigue andando, con las tarjetas de marca */ }
  return fotos;
}

// Color fijo por nombre (FNV-1a con mezcla final): la misma marca siempre igual.
export function colorDe(nombre) {
  let h = 2166136261;
  for (const ch of nombre || "") h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  h ^= h >>> 15; h = Math.imul(h, 2246822507); h ^= h >>> 13;
  return PALETA[(h >>> 0) % PALETA.length];
}

export function foto(marca, familia, clase = "") {
  const f = fotos[`${marca}|${familia}`];
  if (!f) {
    const c = colorDe(marca);
    return el("div", { class: `foto-auto sin-foto ${clase}`, style: `background:linear-gradient(135deg, ${c}, ${c}aa)`, "aria-hidden": "true" },
      el("span", { text: marca }));
  }
  return el("img", {
    class: `foto-auto ${clase}`, src: `img/autos/${f.imagen}`, loading: "lazy", width: 480, height: 320,
    alt: `${marca} ${familia}`.toLowerCase(), title: `Foto: ${f.autor} · ${f.licencia} · Wikimedia Commons`,
  });
}
