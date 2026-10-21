// Repuestos: precio de cada pieza por modelo (alternativo contra original), una
// pieza en todos los modelos, el gasto en repuestos de desgaste por mes y la
// comparacion de la misma pieza original contra alternativa. Datos:
// exportar/sitio.py -> datos/repuestos.json (de mart_repuestos y compania).

import { cargar, pesos, numero, el, coincide, pie, PIEZAS, fecha } from "./comun.js";
import { cargarFotos, foto, fotoAnio, generacion, datosFoto } from "./autos.js";
import { nombreFamilia } from "./respuesta.js";
import { navegacion } from "./nav.js";
import { textoAnios, sirve, sirveMotor, encaja, DEL_MOTOR, preciosDelAuto, motoresDe, textoMotor, claveMotor, leerMotor,
  gastoPorKm } from "./repuestos-anio.js";

const $ = (id) => document.getElementById(id);
const poner = (nodo, ...hijos) => nodo.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));
const KM_MES = 1250;
const ESTE_ANIO = new Date().getFullYear();
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
// El auto del usuario: anio (?a=) y motor (?mo=1.6n), para filtrar productos.
const textoAuto = (auto) => [auto.anio, textoMotor(auto.motor)].filter(Boolean).join(" ");

function elegir(f, { desplazar = false } = {}) {
  const p = new URLSearchParams(location.search);
  if (p.get("m") !== f.slug) { p.delete("a"); p.delete("p"); p.delete("mo"); }
  p.set("m", f.slug);
  // Anio del auto: el de la URL o, si es el mismo modelo, el de "Mi auto" (0 = 0 km).
  if (!p.has("a")) {
    let r = null;
    try { r = JSON.parse(localStorage.getItem("autosar-mi-auto-resumen")); } catch { /* sin almacenamiento */ }
    if (r && r.marca === f.marca && r.familia === f.familia && r.anio !== undefined) p.set("a", Number(r.anio) || ESTE_ANIO);
  }
  history.replaceState(null, "", `?${p}`);
  const auto = { anio: Number(p.get("a")) || null, motor: leerMotor(p.get("mo")) };
  $("buscar").value = "";
  $("sugerencias").classList.add("oculto");
  $("modelo").classList.remove("oculto");

  const cambiar = (clave) => (e) => {
    const q = new URLSearchParams(location.search);
    q.set(clave, e.target.value);
    history.replaceState(null, "", `?${q}`);
    elegir(f);
  };
  const selMotor = el("select", { onchange: cambiar("mo") }, el("option", { value: "", text: "Todos" }));
  const conFoto = datosFoto(f.marca, f.familia);
  const gen = generacion(f.marca, f.familia, auto.anio);
  poner($("modelo-cabeza"),
    el("div", { class: "foto" }, conFoto ? fotoAnio(f.marca, f.familia, auto.anio) : foto(f.marca, f.familia)),
    el("div", {}, el("h2", { text: nombreFamilia(f.marca, f.familia) }),
      el("p", { text: `${Object.keys(f.piezas).length} repuestos con precio relevado` }),
      gen ? el("p", { class: "gen", text: `Foto: modelo ${gen.desde}–${gen.hasta || "hoy"}` }) : null),
    el("div", { class: "tu-auto" },
      el("label", { class: "anio-auto" }, "Año",
        el("select", { onchange: cambiar("a") }, el("option", { value: "", text: "Todos" }),
          Array.from({ length: ESTE_ANIO - 1994 }, (_, i) => ESTE_ANIO - i)
            .map((y) => el("option", { value: y, text: y, selected: y === auto.anio ? "" : null })))),
      el("label", { class: "anio-auto oculto" }, "Motor", selMotor)));

  const ofertas = cargar(`repuestos/${f.slug}.json`).catch(() => ({}));
  dibujarPiezas(f, f.piezas, ofertas, auto);
  dibujarResumen(f, f.por_km, f.por_km_original);
  abrirPieza(desplazar);
  ofertas.then((o) => {
    if (new URLSearchParams(location.search).get("m") !== f.slug) return;
    // Los motores que nombran los productos de este modelo (y el elegido, aunque no aparezca).
    const motores = motoresDe(o);
    if (auto.motor && !motores.some((m) => claveMotor(m) === claveMotor(auto.motor))) motores.push(auto.motor);
    selMotor.append(...motores.map((m) => el("option", { value: claveMotor(m), text: textoMotor(m),
      selected: claveMotor(m) === claveMotor(auto.motor) ? "" : null })));
    selMotor.closest("label").classList.toggle("oculto", !motores.length);
    // Con anio o motor: precios y gasto recalculados sin los productos que, segun
    // el titulo, son para otro anio u otro motor (los que no dicen nada quedan).
    if (!auto.anio && !auto.motor) return;
    const ajuste = preciosDelAuto(f.piezas, o, auto);
    if (!ajuste.cambiadas.size) return;
    dibujarPiezas(f, ajuste.piezas, ofertas, auto, ajuste.cambiadas, ajuste.sinProductos);
    if (f.por_km) dibujarResumen(f, ...gastoPorKm(ajuste.piezas, datos.intervalos), auto);
    abrirPieza(false);
  });
}

