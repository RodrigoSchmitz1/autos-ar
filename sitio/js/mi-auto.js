// "Mi auto": cuanto cuesta mantener un auto en particular (modelo, version,
// anio, provincia y km por mes), nuevo o usado.
//
// Los datos salen de exportar/sitio.py (datos/miauto/): un indice con todos los
// modelos que circulan y un archivo por modelo, que se baja al elegirlo. Las
// cuentas son las mismas que las del comparador (costo.js):
//   combustible = consumo (l/100 km) / 100 x km x precio del litro en la provincia
//   service     = costo por km del plan oficial x km
//   repuestos   = costo por km de las piezas de desgaste x km (alternativo u original)
//                 (con el precio de cada pieza para el anio elegido: repuestos-anio.js)
//   patente     = la de esa version y anio en esa provincia / 12
// La perdida de valor va aparte: no es un gasto del mes.

import { cargar, objetos, pesos, numero, millones, el, coincide, pie, PIEZAS } from "./comun.js";
import { cargarFotos, foto, recorte, datosFoto, fotoAnio } from "./autos.js";
import { nombreFamilia } from "./respuesta.js";
import { navegacion } from "./nav.js";
import { barraApilada, rubros } from "./graficos.js";
import { preciosDelAnio, gastoPorKm } from "./repuestos-anio.js";

const $ = (id) => document.getElementById(id);
// replaceChildren escribe "null" si le llega un null: aca los vacios se descartan.
const poner = (nodo, ...hijos) => nodo.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));
const SVG = "http://www.w3.org/2000/svg";
const GUARDADO = "autosar-mi-auto";
const PARTES = [
  ["combustible", "Combustible", "var(--combustible)"],
  ["patente", "Patente", "var(--patente)"],
  ["service", "Service", "var(--service)"],
  ["repuestos", "Repuestos", "var(--repuestos)"],
  ["seguro", "Seguro", "var(--seguro)"],
];
const ICONOS = {
  freno: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
  motor: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  resorte: '<path d="M8 4h8M8 20h8M8 4l8 3-8 3 8 3-8 3 8 3"/>',
};
const ICONO_PIEZA = { pastillas_freno: "freno", disco_freno: "freno", campana_freno: "freno",
  amortiguador_delantero: "resorte", amortiguador_trasero: "resorte", amortiguador: "resorte" };

let indice, familia, versiones, estado;
let ofertas = {}; // productos de cada repuesto del modelo (datos/repuestos/<slug>.json)

// ---------- Estado: URL (para compartir) y, si no, lo ultimo que se eligio ----------
function leerEstado() {
  const p = new URLSearchParams(location.search);
  if (p.get("m")) {
    return { m: p.get("m"), v: p.get("v"), a: Number(p.get("a")) || null, p: p.get("p") || "06",
      km: Number(p.get("km")) || 1250, odo: p.get("odo") === null ? null : Number(p.get("odo")),
      seg: Number(p.get("seg")) || 0, o: p.get("o") === "1" };
  }
  try { return JSON.parse(localStorage.getItem(GUARDADO)) || null; } catch { return null; }
}

function guardarEstado() {
  const p = new URLSearchParams({ m: estado.m, v: estado.v, a: estado.a, p: estado.p, km: estado.km });
  if (estado.odo !== null) p.set("odo", estado.odo);
  if (estado.seg) p.set("seg", estado.seg);
  if (estado.o) p.set("o", "1");
  history.replaceState(null, "", `?${p}`);
  try { localStorage.setItem(GUARDADO, JSON.stringify(estado)); } catch { /* sin almacenamiento: queda en la URL */ }
}

// ---------- Datos del modelo ----------
const nombreVersion = (modelo) => {
  const fam = familia.familia.replace(/\s*PICK\s*-?\s*UP\b/i, "").trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return modelo.replace(new RegExp(`^${fam}\\s*`, "i"), "") || modelo;
};

