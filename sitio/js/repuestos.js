// Repuestos: precio de cada pieza por modelo (alternativo contra original), una
// pieza en todos los modelos, el gasto en repuestos de desgaste por mes y la
// comparacion de la misma pieza original contra alternativa. Datos:
// exportar/sitio.py -> datos/repuestos.json (de mart_repuestos y compania).

import { cargar, pesos, numero, el, coincide, pie, PIEZAS, fecha } from "./comun.js";
import { cargarFotos, foto, fotoGaleria, datosFoto } from "./autos.js";
import { nombreFamilia } from "./respuesta.js";
import { navegacion } from "./nav.js";

const $ = (id) => document.getElementById(id);
const poner = (nodo, ...hijos) => nodo.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));
const KM_MES = 1250;
const MIN_TRAMITES = 1000;
// Orden en que se muestran las piezas: las de desgaste (con intervalo) primero.
const ORDEN = ["pastillas_freno", "disco_freno", "campana_freno", "amortiguador_delantero", "amortiguador_trasero", "amortiguador",
  "kit_distribucion", "correa_distribucion", "tensor_distribucion", "kit_embrague", "correa_accesorios",
  "filtro_aceite", "filtro_aire", "filtro_combustible", "filtro_habitaculo", "kit_filtros", "kit_service",
  "bujia_encendido", "bujia_precalentamiento"];
const orden = (t) => (ORDEN.indexOf(t) + 1 || 99);
const redondo = (x) => pesos(Math.round(x / 100) * 100);

let datos, familias;

function cadaCuanto(tipo) {
  const i = datos.intervalos[tipo];
  if (i) return `cada ${numero(i.km)} km${i.unidades > 1 ? ` · ${i.unidades} unidades` : ""}`;
  if (tipo.startsWith("filtro") || tipo === "kit_filtros" || tipo === "kit_service" || tipo.startsWith("bujia")) return "va en el service";
  return "";
}

// ---------- Modelo elegido ----------
function elegir(f, { desplazar = false } = {}) {
  const p = new URLSearchParams(location.search);
  p.set("m", f.slug);
  history.replaceState(null, "", `?${p}`);
  $("buscar").value = "";
  $("sugerencias").classList.add("oculto");
  $("modelo").classList.remove("oculto");

  const conFoto = datosFoto(f.marca, f.familia);
  poner($("modelo-cabeza"),
    el("div", { class: "foto" }, conFoto ? fotoGaleria(f.marca, f.familia, 0) : foto(f.marca, f.familia)),
    el("div", {}, el("h2", { text: nombreFamilia(f.marca, f.familia) }),
      el("p", { text: `${Object.keys(f.piezas).length} repuestos con precio relevado` })));

  const piezas = Object.entries(f.piezas).sort((a, b) => orden(a[0]) - orden(b[0]));
  const ofertas = cargar(`repuestos/${f.slug}.json`).catch(() => ({}));
  poner($("lista-piezas"), piezas.map(([tipo, [orig, alt, n]]) => {
    const max = Math.max(orig || 0, alt || 0);
    const fila = (clase, nombre, x) => el("div", { class: `par-fila ${clase}${x ? "" : " sd"}` },
      el("span", { text: nombre }), el("div", { class: "par-pista" }, el("span", { style: `width:${x ? x / max * 100 : 0}%` })),
      el("b", { text: x ? redondo(x) : "no relevado" }));
    const veces = orig && alt && orig > alt ? orig / alt : null;
    return el("div", { class: "pieza" },
      el("h3", {}, PIEZAS[tipo] || tipo, el("small", { text: cadaCuanto(tipo) })),
      el("span", { class: "veces", text: veces ? `original ×${veces.toFixed(1).replace(".", ",")}` : "" }),
      el("div", { class: "par" }, fila("alt", "Alternativo", alt), fila("orig", "Original", orig)),
      detalleOfertas(tipo, n, ofertas));
  }));
  $("nota-modelo").textContent = `Precio mediano por pieza en las tiendas relevadas (Repuestos Express y ARG Autopartes), ${fecha(datos.capturado)}. `
    + "Discos, campanas, amortiguadores y bujías, por unidad (los que se venden de a par se dividen); pastillas y kits, por juego.";

  const r = $("resumen-modelo");
  if (f.por_km) {
    poner(r, el("h2", {}, "En repuestos de desgaste gastás"),
      el("div", { class: "cifra" }, el("sup", { text: "$" }), numero(Math.round(f.por_km * KM_MES / 100) * 100), el("small", { text: " / mes" })),
      el("p", { class: "sub" }, "Con originales: ", el("b", { text: `${redondo(f.por_km_original * KM_MES)} por mes` })),
      el("p", { class: "nota", text: `Frenos, amortiguadores, distribución y embrague para ${numero(KM_MES)} km por mes, con los intervalos de cambio habituales. `
        + (f.propias < f.de ? `${f.de - f.propias} de las ${f.de} piezas no tienen precio de este modelo: van con el precio mediano de todos.` : "") }),
      el("div", { class: "chips" },
        el("a", { class: "boton", href: `mi-auto.html?m=${f.slug}` }, "Todo lo que cuesta mantenerlo"),
        el("a", { class: "boton secundario", href: `ficha.html?m=${encodeURIComponent(`${f.marca}|${f.familia}`)}` }, "Ficha del modelo")));
  } else {
    poner(r, el("h2", {}, "Gasto en repuestos"), el("p", { class: "sub", text: "Sin piezas de desgaste relevadas para este modelo." }),
      el("div", { class: "chips" }, el("a", { class: "boton", href: `mi-auto.html?m=${f.slug}` }, "Todo lo que cuesta mantenerlo")));
  }
  // ?p=<tipo>: abre los productos de esa pieza (enlace directo a una pieza).
  const abrir = new URLSearchParams(location.search).get("p");
  const pieza = abrir && $("lista-piezas").querySelector(`.detalle-ofertas[data-tipo="${CSS.escape(abrir)}"]`);
  if (pieza) {
    pieza.open = true;
    pieza.closest(".pieza").scrollIntoView({ block: "start" });
  } else if (desplazar) $("modelo").scrollIntoView({ behavior: "smooth", block: "start" });
}