function dibujarPiezas(f, valores, ofertas, auto, cambiadas = new Set(), sinProductos = new Set()) {
  const piezas = Object.entries(valores).sort((a, b) => orden(a[0]) - orden(b[0]));
  poner($("lista-piezas"), piezas.map(([tipo, [orig, alt, n, amin, amax, omin, omax]]) => {
    // Rango de precios de cada calidad (del mas barato al mas caro) y la mediana
    // marcada: un alternativo caro no queda escondido detras de un solo numero.
    const max = Math.max(amax || alt || 0, omax || orig || 0);
    const fila = (clase, nombre, x, desde = x, hasta = x) => el("div", { class: `par-fila ${clase}${x ? "" : " sd"}` },
      el("span", { text: nombre }),
      el("b", { text: !x ? "no relevado" : redondo(desde) === redondo(hasta) ? redondo(x) : `${redondo(desde)} a ${redondo(hasta)}` }),
      el("div", { class: "par-pista" }, x ? el("span", { style: `left:${desde / max * 100}%;width:${Math.max((hasta - desde) / max * 100, 1.5)}%` }) : null,
        x ? el("i", { style: `left:${x / max * 100}%`, title: `Mediana: ${redondo(x)}` }) : null));
    const veces = orig && alt && orig > alt ? orig / alt : null;
    return el("div", { class: "pieza" },
      el("h3", {}, PIEZAS[tipo] || tipo, el("small", { text: cadaCuanto(tipo) }),
        cambiadas.has(tipo) ? el("span", { class: `para-anio${sinProductos.has(tipo) ? " sin" : ""}`,
          // El motor solo filtra las piezas del motor: los frenos dicen solo el anio.
          text: sinProductos.has(tipo) ? `ninguno dice ser para un ${textoAuto(auto)}`
            : `para ${DEL_MOTOR.has(tipo) ? textoAuto(auto) : auto.anio}` }) : null),
      el("span", { class: "veces", text: veces ? `original ×${veces.toFixed(1).replace(".", ",")}` : "" }),
      el("div", { class: "par" }, fila("alt", "Alternativo", alt, amin ?? alt, amax ?? alt), fila("orig", "Original", orig, omin ?? orig, omax ?? orig)),
      detalleOfertas(tipo, f.piezas[tipo][2], ofertas, auto));
  }));
  $("nota-modelo").textContent = `Del más barato al más caro de cada calidad, en las tiendas relevadas (Repuestos Express y ARG Autopartes), ${fecha(datos.capturado)}; `
    + "la marca en la barra es la mediana, la que se usa para calcular el gasto. "
    + "Discos, campanas, amortiguadores y bujías, por unidad (los que se venden de a par se dividen); pastillas y kits, por juego."
    + (cambiadas.size ? ` "Para ${textoAuto(auto)}": sin los productos que, según el título, son para otro año`
      + (auto.motor ? " u otro motor (el motor cuenta en distribución, embrague, filtros, bujías y correas)" : "") + "." : "");
}

