// Precios de repuestos para un auto en particular (anio y motor), a partir de
// los productos de cada pieza (datos/repuestos/<slug>.json, con el anio y el
// motor que dice el titulo: exportar/sitio.py, anios_titulo y motor_titulo).
// Lo usan Repuestos y Mi auto.
//
// Producto: [tienda, titulo, calidad, precio, unidades, url, desde, hasta, cilindradas, diesel]
// Auto: { anio, motor: { cil: "1.6", diesel: true|false|null } }, cada parte opcional.

// Anios del auto que dice el titulo, como texto: "2013–2019", "desde 2013".
export const textoAnios = (d, h) => d && h ? (d === h ? `${d}` : `${d}–${h}`) : d ? `desde ${d}` : h ? `hasta ${h}` : "";

// true: el titulo incluye ese anio; false: lo excluye; null: el titulo no dice.
export const sirve = (d, h, anio) => (!anio || (!d && !h) ? null : (!d || d <= anio) && (!h || h >= anio));

// Piezas que dependen del motor: en las demas (frenos, suspension) la
// cilindrada del titulo solo identifica el modelo.
export const DEL_MOTOR = new Set(["kit_distribucion", "correa_distribucion", "tensor_distribucion", "kit_embrague",
  "correa_accesorios", "filtro_aceite", "filtro_aire", "filtro_combustible", "kit_filtros", "kit_service",
  "bujia_encendido", "bujia_precalentamiento"]);

// true/false/null como `sirve`, para el motor: excluye si el titulo nombra otra
// cilindrada u otro combustible.
export function sirveMotor(cils, diesel, motor) {
  if (!motor?.cil) return null;
  if (diesel !== null && diesel !== undefined && motor.diesel !== null && motor.diesel !== undefined
      && Boolean(diesel) !== motor.diesel) return false;
  if (!cils) return diesel === null || diesel === undefined || motor.diesel === null || motor.diesel === undefined ? null : true;
  return cils.split("/").includes(motor.cil);
}

// Si un producto le sirve al auto: false si el anio o el motor lo excluyen,
// true si alguno lo confirma, null si el titulo no dice nada de eso.
export function encaja(x, tipo, auto = {}) {
  const a = sirve(x[6], x[7], auto.anio);
  const m = DEL_MOTOR.has(tipo) ? sirveMotor(x[8], x[9], auto.motor) : null;
  if (a === false || m === false) return false;
  return a === true || m === true ? true : null;
}

// Motor elegido como texto ("1.6 nafta") y su clave en la URL ("1.6n").
export const textoMotor = (m) => m?.cil ? `${m.cil}${m.diesel === true ? " diésel" : m.diesel === false ? " nafta" : ""}` : "";
export const claveMotor = (m) => m?.cil ? `${m.cil}${m.diesel === true ? "d" : m.diesel === false ? "n" : ""}` : "";
export function leerMotor(clave) {
  const r = /^([1-6]\.[0-9])([dn]?)$/.exec(clave || "");
  return r ? { cil: r[1], diesel: r[2] === "d" ? true : r[2] === "n" ? false : null } : null;
}

// Mediana como la de DuckDB (con cantidad par, el promedio de las dos del medio).
export function mediana(xs) {
  const v = [...xs].sort((a, b) => a - b), m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

// Precio de cada pieza solo con los productos que le sirven al auto (o que no
// dicen nada). Una calidad que se quedaria sin productos conserva los de todos.
// piezas: {tipo: [original, alternativo, productos, ...]}; devuelve el mismo
// formato ([original, alternativo, productos, min alt, max alt, min orig, max orig])
// las piezas que cambiaron y las del motor que se quedaron sin productos.
export function preciosDelAuto(piezas, ofertas, auto = {}) {
  const salida = {}, cambiadas = new Set(), sinProductos = new Set();
  for (const [tipo, base] of Object.entries(piezas)) {
    const lista = ofertas[tipo] || [];
    const quedan = lista.filter((x) => encaja(x, tipo, auto) !== false);
    if (!lista.length || quedan.length === lista.length) { salida[tipo] = base; continue; }
    // Pieza del motor sin ningun producto que confirme que le sirve: los que quedan
    // no dicen nada (un "Kit Distribucion Hilux" sin motor ni anio) y no alcanzan
    // para un precio. Queda sin precio propio: el gasto usa la mediana de todos.
    // (Puede ser un motor con cadena de distribucion, que no lleva kit.)
    if (auto.motor && DEL_MOTOR.has(tipo) && !quedan.some((x) => encaja(x, tipo, auto) === true)) {
      salida[tipo] = [null, null, 0, null, null, null, null];
      cambiadas.add(tipo);
      sinProductos.add(tipo);
      continue;
    }
    const precios = (xs, orig) => xs.filter((x) => (x[2] === "Original") === orig).map((x) => x[3]);
    const calidad = (orig) => {
      const xs = precios(quedan, orig).length ? precios(quedan, orig) : precios(lista, orig);
      return xs.length ? [mediana(xs), Math.min(...xs), Math.max(...xs)] : [null, null, null];
    };
    const [o, omin, omax] = calidad(true), [a, amin, amax] = calidad(false);
    salida[tipo] = [o, a, quedan.length, amin, amax, omin, omax];
    cambiadas.add(tipo);
  }
  return { piezas: salida, cambiadas, sinProductos };
}

// Motores que aparecen en los productos de un modelo (para elegir el propio):
// cilindrada y combustible nombrados en al menos dos productos de piezas del motor.
export function motoresDe(ofertas) {
  const cuenta = new Map();
  for (const [tipo, lista] of Object.entries(ofertas)) {
    if (!DEL_MOTOR.has(tipo)) continue;
    for (const x of lista) {
      if (!x[8] || x[8].includes("/")) continue;
      const clave = claveMotor({ cil: x[8], diesel: x[9] === 1 ? true : x[9] === 0 ? false : null });
      cuenta.set(clave, (cuenta.get(clave) || 0) + 1);
    }
  }
  // Una cilindrada sin combustible solo si no aparece ya con combustible.
  const claves = [...cuenta].filter(([, n]) => n >= 2).map(([k]) => k);
  return claves.filter((k) => /[dn]$/.test(k) || !claves.some((o) => o !== k && o.startsWith(k)))
    .map(leerMotor).sort((a, b) => a.cil.localeCompare(b.cil) || Number(a.diesel) - Number(b.diesel));
}

// Gasto por km en repuestos de desgaste, igual que int_mantenimiento_familia:
// cada pieza con intervalo, con el precio del modelo o la mediana de todos
// (intervalos[tipo].mediana = [original, alternativo]). Sin embrague para las
// cajas automaticas. Devuelve [alternativo, original].
export function gastoPorKm(piezas, intervalos, { embrague = true } = {}) {
  let alt = 0, orig = 0;
  for (const [tipo, i] of Object.entries(intervalos)) {
    if (i.solo_manual && !embrague) continue;
    const [o, a] = piezas[tipo] || [];
    alt += (a ?? o ?? i.mediana[1]) * i.unidades / i.km;
    orig += (o ?? a ?? i.mediana[0]) * i.unidades / i.km;
  }
  return [alt, orig];
}