function aniosDe(v) {
  const anios = new Set([...(familia.patente[v.id]?.anios || []), ...Object.keys(familia.valor[v.id] || {}).filter((a) => a !== "0").map(Number)]);
  if (familia.valor[v.id]?.["0"]) anios.add(new Date().getFullYear());
  return [...anios].sort((a, b) => b - a);
}
const esCeroKm = (v, anio) => familia.valor[v.id]?.["0"] && anio >= new Date().getFullYear();
const valorDe = (v, anio) => familia.valor[v.id]?.[String(anio)] ?? (esCeroKm(v, anio) ? familia.valor[v.id]["0"] : null);

function patenteDe(v, anio, prov) {
  const p = familia.patente[v.id];
  if (!p) return null;
  const i = p.anios.indexOf(anio);
  return i < 0 ? null : p.valores[prov]?.[i] ?? null;
}

function odometro(anio) {
  if (estado.odo !== null && estado.odo !== undefined) return estado.odo;
  const anios = Math.max(0, new Date().getFullYear() - anio);
  return Math.round(anios * estado.km * 12 / 1000) * 1000;
}

function calcular(v) {
  const precio = v.combustible === "electrico" ? null
    : indice.precio_litro[estado.p]?.[v.combustible === "diesel" ? "diesel" : "nafta"] ?? null;
  const aj = repuestosDelAnio(v);
  const rep = aj ? (estado.o ? aj.orig : aj.alt)
    : estado.o && v.repuestos_por_km_original !== null ? v.repuestos_por_km_original : v.repuestos_por_km;
  const patente = patenteDe(v, estado.a, estado.p);
  const partes = {
    combustible: v.consumo_l100km !== null && precio !== null ? v.consumo_l100km / 100 * estado.km * precio : null,
    patente: patente !== null ? patente / 12 : null,
    service: v.service_por_km * estado.km,
    repuestos: rep * estado.km,
    seguro: estado.seg || null,
  };
  const total = Object.values(partes).reduce((s, x) => s + (x || 0), 0);
  return { partes, total, precio, patente, aj };
}

// Repuestos para el anio elegido: el precio de cada pieza sin los productos que,
// segun el titulo, son para otros anios (un Gol Trend 2010 no lleva las piezas
// del 2018), y el costo por km con la misma cuenta que dbt. null si no cambia
// nada (o el modelo no tiene precios propios).
function repuestosDelAnio(v) {
  if (v.repuestos_fuente === "mediana_general" || !familia.repuestos.length) return null;
  const base = Object.fromEntries(familia.repuestos.map(([tipo, orig, alt, n]) => [tipo, [orig, alt, n]]));
  const { piezas, cambiadas } = preciosDelAnio(base, ofertas, Number(estado.a) || new Date().getFullYear());
  if (![...cambiadas].some((t) => indice.intervalos[t])) return null;
  const [alt, orig] = gastoPorKm(piezas, indice.intervalos, { embrague: !v.automatica });
  return { alt, orig, piezas, cambiadas };
}

// ---------- Pantalla 1: elegir modelo ----------
function aniosTexto([desde, hasta]) {
  if (!desde && !hasta) return "";
  const fin = hasta >= new Date().getFullYear() ? "hoy" : hasta;
  return desde === hasta ? String(desde) : `${desde ?? ""}–${fin}`;
}

function mostrarElegir() {
  $("elegir").classList.remove("oculto");
  $("tablero").classList.add("oculto");
  $("abrir-ajustes").classList.add("oculto");
  const dibujar = () => {
    const q = $("buscar").value.trim();
    const lista = (q ? indice.familias.filter((f) => coincide(`${f.marca} ${f.familia}`, q)) : indice.familias).slice(0, q ? 40 : 24);
    poner($("modelos"), ...lista.map((f) => el("button", { type: "button", class: "modelo-btn", onclick: () => elegirModelo(f.slug) },
      foto(f.marca, f.familia),
      el("span", { class: "nombre" }, nombreFamilia(f.marca, f.familia), el("small", { text: aniosTexto(f.anios) })))));
    if (!lista.length) poner($("modelos"), el("p", { class: "vacio", text: "No encontramos ese modelo. Probá con otro nombre." }));
  };
  $("buscar").oninput = dibujar;
  dibujar();
}