// Los productos de una pieza (datos/repuestos/<slug>.json): se dibujan al abrir.
const TIENDAS = { rex: "Repuestos Express", arg: "ARG Autopartes" };
const PARES = { 2: "el par", 4: "el juego de 4" };

function detalleOfertas(tipo, n, ofertas) {
  const lista = el("div", { class: "ofertas" });
  const detalle = el("details", { class: "detalle-ofertas", "data-tipo": tipo },
    el("summary", { text: n > 1 ? `Ver los ${n} productos` : "Ver el producto" }), lista);
  detalle.addEventListener("toggle", async () => {
    if (!detalle.open || lista.childElementCount) return;
    const productos = (await ofertas)[tipo] || [];
    poner(lista, productos.map(([tienda, titulo, calidad, precio, unidades, url]) =>
      el("a", { class: "oferta", href: url, target: "_blank", rel: "noopener" },
        el("span", { class: "titulo", text: titulo }),
        el("b", { text: pesos(precio) }),
        el("small", {}, el("span", { class: calidad === "Original" ? "sello orig" : "sello", text: calidad }),
          ` ${TIENDAS[tienda] || tienda}`, unidades > 1 ? ` · ${pesos(precio * unidades)} ${PARES[unidades] || `x${unidades}`}` : ""),
        el("span", { class: "flecha", "aria-hidden": "true", text: "↗" }))),
      productos.length < n ? el("p", { class: "nota", text: `Los ${productos.length} más baratos de cada calidad, precio por unidad.` }) : null);
  });
  return detalle;
}

// ---------- Buscador ----------
function conectarBuscador() {
  const caja = $("sugerencias");
  let activa = -1, lista = [];
  const dibujar = () => {
    const q = $("buscar").value.trim();
    lista = q ? familias.filter((f) => coincide(`${f.marca} ${f.familia}`, q)).slice(0, 10) : [];
    activa = lista.length ? 0 : -1;
    caja.classList.toggle("oculto", !lista.length);
    poner(caja, lista.map((f, i) => el("li", { role: "option", class: i === activa ? "activa" : "", onclick: () => elegir(f, { desplazar: true }) },
      nombreFamilia(f.marca, f.familia), el("small", { text: `${Object.keys(f.piezas).length} piezas` }))));
  };
  $("buscar").addEventListener("input", dibujar);
  $("buscar").addEventListener("keydown", (e) => {
    if (!lista.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      activa = (activa + (e.key === "ArrowDown" ? 1 : -1) + lista.length) % lista.length;
      [...caja.children].forEach((li, i) => li.classList.toggle("activa", i === activa));
    } else if (e.key === "Enter" && activa >= 0) {
      elegir(lista[activa], { desplazar: true });
    } else if (e.key === "Escape") {
      caja.classList.add("oculto");
    }
  });
}

