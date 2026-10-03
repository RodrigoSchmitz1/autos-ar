import { cargar, pesos, numero, decimal, el, coincide, pie } from "./comun.js";
import { cargarFotos, foto } from "./autos.js";

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";
const PIEZAS = {
  pastillas_freno: "Pastillas de freno", disco_freno: "Disco de freno", campana_freno: "Campana de freno",
  filtro_aceite: "Filtro de aceite", filtro_aire: "Filtro de aire", filtro_habitaculo: "Filtro de habitáculo",
  filtro_combustible: "Filtro de combustible", kit_filtros: "Kit de filtros", kit_service: "Kit de service",
  bujia_encendido: "Bujía", bujia_precalentamiento: "Bujía de precalentamiento", kit_distribucion: "Kit de distribución",
  correa_distribucion: "Correa de distribución", tensor_distribucion: "Tensor de distribución",
  correa_accesorios: "Correa de accesorios", amortiguador_delantero: "Amortiguador delantero",
  amortiguador_trasero: "Amortiguador trasero", amortiguador: "Amortiguador", kit_embrague: "Kit de embrague",
};
let fichas;

function svg(tag, atributos) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) e.setAttribute(k, v);
  return e;
}

// Curva de depreciacion: % del valor 0 km que conserva a cada edad.
function grafico(puntos) {
  const ancho = 640, alto = 220, m = { i: 40, d: 12, s: 12, b: 28 };
  const x = (a) => m.i + (a - 1) / 13 * (ancho - m.i - m.d);
  const y = (p) => m.s + (1 - p) * (alto - m.s - m.b);
  const s = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: "100%", role: "img",
    "aria-label": "Proporción del valor 0 km que conserva por años de antigüedad" });
  for (const p of [0.25, 0.5, 0.75, 1]) {
    s.append(svg("line", { x1: m.i, x2: ancho - m.d, y1: y(p), y2: y(p), stroke: "var(--borde)" }));
    const t = svg("text", { x: 4, y: y(p) + 4 }); t.textContent = `${p * 100}%`; s.append(t);
  }
  for (const a of [1, 5, 10, 14]) { const t = svg("text", { x: x(a), y: alto - 8, "text-anchor": a === 1 ? "start" : a === 14 ? "end" : "middle" }); t.textContent = a === 1 ? "1 año" : `${a} años`; s.append(t); }
  for (const [idx, color, nombre] of [[2, "var(--c-depreciacion)", "mercado"], [1, "var(--c-combustible)", "fiscal"]]) {
    const ps = puntos.filter((p) => p[idx] !== null);
    if (ps.length < 2) continue;
    s.append(svg("polyline", { points: ps.map((p) => `${x(p[0])},${y(p[idx])}`).join(" "), fill: "none", stroke: color, "stroke-width": 2.5 }));
    const u = ps[ps.length - 1];
    const t = svg("text", { x: x(u[0]) - 40, y: y(u[idx]) - 6, fill: color }); t.textContent = nombre; s.append(t);
  }
  return s;
}

function mostrar(f) {
  $("titulo").textContent = `${f.marca} ${f.familia}`;
  $("foto").replaceChildren(foto(f.marca, f.familia, "grande"));
  history.replaceState(null, "", `?m=${encodeURIComponent(`${f.marca}|${f.familia}`)}`);
  const partes = [];
  if (f.depreciacion) {
    const a5 = f.depreciacion.find((p) => p[0] === 5);
    partes.push(el("h2", { text: "Cuánto valor conserva" }),
      el("p", { class: "bajada", text: a5 && a5[2] !== null
        ? `A los 5 años conserva el ${Math.round(100 * a5[2])}% del valor de un 0 km según la guía de precios de usados (mercado), y el ${Math.round(100 * a5[1])}% según la valuación fiscal.`
        : "Proporción del valor de un 0 km que conserva según la antigüedad." }),
      el("div", { class: "tarjeta" }, grafico(f.depreciacion)));
  }
  if (f.service) {
    partes.push(el("h2", { text: "Service oficial" }), el("div", { class: "tabla-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Versión" }), el("th", { class: "num", text: "Service típico" }),
        el("th", { class: "num", text: "Costo por km" }), el("th", { class: "num", text: "Plan hasta" }))),
      el("tbody", {}, f.service.map(([modelo, km, med, hasta]) => el("tr", {}, el("td", { text: modelo }),
        el("td", { class: "num", text: pesos(med) }), el("td", { class: "num", text: `$${decimal(km)}` }),
        el("td", { class: "num", text: `${numero(hasta)} km` })))))));
  }
  if (f.repuestos) {
    partes.push(el("h2", { text: "Repuestos de desgaste" }), el("p", { class: "bajada", text: "Precio mediano en la tienda relevada, original contra alternativo." }),
      el("div", { class: "tabla-scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", { text: "Pieza" }), el("th", { class: "num", text: "Original" }),
          el("th", { class: "num", text: "Alternativo" }), el("th", { class: "num", text: "Productos" }))),
        el("tbody", {}, f.repuestos.sort((a, b) => (PIEZAS[a[0]] || a[0]).localeCompare(PIEZAS[b[0]] || b[0], "es"))
          .map(([tipo, orig, alt, n]) => el("tr", {}, el("td", { text: PIEZAS[tipo] || tipo }),
            el("td", { class: "num", text: pesos(orig) }), el("td", { class: "num", text: pesos(alt) }), el("td", { class: "num", text: n })))))));
  }
  if (f.mercado) {
    const insc = f.mercado.reduce((s, m) => s + (m[1] || 0), 0);
    const transf = f.mercado.reduce((s, m) => s + (m[2] || 0), 0);
    partes.push(el("h2", { text: "Mercado (últimos 12 meses)" }),
      el("p", { class: "bajada", text: `${numero(insc)} patentamientos 0 km y ${numero(transf)} transferencias de usados en todo el país.` }));
  }
  $("contenido").replaceChildren(...partes);
  $("estado").textContent = partes.length ? "" : "No hay datos para este modelo.";
}

function sugerir() {
  const q = $("buscar").value.trim();
  const lista = $("sugerencias");
  lista.replaceChildren();
  if (q.length < 2) { lista.hidden = true; return; }
  const encontradas = fichas.filter((f) => coincide(`${f.marca} ${f.familia}`, q)).slice(0, 12);
  for (const f of encontradas) {
    lista.append(el("li", { role: "option", text: `${f.marca} ${f.familia}`,
      onclick: () => { $("buscar").value = ""; lista.hidden = true; mostrar(f); } }));
  }
  lista.hidden = encontradas.length === 0;
}

async function iniciar() {
  fichas = (await Promise.all([cargar("fichas.json"), cargarFotos()]))[0].fichas;
  // Primero las que tienen mas datos y mas ventas.
  fichas.sort((a, b) => (b.mercado || []).reduce((s, m) => s + (m[1] || 0), 0) - (a.mercado || []).reduce((s, m) => s + (m[1] || 0), 0));
  $("buscar").addEventListener("input", sugerir);
  const pedida = new URLSearchParams(location.search).get("m");
  mostrar(fichas.find((f) => `${f.marca}|${f.familia}` === pedida) || fichas[0]);
}

iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