async function elegirModelo(slug) {
  const nuevo = !estado || estado.m !== slug;
  await cargarFamilia(slug);
  const v = versiones[0];
  estado = { ...(estado || {}), m: slug, v: v.id, a: aniosDe(v)[0], p: estado?.p || "06", km: estado?.km || 1250,
    odo: nuevo ? null : estado.odo, seg: estado?.seg || 0, o: estado?.o || false };
  mostrarTablero();
  abrirAjustes();
}

async function cargarFamilia(slug) {
  [familia, ofertas] = await Promise.all([cargar(`miauto/${slug}.json`), cargar(`repuestos/${slug}.json`).catch(() => ({}))]);
  versiones = objetos(familia.columnas, familia.versiones);
}

// ---------- Ajustes ----------
function abrirAjustes() {
  const v = versiones.find((x) => x.id === estado.v) || versiones[0];
  $("cambiar-modelo").textContent = `${nombreFamilia(familia.marca, familia.familia)} · cambiar modelo`;
  poner($("f-version"), ...versiones.map((x) => el("option", { value: x.id, text: nombreVersion(x.modelo) })));
  $("f-version").value = v.id;
  llenarAnios(v);
  poner($("f-provincia"), ...Object.entries(indice.provincias).sort((a, b) => a[1].localeCompare(b[1], "es"))
    .map(([id, n]) => el("option", { value: id, text: n === "Ciudad Autónoma de Buenos Aires" ? "CABA" : n })));
  $("f-provincia").value = estado.p;
  $("f-km").value = estado.km;
  $("f-km-valor").textContent = `${numero(estado.km)} km`;
  $("f-odometro").value = odometro(estado.a);
  $("f-seguro").value = estado.seg || "";
  $("hoja").classList.add("abierta");
  $("velo").classList.add("abierto");
}

function llenarAnios(v) {
  const anios = aniosDe(v);
  if (!anios.includes(estado.a)) estado.a = anios[0];
  poner($("f-anio"), ...anios.map((a) => el("option", { value: a, text: esCeroKm(v, a) ? `${a} · 0 km` : String(a) })));
  $("f-anio").value = estado.a;
}

function cerrarAjustes() {
  $("hoja").classList.remove("abierta");
  $("velo").classList.remove("abierto");
}

function conectarAjustes() {
  $("abrir-ajustes").onclick = abrirAjustes;
  $("velo").onclick = cerrarAjustes;
  $("listo").onclick = cerrarAjustes;
  $("cambiar-modelo").onclick = () => { cerrarAjustes(); mostrarElegir(); $("buscar").focus(); };
  $("f-version").onchange = () => {
    estado.v = $("f-version").value;
    llenarAnios(versiones.find((x) => x.id === estado.v));
    estado.odo = null; $("f-odometro").value = odometro(estado.a);
    dibujarTablero();
  };
  $("f-anio").onchange = () => { estado.a = Number($("f-anio").value); estado.odo = null; $("f-odometro").value = odometro(estado.a); dibujarTablero(); };
  $("f-provincia").onchange = () => { estado.p = $("f-provincia").value; dibujarTablero(); };
  $("f-km").oninput = () => {
    estado.km = Number($("f-km").value);
    $("f-km-valor").textContent = `${numero(estado.km)} km`;
    if (estado.odo === null) $("f-odometro").value = odometro(estado.a);
    dibujarTablero();
  };
  $("f-odometro").oninput = () => { const x = Number($("f-odometro").value); estado.odo = $("f-odometro").value === "" ? null : Math.max(0, x); dibujarTablero(); };
  $("f-seguro").oninput = () => { estado.seg = Math.max(0, Number($("f-seguro").value) || 0); dibujarTablero(); };
  document.querySelectorAll("#tipo-repuestos button").forEach((b) => b.addEventListener("click", () => {
    estado.o = b.dataset.o === "1";
    dibujarTablero();
  }));
}

