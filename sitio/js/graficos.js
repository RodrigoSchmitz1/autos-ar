// Graficos del gasto por rubro (combustible, patente, service, repuestos...):
// una barra apilada con los rubros y una lista con el monto y la parte de cada uno.
// Mismo aspecto en Mi auto, la portada y el comparador.

import { el } from "./comun.js";

// Barra apilada: un tramo por rubro, proporcional, con una separacion fina entre
// tramos y las puntas redondeadas. partes: [{ nombre, valor, color }].
export function barraApilada(partes, { clase = "" } = {}) {
  const validas = partes.filter((p) => p.valor > 0);
  const total = validas.reduce((s, p) => s + p.valor, 0);
  return el("div", { class: `apilada ${clase}`, role: "img",
    "aria-label": validas.map((p) => `${p.nombre} ${Math.round(p.valor / total * 100)}%`).join(", ") },
  validas.map((p) => el("span", { style: `flex-grow:${p.valor};--c:${p.color}`, title: `${p.nombre}: ${Math.round(p.valor / total * 100)}%` })));
}

// Leyenda compacta (tarjetas chicas): punto, nombre y porcentaje, en dos columnas.
export function leyendaCompacta(partes) {
  const total = partes.reduce((s, p) => s + (p.valor || 0), 0);
  return el("ul", { class: "leyenda-compacta" }, partes.filter((p) => p.valor > 0).map((p) =>
    el("li", {}, el("i", { style: `--c:${p.color}` }), p.nombre, el("b", { text: `${Math.round(p.valor / total * 100)}%` }))));
}

// Lista de rubros, como un estado de cuenta: marca de color y nombre (con un
// detalle abajo), porcentaje y monto en columnas alineadas, y una barra fina con
// la parte de cada uno. formato(valor) da el texto del monto.
export function rubros(partes, formato) {
  const total = partes.reduce((s, p) => s + (p.valor || 0), 0);
  return el("div", { class: "rubros" }, partes.map((p) => {
    const pct = p.valor ? p.valor / total * 100 : 0;
    return el("div", { class: `rubro${p.valor ? "" : " sd"}`, style: `--c:${p.color}` },
      el("div", { class: "rubro-texto" }, el("strong", {}, el("i", { class: "rubro-marca" }), p.nombre),
        p.valor ? (p.detalle ? el("small", { text: p.detalle }) : null) : el("small", { text: p.motivo || "sin dato" })),
      el("span", { class: "rubro-pct", text: p.valor ? `${pct < 1 ? "<1" : Math.round(pct)}%` : "" }),
      el("strong", { class: "rubro-monto", text: p.valor ? formato(p.valor) : "—" }),
      el("div", { class: "rubro-pista" }, el("span", { style: `width:${pct}%` })));
  }));
}
