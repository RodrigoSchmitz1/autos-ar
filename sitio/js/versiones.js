// "Que suma cada version": escalera de versiones de un modelo, de la de entrada
// a la mas equipada, con el precio de cada salto y lo que agrega. Los datos
// salen de la ficha tecnica oficial (ingesta/equipamiento.py).

import { millones, el } from "./comun.js";

const VISIBLES = 6; // items por escalon antes de "ver todo"

const titulo = (t) => t.charAt(0) + t.slice(1).toLowerCase();

function lista(items, clase, texto) {
  const ul = el("ul", { class: `suma ${clase}` }, items.slice(0, VISIBLES).map((i) => el("li", { text: texto(i) })));
  if (items.length > VISIBLES) {
    const resto = items.slice(VISIBLES);
    const mas = el("button", { type: "button", class: "ver-mas", text: `y ${resto.length} más` });
    mas.addEventListener("click", () => { ul.append(...resto.map((i) => el("li", { text: texto(i) }))); mas.remove(); });
    return el("div", {}, ul, mas);
  }
  return ul;
}

function escalon(e, i) {
  const v = e.versiones[i];
  const suma = e.suma?.[String(i)] || { agrega: [], mejora: [], quita: [] };
  const anterior = e.versiones[i - 1];
  const salto = v.valor_0km && anterior?.valor_0km ? v.valor_0km - anterior.valor_0km : null;
  const incluidos = e.secciones.flatMap((s) => s.items).filter(([, vals]) => vals[i] === "si").length;
  return el("div", { class: "escalon", style: `--paso:${i / Math.max(1, e.versiones.length - 1)}` },
    el("div", { class: "escalon-cabeza" },
      el("div", { class: "escalon-nombre", text: v.nombre }),
      el("div", { class: "escalon-precio", text: v.valor_0km ? millones(v.valor_0km) : "sin precio" }),
      i === 0
        ? el("div", { class: "escalon-salto", text: `Versión de entrada · ${incluidos} ítems de serie` })
        : el("div", { class: "escalon-salto", text: salto !== null ? `${salto >= 0 ? "+" : "−"}${millones(Math.abs(salto))} sobre ${anterior.nombre}` : `sobre ${anterior.nombre}` })),
    i === 0 ? null : el("div", { class: "escalon-cuerpo" },
      suma.agrega.length ? lista(suma.agrega, "agrega", (x) => x) : null,
      suma.mejora.length ? lista(suma.mejora, "mejora", ([item, de, a]) => `${item}: ${de} → ${a}`) : null,
      suma.quita.length ? lista(suma.quita, "quita", (x) => x) : null,
      !suma.agrega.length && !suma.mejora.length ? el("p", { class: "nota", text: "Mismo equipamiento que la anterior." }) : null));
}

function tabla(e) {
  const marca = (v) => (v === "si" ? "✓" : v === "no" ? "—" : v === "opcional" ? "opc." : v ?? "");
  return el("details", { class: "ficha-completa" },
    el("summary", { text: "Ver la ficha completa" }),
    el("div", { class: "tabla-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "" }), e.versiones.map((v) => el("th", { class: "num", text: v.nombre })))),
      el("tbody", {}, e.secciones.flatMap((s) => [
        el("tr", { class: "fila-seccion" }, el("td", { colspan: e.versiones.length + 1, text: titulo(s.nombre || "") })),
        ...s.items.map(([item, vals]) => el("tr", {}, el("td", { text: item }),
          vals.map((x) => el("td", { class: `num${x === "si" ? " si" : x === "no" ? " no" : ""}`, text: marca(x) })))),
      ])))));
}

export function seccionVersiones(e) {
  if (!e || e.versiones.length < 2) return [];
  return [
    el("h2", { text: "Qué suma cada versión" }),
    el("p", { class: "bajada" }, "De la versión de entrada a la más equipada, con lo que cuesta cada salto. Según la ",
      el("a", { href: e.fuente, text: "ficha técnica oficial" }), "."),
    el("div", { class: "leyenda-suma" },
      el("span", { class: "agrega", text: "agrega" }), el("span", { class: "mejora", text: "mejora" }), el("span", { class: "quita", text: "deja de tener" })),
    el("div", { class: "escalera" }, e.versiones.map((_, i) => escalon(e, i))),
    tabla(e),
  ];
}
