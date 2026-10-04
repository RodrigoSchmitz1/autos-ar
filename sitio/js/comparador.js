import { calcular, componentes } from "./costo.js";
import { cargar, objetos, pesos, millones, decimal, el, coincide, pie } from "./comun.js";
import { cargarFotos, foto } from "./autos.js";
import { seccionEquipamiento } from "./equipamiento.js";

const COMPONENTES = [
  ["combustible_anual", "Combustible", "--c-combustible"],
  ["service_anual", "Service", "--c-service"],
  ["repuestos_anual", "Repuestos", "--c-repuestos"],
  ["patente_anual", "Patente", "--c-patente"],
  ["depreciacion_anual", "Depreciación", "--c-depreciacion"],
  ["seguro_anual", "Seguro", "--c-seguro"],
];
const ESTIMACION = {
  familia_motor: "consumo de la familia y motor", familia: "consumo de la familia",
  cilindrada: "consumo estimado por cilindrada",
};

const $ = (id) => document.getElementById(id);
let datos, versiones, equipamiento = {}, elegidas = [];

function leerPerfil() {
  return {
    km_anio: Number($("km").value) || 15000,
    anios: Number($("anios").value) || 5,
    seguro_mensual: Number($("seguro").value) || 0,
    repuestos_originales: $("originales").checked,
  };
}

function avisos(v) {
  const chips = [];
  if (v.consumo_estimacion && v.consumo_estimacion !== "version") chips.push(ESTIMACION[v.consumo_estimacion] || "consumo estimado");
  if (v.service_fuente !== "familia") chips.push("service: mediana general");
  if (v.repuestos_fuente !== "familia") chips.push("repuestos: mediana general");
  if (v.depreciacion_fuente === "mediana_marca") chips.push("depreciación: mediana de la marca");
  if (v.depreciacion_fuente === "mediana_general") chips.push("depreciación: mediana general");
  return chips.map((t) => el("span", { class: "chip aviso", text: t }));
}

function dibujar() {
  const tabla = $("resultado");
  tabla.replaceChildren();
  const leyenda = $("leyenda");
  leyenda.replaceChildren(...COMPONENTES.map(([, n, c]) => el("span", {}, el("i", { style: `background:var(${c})` }), n)));
  if (!elegidas.length) {
    $("estado").textContent = "Agregá modelos con el buscador.";
    return;
  }
  $("estado").textContent = "";
  let perfil;
  try { perfil = leerPerfil(); } catch (e) { $("estado").textContent = e.message; return; }
  const provincia = $("provincia").value;
  const filas = elegidas.map((v) => ({ v, k: calcular(componentes(v, provincia, datos.precio_litro), perfil) }))
    .sort((a, b) => (a.k.completo === b.k.completo ? a.k.anual - b.k.anual : a.k.completo ? -1 : 1));
  const maximo = Math.max(...filas.filter((f) => f.k.completo).map((f) => f.k.anual), 1);

  tabla.append(el("thead", {}, el("tr", {},
    el("th", { text: "Modelo" }), el("th", { class: "num", text: "Por mes" }), el("th", { class: "num", text: "Por km" }),
    el("th", { text: "Composición" }), el("th", { text: "" }))));
  const cuerpo = el("tbody");
  for (const { v, k } of filas) {
    const quitar = el("button", { class: "quitar", "aria-label": `Quitar ${v.modelo}`, text: "×",
      onclick: () => { elegidas = elegidas.filter((x) => x !== v); dibujar(); } });
    const nombre = el("td", {}, el("div", { class: "celda-auto" }, foto(v.marca, v.familia, "mini"), el("div", {},
      el("strong", { text: `${v.marca} ${v.modelo}` }), el("br"),
      el("span", { class: "nota", text: `0 km ${millones(v.valor_0km)} · ${v.combustible} · ${decimal(v.consumo_l100km)} l/100 km` }),
      el("div", {}, avisos(v)))));
    if (!k.completo) {
      cuerpo.append(el("tr", {}, nombre, el("td", { colspan: 3, class: "estado", text: `Incompleto: falta ${k.faltantes.join(", ")}` }), el("td", {}, quitar)));
      continue;
    }
    const barra = el("div", { class: "barra", style: `width:${Math.max(20, 100 * k.anual / maximo)}%`,
      title: COMPONENTES.map(([c, n]) => `${n}: ${pesos(k[c] / 12)} por mes`).join("\n") },
    COMPONENTES.filter(([c]) => k[c] > 0).map(([c, , color]) => el("span", { style: `width:${100 * k[c] / k.anual}%;background:var(${color})` })));
    cuerpo.append(el("tr", {}, nombre, el("td", { class: "num" }, el("strong", { text: pesos(k.mensual) })),
      el("td", { class: "num", text: pesos(k.por_km) }), el("td", {}, barra), el("td", {}, quitar)));
  }
  tabla.append(cuerpo);
  $("equipamiento").replaceChildren(...seccionEquipamiento(filas.map((f) => f.v), equipamiento));
  guardarEnUrl();
}

function guardarEnUrl() {
  const p = new URLSearchParams({ prov: $("provincia").value, km: $("km").value, anios: $("anios").value,
    seguro: $("seguro").value, v: elegidas.map((v) => v.id).join(",") });
  if ($("originales").checked) p.set("orig", "1");
  history.replaceState(null, "", `?${p}`);
}

function sugerir() {
  const lista = $("sugerencias");
  const q = $("buscar").value.trim();
  lista.replaceChildren();
  if (q.length < 2) { lista.hidden = true; return; }
  const encontradas = versiones.filter((v) => !elegidas.includes(v) && coincide(`${v.marca} ${v.modelo}`, q)).slice(0, 12);
  for (const v of encontradas) {
    lista.append(el("li", { role: "option", text: `${v.marca} ${v.modelo}`,
      onclick: () => { elegidas.push(v); $("buscar").value = ""; lista.hidden = true; dibujar(); } }));
  }
  lista.hidden = encontradas.length === 0;
}

async function iniciar() {
  [datos, equipamiento] = await Promise.all([cargar("costo.json"), cargar("equipamiento.json").catch(() => ({})), cargarFotos()]);
  versiones = objetos(datos.columnas, datos.versiones);
  const sel = $("provincia");
  for (const [id, nombre] of Object.entries(datos.provincias).sort((a, b) => a[1].localeCompare(b[1], "es"))) {
    sel.append(el("option", { value: id, text: nombre }));
  }
  const p = new URLSearchParams(location.search);
  sel.value = p.get("prov") || "06";
  for (const campo of ["km", "anios", "seguro"]) if (p.get(campo)) $(campo).value = p.get(campo);
  $("originales").checked = p.get("orig") === "1";
  const ids = (p.get("v") || "").split(",").filter(Boolean);
  elegidas = ids.length ? versiones.filter((v) => ids.includes(v.id)) : versiones.filter((v) => v.consumo_l100km !== null).slice(0, 4);
  for (const id of ["provincia", "km", "anios", "seguro", "originales"]) $(id).addEventListener("input", dibujar);
  $("buscar").addEventListener("input", sugerir);
  dibujar();
}

iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