// ---------- Pantalla 2: el tablero ----------
function mostrarTablero() {
  $("elegir").classList.add("oculto");
  $("tablero").classList.remove("oculto");
  $("abrir-ajustes").classList.remove("oculto");
  const marca = familia.marca, fam = familia.familia;
  // La foto real del modelo (el auto recortado se ve pegado); sin foto, la marca en grande.
  const conFoto = Boolean(datosFoto(marca, fam));
  $("hero-foto").classList.toggle("con-foto", conFoto);
  if (!conFoto) poner($("hero-foto"), el("div", { class: "hero-marca", text: marca }));
  $("nombre").textContent = nombreFamilia(marca, fam);
  dibujarTablero();
}

function dibujarTablero() {
  const v = versiones.find((x) => x.id === estado.v) || versiones[0];
  estado.v = v.id;
  guardarEstado();
  // La foto, de la generacion del anio elegido (el 0 km es este anio).
  if (datosFoto(familia.marca, familia.familia)) {
    poner($("hero-foto"), fotoAnio(familia.marca, familia.familia, Number(estado.a) || new Date().getFullYear()));
  }
  const k = calcular(v);
  const odo = odometro(estado.a);
  const nombreProv = indice.provincias[estado.p] === "Ciudad Autónoma de Buenos Aires" ? "CABA" : indice.provincias[estado.p];

  $("version").textContent = [nombreVersion(v.modelo), v.automatica ? "automático" : "manual", v.combustible].filter(Boolean).join(" · ");
  const chip = (texto, sub) => el("button", { type: "button", class: "chip", onclick: abrirAjustes }, texto, sub ? el("small", { text: sub }) : null);
  poner($("chips"), 
    chip(numero(estado.km), "km/mes"), chip(nombreProv),
    esCeroKm(v, estado.a) ? chip("0 km", `· ${estado.a}`) : chip(String(estado.a), `· ${numero(odo)} km`));

  // Total del mes y desglose
  $("total").textContent = numero(Math.round(k.total / 100) * 100);
  poner($("total-sub"), el("b", { text: millones(k.total * 12) }), " al año · ",
    el("b", { text: pesos(k.total / estado.km) }), " por km");
  const detalle = {
    combustible: v.consumo_l100km ? `${numero(v.consumo_l100km / 100 * estado.km)} litros por mes` : "",
    patente: k.patente !== null ? `$${numero(k.patente / 1000)} mil al año` : "",
    service: v.service_fuente === "familia" ? "plan oficial" : "estimado",
    repuestos: (estado.o ? "originales" : "alternativos") + (k.aj ? `, para un ${estado.a}` : ""),
    seguro: "el que cargaste",
  };
  const partes = PARTES.filter(([id]) => id !== "seguro" || k.partes.seguro).map(([id, nombre, color]) => ({
    nombre, color, valor: k.partes[id], detalle: detalle[id], motivo: k.partes[id] === null ? detalleSinDato(id, v) : "" }));
  poner($("apilada"), barraApilada(partes));
  poner($("rubros"), rubros(partes, (x) => pesos(Math.round(x / 100) * 100)));
  document.querySelectorAll("#tipo-repuestos button").forEach((b) => b.classList.toggle("on", (b.dataset.o === "1") === estado.o));

  // Resumen para la portada ("tu auto te cuesta...").
  try {
    localStorage.setItem(`${GUARDADO}-resumen`, JSON.stringify({ marca: familia.marca, familia: familia.familia,
      version: nombreVersion(v.modelo), anio: estado.a, total: k.total, url: `mi-auto.html${location.search}` }));
  } catch { /* sin almacenamiento */ }

  dibujarService(v, odo);
  dibujarValor(v);
  dibujarRepuestos(v, odo);
  $("fuentes").textContent = fuentes(v, k, nombreProv);
}

