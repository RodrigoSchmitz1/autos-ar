import { cargar, objetos, pesos, numero, decimal, millones, el, coincide, pie } from "./comun.js";
import { cargarFotos, foto, recorte, variantes, datosFoto, colorDe } from "./autos.js";
import { seccionVersiones } from "./versiones.js";
import { cargarMedios, seccionGaleria, enlaceOficial } from "./galeria.js";
import { nombreFamilia } from "./respuesta.js";

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
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
let fichas, equipamiento = {}, versionesCosto = [];

function svg(tag, atributos) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) e.setAttribute(k, v);
  return e;
}

const mediana = (xs) => {
  const v = xs.filter((x) => x !== null && x !== undefined).sort((a, b) => a - b);
  return v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null;
};
const patentados = (f) => (f.mercado || []).reduce((s, m) => s + (m[1] || 0), 0);
const lindo = (t) => t.toLowerCase().replace(/(^|[\s-])([a-z])/g, (m, a, b) => a + b.toUpperCase());

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
  const series = [[2, "var(--c-depreciacion)", "mercado"], [1, "var(--c-combustible)", "fiscal"]]
    .map(([idx, color, nombre]) => ({ color, nombre, ps: puntos.filter((p) => p[idx] !== null).map((p) => [p[0], p[idx]]) }))
    .filter((c) => c.ps.length >= 2);
  // Etiqueta al final de cada curva: la de arriba por encima de su linea, la otra por debajo.
  const fin = (c) => c.ps[c.ps.length - 1][1];
  const arriba = series.length ? series.reduce((a, b) => (fin(b) > fin(a) ? b : a)) : null;
  for (const c of series) {
    s.append(svg("polyline", { points: c.ps.map(([a, p]) => `${x(a)},${y(p)}`).join(" "), fill: "none", stroke: c.color, "stroke-width": 3, "stroke-linejoin": "round" }));
    const [a, p] = c.ps[c.ps.length - 1];
    const t = svg("text", { x: x(a), y: y(p) + (c === arriba ? -8 : 16), fill: c.color, "font-weight": 600, "text-anchor": "end" });
    t.textContent = c.nombre; s.append(t);
  }
  return s;
}

// Barras de patentamientos 0 km por mes.
function barrasMercado(mercado, color) {
  const ancho = 640, alto = 200, b = 26, s0 = 18;
  const max = Math.max(...mercado.map((m) => m[1] || 0), 1);
  const paso = ancho / mercado.length;
  const s = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: "100%", role: "img", "aria-label": "Patentamientos 0 km por mes" });
  mercado.forEach(([periodo, insc], i) => {
    const h = ((insc || 0) / max) * (alto - b - s0);
    s.append(svg("rect", { x: i * paso + paso * 0.18, y: alto - b - h, width: paso * 0.64, height: h, rx: 6, fill: color }));
    const v = svg("text", { x: i * paso + paso / 2, y: alto - b - h - 5, "text-anchor": "middle" }); v.textContent = numero(insc); s.append(v);
    const t = svg("text", { x: i * paso + paso / 2, y: alto - 8, "text-anchor": "middle" }); t.textContent = MESES[Number(periodo.slice(5, 7)) - 1]; s.append(t);
  });
  return s;
}

