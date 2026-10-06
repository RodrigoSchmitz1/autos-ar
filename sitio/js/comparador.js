// Comparador: hasta 4 autos lado a lado, como las paginas de "comparar
// modelos" de las marcas. Arriba los autos (con la version de cada uno); abajo,
// alineado en columnas: cuanto cuesta mantenerlo, cuanto valor pierde, cuanto
// llevas gastado anio a anio y el equipamiento.

import { calcular, componentes, proporcionConservada } from "./costo.js";
import { cargar, objetos, pesos, numero, millones, decimal, el, coincide, normalizar, pie } from "./comun.js";
import { cargarFotos, foto, recorte } from "./autos.js";
import { seccionEquipamiento } from "./equipamiento.js";
import { nombreFamilia } from "./respuesta.js";

const MAXIMO = 4;
const COLORES = ["#3a5bdc", "#ef476f", "#06a77d", "#fb8500"];
const SVG = "http://www.w3.org/2000/svg";
// Mantener: lo que se paga mientras se usa. La perdida de valor va aparte.
const PARTES = [
  ["combustible_anual", "Combustible", "--c-combustible"],
  ["service_anual", "Service oficial", "--c-service"],
  ["repuestos_anual", "Repuestos", "--c-repuestos"],
  ["patente_anual", "Patente", "--c-patente"],
  ["seguro_anual", "Seguro", "--c-seguro"],
];
const ESTIMACION = {
  familia_motor: "consumo de la familia y motor", familia: "consumo de la familia",
  cilindrada: "consumo estimado por cilindrada",
};

const $ = (id) => document.getElementById(id);
let datos, versiones, familias, equipamiento = {}, elegidas = [];

const clave = (v) => `${v.marca}|${v.familia}`;
const corto = (v) => nombreFamilia(v.marca, v.familia);
const marcaLinda = (m) => m.charAt(0) + m.slice(1).toLowerCase();
// La version sin el nombre de la familia adelante ("CRONOS DRIVE 1.3" -> "DRIVE 1.3").
const nombreVersion = (v) => v.modelo.replace(new RegExp(`^${v.familia.replace(/\s*PICK\s*-?\s*UP\b/i, "").trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*`, "i"), "") || v.modelo;

function svg(tag, atributos) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) e.setAttribute(k, v);
  return e;
}

function leerPerfil() {
  return {
    km_anio: Number($("km").value) || 15000,
    anios: Number($("anios").value) || 5,
    seguro_mensual: Number($("seguro").value) || 0,
    repuestos_originales: $("originales").checked,
  };
}

function avisos(v) {
  const t = [];
  if (v.consumo_estimacion && v.consumo_estimacion !== "version") t.push(ESTIMACION[v.consumo_estimacion] || "consumo estimado");
  if (v.service_fuente !== "familia") t.push("service: mediana general");
  if (v.repuestos_fuente !== "familia") t.push("repuestos: mediana general");
  if (v.depreciacion_fuente === "mediana_marca") t.push("valor: mediana de la marca");
  if (v.depreciacion_fuente === "mediana_general") t.push("valor: mediana general");
  return t.map((x) => el("span", { class: "chip aviso", text: x }));
}

// ---------- Los autos elegidos (arriba) ----------

function tarjetaAuto(v, i) {
  const fam = familias.get(clave(v));
  const elegir = el("select", { class: "comp-version", "aria-label": `Versión de ${corto(v)}` },
    fam.versiones.map((x) => el("option", { value: x.id, text: `${nombreVersion(x)}${x.valor_0km ? ` · ${millones(x.valor_0km)}` : ""}` })));
  elegir.value = v.id;
  elegir.addEventListener("change", () => { elegidas[i] = versiones.find((x) => x.id === elegir.value); dibujar(); });
  const imagen = recorte(v.marca, v.familia) || foto(v.marca, v.familia);
  return el("article", { class: "comp-auto", style: `--color:${COLORES[i]}` },
    el("button", { type: "button", class: "comp-quitar", "aria-label": `Quitar ${corto(v)}`, text: "×",
      onclick: () => { elegidas.splice(i, 1); dibujar(); } }),
    el("a", { class: "comp-auto-foto", href: `ficha.html?m=${encodeURIComponent(clave(v))}`, title: `Ficha del ${corto(v)}` }, imagen),
    el("p", { class: "comp-auto-marca", text: marcaLinda(v.marca) }),
    el("h2", { class: "comp-auto-nombre", text: corto(v).slice(v.marca.length + 1) }),
    el("p", { class: "comp-auto-precio" }, v.valor_0km ? ["0 km ", el("strong", { text: millones(v.valor_0km) })] : "sin precio de lista"),
    elegir);
}