function detalleSinDato(id, v) {
  if (id === "combustible") return v.combustible === "electrico" ? "eléctrico: no lo calculamos" : "sin consumo oficial";
  if (id === "patente") return "exento o municipal";
  return "sin dato";
}

// Plan de service: el proximo segun los km de hoy. Pasado el plan oficial, se
// repite el ciclo (estimado).
function proximosServices(odo, n = 5) {
  const plan = familia.service;
  if (!plan?.length) return [];
  const intervalo = plan.length > 1 ? Math.min(...plan.slice(1).map((p, i) => p[0] - plan[i][0])) : plan[0][0];
  const fin = plan[plan.length - 1][0];
  const lista = [];
  for (let km = (Math.floor(odo / intervalo) + 1) * intervalo; lista.length < n; km += intervalo) {
    const enPlan = ((km - 1) % fin) + 1;
    const p = plan.find((x) => x[0] >= enPlan) || plan[plan.length - 1];
    lista.push({ km, precio: p[1], items: p[2], estimado: km > fin });
  }
  return lista;
}

function dibujarService(v, odo) {
  const t = $("tarjeta-service");
  const prox = proximosServices(odo);
  if (!prox.length) {
    poner(t, el("h2", {}, "Service"),
      el("div", { class: "proximo" }, el("div", { class: "grande" }, pesos(v.service_por_km * 10000), el("small", { text: " cada 10.000 km" }))),
      el("p", { class: "nota", text: "Esta marca no publica su plan de service oficial: usamos el promedio de las marcas que sí lo publican." }));
    return;
  }
  const p = prox[0];
  const meses = Math.max(0, Math.round((p.km - odo) / estado.km));
  const cuando = meses < 1 ? "ya" : meses < 24 ? `en ${meses} ${meses === 1 ? "mes" : "meses"}` : `en ${(meses / 12).toFixed(1).replace(".", ",")} años`;
  const hitos = [{ km: odo, hoy: true }, ...prox];
  const ancho = hitos[hitos.length - 1].km - odo || 1;
  poner(t, 
    el("h2", {}, "Próximo service ", el("b", { text: p.estimado ? "(estimado)" : "oficial" })),
    el("div", { class: "proximo" },
      el("div", {}, el("div", { class: "grande" }, numero(p.km), el("small", { text: " km" })), el("p", { class: "sub", style: "margin-top:4px", text: cuando })),
      el("div", { class: "precio", text: pesos(p.precio) })),
    el("div", { class: "linea-tiempo" }, hitos.map((h, i) => el("div", {
      class: `hito${h.hoy ? " hoy" : ""}${i === 1 ? " prox" : ""}`, style: `left:${4 + (h.km - odo) / ancho * 90}%` },
    el("i"), h.hoy ? "Hoy" : `${numero(h.km / 1000)}k`))),
    p.items ? el("p", { class: "items-service", text: p.items.split("|").map((x) => x.trim()).filter(Boolean).slice(0, 6).join(" · ") }) : null,
    el("p", { class: "nota", text: p.estimado
      ? "El plan oficial publicado no llega a estos kilómetros: repetimos el ciclo del plan. Precio de lista de la red oficial."
      : "Precio de lista de la red oficial para esos kilómetros." }));
}

