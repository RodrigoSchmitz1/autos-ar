import { cargar, pesos, numero, millones, fecha, el, pie, slugModelo } from "./comun.js";
import { cargarFotos, foto, recorte, colorDe, datosFoto } from "./autos.js";
import { nombreFamilia } from "./respuesta.js";
import { navegacion } from "./nav.js";
import { barraApilada, leyendaCompacta } from "./graficos.js";

const $ = (id) => document.getElementById(id);
const poner = (nodo, ...hijos) => nodo.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));

// "HILUX PICK - UP" -> "Hilux": el sitio muestra el nombre corto de la familia.
function nombreCorto(familia) {
  return familia.replace(/\s*PICK\s*-?\s*UP\b/i, "").replace(/\b([A-Z])([A-Z]+)\b/g, (_, a, b) => a + b.toLowerCase()).trim();
}
const marcaLinda = (m) => m.charAt(0) + m.slice(1).toLowerCase();
const fichaUrl = (m, f) => `ficha.html?m=${encodeURIComponent(`${m}|${f}`)}`;
const slug = slugModelo;

function tarjeta(item, puesto, href, cuerpo) {
  return el("a", { class: "ficha-auto", href },
    // En chico, la foto entera (el auto recortado en miniatura parece pegado).
    el("div", { class: "estudio" }, datosFoto(item.marca, item.familia) ? foto(item.marca, item.familia) : recorte(item.marca, item.familia) || foto(item.marca, item.familia),
      el("span", { class: "puesto", text: puesto })),
    el("div", { class: "ficha-cuerpo" },
      el("div", { class: "marca-auto", text: marcaLinda(item.marca) }),
      el("div", { class: "nombre", text: nombreCorto(item.familia) }), cuerpo));
}

// Escena de la portada: los mas vendidos con recorte, de a uno, sobre un brillo del color de la marca.
function escena(vendidos) {
  const autos = vendidos.map((v, i) => ({ ...v, puesto: i + 1, img: recorte(v.marca, v.familia) })).filter((v) => v.img).slice(0, 6);
  const caja = $("escena");
  if (!autos.length) return;
  const nombre = el("a", { class: "escena-nombre" });
  caja.append(...autos.map((a) => a.img), nombre);
  let i = 0;
  const mostrar = () => {
    autos.forEach((a, k) => a.img.classList.toggle("activa", k === i));
    const a = autos[i];
    caja.style.setProperty("--marca", colorDe(a.marca));
    nombre.href = fichaUrl(a.marca, a.familia);
    poner(nombre, `N.º ${a.puesto} en ventas`, el("strong", { text: `${marcaLinda(a.marca)} ${nombreCorto(a.familia)}` }));
  };
  mostrar();
  if (autos.length > 1 && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setInterval(() => { i = (i + 1) % autos.length; mostrar(); }, 4500);
  }
}

// Si el usuario ya cargo su auto en "Mi auto", lo que le cuesta por mes.
function tuAuto() {
  let r = null;
  try { r = JSON.parse(localStorage.getItem("autosar-mi-auto-resumen")); } catch { /* sin almacenamiento */ }
  if (!r?.total) return;
  const t = $("tu-auto");
  t.href = r.url || "mi-auto.html";
  poner(t, el("div", {}, el("p", { text: "Tu auto" }), el("strong", { text: `${nombreFamilia(r.marca, r.familia)} ${r.anio || ""}` }),
    el("p", { text: r.version })),
  el("div", { class: "monto" }, pesos(Math.round(r.total / 100) * 100), el("small", { text: "por mes" })));
  t.classList.remove("oculto");
}

async function iniciar() {
  const [home, meta] = await Promise.all([cargar("home.json"), cargar("meta.json"), cargarFotos()]);
  escena(home.vendidos);
  tuAuto();

  // Los mas baratos de mantener: al tocar, ese auto en "Mi auto" (2021, Buenos Aires, 1.250 km por mes).
  const partes = [["combustible", "Combustible", "var(--combustible)"], ["patente", "Patente", "var(--patente)"],
    ["service", "Service", "var(--service)"], ["repuestos", "Repuestos", "var(--repuestos)"]];
  poner($("mantener"), home.mantener.map((v, i) => tarjeta(v, i + 1, `mi-auto.html?m=${slug(v.marca, v.familia)}&a=2021&p=06&km=1250`, [
    el("div", { class: "dato" }, pesos(Math.round(v.mensual / 100) * 100), el("small", { text: " / mes" })),
    (() => {
      const p = partes.map(([id, nombre, color]) => ({ nombre, color, valor: v[id] }));
      return el("div", { class: "gasto-mini" }, barraApilada(p, { clase: "chica" }), leyendaCompacta(p));
    })(),
  ])));

  $("b-vendidos").textContent = `Patentamientos de los últimos 12 meses en todo el país (hasta ${fecha(meta.periodos.mercado.slice(0, 7))}).`;
  const maxVendidos = home.vendidos[0].unidades;
  poner($("vendidos"), home.vendidos.map((v, i) => tarjeta(v, i + 1, fichaUrl(v.marca, v.familia), [
    el("div", { class: "dato" }, numero(v.unidades), el("small", { text: " patentados" })),
    el("div", { class: "medidor" }, el("span", { style: `width:${100 * v.unidades / maxVendidos}%;background:var(--acento)` })),
    el("div", { class: "detalle", text: v.precio_desde ? `Desde ${millones(v.precio_desde)}` : "" }),
  ])));

  poner($("conservan"), home.conservan.map((v, i) => tarjeta(v, i + 1, fichaUrl(v.marca, v.familia), [
    el("div", { class: "dato" }, `${Math.round(100 * v.conserva_5)}%`, el("small", { text: " del valor a 5 años" })),
    el("div", { class: "medidor" }, el("span", { style: `width:${100 * v.conserva_5}%;background:var(--service)` })),
    el("div", { class: "detalle", text: `${v.conserva_10 ? `${Math.round(100 * v.conserva_10)}% a los 10 · ` : ""}${numero(v.transferencias)} usados vendidos en el año` }),
  ])));

  $("b-combustible").textContent = `Precio promedio de la nafta súper por litro en ${fecha(meta.periodos.combustible.slice(0, 7))}, ponderado por lo que vende cada estación.`;
  const comb = home.combustible.filter((c) => c.nafta);
  const min = Math.min(...comb.map((c) => c.nafta)) * 0.85, max = Math.max(...comb.map((c) => c.nafta));
  poner($("combustible"), comb.map((c) => el("div", { class: "fila-n" },
    el("span", { text: c.provincia === "Ciudad Autónoma de Buenos Aires" ? "CABA" : c.provincia }),
    el("div", { class: "pista" }, el("span", { style: `width:${100 * (c.nafta - min) / (max - min)}%` })),
    el("span", { class: "valor", text: pesos(c.nafta) }))));
}

// Flechas de los carruseles (en la computadora no hay barra para deslizar).
document.querySelectorAll(".flechas").forEach((f) => f.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  const c = $(f.dataset.carrusel);
  if (b && c) c.scrollBy({ left: Number(b.dataset.dir) * c.clientWidth, behavior: "smooth" });
}));

navegacion();
iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
