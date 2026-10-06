// Equipamiento lado a lado de los autos del comparador, con las
// caracteristicas comunes entre marcas (mart_equipamiento_comparable; la
// clasificacion de los items de cada ficha esta en equipamiento/clasificar.py).
// Lo que una ficha no menciona es "s/d" (sin dato), no "no".

import { el, normalizar } from "./comun.js";
import { foto, recorte } from "./autos.js";
import { nombreFamilia } from "./respuesta.js";

const GRUPOS = { seguridad: "Seguridad", confort: "Confort", tecnologia: "Tecnología", exterior: "Exterior" };
// Marcas cuyas fichas no se pueden leer automaticamente (ver ingesta/equipamiento.py).
const SIN_FICHA = {
  FIAT: "Fiat no deja consultar su sitio a programas", TOYOTA: "Toyota no deja consultar su sitio a programas",
  CITROEN: "Citroën no permite leer su sitio (robots.txt)",
  JEEP: "en la ficha de Jeep las marcas son dibujos, no texto",
};
let soloDiferencias = false;

// Palabras de un nombre de version, como en int_equipamiento_version.py: sin la
// familia, sin el codigo de anio modelo ("AM26.5", "MY26") ni lo que va entre parentesis.
function palabras(texto, familia) {
  const fam = new Set(normalizar(familia).split(/[^A-Z0-9+.]+/));
  return new Set(normalizar(texto).replace(/\b(AM\d+(\.\d+)?|MY\d+)\b/g, " ").replace(/\((C[SD])\)/g, " $1 ").replace(/\(.*?\)|\*/g, " ")
    .replace(/(?<=[0-9])(?=[A-Z])|(?<=[A-Z])(?=[0-9])/g, " ").split(/[^A-Z0-9+.]+/)
    .filter((p) => p && !fam.has(p) && !/^(AM\d+(\.\d+)?|MY\d+|G\d)$/.test(p) && !["PICK", "UP"].includes(p)));
}

// La version de la ficha que corresponde a una version del comparador: la que el
// pipeline cruzo con ese id DNRPA; si no (DNRPA tiene varias que cumplen y el cruce
// se quedo con la mas vendida), la que tiene todas sus palabras en el nombre DNRPA.
function fichaDe(v, eq) {
  const familia = eq.familias?.[`${v.marca}|${v.familia}`];
  if (!familia) return null;
  const exacta = familia.versiones.find((x) => x.id === v.id);
  if (exacta) return exacta;
  const dnrpa = palabras(v.modelo, v.familia);
  const cumplen = familia.versiones.map((x) => ({ x, p: palabras(x.nombre, v.familia) }))
    .filter(({ p }) => p.size && [...p].every((w) => dnrpa.has(w)));
  return cumplen.sort((a, b) => b.p.size - a.p.size)[0]?.x || null;
}

function celda(valor, tipo) {
  if (valor === undefined) return el("td", { class: "num sd", text: "s/d", title: "La ficha no lo menciona" });
  if (tipo === "numero" && typeof valor === "number") return el("td", { class: "num si" }, el("span", { class: "eq-dato", text: `${String(valor).replace(".", ",")}"` }));
  if (valor === "si") return el("td", { class: "num si" }, el("span", { class: "eq-tilde", text: "✓", "aria-label": "Sí" }));
  if (valor === "opcional") return el("td", { class: "num opc" }, el("span", { class: "eq-dato", text: "opcional" }));
  return el("td", { class: "num no" }, el("span", { class: "eq-no", text: "—", "aria-label": "No" }));
}

function motivo(v, eq) {
  if (SIN_FICHA[v.marca]) return `Sin ficha: ${SIN_FICHA[v.marca]}.`;
  if (eq.familias?.[`${v.marca}|${v.familia}`]) return "Esta versión no figura en la ficha oficial.";
  return "Todavía no tenemos la ficha de este modelo.";
}

export function seccionEquipamiento(elegidas, eq, colores = []) {
  if (!eq?.caracteristicas || !elegidas.length) return [];
  const columnas = elegidas.map((v, i) => ({ v, ficha: fichaDe(v, eq), color: colores[i] }));
  const conFicha = columnas.filter((c) => c.ficha);
  if (!conFicha.length) {
    return [el("div", { class: "eq-vacio" }, columnas.map((c) => el("p", {},
      el("strong", { style: `color:${c.color}`, text: nombreFamilia(c.v.marca, c.v.familia) }), ` · ${motivo(c.v, eq)}`)))];
  }
  const valor = (c, id) => c.ficha?.comparable?.[id];
  const filasPorGrupo = Object.keys(GRUPOS).map((g) => ({
    g, cars: eq.caracteristicas.filter((k) => k.grupo === g && conFicha.some((c) => valor(c, k.id) !== undefined)),
  })).filter((x) => x.cars.length);

  const cuenta = (c, g) => eq.caracteristicas.filter((k) => k.grupo === g)
    .filter((k) => { const x = valor(c, k.id); return x === "si" || typeof x === "number"; }).length;

  const cabeza = (c) => el("th", { class: "num eq-col", style: `--color:${c.color}` },
    el("div", { class: "eq-cabeza" },
      el("div", { class: "eq-foto" }, recorte(c.v.marca, c.v.familia) || foto(c.v.marca, c.v.familia, "mini")),
      el("strong", { text: nombreFamilia(c.v.marca, c.v.familia) }),
      el("span", { class: "nota", text: c.ficha ? c.ficha.nombre : "sin ficha" }),
      c.ficha ? el("div", { class: "eq-resumen" }, Object.keys(GRUPOS).map((g) => el("span", { title: GRUPOS[g] }, el("b", { text: cuenta(c, g) }), ` ${GRUPOS[g].toLowerCase()}`)))
        : el("span", { class: "eq-sin", text: motivo(c.v, eq) })));

  const tabla = el("table", { class: "tabla-equipamiento" },
    el("thead", {}, el("tr", {}, el("th", { class: "eq-esquina", text: "" }), columnas.map(cabeza))),
    el("tbody", {}, filasPorGrupo.flatMap(({ g, cars }) => [
      el("tr", { class: "fila-seccion" }, el("td", { colspan: columnas.length + 1, text: GRUPOS[g] })),
      ...cars.map((k) => {
        const vals = columnas.map((c) => (c.ficha ? valor(c, k.id) : null));
        const conDato = vals.filter((x) => x !== undefined && x !== null).map(String);
        const difiere = conFicha.length > 1 && new Set(conDato).size > 1;
        return el("tr", { class: difiere ? "difiere" : "igual" }, el("td", { text: k.nombre }),
          vals.map((x, i) => (x === null ? el("td", { class: "num sin-ficha", style: `--color:${columnas[i].color}` }) : celda(x, k.tipo))));
      }),
    ])));
  tabla.classList.toggle("solo-diferencias", soloDiferencias);

  const casilla = el("input", { type: "checkbox", id: "solo-diferencias" });
  casilla.checked = soloDiferencias;
  casilla.addEventListener("change", () => { soloDiferencias = casilla.checked; tabla.classList.toggle("solo-diferencias", soloDiferencias); });

  return [
    el("p", { class: "bajada", text: "Según las fichas técnicas oficiales, agrupadas en características comunes entre marcas. "
      + "Resaltado: donde difieren. \"s/d\": la ficha no lo menciona (no quiere decir que no lo tenga)." }),
    el("label", { class: "interruptor" }, casilla, el("span", { class: "interruptor-pista", "aria-hidden": "true" }), "Mostrar solo las diferencias"),
    el("div", { class: "tabla-scroll eq-marco" }, tabla),
  ];
}
