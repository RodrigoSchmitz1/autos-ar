// Navegacion del sitio, igual en todas las paginas: arriba en la computadora y
// una barra abajo en el celular (estilo app). Cada pagina pone
// <header class="barra-nav" data-pagina="inicio"></header> y llama a navegacion().

const PAGINAS = [
  ["inicio", "Inicio", "index.html", '<path d="M4 11l8-6 8 6v8a1 1 0 0 1-1 1h-4v-5h-6v5H5a1 1 0 0 1-1-1z"/>'],
  ["mi-auto", "Mi auto", "mi-auto.html", '<path d="M5 16l1.5-5a2 2 0 0 1 1.9-1.4h7.2a2 2 0 0 1 1.9 1.4L19 16"/><rect x="3" y="15" width="18" height="4" rx="1.5"/><circle cx="7.5" cy="19.5" r="1"/><circle cx="16.5" cy="19.5" r="1"/>'],
  ["repuestos", "Repuestos", "repuestos.html", '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>'],
  ["comparar", "Comparar", "comparador.html", '<path d="M7 4v16M17 4v16M3 8h8M13 16h8"/>'],
  ["modelos", "Modelos", "ficha.html", '<rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/>'],
  ["asistente", "Asistente", "asistente.html", '<path d="M4 5h16v11H9l-5 4z"/>'],
];

export function navegacion() {
  const cabecera = document.querySelector(".barra-nav[data-pagina]");
  if (!cabecera) return;
  const activa = cabecera.dataset.pagina;
  const extra = [...cabecera.children];  // botones propios de la pagina (ajustes de Mi auto)
  const marca = document.createElement("a");
  marca.className = "marca"; marca.href = "index.html"; marca.innerHTML = "Autos<span>AR</span>";
  const arriba = document.createElement("nav");
  arriba.className = "nav-escritorio";
  arriba.setAttribute("aria-label", "Secciones");
  const abajo = document.createElement("nav");
  abajo.className = "tabs";
  abajo.setAttribute("aria-label", "Secciones");
  for (const [id, nombre, href, icono] of PAGINAS) {
    const a = document.createElement("a");
    a.href = href; a.textContent = nombre;
    if (id === activa) { a.className = "activo"; a.setAttribute("aria-current", "page"); }
    arriba.append(a);
    const t = document.createElement("a");
    t.href = href;
    if (id === activa) { t.className = "activo"; t.setAttribute("aria-current", "page"); }
    t.innerHTML = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icono}</svg>`;
    t.append(nombre);
    abajo.append(t);
  }
  const lado = document.createElement("div");
  lado.className = "barra-lado";
  lado.append(...extra);
  cabecera.replaceChildren(marca, arriba, lado);
  document.body.append(abajo);
}