// ---------- Rankings ----------
function filaRanking(f, i, valor, max, color) {
  return el("a", { class: "ranking-fila", href: `?m=${f.slug}`, onclick: (e) => { e.preventDefault(); elegir(f, { desplazar: true }); } },
    el("span", { class: "n", text: i + 1 }), el("span", { text: nombreFamilia(f.marca, f.familia) }), el("b", { text: redondo(valor) }),
    el("div", { class: "pista" }, el("span", { style: `width:${valor / max * 100}%;background:${color}` })));
}

function dosListas(destino, filas, titulos) {
  const max = Math.max(...filas.map((x) => x.valor));
  const baratos = filas.slice(0, 10), caros = filas.slice(-10).reverse();
  poner(destino,
    el("div", { class: "tarjeta" }, el("h3", { text: titulos[0] }), baratos.map((x, i) => filaRanking(x.f, i, x.valor, max, "var(--service)"))),
    el("div", { class: "tarjeta" }, el("h3", { text: titulos[1] }), caros.map((x, i) => filaRanking(x.f, i, x.valor, max, "var(--repuestos)"))));
}

function rankingPieza(tipo) {
  document.querySelectorAll("#chips-piezas .chip").forEach((c) => c.classList.toggle("on", c.dataset.tipo === tipo));
  // Solo el alternativo: mezclar con originales (de los modelos que no tienen
  // alternativo) pondria arriba piezas que no son comparables.
  const filas = familias.filter((f) => f.tramites >= MIN_TRAMITES && f.piezas[tipo]?.[1])
    .map((f) => ({ f, valor: f.piezas[tipo][1] })).sort((a, b) => a.valor - b.valor);
  dosListas($("ranking-pieza"), filas, [`${PIEZAS[tipo]}: las más baratas`, `${PIEZAS[tipo]}: las más caras`]);
}

function rankingKm() {
  const filas = familias.filter((f) => f.por_km && f.tramites >= MIN_TRAMITES && f.propias >= Math.ceil(f.de * 0.66))
    .map((f) => ({ f, valor: f.por_km * KM_MES })).sort((a, b) => a.valor - b.valor);
  dosListas($("ranking-km"), filas, ["Los que menos gastan, por mes", "Los que más gastan, por mes"]);
}

function comparables() {
  const c = datos.comparables;
  $("b-comparables").textContent = `En ${c.piezas} repuestos Repuestos Express vende la misma pieza (mismo código) en calidad original y alternativa: así se puede comparar el precio sin mezclar piezas distintas.`;
  poner($("comparables-cifra"), el("h2", {}, "La original cuesta, en la mitad de los casos, más de"),
    el("div", { class: "destacado-cifra" }, `${String(c.veces_mediana.toFixed(1)).replace(".", ",")} veces`, el("small", { text: " la alternativa" })),
    el("p", { class: "nota", text: "Alternativa: la más barata de otras marcas (Mahle, Bosch, importado...). No siempre es la misma calidad; para piezas de seguridad, como frenos, conviene una marca reconocida." }));
  poner($("comparables-ejemplos"), el("h3", { text: "Las diferencias más grandes" }),
    c.ejemplos.slice(0, 7).map((x) => el("div", { class: "ejemplo" },
      el("span", { text: x.titulo }), el("b", { text: `×${String(x.veces.toFixed(1)).replace(".", ",")}` }),
      el("small", { text: `Original ${pesos(x.original)} · ${x.calidad} ${pesos(x.alternativo)}` }))));
}

async function iniciar() {
  [datos] = await Promise.all([cargar("repuestos.json"), cargarFotos()]);
  familias = datos.familias.sort((a, b) => (b.tramites || 0) - (a.tramites || 0));
  conectarBuscador();

  // Modelo inicial: el de la URL, el de "Mi auto" o el mas tramitado.
  const slug = new URLSearchParams(location.search).get("m");
  let r = null;
  try { r = JSON.parse(localStorage.getItem("autosar-mi-auto-resumen")); } catch { /* sin almacenamiento */ }
  const inicial = familias.find((f) => f.slug === slug)
    || (r && familias.find((f) => f.marca === r.marca && f.familia === r.familia)) || familias[0];
  elegir(inicial);

  const tipos = ORDEN.filter((t) => datos.piezas.some((p) => p.tipo === t && p.modelos >= 30));
  poner($("chips-piezas"), tipos.map((t) => el("button", { type: "button", class: "chip", "data-tipo": t, onclick: () => rankingPieza(t) }, PIEZAS[t] || t)));
  rankingPieza(tipos[0]);
  rankingKm();
  comparables();
}

navegacion();
iniciar().catch((e) => {
  $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`;
  $("estado").classList.remove("oculto");
});
pie();