function dibujarResumen(f, porKm, porKmOriginal, auto = null) {
  const r = $("resumen-modelo");
  if (!porKm) {
    poner(r, el("h2", {}, "Gasto en repuestos"), el("p", { class: "sub", text: "Sin piezas de desgaste relevadas para este modelo." }),
      el("div", { class: "chips" }, el("a", { class: "boton", href: `mi-auto.html?m=${f.slug}` }, "Todo lo que cuesta mantenerlo")));
    return;
  }
  poner(r, el("h2", {}, auto ? `Con un ${textoAuto(auto)}, en repuestos de desgaste gastás` : "En repuestos de desgaste gastás"),
    el("div", { class: "cifra" }, el("sup", { text: "$" }), numero(Math.round(porKm * KM_MES / 100) * 100), el("small", { text: " / mes" })),
    el("p", { class: "sub" }, "Con originales: ", el("b", { text: `${redondo(porKmOriginal * KM_MES)} por mes` })),
    auto && Math.abs(porKm - f.por_km) * KM_MES >= 100
      ? el("p", { class: "sub" }, "Mezclando todos los años y motores: ", el("b", { text: `${redondo(f.por_km * KM_MES)} por mes` })) : null,
    el("p", { class: "nota", text: `Frenos, amortiguadores, distribución y embrague para ${numero(KM_MES)} km por mes, con los intervalos de cambio habituales. `
      + (f.propias < f.de ? `${f.de - f.propias} de las ${f.de} piezas no tienen precio de este modelo: van con el precio mediano de todos.` : "") }),
    el("div", { class: "chips" },
      el("a", { class: "boton", href: `mi-auto.html?m=${f.slug}` }, "Todo lo que cuesta mantenerlo"),
      el("a", { class: "boton secundario", href: `ficha.html?m=${encodeURIComponent(`${f.marca}|${f.familia}`)}` }, "Ficha del modelo")));
}