function tarjetaAgregar() {
  const buscar = el("input", { type: "search", placeholder: "Buscar modelo…", "aria-label": "Agregar un modelo", autocomplete: "off" });
  const lista = el("ul", { class: "sugerencias", role: "listbox", hidden: true });
  buscar.addEventListener("input", () => {
    const q = buscar.value.trim();
    lista.replaceChildren();
    if (q.length < 2) { lista.hidden = true; return; }
    const ya = new Set(elegidas.map(clave));
    const encontradas = [...familias.values()].filter((f) => !ya.has(f.clave) &&
      (coincide(`${f.marca} ${f.familia}`, q) || f.versiones.some((x) => coincide(`${x.marca} ${x.modelo}`, q)))).slice(0, 8);
    for (const f of encontradas) {
      // Si lo buscado nombra una version ("cronos drive"), esa; si no, la mas vendida.
      const v = f.versiones.find((x) => coincide(`${x.marca} ${x.modelo}`, q) && normalizar(q).split(/\s+/).length > 1) || f.versiones[0];
      lista.append(el("li", { role: "option", onclick: () => { elegidas.push(v); dibujar(); } },
        foto(f.marca, f.familia, "mini"), el("span", { text: nombreFamilia(f.marca, f.familia) })));
    }
    lista.hidden = encontradas.length === 0;
  });
  return el("article", { class: "comp-auto comp-agregar" },
    el("div", { class: "comp-mas", "aria-hidden": "true", text: "+" }),
    el("p", { class: "comp-agregar-texto", text: elegidas.length ? "Agregá otro auto" : "Agregá un auto para empezar" }),
    el("div", { class: "comp-buscar" }, buscar, lista));
}

// ---------- Cuanto cuesta ----------

function columnas(n, ...hijos) {
  return el("div", { class: "comp-columnas", style: `--n:${n}` }, ...hijos);
}

function bloque(id, ceja, titulo, bajada, ...contenido) {
  return el("section", { class: "bloque", id },
    el("p", { class: "ceja", text: ceja }), el("h2", { text: titulo }),
    bajada ? el("p", { class: "bajada", text: bajada }) : null, ...contenido);
}

