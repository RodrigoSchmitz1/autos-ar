import { cargar, objetos, pesos, millones, el, pie } from "./comun.js";
import { cargarFotos, foto } from "./autos.js";
import { interpretar, prepararCatalogo } from "./interprete.js";
import { responder, explicar, nombreFamilia, POR_DEFECTO } from "./respuesta.js";

// Intermediario de Gemini (Cloudflare Worker, ver asistente/worker/). Vacio: sin
// IA, el asistente funciona solo con reglas y el boton no aparece.
const IA_URL = "https://autos-ar-asistente.rodri-schmitz-7e9.workers.dev";

const COMPONENTES = [
  ["combustible_anual", "Combustible", "--c-combustible"], ["service_anual", "Service", "--c-service"],
  ["repuestos_anual", "Repuestos", "--c-repuestos"], ["patente_anual", "Patente", "--c-patente"],
  ["depreciacion_anual", "Depreciación", "--c-depreciacion"], ["seguro_anual", "Seguro", "--c-seguro"],
];
const CARROCERIAS = { hatch: "Hatch", sedan: "Sedán", suv: "SUV", pickup: "Pick-up", utilitario: "Utilitario" };
const COMBUSTIBLES = { nafta: "Nafta", diesel: "Diésel", hibrido: "Híbrido", electrico: "Eléctrico" };
const EJEMPLOS = [
  "cronos o polo? hago 15000 km por año en Córdoba",
  "camioneta gasolera hasta 50 palos",
  "manejo 20 km por día, somos 4",
  "híbrido automático, sedán o SUV, hasta 55 millones",
  "Hilux vs Ranger vs Amarok, 30.000 km anuales en Neuquén",
];

const $ = (id) => document.getElementById(id);
let datos, versiones, catalogo, p = {};

function avisos(v) {
  const t = [];
  if (v.service_fuente !== "familia") t.push("service estimado");
  if (v.repuestos_fuente !== "familia") t.push("repuestos estimados");
  if (v.depreciacion_fuente === "mediana_marca") t.push("depreciación de la marca");
  if (v.depreciacion_fuente === "mediana_general") t.push("depreciación estimada");
  if (v.consumo_estimacion && v.consumo_estimacion !== "version") t.push("consumo estimado");
  return t.map((x) => el("span", { class: "chip aviso", text: x }));
}

function tarjeta({ v, k, nota }, puesto) {
  const barra = k.completo
    ? el("div", { class: "barra", title: COMPONENTES.map(([c, n]) => `${n}: ${pesos(k[c] / 12)} por mes`).join("\n") },
      COMPONENTES.filter(([c]) => k[c] > 0).map(([c, , color]) => el("span", { style: `width:${100 * k[c] / k.anual}%;background:var(${color})` })))
    : null;
  return el("a", { class: "auto-tarjeta", href: `ficha.html?m=${encodeURIComponent(`${v.marca}|${v.familia}`)}` },
    el("div", { class: "auto-foto" }, foto(v.marca, v.familia), el("div", { class: "puesto", text: puesto })),
    el("div", { class: "auto-cuerpo" },
      el("p", { class: "nombre", text: nombreFamilia(v.marca, v.familia) }),
      el("div", { class: "marca-auto", text: v.modelo }),
      el("div", { class: "cifra", text: k.completo ? `${pesos(k.mensual)} por mes` : `Falta: ${k.faltantes.join(", ")}` }),
      barra,
      el("div", { class: "detalle", text: `${k.completo ? `${pesos(k.por_km)} por km · ` : ""}0 km ${millones(v.valor_0km)} · ${v.combustible}` }),
      nota ? el("div", {}, el("span", { class: "chip aviso", text: nota })) : null,
      el("div", {}, avisos(v))));
}

function mostrarRespuesta() {
  const r = responder(p, versiones, datos.precio_litro);
  $("texto-respuesta").textContent = explicar(r, datos.provincias[r.provincia], pesos);
  $("tarjetas").replaceChildren(...r.filas.map((f, i) => tarjeta(f, i + 1)));
  $("leyenda").hidden = !r.filas.length;
  const ids = r.filas.map((f) => f.v.id).join(",");
  const enlace = $("al-comparador");
  enlace.hidden = !r.filas.length;
  enlace.href = `comparador.html?${new URLSearchParams({ prov: r.provincia, km: r.perfil.km_anio, anios: r.perfil.anios,
    seguro: r.perfil.seguro_mensual, v: ids, ...(r.perfil.repuestos_originales ? { orig: "1" } : {}) })}`;
}