// Lo que va arriba de todo: el auto grande sobre un degradado del color de la
// marca, el nombre y cuatro datos.
function hero(f) {
  const versiones = versionesCosto.filter((v) => v.marca === f.marca && v.familia === f.familia);
  const desde = versiones.length ? Math.min(...versiones.map((v) => v.valor_0km).filter(Boolean)) : null;
  const consumo = mediana(versiones.map((v) => v.consumo_l100km));
  const a5 = f.depreciacion?.find((p) => p[0] === 5)?.[2];
  const puesto = fichas.filter((x) => patentados(x) > patentados(f)).length + 1;
  const service = mediana((f.service || []).map((s) => s[2]));
  const datos = [
    a5 != null && ["Conserva a 5 años", `${Math.round(100 * a5)}%`, "del valor de un 0 km"],
    f.mercado && ["Patentados en 12 meses", numero(patentados(f)), `puesto ${puesto} del mercado`],
    consumo && ["Consumo", `${decimal(consumo)} l`, `cada 100 km (${versiones[0]?.combustible || "nafta"})`],
    service && ["Service típico", pesos(service), "en el concesionario oficial"],
  ].filter(Boolean);
  const color = colorDe(f.marca);
  const imagen = recorte(f.marca, f.familia, "hero-recorte") || foto(f.marca, f.familia, "hero-foto");
  const credito = datosFoto(f.marca, f.familia);
  const oficial = enlaceOficial(f.marca, f.familia);
  return [
    el("div", { class: "hero-fondo", style: `--marca:${color}`, "aria-hidden": "true" },
      el("span", { class: "hero-marca-agua", text: lindo(f.familia.replace(/\s*PICK\s*-?\s*UP\b/i, "")) })),
    el("div", { class: "hero-interior" },
      el("div", { class: "hero-texto" },
        el("p", { class: "hero-marca", text: lindo(f.marca) }),
        el("h1", { text: nombreFamilia(f.marca, f.familia).slice(f.marca.length + 1) }),
        desde ? el("p", { class: "hero-precio" }, "0 km desde ", el("strong", { text: millones(desde) })) : null,
        el("div", { class: "hero-acciones" },
          el("a", { class: "boton", href: "#versiones", text: "Ver versiones" }),
          oficial ? el("a", { class: "boton boton-vidrio", href: oficial.url, target: "_blank", rel: "noopener", text: oficial.texto }) : null)),
      el("div", { class: "hero-auto" }, imagen, el("div", { class: "hero-sombra", "aria-hidden": "true" }))),
    datos.length ? el("div", { class: "hero-datos" }, datos.map(([t, v, d]) =>
      el("div", { class: "hero-dato" }, el("span", { class: "hero-dato-titulo", text: t }),
        el("strong", { text: v }), el("span", { class: "hero-dato-detalle", text: d })))) : null,
    credito ? el("p", { class: "hero-credito" }, `Foto: ${credito.autor} · `, el("a", { href: credito.url_licencia, text: credito.licencia }),
      " · ", el("a", { href: credito.pagina, text: "Wikimedia Commons" }), recorte(f.marca, f.familia) ? " · fondo removido" : "") : null,
  ];
}

// Cada seccion de la ficha: una "ceja" con el nombre corto (el de la barra de
// secciones), el titulo y el contenido.
function bloque(id, ceja, titulo, bajada, ...contenido) {
  return el("section", { class: "bloque", id },
    el("p", { class: "ceja", text: ceja }), el("h2", { text: titulo }),
    bajada ? (typeof bajada === "string" ? el("p", { class: "bajada", text: bajada }) : bajada) : null, ...contenido);
}

