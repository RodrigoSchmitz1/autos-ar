import { cargar, pesos, numero, millones, fecha, el, pie } from "./comun.js";
import { cargarFotos, foto, recorte, colorDe } from "./autos.js";

const $ = (id) => document.getElementById(id);

// "HILUX PICK - UP" -> "Hilux": el sitio muestra el nombre corto de la familia.
function nombreCorto(familia) {
  return familia.replace(/\s*PICK\s*-?\s*UP\b/i, "").replace(/\b([A-Z])([A-Z]+)\b/g, (_, a, b) => a + b.toLowerCase()).trim();
}
const marcaLinda = (m) => m.charAt(0) + m.slice(1).toLowerCase();

// El auto recortado sobre un fondo claro de estudio; sin recorte, la foto comun.
function fotoTarjeta(marca, familia) {
  const r = recorte(marca, familia);
  return r ? el("div", { class: "auto-estudio" }, r) : foto(marca, familia);
}

function tarjeta(item, puesto, cuerpo) {
  const t = el("a", { class: "auto-tarjeta", href: `ficha.html?m=${encodeURIComponent(`${item.marca}|${item.familia}`)}` },
    el("div", { class: "auto-foto" }, fotoTarjeta(item.marca, item.familia), el("div", { class: "puesto", text: puesto })),
    el("div", { class: "auto-cuerpo" },
      el("div", { class: "marca-auto", text: marcaLinda(item.marca) }),
      el("p", { class: "nombre", text: nombreCorto(item.familia) }), cuerpo));
  return t;
}

// Portada: los mas vendidos con recorte, uno por vez, grandes, con su nombre.
function portada(vendidos) {
  const autos = vendidos.map((v, i) => ({ ...v, puesto: i + 1, img: recorte(v.marca, v.familia, "portada-recorte") })).filter((v) => v.img).slice(0, 5);
  const caja = $("autos-portada");
  if (!autos.length) { caja.replaceChildren(...vendidos.slice(0, 4).map((v) => foto(v.marca, v.familia))); return; }
  const nombre = el("a", { class: "portada-nombre" });
  const brillo = el("div", { class: "portada-brillo" });
  caja.classList.add("portada-autos");
  caja.replaceChildren(brillo, ...autos.map((a) => a.img), el("div", { class: "hero-sombra" }), nombre);
  let i = 0;
  const mostrar = () => {
    autos.forEach((a, k) => a.img.classList.toggle("activa", k === i));
    const a = autos[i];
    brillo.style.setProperty("--marca", colorDe(a.marca));
    nombre.href = `ficha.html?m=${encodeURIComponent(`${a.marca}|${a.familia}`)}`;
    nombre.replaceChildren(el("span", { text: `N.º ${a.puesto} en ventas` }), el("strong", { text: `${marcaLinda(a.marca)} ${nombreCorto(a.familia)}` }));
  };
  mostrar();
  if (autos.length > 1 && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setInterval(() => { i = (i + 1) % autos.length; mostrar(); }, 4500);
  }
}

async function iniciar() {
  const [home, meta] = await Promise.all([cargar("home.json"), cargar("meta.json"), cargarFotos()]);

  portada(home.vendidos);

  $("b-vendidos").textContent = `Patentamientos de los últimos 12 meses en todo el país (hasta ${fecha(meta.periodos.mercado.slice(0, 7))}).`;
  const maxVendidos = home.vendidos[0].unidades;
  $("vendidos").replaceChildren(...home.vendidos.map((v, i) => tarjeta(v, i + 1, [
    el("div", { class: "cifra", text: `${numero(v.unidades)} 0 km` }),
    el("div", { class: "medidor" }, el("span", { style: `width:${100 * v.unidades / maxVendidos}%;background:var(--s-vendidos)` })),
    el("div", { class: "detalle", text: v.precio_desde ? `Desde ${millones(v.precio_desde)}` : "" }),
  ])));

  $("conservan").replaceChildren(...home.conservan.map((v, i) => tarjeta(v, i + 1, [
    el("div", { class: "cifra", text: `${Math.round(100 * v.conserva_5)}% del valor` }),
    el("div", { class: "medidor" }, el("span", { style: `width:${100 * v.conserva_5}%;background:var(--s-conservan)` })),
    el("div", { class: "detalle", text: `a los 5 años${v.conserva_10 ? ` · ${Math.round(100 * v.conserva_10)}% a los 10` : ""} · ${numero(v.transferencias)} usados vendidos en el año` }),
  ])));

  const maxMantener = Math.max(...home.mantener.map((v) => v.mensual));
  $("mantener").replaceChildren(...home.mantener.map((v, i) => {
    const partes = [["combustible", "--c-combustible"], ["service", "--c-service"], ["repuestos", "--c-repuestos"], ["patente", "--c-patente"]];
    return tarjeta(v, i + 1, [
      el("div", { class: "cifra", text: `${pesos(v.mensual)} por mes` }),
      el("div", { class: "barra", style: `width:${100 * v.mensual / maxMantener}%`, title: partes.map(([p]) => `${p}: ${pesos(v[p])}`).join("\n") },
        partes.map(([p, c]) => el("span", { style: `width:${100 * v[p] / v.mensual}%;background:var(${c})` }))),
      el("div", { class: "desglose" }, partes.map(([p, c]) => el("span", {}, el("i", { style: `background:var(${c})` }), p.charAt(0).toUpperCase() + p.slice(1), el("b", { text: pesos(v[p]) })))),
    ]);
  }));

  $("b-combustible").textContent = `Precio promedio de la nafta súper por litro en ${fecha(meta.periodos.combustible.slice(0, 7))}, ponderado por lo que vende cada estación.`;
  const comb = home.combustible.filter((c) => c.nafta);
  const min = Math.min(...comb.map((c) => c.nafta)) * 0.85, max = Math.max(...comb.map((c) => c.nafta));
  $("combustible").replaceChildren(...comb.map((c) => el("div", { class: "fila" },
    el("span", { text: c.provincia === "Ciudad Autónoma de Buenos Aires" ? "CABA" : c.provincia }),
    el("div", { class: "pista" }, el("span", { style: `width:${100 * (c.nafta - min) / (max - min)}%` })),
    el("span", { class: "valor", text: pesos(c.nafta) }))));
}

iniciar().catch((e) => { $("estado").textContent = `No se pudieron cargar los datos: ${e.message}`; });
pie();