// "Entendi esto": cada campo editable; al cambiar, se recalcula la respuesta.
function mostrarEntendido() {
  const campo = (etiqueta, control) => el("div", {}, el("label", { text: etiqueta }), control);
  const numeroCampo = (clave, placeholder, factor = 1) => {
    const i = el("input", { type: "number", min: 0, placeholder, value: p[clave] !== undefined ? p[clave] / factor : "" });
    i.addEventListener("input", () => {
      if (i.value === "") delete p[clave]; else p[clave] = Number(i.value) * factor;
      mostrarRespuesta();
    });
    return i;
  };
  const prov = el("select", {}, el("option", { value: "", text: `${datos.provincias[POR_DEFECTO.provincia_id]} (por defecto)` }),
    Object.entries(datos.provincias).sort((a, b) => a[1].localeCompare(b[1], "es")).map(([id, n]) => el("option", { value: id, text: n })));
  prov.value = p.provincia_id ?? "";
  prov.addEventListener("input", () => { if (prov.value) p.provincia_id = prov.value; else delete p.provincia_id; mostrarRespuesta(); });
  const caja = el("select", {}, el("option", { value: "", text: "Cualquiera" }), el("option", { value: "si", text: "Automática" }), el("option", { value: "no", text: "Manual" }));
  caja.value = p.automatica === undefined ? "" : p.automatica ? "si" : "no";
  caja.addEventListener("input", () => { if (caja.value) p.automatica = caja.value === "si"; else delete p.automatica; mostrarRespuesta(); });

  const alternar = (clave, opciones) => el("div", { class: "alternar" }, Object.entries(opciones).map(([valor, texto]) => {
    const b = el("button", { type: "button", class: `chip-alternar${p[clave]?.includes(valor) ? " activo" : ""}`, text: texto,
      "aria-pressed": String(Boolean(p[clave]?.includes(valor))) });
    b.addEventListener("click", () => {
      const lista = new Set(p[clave] || []);
      if (lista.has(valor)) lista.delete(valor); else lista.add(valor);
      if (lista.size) p[clave] = [...lista]; else delete p[clave];
      b.classList.toggle("activo"); b.setAttribute("aria-pressed", String(lista.has(valor)));
      mostrarRespuesta();
    });
    return b;
  }));

  const modelos = el("div", { class: "alternar" }, (p.modelos || []).map((clave) => {
    const [marca, familia] = clave.split("|");
    return el("span", { class: "chip" }, nombreFamilia(marca, familia),
      el("button", { type: "button", class: "quitar", "aria-label": `Quitar ${familia}`, text: "×",
        onclick: (e) => { p.modelos = p.modelos.filter((m) => m !== clave); if (!p.modelos.length) delete p.modelos; e.target.parentElement.remove(); mostrarRespuesta(); } }));
  }));

  $("entendido").replaceChildren(
    el("h2", { text: "Entendí esto" }),
    el("p", { class: "nota", text: "Si algo no es lo que quisiste decir, corregilo acá: la respuesta se recalcula." }),
    p.modelos ? campo("Modelos", modelos) : null,
    el("div", { class: "controles" },
      campo("Provincia", prov),
      campo("Km por año", numeroCampo("km_anio", `${POR_DEFECTO.km_anio} (por defecto)`)),
      campo("Años que lo tenés", numeroCampo("anios", `${POR_DEFECTO.anios} (por defecto)`)),
      campo("Presupuesto (millones)", numeroCampo("presupuesto_max", "sin tope", 1_000_000)),
      campo("Seguro por mes ($)", numeroCampo("seguro_mensual", "0")),
      campo("Caja", caja)),
    campo("Carrocería", alternar("carroceria", CARROCERIAS)),
    campo("Combustible", alternar("combustible", COMBUSTIBLES)));
  $("entendido").hidden = false;
}

function preguntar(texto) {
  p = interpretar(texto, catalogo);
  history.replaceState(null, "", `?${new URLSearchParams({ q: texto })}`);
  mostrarEntendido();
  mostrarRespuesta();
  $("respuesta").hidden = false;
  const boton = $("con-ia");
  boton.hidden = !IA_URL;
  boton.disabled = false;
  boton.textContent = "¿No entendió bien? Probá con IA";
  // Si las reglas no entendieron nada, se le pregunta a la IA sin esperar el clic.
  if (IA_URL && !Object.keys(p).length) preguntarConIA();
}

// Respaldo con IA: Gemini devuelve los mismos parametros, con los modelos en
// texto; el catalogo (codigo) los valida, asi la IA no puede inventar un modelo.
async function preguntarConIA() {
  const texto = $("pregunta").value.trim();
  const boton = $("con-ia");
  boton.disabled = true; boton.textContent = "Preguntando a la IA…";
  try {
    const r = await fetch(IA_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto }) });
    if (!r.ok) throw new Error(r.status === 429 ? "se agotó la cuota gratis de hoy" : `error ${r.status}`);
    const ia = await r.json();
    const modelos = ia.modelos?.length ? interpretar(ia.modelos.join(" o "), catalogo).modelos : undefined;
    p = Object.fromEntries(Object.entries({ ...ia, modelos }).filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && !v.length)));
    mostrarEntendido();
    mostrarRespuesta();
    boton.textContent = "Interpretado con IA";
  } catch (e) {
    boton.textContent = `La IA no respondió (${e.message})`;
  }
}

async function iniciar() {
  [datos] = await Promise.all([cargar("costo.json"), cargarFotos()]);
  versiones = objetos(datos.columnas, datos.versiones);
  const ventas = new Map();
  for (const v of versiones) ventas.set(`${v.marca}|${v.familia}`, (ventas.get(`${v.marca}|${v.familia}`) || 0) + (v.inscripciones_12m || 0));
  catalogo = prepararCatalogo([...ventas].map(([k, n]) => ({ marca: k.split("|")[0], familia: k.split("|")[1], inscripciones: n })));

  $("leyenda").replaceChildren(...COMPONENTES.map(([, n, c]) => el("span", {}, el("i", { style: `background:var(${c})` }), n)));
  $("ejemplos").replaceChildren(...EJEMPLOS.map((t) => el("button", { type: "button", class: "chip-alternar", text: t,
    onclick: () => { $("pregunta").value = t; preguntar(t); } })));
  $("formulario").addEventListener("submit", (e) => { e.preventDefault(); const t = $("pregunta").value.trim(); if (t) preguntar(t); });
  $("con-ia").addEventListener("click", preguntarConIA);
  const q = new URLSearchParams(location.search).get("q");
  if (q) { $("pregunta").value = q; preguntar(q); }
  $("estado").textContent = "";
}

iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
