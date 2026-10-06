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

const credito = (f) => `Foto: ${f.autor} · ${f.licencia} · Wikimedia Commons`;

// Pantalla completa con flechas (y teclado: izquierda, derecha, Escape).
function ampliar(fotos, inicial, alt) {
  let i = inicial;
  const img = el("img", { alt });
  const pie = el("p", { class: "lightbox-credito" });
  const mostrarFoto = () => { img.src = `img/autos/${fotos[i].imagen}`; pie.textContent = `${credito(fotos[i])} · ${i + 1} / ${fotos.length}`; };
  const mover = (d) => { i = (i + d + fotos.length) % fotos.length; mostrarFoto(); };
  const flecha = (d, t) => el("button", { type: "button", class: `lightbox-flecha ${d < 0 ? "izq" : "der"}`, "aria-label": d < 0 ? "Anterior" : "Siguiente", text: t,
    onclick: (e) => { e.stopPropagation(); mover(d); } });
  const fondo = el("div", { class: "lightbox", role: "dialog", "aria-label": alt }, img, pie,
    fotos.length > 1 ? flecha(-1, "‹") : null, fotos.length > 1 ? flecha(1, "›") : null);
  const cerrar = () => { fondo.remove(); document.removeEventListener("keydown", tecla); };
  const tecla = (e) => { if (e.key === "Escape") cerrar(); else if (e.key === "ArrowLeft") mover(-1); else if (e.key === "ArrowRight") mover(1); };
  fondo.addEventListener("click", cerrar);
  img.addEventListener("click", (e) => { e.stopPropagation(); mover(1); });
  document.addEventListener("keydown", tecla);
  mostrarFoto();
  document.body.append(fondo);
}

// Visor de fotos: una grande con flechas y la tira de miniaturas abajo.
function visor(fotos, marca, familia) {
  const alt = `${marca} ${familia}`.toLowerCase();
  let actual = 0;
  const grande = el("img", { alt, width: 960, height: 640 });
  const contador = el("span", { class: "visor-contador" });
  const pie = el("span", { class: "visor-credito" });
  const miniaturas = fotos.map((f, n) => el("button", { type: "button", class: "tira-foto", "aria-label": `Ver la foto ${n + 1}`, onclick: () => ir(n) },
    el("img", { src: `img/autos/${f.imagen}`, alt: "", loading: "lazy" })));
  function ir(n) {
    actual = (n + fotos.length) % fotos.length;
    const f = fotos[actual];
    grande.src = `img/autos/${f.imagen}`;
    grande.alt = `${alt} (${f.vista})`;
    contador.textContent = `${actual + 1} / ${fotos.length}`;
    pie.textContent = credito(f);
    miniaturas.forEach((m, k) => m.classList.toggle("activa", k === actual));
  }
  const flecha = (d, t) => el("button", { type: "button", class: `visor-flecha ${d < 0 ? "izq" : "der"}`, "aria-label": d < 0 ? "Foto anterior" : "Foto siguiente", text: t,
    onclick: (e) => { e.stopPropagation(); ir(actual + d); } });
  const marco = el("div", { class: "visor-marco", title: "Ampliar", onclick: () => ampliar(fotos, actual, alt) },
    grande, contador, fotos.length > 1 ? flecha(-1, "‹") : null, fotos.length > 1 ? flecha(1, "›") : null);
  ir(0);
  return el("div", { class: "visor" }, marco, pie, fotos.length > 1 ? el("div", { class: "tira" }, miniaturas) : null);
}

function video(v, marca) {
  const caja = el("div", { class: "mosaico-pieza galeria-video" });
  const portada = el("button", { type: "button", class: "video-portada", "aria-label": `Reproducir: ${v.titulo}`,
    style: `--color:${colorDe(marca)}` },
    el("img", { src: `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`, alt: "", loading: "lazy" }),
    el("span", { class: "video-play", text: "▶" }),
    el("span", { class: "video-titulo" }, el("strong", { text: v.titulo }), el("span", { text: `${v.canal} · YouTube` })));
  portada.addEventListener("click", () => {
    portada.replaceWith(el("iframe", {
      src: `https://www.youtube-nocookie.com/embed/${v.id}?autoplay=1&rel=0`, title: v.titulo,
      allow: "accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen", allowfullscreen: "",
    }));
  });
  caja.append(portada);
  return caja;
}

// El enlace al sitio oficial del modelo (360 y configurador) o, si no hay
// pagina del modelo, a la gama de la marca.
export function enlaceOficial(marca, familia) {
  const o = medios.oficiales[`${marca}|${familia}`];
  if (!o) return null;
  const marcaLinda = marca.charAt(0) + marca.slice(1).toLowerCase();
  return { url: o.url, modelo: o.alcance === "modelo",
    texto: o.alcance === "modelo" ? "360° en el sitio oficial ↗" : `Gama en el sitio de ${marcaLinda} ↗` };
}

export function seccionGaleria(marca, familia) {
  const clave = `${marca}|${familia}`;
  const f = medios.fotos[clave], v = medios.videos[clave];
  const o = enlaceOficial(marca, familia);
  if (!f && !v && !o) return [];
  const dominio = o ? new URL(o.url).hostname.replace(/^www\./, "") : "";
  const tarjetaOficial = o && el("a", { class: "mosaico-pieza mosaico-oficial", href: o.url, target: "_blank", rel: "noopener",
      style: `--marca:${colorDe(marca)}` },
    el("span", { class: "oficial-icono", text: o.modelo ? "360°" : "↗", "aria-hidden": "true" }),
    el("strong", { text: o.modelo ? "Vista 360°, colores y configurador" : "La gama en el sitio de la marca" }),
    el("span", { text: `en ${dominio} ↗` }));
  // Las fotos de la galeria (en alta) y el interior; sin galeria, la foto de exterior.
  // Sin repetir: el interior de fotos_interior.csv puede estar tambien en la galeria.
  const fotos = [
    ...(f?.galeria?.length ? f.galeria : f ? [{ ...f, vista: "exterior" }] : []),
    ...(f?.interior && !f.galeria?.some((g) => g.archivo === f.interior.archivo) ? [{ ...f.interior, vista: "interior" }] : []),
  ];
  return [
    el("div", { class: "galeria-grilla" },
      fotos.length ? visor(fotos, marca, familia) : null,
      el("div", { class: "galeria-costado" }, v ? video(v, marca) : null, tarjetaOficial)),
    el("p", { class: "nota", text: "Fotos de Wikimedia Commons con licencia libre. Los videos, fotos y vistas 360° de las marcas tienen derechos: el video se ve con el reproductor de YouTube y el 360°, en el sitio oficial." }),
  ];
}