function seccionCosto(filas, perfil) {
  const completas = filas.filter((f) => f.k.completo);
  const n = filas.length;
  // El titular: cuanto mas cuesta mantener uno que otro.
  let titular = null;
  if (completas.length >= 2) {
    const orden = [...completas].sort((a, b) => a.mantener - b.mantener);
    const barato = orden[0], caro = orden[orden.length - 1];
    const dif = caro.mantener - barato.mantener;
    titular = el("div", { class: "comp-titular" },
      el("p", {}, "El más barato de mantener es el ", el("strong", { style: `color:${barato.color}`, text: corto(barato.v) }), ": ",
        el("strong", { text: pesos(dif) }), " por mes menos que el ", el("strong", { style: `color:${caro.color}`, text: corto(caro.v) }), "."),
      el("p", { class: "comp-titular-grande" }, el("span", { text: pesos(dif * 12 * perfil.anios) }),
        ` de diferencia en ${perfil.anios} ${perfil.anios === 1 ? "año" : "años"} con ${numero(perfil.km_anio)} km por año.`));
  }
  const maximo = Math.max(...completas.map((f) => f.k.mensual), 1);
  const menorMantener = Math.min(...completas.map((f) => f.mantener));
  const tarjetas = filas.map((f) => {
    if (!f.k.completo) {
      return el("div", { class: "comp-costo", style: `--color:${f.color}` },
        el("p", { class: "comp-costo-nombre", text: corto(f.v) }),
        el("p", { class: "estado", text: `Sin datos suficientes: falta ${f.k.faltantes.join(", ")}.` }));
    }
    const mejor = completas.length > 1 && f.mantener === menorMantener;
    return el("div", { class: `comp-costo${mejor ? " mejor" : ""}`, style: `--color:${f.color}` },
      mejor ? el("span", { class: "comp-medalla", text: "Más barato de mantener" }) : null,
      el("p", { class: "comp-costo-nombre", text: corto(f.v) }),
      el("p", { class: "comp-costo-mantener" }, el("strong", { text: pesos(f.mantener) }), el("span", { text: "por mes para mantenerlo" })),
      el("div", { class: "barra comp-barra", style: `width:${Math.max(25, 100 * f.k.mensual / maximo)}%` },
        PARTES.filter(([c]) => f.k[c] > 0).map(([c, n2, color]) => el("span", { title: `${n2}: ${pesos(f.k[c] / 12)} por mes`, style: `width:${100 * f.k[c] / f.k.anual}%;background:var(${color})` })),
        el("span", { title: `Pérdida de valor: ${pesos(f.k.depreciacion_anual / 12)} por mes`, class: "rayado", style: `width:${100 * f.k.depreciacion_anual / f.k.anual}%` })),
      el("p", { class: "comp-costo-detalle" }, "+ ", el("strong", { text: pesos(f.k.depreciacion_anual / 12) }), " por mes de pérdida de valor"),
      el("p", { class: "comp-costo-total" }, "Total ", el("strong", { text: pesos(f.k.mensual) }), ` /mes · ${pesos(f.k.por_km)} por km`),
      el("div", { class: "comp-avisos" }, avisos(f.v)));
  });
  const leyenda = el("div", { class: "leyenda" },
    PARTES.filter(([c]) => completas.some((f) => f.k[c] > 0)).map(([, n2, c]) => el("span", {}, el("i", { style: `background:var(${c})` }), n2)),
    el("span", {}, el("i", { class: "rayado" }), "Pérdida de valor"));

  // Componente por componente: el mas barato de cada fila resaltado; los demas, cuanto mas.
  const filasTabla = [...PARTES.filter(([c]) => completas.some((f) => f.k[c] > 0)),
    ["depreciacion_anual", "Pérdida de valor", "--c-depreciacion"], ["anual", "Total", null]];
  const tabla = el("table", { class: "comp-tabla" },
    el("thead", {}, el("tr", {}, el("th", { text: "" }),
      filas.map((f) => el("th", { class: "num", style: `--color:${f.color}` }, el("span", { class: "comp-tabla-auto", text: corto(f.v) }))))),
    el("tbody", {}, filasTabla.map(([c, nombre, color]) => {
      const vals = filas.map((f) => (f.k.completo ? f.k[c] / 12 : null));
      const conDato = vals.filter((x) => x !== null);
      const min = Math.min(...conDato);
      return el("tr", { class: c === "anual" ? "comp-fila-total" : "" },
        el("th", { scope: "row" }, color ? el("i", { class: "punto", style: `background:var(${color})` }) : null, nombre),
        vals.map((x) => el("td", { class: x !== null && conDato.length > 1 && x === min ? "num gana" : "num" },
          x === null ? "s/d" : el("strong", { text: pesos(x) }),
          x !== null && conDato.length > 1 && x > min ? el("span", { class: "comp-mas-caro", text: `+${pesos(x - min)}` }) : null)));
    })));

  return bloque("costo", "Costo", "Cuánto cuesta tenerlo, por mes",
    `Con ${numero(perfil.km_anio)} km por año durante ${perfil.anios} ${perfil.anios === 1 ? "año" : "años"} en ${$("provincia").selectedOptions[0]?.text || ""}. Cambialo en la barra de arriba.`,
    titular, columnas(n, ...tarjetas), leyenda,
    el("details", { class: "comp-detalle", open: true }, el("summary", { text: "Componente por componente (por mes)" }),
      el("div", { class: "tabla-scroll" }, el("div", { class: "comp-tabla-marco", style: `--n:${n}` }, tabla))));
}

// Lo que llevas gastado al anio t: mantenerlo t anios + lo que perdio de valor hasta ahi.
function acumulado(f, t) {
  const prop = proporcionConservada(f.v, t);
  return f.mantener * 12 * t + (prop === null ? 0 : f.v.valor_0km * (1 - prop));
}

