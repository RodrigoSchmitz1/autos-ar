import { el, pie } from "./comun.js";
import { cargarFotos, foto, tieneRecorte } from "./autos.js";

function fila(marca, familia, vista, f, miniatura) {
  return el("tr", {},
    el("td", {}, el("div", { class: "celda-auto" }, miniatura, el("a", { href: f.pagina, text: `${marca} ${familia} (${vista})` }))),
    el("td", { text: f.autor }),
    el("td", {}, f.url_licencia ? el("a", { href: f.url_licencia, text: f.licencia }) : f.licencia));
}

async function iniciar() {
  const fotos = await cargarFotos();
  const claves = Object.keys(fotos).sort((a, b) => a.localeCompare(b, "es"));
  document.getElementById("creditos").append(
    el("thead", {}, el("tr", {}, el("th", { text: "Foto" }), el("th", { text: "Autor" }), el("th", { text: "Licencia" }))),
    el("tbody", {}, claves.flatMap((k) => {
      const [marca, familia] = k.split("|");
      const f = fotos[k];
      // La foto de exterior tambien se muestra recortada (sin fondo) en la ficha.
      const filas = [fila(marca, familia, tieneRecorte(marca, familia) ? "exterior; en la ficha, también con el fondo removido" : "exterior",
        f, foto(marca, familia, "mini"))];
      for (const g of f.galeria || []) {
        filas.push(fila(marca, familia, g.vista, g,
          el("img", { class: "foto-auto mini", src: `img/autos/${g.imagen}`, alt: "", loading: "lazy" })));
      }
      if (f.interior) {
        filas.push(fila(marca, familia, "interior", f.interior,
          el("img", { class: "foto-auto mini", src: `img/autos/${f.interior.imagen}`, alt: "", loading: "lazy" })));
      }
      return filas;
    })));
  document.getElementById("estado").textContent = claves.length ? "" : "No se pudieron cargar los créditos.";
}

iniciar();
pie();
