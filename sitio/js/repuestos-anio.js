// Precios de repuestos para el anio de un auto, a partir de los productos de
// cada pieza (datos/repuestos/<slug>.json, con los anios que dice el titulo:
// exportar/sitio.py, anios_titulo). Lo usan Repuestos y Mi auto.

// Anios del auto que dice el titulo, como texto: "2013–2019", "desde 2013".
export const textoAnios = (d, h) => d && h ? (d === h ? `${d}` : `${d}–${h}`) : d ? `desde ${d}` : h ? `hasta ${h}` : "";

// true: el titulo incluye ese anio; false: lo excluye; null: el titulo no dice.
export const sirve = (d, h, anio) => (!anio || (!d && !h) ? null : (!d || d <= anio) && (!h || h >= anio));

// Mediana como la de DuckDB (con cantidad par, el promedio de las dos del medio).
export function mediana(xs) {
  const v = [...xs].sort((a, b) => a - b), m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

// Precio de cada pieza solo con los productos que sirven para el anio (o que no
// dicen anio). Una calidad que se quedaria sin productos conserva los de todos.
// piezas: {tipo: [original, alternativo, productos, ...]}; devuelve el mismo
// formato ([original, alternativo, productos, min alt, max alt, min orig, max orig])
// y las piezas que cambiaron.
export function preciosDelAnio(piezas, ofertas, anio) {
  const salida = {}, cambiadas = new Set();
  for (const [tipo, base] of Object.entries(piezas)) {
    const lista = ofertas[tipo] || [];
    const quedan = lista.filter((x) => sirve(x[6], x[7], anio) !== false);
    if (!anio || !lista.length || quedan.length === lista.length) { salida[tipo] = base; continue; }
    const precios = (xs, orig) => xs.filter((x) => (x[2] === "Original") === orig).map((x) => x[3]);
    const calidad = (orig) => {
      const xs = precios(quedan, orig).length ? precios(quedan, orig) : precios(lista, orig);
      return xs.length ? [mediana(xs), Math.min(...xs), Math.max(...xs)] : [null, null, null];
    };
    const [o, omin, omax] = calidad(true), [a, amin, amax] = calidad(false);
    salida[tipo] = [o, a, quedan.length, amin, amax, omin, omax];
    cambiadas.add(tipo);
  }
  return { piezas: salida, cambiadas };
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