// ?p=<tipo>: abre los productos de esa pieza (enlace directo a una pieza).
function abrirPieza(desplazar) {
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
const PRIMEROS = 10;

function detalleOfertas(tipo, n, ofertas, auto) {
  const lista = el("div", { class: "ofertas" });
  const resumen = el("summary", { text: n > 1 ? `Ver los ${n} productos` : "Ver el producto" });
  const detalle = el("details", { class: "detalle-ofertas", "data-tipo": tipo }, resumen, lista);
  const filtra = Boolean(auto.anio || (auto.motor && DEL_MOTOR.has(tipo)));
  const oferta = (x) => {
    const [tienda, titulo, calidad, precio, unidades, url, desde, hasta, cils, diesel] = x;
    const s = encaja(x, tipo, auto), a = sirve(desde, hasta, auto.anio);
    const m = DEL_MOTOR.has(tipo) ? sirveMotor(cils, diesel, auto.motor) : null;
    const motor = [cils?.replaceAll("/", " / "), diesel === 1 ? "diésel" : diesel === 0 ? "nafta" : ""].filter(Boolean).join(" ");
    const sello = (texto, ok) => el("span", { class: `sello anio${ok === true ? " si" : ok === false ? " no" : ""}`, text: texto });
    return el("a", { class: `oferta${s === false ? " otro-anio" : ""}`, href: url, target: "_blank", rel: "noopener" },
      el("span", { class: "titulo", text: titulo }),
      el("b", { text: pesos(precio) }),
      el("small", {}, el("span", { class: calidad === "Original" ? "sello orig" : "sello", text: calidad }),
        desde || hasta ? sello(textoAnios(desde, hasta), a) : null,
        motor && DEL_MOTOR.has(tipo) ? sello(motor, m) : null,
        ` ${TIENDAS[tienda] || tienda}`, unidades > 1 ? ` · ${pesos(precio * unidades)} ${PARES[unidades] || `x${unidades}`}` : ""),
      el("span", { class: "flecha", "aria-hidden": "true", text: "↗" }));
  };
  // Con anio o motor elegidos: primero los que el titulo confirma que le sirven,
  // despues los que no dicen y al final (apagados) los de otro anio o motor;
  // cada grupo, del mas barato.
  ofertas.then((o) => {
    const productos = o[tipo] || [];
    if (!filtra || !productos.length) return;
    const k = productos.filter((x) => encaja(x, tipo, auto)).length;
    if (k) resumen.textContent += ` · ${k} para tu auto`;
  });
  detalle.addEventListener("toggle", async () => {
    if (!detalle.open || lista.childElementCount) return;
    const rango = (x) => ({ true: 0, null: 1, false: 2 })[encaja(x, tipo, auto)];
    const productos = [...((await ofertas)[tipo] || [])].sort((a, b) => rango(a) - rango(b));
    const resto = productos.slice(PRIMEROS);
    const mas = resto.length ? el("button", { type: "button", class: "chip mas-ofertas", text: `Ver ${resto.length} más`,
      onclick: () => mas.replaceWith(...resto.map(oferta)) }) : null;
    poner(lista, productos.slice(0, PRIMEROS).map(oferta), mas,
      el("p", { class: "nota", text: "Precio por unidad. " + (filtra
        ? `Primero los que, según el título, son para un ${textoAuto(auto)}; después los que no dicen; los de otro año o motor, al final y apagados.`
        : "Elegí el año y el motor de tu auto arriba para ver primero los que le sirven.") }));
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

// Escala de las barras: de la mitad del precio tipico (izquierda) al doble (derecha),
// en escala logaritmica para que "-50%" y "x2" midan lo mismo.
function rankingMarcas(tipo) {
  document.querySelectorAll("#chips-marcas .chip").forEach((c) => c.classList.toggle("on", c.dataset.tipo === tipo));
  const lado = (x) => Math.max(-1, Math.min(1, Math.log2(x)));
  const texto = (x) => Math.abs(x - 1) < 0.05 ? "igual" : x < 1 ? `−${Math.round((1 - x) * 100)}%`
    : x >= 2 ? `×${x.toFixed(1).replace(".", ",")}` : `+${Math.round((x - 1) * 100)}%`;
  poner($("marcas"),
    el("div", { class: "eje-titulos" }, el("span"), el("div", {}, el("span", { text: "más barata" }), el("span", { text: "típico" }), el("span", { text: "más cara" })), el("span")),
    datos.marcas[tipo].map(([marca, x, productos, familias]) => {
      const d = lado(x) * 50;
      const clase = Math.abs(x - 1) < 0.05 ? "igual" : x < 1 ? "barata" : "cara";
      return el("div", { class: `marca-fila ${clase}${marca === "Original" ? " orig" : ""}` },
        el("span", {}, marca, el("small", { text: `${productos} productos · ${familias} modelos` })),
        el("div", { class: "eje" }, el("span", { style: d < 0 ? `left:${50 + d}%;width:${-d}%` : `left:50%;width:${Math.max(d, 1)}%` })),
        el("b", { text: texto(x) }));
    }),
    el("p", { class: "nota", text: "Cada producto se divide por el precio mediano de los alternativos para ese modelo y pieza en la misma tienda; la marca muestra la mediana de esos cocientes. "
      + "\"Sin marca\": los que la tienda no identifica (importados). El precio no dice nada de la calidad." }));
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
  const conMarcas = ORDEN.filter((t) => datos.marcas?.[t]);
  poner($("chips-marcas"), conMarcas.map((t) => el("button", { type: "button", class: "chip", "data-tipo": t, onclick: () => rankingMarcas(t) }, PIEZAS[t] || t)));
  // Arranca por la pieza donde mas cambia el precio entre marcas (sin contar el original).
  const rango = (t) => { const x = datos.marcas[t].filter((m) => m[0] !== "Original").map((m) => m[1]); return Math.max(...x) / Math.min(...x); };
  if (conMarcas.length) rankingMarcas(conMarcas.reduce((a, b) => (rango(b) > rango(a) ? b : a)));
  comparables();
}

navegacion();
iniciar().catch((e) => {
  $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`;
  $("estado").classList.remove("oculto");
});
pie();
