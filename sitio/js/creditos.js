import { el, pie } from "./comun.js";
import { cargarFotos, foto } from "./autos.js";

async function iniciar() {
  const fotos = await cargarFotos();
  const claves = Object.keys(fotos).sort((a, b) => a.localeCompare(b, "es"));
  document.getElementById("creditos").append(
    el("thead", {}, el("tr", {}, el("th", { text: "Modelo" }), el("th", { text: "Autor" }), el("th", { text: "Licencia" }))),
    el("tbody", {}, claves.map((k) => {
      const [marca, familia] = k.split("|");
      const f = fotos[k];
      return el("tr", {},
        el("td", {}, el("div", { class: "celda-auto" }, foto(marca, familia, "mini"), el("a", { href: f.pagina, text: `${marca} ${familia}` }))),
        el("td", { text: f.autor }),
        el("td", {}, f.url_licencia ? el("a", { href: f.url_licencia, text: f.licencia }) : f.licencia));
    })));
  document.getElementById("estado").textContent = claves.length ? "" : "No se pudieron cargar los créditos.";
}

iniciar();
pie();
