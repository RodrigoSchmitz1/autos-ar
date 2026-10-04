// Galeria de un modelo: fotos (exterior e interior, de Wikimedia Commons, con
// credito), video de YouTube y enlace a la pagina oficial (360 y configurador).
//
// El video no se carga hasta el clic: se muestra la miniatura y, al apretar,
// el reproductor de youtube-nocookie.com (el modo de YouTube que no deja
// cookies hasta que se reproduce). Asi la pagina sigue liviana.

import { el } from "./comun.js";
import { colorDe } from "./autos.js";

let medios = { fotos: {}, videos: {}, oficiales: {} };

export async function cargarMedios(oficiales) {
  const leer = (url) => fetch(url).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  const [fotos, videos] = await Promise.all([leer("img/autos/fotos.json"), leer("img/autos/videos.json")]);
  medios = { fotos, videos, oficiales: oficiales || {} };
}

function ampliar(src, alt, credito) {
  const fondo = el("div", { class: "lightbox", role: "dialog", "aria-label": alt },
    el("img", { src, alt }), el("p", { class: "lightbox-credito", text: credito }));
  const cerrar = () => { fondo.remove(); document.removeEventListener("keydown", tecla); };
  const tecla = (e) => { if (e.key === "Escape") cerrar(); };
  fondo.addEventListener("click", cerrar);
  document.addEventListener("keydown", tecla);
  document.body.append(fondo);
}

function miniFoto(f, vista, marca, familia) {
  const alt = `${marca} ${familia} (${vista})`.toLowerCase();
  const credito = `Foto: ${f.autor} · ${f.licencia} · Wikimedia Commons`;
  const b = el("button", { type: "button", class: "galeria-foto", title: credito, "aria-label": `Ampliar ${vista}` },
    el("img", { src: `img/autos/${f.imagen}`, alt, loading: "lazy", width: 480, height: 320 }),
    el("span", { class: "galeria-etiqueta", text: vista }));
  b.addEventListener("click", () => ampliar(`img/autos/${f.imagen}`, alt, credito));
  return b;
}

function video(v, marca) {
  const caja = el("div", { class: "galeria-video" });
  const portada = el("button", { type: "button", class: "video-portada", "aria-label": `Reproducir: ${v.titulo}`,
    style: `--color:${colorDe(marca)}` },
    el("img", { src: `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`, alt: "", loading: "lazy" }),
    el("span", { class: "video-play", text: "▶" }));
  portada.addEventListener("click", () => {
    portada.replaceWith(el("iframe", {
      src: `https://www.youtube-nocookie.com/embed/${v.id}?autoplay=1&rel=0`, title: v.titulo,
      allow: "accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen", allowfullscreen: "",
    }));
  });
  caja.append(portada, el("p", { class: "nota" }, el("strong", { text: v.titulo }), " · ",
    el("a", { href: v.url_canal, text: v.canal }), " (YouTube)"));
  return caja;
}

export function seccionGaleria(marca, familia) {
  const clave = `${marca}|${familia}`;
  const f = medios.fotos[clave], v = medios.videos[clave], o = medios.oficiales[clave];
  // El exterior ya esta grande en la cabecera de la ficha: aca va el interior.
  const fotos = f?.interior ? [miniFoto(f.interior, "interior", marca, familia)] : [];
  if (!fotos.length && !v && !o) return [];
  const marcaLinda = marca.charAt(0) + marca.slice(1).toLowerCase();
  const boton = o && el("a", { class: "boton-oficial", href: o.url, target: "_blank", rel: "noopener" },
    o.alcance === "modelo" ? "Ver en 360° y configurador en el sitio oficial ↗" : `Ver la gama en el sitio oficial de ${marcaLinda} ↗`);
  return [el("section", { class: "galeria" },
    v ? video(v, marca) : null,
    el("div", { class: "galeria-lateral" },
      fotos.length ? el("div", { class: "galeria-fotos" }, fotos) : null,
      boton,
      el("p", { class: "nota", text: "Las fotos, videos y vistas 360° de las marcas tienen derechos: el video se ve con el reproductor de YouTube y el 360°, en el sitio oficial." })))];
}