function seccionAcumulado(filas, perfil) {
  const completas = filas.filter((f) => f.k.completo);
  if (completas.length < 1) return null;
  const hasta = Math.max(perfil.anios, 10);
  const anios = Array.from({ length: hasta }, (_, i) => i + 1);
  const ancho = 720, alto = 280, m = { i: 70, d: 150, s: 16, b: 30 };
  const max = Math.max(...completas.map((f) => acumulado(f, hasta)));
  const x = (t) => m.i + (t - 1) / Math.max(1, hasta - 1) * (ancho - m.i - m.d);
  const y = (p) => m.s + (1 - p / max) * (alto - m.s - m.b);
  const s = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: "100%", role: "img", "aria-label": "Gasto acumulado por año de cada auto" });
  for (const p of [0.25, 0.5, 0.75, 1]) {
    s.append(svg("line", { x1: m.i, x2: ancho - m.d, y1: y(max * p), y2: y(max * p), stroke: "var(--borde)" }));
    const t = svg("text", { x: m.i - 8, y: y(max * p) + 4, "text-anchor": "end" }); t.textContent = millones(max * p); s.append(t);
  }
  for (const a of anios) {
    if (hasta > 8 && a % 2 === 0 && a !== hasta) continue;
    const t = svg("text", { x: x(a), y: alto - 8, "text-anchor": "middle" }); t.textContent = a === 1 ? "1 año" : `${a}`; s.append(t);
  }
  s.append(svg("line", { x1: x(perfil.anios), x2: x(perfil.anios), y1: m.s, y2: alto - m.b, stroke: "var(--suave)", "stroke-dasharray": "4 4" }));
  // Etiquetas al final, separadas para que no se pisen.
  const finales = completas.map((f) => ({ f, y: y(acumulado(f, hasta)) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < finales.length; i++) finales[i].y = Math.max(finales[i].y, finales[i - 1].y + 18);
  for (const f of completas) {
    s.append(svg("polyline", { points: anios.map((a) => `${x(a)},${y(acumulado(f, a))}`).join(" "), fill: "none", stroke: f.color, "stroke-width": 3.5, "stroke-linejoin": "round" }));
    const fin = finales.find((e) => e.f === f);
    s.append(svg("circle", { cx: x(hasta), cy: y(acumulado(f, hasta)), r: 4.5, fill: f.color }));
    const t = svg("text", { x: x(hasta) + 10, y: fin.y + 4, fill: f.color, "font-weight": 700, "font-size": 12 });
    t.textContent = `${corto(f.v).split(" ").slice(1).join(" ")} ${millones(acumulado(f, hasta))}`;
    s.append(t);
  }
  return bloque("acumulado", "En el tiempo", "Cuánto llevás gastado, año a año",
    "Lo que pagaste para mantenerlo más lo que perdió de valor hasta ese año. La línea punteada marca los años que elegiste.",
    el("div", { class: "tarjeta" }, s));
}

// ---------- Todo ----------

function dibujar() {
  const n = elegidas.length;
  $("autos").style.setProperty("--n", Math.min(MAXIMO, n + (n < MAXIMO ? 1 : 0)));
  $("autos").replaceChildren(...elegidas.map(tarjetaAuto), ...(n < MAXIMO ? [tarjetaAgregar()] : []));
  guardarEnUrl();
  if (!n) { $("contenido").replaceChildren(); $("estado").textContent = ""; return; }
  $("estado").textContent = "";
  const perfil = leerPerfil();
  const provincia = $("provincia").value;
  const filas = elegidas.map((v, i) => {
    const k = calcular(componentes(v, provincia, datos.precio_litro), perfil);
    return { v, k, color: COLORES[i], mantener: (k.anual - k.depreciacion_anual) / 12 };
  });
  const eq = seccionEquipamiento(elegidas, equipamiento, COLORES);
  $("contenido").replaceChildren(...[
    seccionCosto(filas, perfil),
    seccionAcumulado(filas, perfil),
    eq.length ? bloque("equipamiento", "Equipamiento", "Qué trae cada uno", null, ...eq) : null].filter(Boolean));
}

function guardarEnUrl() {
  const p = new URLSearchParams({ prov: $("provincia").value, km: $("km").value, anios: $("anios").value,
    seguro: $("seguro").value, v: elegidas.map((v) => v.id).join(",") });
  if ($("originales").checked) p.set("orig", "1");
  history.replaceState(null, "", `?${p}`);
}

async function iniciar() {
  let eq;
  [datos, eq] = await Promise.all([cargar("costo.json"), cargar("equipamiento.json").catch(() => ({})), cargarFotos()]);
  equipamiento = eq;
  versiones = objetos(datos.columnas, datos.versiones);
  // Familias, con sus versiones de la mas vendida a la menos.
  familias = new Map();
  for (const v of versiones) {
    if (!familias.has(clave(v))) familias.set(clave(v), { clave: clave(v), marca: v.marca, familia: v.familia, versiones: [], ventas: 0 });
    const f = familias.get(clave(v));
    f.versiones.push(v);
    f.ventas += v.inscripciones_12m || 0;
  }
  for (const f of familias.values()) f.versiones.sort((a, b) => (b.inscripciones_12m || 0) - (a.inscripciones_12m || 0));
  familias = new Map([...familias].sort((a, b) => b[1].ventas - a[1].ventas));

  const sel = $("provincia");
  for (const [id, nombre] of Object.entries(datos.provincias).sort((a, b) => a[1].localeCompare(b[1], "es"))) {
    sel.append(el("option", { value: id, text: nombre === "Ciudad Autónoma de Buenos Aires" ? "CABA" : nombre }));
  }
  const p = new URLSearchParams(location.search);
  sel.value = p.get("prov") || "06";
  for (const campo of ["km", "anios", "seguro"]) if (p.get(campo)) $(campo).value = p.get(campo);
  $("originales").checked = p.get("orig") === "1";
  const ids = (p.get("v") || "").split(",").filter(Boolean);
  // Sin elegidas: los tres mas vendidos que tienen todos los datos.
  elegidas = ids.length ? ids.map((id) => versiones.find((v) => v.id === id)).filter(Boolean)
    : [...familias.values()].map((f) => f.versiones.find((v) => calcular(componentes(v, "06", datos.precio_litro)).completo))
      .filter(Boolean).slice(0, 3);
  for (const id of ["provincia", "km", "anios", "seguro", "originales"]) $(id).addEventListener("input", dibujar);
  dibujar();
}

iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