function dibujarValor(v) {
  const t = $("tarjeta-valor");
  const hoy = valorDe(v, estado.a);
  if (!hoy) { poner(t, el("h2", {}, "Cuánto vale"), el("p", { class: "nota", text: "No tenemos la valuación de esta versión y año." })); return; }
  // Dentro de N anios: lo que hoy vale la misma version N anios mas vieja (hasta 5).
  let n = 5;
  while (n > 1 && !valorDe(v, estado.a - n)) n--;
  const futuro = valorDe(v, estado.a - n);
  // Curva: lo que hoy vale la misma version con 0, 1, 2... anios mas.
  const puntos = [];
  for (let edad = 0; edad <= 10; edad++) { const x = valorDe(v, estado.a - edad); if (x) puntos.push([edad, x]); }
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "curva"); svg.setAttribute("viewBox", "0 0 300 120"); svg.setAttribute("preserveAspectRatio", "none");
  if (puntos.length > 1) {
    const max = Math.max(...puntos.map((p) => p[1]));
    const ultima = puntos[puntos.length - 1][0];
    const xy = puntos.map(([e, x]) => [e / ultima * 300, 112 - x / max * 100]);
    const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    svg.innerHTML = `<defs><linearGradient id="g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#4c8dff" stop-opacity=".35"/>`
      + `<stop offset="1" stop-color="#4c8dff" stop-opacity="0"/></linearGradient></defs>`
      + `<path d="${d} L${xy[xy.length - 1][0]},120 L0,120 Z" fill="url(#g)"/><path d="${d}" fill="none" stroke="#4c8dff" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
  }
  poner(t, el("h2", {}, "Cuánto vale"),
    el("div", { class: "valor-cifras" },
      el("div", {}, "Hoy", el("strong", { text: millones(hoy) })),
      futuro && n > 0 ? el("div", { style: "text-align:right" }, `En ${n} ${n === 1 ? "año" : "años"}`, el("strong", { text: millones(futuro) })) : null),
    puntos.length > 1 ? svg : null,
    el("p", { class: "nota", text: "Valuación fiscal (DNRPA): la base de la patente. El precio de venta real suele ser otro. "
      + "A futuro, lo que vale hoy la misma versión más vieja, en pesos de hoy. No se suma al gasto del mes." }));
}

function dibujarRepuestos(v, odo) {
  const conIntervalo = [], otros = [];
  const aj = repuestosDelAnio(v);
  const propios = aj ? aj.piezas : Object.fromEntries(familia.repuestos.map(([tipo, orig, alt]) => [tipo, [orig, alt]]));
  // Las piezas de desgaste que el costo cuenta: con el precio del modelo o, si no lo
  // relevamos, con el mediano de esa pieza en todos los modelos (como el total del mes).
  for (const [tipo, i] of Object.entries(indice.intervalos)) {
    if (i.solo_manual && v.automatica) continue;
    const [orig, alt] = propios[tipo] || i.mediana;
    const precio = estado.o ? orig ?? alt : alt ?? orig;
    const proximo = (Math.floor(odo / i.km) + 1) * i.km;
    conIntervalo.push({ tipo, i, precio, orig, alt, proximo, meses: (proximo - odo) / estado.km, promedio: !propios[tipo] });
  }
  for (const [tipo, [orig, alt]] of Object.entries(propios)) {
    const precio = estado.o ? orig ?? alt : alt ?? orig;
    if (!indice.intervalos[tipo] && precio) otros.push([tipo, precio]);
  }
  conIntervalo.sort((a, b) => a.meses - b.meses);
  poner($("lista-repuestos"), ...conIntervalo.map((r) => {
    const m = Math.round(r.meses);
    const cuando = m < 1 ? "ya" : m < 24 ? `en ${m} ${m === 1 ? "mes" : "meses"}` : `en ${(m / 12).toFixed(1).replace(".", ",")} años`;
    const clase = m <= 3 ? "ya" : m > 40 ? "lejos" : "";
    const icono = el("span", { class: "ico" });
    icono.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">${ICONOS[ICONO_PIEZA[r.tipo] || "motor"]}</svg>`;
    const otro = r.promedio ? "precio promedio" : estado.o ? (r.orig ? null : "no hay original")
      : (r.orig && r.alt ? `original ${pesos(r.orig * r.i.unidades)}` : null);
    // Con precio propio, la fila lleva a los productos de esa pieza en Repuestos.
    const atributos = r.promedio ? { class: "fila" }
      : { class: "fila enlace", href: `repuestos.html?m=${estado.m}&p=${r.tipo}&a=${Number(estado.a) || new Date().getFullYear()}`, title: "Ver los productos y dónde comprarlo" };
    return el(r.promedio ? "div" : "a", atributos, icono,
      el("div", {}, el("h3", {}, PIEZAS[r.tipo] || r.tipo, el("span", { class: `pildora ${clase}`, text: cuando })),
        el("p", { text: `Cada ${numero(r.i.km)} km${r.i.unidades > 1 ? ` · ${r.i.unidades} unidades` : ""} · a los ${numero(r.proximo)} km` })),
      el("div", { class: "der" }, el("strong", { text: pesos(r.precio * r.i.unidades) }), otro ? el("small", { text: otro }) : null));
  }));
  poner($("otros-repuestos"), ...otros.sort((a, b) => (PIEZAS[a[0]] || a[0]).localeCompare(PIEZAS[b[0]] || b[0], "es"))
    .map(([t, p]) => el("span", {}, PIEZAS[t] || t, el("b", { text: pesos(p) }))));
  $("nota-repuestos").textContent = `Precio mediano en las tiendas relevadas (Repuestos Express y ARG Autopartes), ${estado.o ? "original" : "alternativo (si no hay, el original)"}. `
    + "Intervalos de cambio habituales; dependen del uso. Tocá un repuesto para ver los productos y dónde comprarlo."
    + (aj ? ` Para un ${estado.a}: sin los productos que, según el título, son para otros años.` : "")
    + (conIntervalo.some((r) => r.promedio) ? " \"Precio promedio\": no relevamos esa pieza para este modelo y usamos el precio mediano de todos." : "") + (otros.length ? " Abajo, otros repuestos de este modelo (filtros y bujías van en el service)." : "");
}

