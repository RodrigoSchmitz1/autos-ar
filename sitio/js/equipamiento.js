// Equipamiento lado a lado de las versiones del comparador, con las
// caracteristicas comunes entre marcas (mart_equipamiento_comparable; la
// clasificacion de los items de cada ficha esta en equipamiento/clasificar.py).
// Lo que una ficha no menciona es "s/d" (sin dato), no "no".

import { el, millones } from "./comun.js";
import { foto } from "./autos.js";
import { nombreFamilia } from "./respuesta.js";

const GRUPOS = { seguridad: "Seguridad", confort: "Confort", tecnologia: "Tecnología", exterior: "Exterior" };
let soloDiferencias = false;

// La version de la ficha que corresponde a una version del comparador (por su id DNRPA).
function fichaDe(v, eq) {
  const familia = eq.familias?.[`${v.marca}|${v.familia}`];
  return familia?.versiones.find((x) => x.id === v.id) || null;
}

function celda(valor, tipo) {
  if (valor === undefined) return el("td", { class: "num sd", text: "s/d", title: "La ficha no lo menciona" });
  if (tipo === "numero" && typeof valor === "number") return el("td", { class: "num si", text: `${String(valor).replace(".", ",")}"` });
  if (valor === "si") return el("td", { class: "num si", text: "✓" });
  if (valor === "opcional") return el("td", { class: "num opc", text: "opc." });
  return el("td", { class: "num no", text: "—" });
}

export function seccionEquipamiento(elegidas, eq) {
  if (!eq?.caracteristicas) return [];
  const columnas = elegidas.map((v) => ({ v, ficha: fichaDe(v, eq) })).filter((c) => c.ficha);
  const sinFicha = elegidas.filter((v) => !fichaDe(v, eq));
  const titulo = el("h2", { text: "Equipamiento lado a lado" });
  if (columnas.length < 1) {
    return [titulo, el("p", { class: "bajada", text: "Ninguno de estos modelos tiene ficha de equipamiento todavía (hay de VW, Chevrolet, Ford y Peugeot)." })];
  }
  const valor = (c, id) => c.ficha.comparable?.[id];
  const filasPorGrupo = Object.keys(GRUPOS).map((g) => {
    const cars = eq.caracteristicas.filter((k) => k.grupo === g && columnas.some((c) => valor(c, k.id) !== undefined));
    return { g, cars };
  }).filter((x) => x.cars.length);

  const resumen = (c, g) => {
    const cars = eq.caracteristicas.filter((k) => k.grupo === g);
    const tiene = cars.filter((k) => { const x = valor(c, k.id); return x === "si" || typeof x === "number"; }).length;
    return `${GRUPOS[g]}: ${tiene}`;
  };

  const tabla = el("table", { class: "tabla-equipamiento" },
    el("thead", {}, el("tr", {}, el("th", { text: "" }), columnas.map((c) => el("th", { class: "num" },
      el("div", { class: "eq-cabeza" }, foto(c.v.marca, c.v.familia, "mini"),
        el("strong", { text: nombreFamilia(c.v.marca, c.v.familia) }),
        el("span", { class: "nota", text: c.ficha.nombre }),
        el("span", { class: "nota", text: c.v.valor_0km ? millones(c.v.valor_0km) : "" }),
        el("span", { class: "eq-resumen", text: Object.keys(GRUPOS).map((g) => resumen(c, g)).join(" · ") })))))),
    el("tbody", {}, filasPorGrupo.flatMap(({ g, cars }) => [
      el("tr", { class: "fila-seccion" }, el("td", { colspan: columnas.length + 1, text: GRUPOS[g] })),
      ...cars.map((k) => {
        const vals = columnas.map((c) => valor(c, k.id));
        const conDato = vals.filter((x) => x !== undefined).map(String);
        const difiere = columnas.length > 1 && new Set(conDato).size > 1;
        return el("tr", { class: difiere ? "difiere" : "igual" }, el("td", { text: k.nombre }), vals.map((x) => celda(x, k.tipo)));
      }),
    ])));
  tabla.classList.toggle("solo-diferencias", soloDiferencias);

  const casilla = el("input", { type: "checkbox", id: "solo-diferencias" });
  casilla.checked = soloDiferencias;
  casilla.addEventListener("change", () => { soloDiferencias = casilla.checked; tabla.classList.toggle("solo-diferencias", soloDiferencias); });

  return [
    titulo,
    el("p", { class: "bajada", text: "Según las fichas técnicas oficiales, agrupadas en características comunes entre marcas. "
      + "Resaltado: donde los modelos difieren. \"s/d\": la ficha no lo menciona (no quiere decir que no lo tenga)." }),
    el("div", { class: "casilla" }, casilla, el("label", { for: "solo-diferencias", style: "margin:0", text: "Solo diferencias" })),
    el("div", { class: "tabla-scroll" }, tabla),
    sinFicha.length ? el("p", { class: "nota", text: `Sin ficha de equipamiento: ${sinFicha.map((v) => nombreFamilia(v.marca, v.familia)).join(", ")}.` }) : null,
  ];
}