function mostrar(f) {
  document.title = `${nombreFamilia(f.marca, f.familia)} · AutosAR`;
  $("hero").replaceChildren(...hero(f));
  $("subnav-nombre").textContent = nombreFamilia(f.marca, f.familia);
  history.replaceState(null, "", `?m=${encodeURIComponent(`${f.marca}|${f.familia}`)}`);
  const color = colorDe(f.marca);
  const bloques = [];

  const galeria = seccionGaleria(f.marca, f.familia);
  if (galeria.length) bloques.push(bloque("galeria", "Galería", "Por fuera y por dentro", null, ...galeria));

  const versiones = seccionVersiones(equipamiento[`${f.marca}|${f.familia}`],
    // Cada version con un auto de otro color, si hay; la primera distinta de la del hero.
    (i) => recorte(f.marca, f.familia, "", variantes(f.marca, f.familia) > 1 ? i + 1 : 0) || foto(f.marca, f.familia));
  if (versiones.length) bloques.push(bloque("versiones", "Versiones", "Qué suma cada versión", ...versiones.slice(1)));

  if (f.depreciacion) {
    const a5 = f.depreciacion.find((p) => p[0] === 5);
    const a10 = f.depreciacion.find((p) => p[0] === 10);
    bloques.push(bloque("valor", "Valor", "Cuánto valor conserva",
      "Proporción del valor de un 0 km que conserva un usado según la antigüedad: precio de mercado (guía de precios de usados) y valuación fiscal.",
      el("div", { class: "valor-grilla" },
        el("div", { class: "cifras" },
          a5?.[2] != null ? el("div", { class: "cifra-grande" }, el("strong", { text: `${Math.round(100 * a5[2])}%` }), el("span", { text: "a los 5 años" })) : null,
          a10?.[2] != null ? el("div", { class: "cifra-grande" }, el("strong", { text: `${Math.round(100 * a10[2])}%` }), el("span", { text: "a los 10 años" })) : null),
        el("div", { class: "tarjeta" }, grafico(f.depreciacion)))));
  }
  if (f.service) {
    bloques.push(bloque("service", "Service", "Service oficial", "Precio del service en la red oficial, por versión.",
      el("div", { class: "tarjeta tabla-scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", { text: "Versión" }), el("th", { class: "num", text: "Service típico" }),
          el("th", { class: "num", text: "Costo por km" }), el("th", { class: "num", text: "Plan hasta" }))),
        el("tbody", {}, f.service.map(([modelo, km, med, hasta]) => el("tr", {}, el("td", { text: modelo }),
          el("td", { class: "num", text: pesos(med) }), el("td", { class: "num", text: `$${decimal(km)}` }),
          el("td", { class: "num", text: `${numero(hasta)} km` }))))))));
  }
  if (f.repuestos) {
    bloques.push(bloque("repuestos", "Repuestos", "Repuestos de desgaste", "Precio mediano en la tienda relevada, original contra alternativo.",
      el("div", { class: "tarjeta tabla-scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", { text: "Pieza" }), el("th", { class: "num", text: "Original" }),
          el("th", { class: "num", text: "Alternativo" }), el("th", { class: "num", text: "Productos" }))),
        el("tbody", {}, f.repuestos.sort((a, b) => (PIEZAS[a[0]] || a[0]).localeCompare(PIEZAS[b[0]] || b[0], "es"))
          .map(([tipo, orig, alt, n]) => el("tr", {}, el("td", { text: PIEZAS[tipo] || tipo }),
            el("td", { class: "num", text: pesos(orig) }), el("td", { class: "num", text: pesos(alt) }), el("td", { class: "num", text: n }))))))));
  }
  if (f.mercado) {
    const transf = f.mercado.reduce((s, m) => s + (m[2] || 0), 0);
    bloques.push(bloque("mercado", "Mercado", "Cuántos se venden", "Últimos 12 meses en todo el país, según los registros del automotor.",
      el("div", { class: "valor-grilla" },
        el("div", { class: "cifras" },
          el("div", { class: "cifra-grande" }, el("strong", { text: numero(patentados(f)) }), el("span", { text: "0 km patentados" })),
          el("div", { class: "cifra-grande" }, el("strong", { text: numero(transf) }), el("span", { text: "usados transferidos" }))),
        el("div", { class: "tarjeta" }, barrasMercado(f.mercado, color)))));
  }

  $("subnav-enlaces").replaceChildren(...bloques.map((b) => el("a", { href: `#${b.id}`, text: b.querySelector(".ceja").textContent })));
  $("contenido").replaceChildren(...bloques);
  $("estado").textContent = bloques.length ? "" : "No hay datos para este modelo.";
  window.scrollTo({ top: 0 });
}

function sugerir() {
  const q = $("buscar").value.trim();
  const lista = $("sugerencias");
  lista.replaceChildren();
  if (q.length < 2) { lista.hidden = true; return; }
  const encontradas = fichas.filter((f) => coincide(`${f.marca} ${f.familia}`, q)).slice(0, 12);
  for (const f of encontradas) {
    lista.append(el("li", { role: "option", onclick: () => { $("buscar").value = ""; lista.hidden = true; mostrar(f); } },
      foto(f.marca, f.familia, "mini"), el("span", { text: nombreFamilia(f.marca, f.familia) })));
  }
  lista.hidden = encontradas.length === 0;
}

async function iniciar() {
  let datos, oficiales, costo;
  [datos, equipamiento, oficiales, costo] = await Promise.all([cargar("fichas.json"),
    cargar("equipamiento.json").then((e) => e.familias || {}).catch(() => ({})),
    cargar("oficiales.json").catch(() => ({})), cargar("costo.json").catch(() => null), cargarFotos()]);
  await cargarMedios(oficiales);
  versionesCosto = costo ? objetos(costo.columnas, costo.versiones) : [];
  fichas = datos.fichas;
  // Primero las que tienen mas datos y mas ventas.
  fichas.sort((a, b) => patentados(b) - patentados(a));
  $("buscar").addEventListener("input", sugerir);
  const pedida = new URLSearchParams(location.search).get("m");
  mostrar(fichas.find((f) => `${f.marca}|${f.familia}` === pedida) || fichas[0]);
}

iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