function fuentes(v, k, prov) {
  const partes = [];
  if (k.precio) partes.push(`Combustible: consumo ${v.consumo_estimacion === "familia" ? "promedio del modelo" : "oficial"} de ${String(v.consumo_l100km).replace(".", ",")} l/100 km y ${v.combustible === "diesel" ? "gasoil" : "nafta"} a ${pesos(k.precio)} el litro en ${prov}.`);
  if (k.patente !== null) partes.push(`Patente estimada con la valuación fiscal y la alícuota de ${prov}.`);
  else partes.push(`Patente: no tenemos el valor para un ${estado.a} en ${prov} (puede estar exento por antigüedad o cobrarla el municipio).`);
  if (v.service_fuente !== "familia") partes.push("Service: sin plan oficial publicado; promedio de las marcas que lo publican.");
  if (v.repuestos_fuente === "parcial") partes.push("Repuestos: las piezas sin precio relevado para este modelo usan el precio mediano de esa pieza en todos los modelos.");
  else if (v.repuestos_fuente !== "familia") partes.push("Repuestos: sin precios de este modelo; promedio de todos.");
  return partes.join(" ");
}

// ---------- Inicio ----------
async function iniciar() {
  [indice] = await Promise.all([cargar("miauto/indice.json"), cargarFotos()]);
  conectarAjustes();
  estado = leerEstado();
  if (estado?.m && indice.familias.some((f) => f.slug === estado.m)) {
    await cargarFamilia(estado.m);
    // Un enlace puede traer solo el modelo (?m=fiat-cronos): version y anio por defecto.
    const v = versiones.find((x) => x.id === estado.v) || versiones[0];
    estado.v = v.id;
    const anios = aniosDe(v);
    if (!anios.includes(estado.a)) estado.a = estado.a ? anios.reduce((m, x) => Math.abs(x - estado.a) < Math.abs(m - estado.a) ? x : m) : anios[0];
    mostrarTablero();
  } else {
    estado = null;
    mostrarElegir();
  }
}

navegacion();
iniciar().catch((e) => {
  $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`;
  $("estado").classList.remove("oculto");
});
pie();
