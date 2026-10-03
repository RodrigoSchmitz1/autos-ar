// Costo total de tener un auto: el mismo calculo que costo/calculo.py.
//
// El sitio no tiene servidor, asi que el comparador calcula en el navegador.
// Para que esta copia y la de Python no diverjan, las dos se prueban contra
// los mismos casos (costo/casos_prueba.json): test_calculo.py y test_costo.mjs.
//
//   costo anual = km_anio x (combustible + service + repuestos por km)
//               + patente anual
//               + depreciacion anual = valor 0 km x (1 - proporcion conservada) / anios
//               + seguro (12 x el mensual)

export function proporcionConservada(c, anios) {
  const puntos = [[1, c.proporcion_conservada_1], [5, c.proporcion_conservada_5], [10, c.proporcion_conservada_10]]
    .filter(([, p]) => p !== null && p !== undefined);
  if (puntos.length === 0) return null;
  if (anios <= puntos[0][0]) {
    const [a, p] = puntos[0];
    return 1 - (1 - p) * anios / a;  // antes del primer punto: recta desde el 100% del 0 km
  }
  for (let i = 0; i < puntos.length - 1; i++) {
    const [a0, p0] = puntos[i], [a1, p1] = puntos[i + 1];
    if (anios <= a1) return p0 + (p1 - p0) * (anios - a0) / (a1 - a0);
  }
  return puntos[puntos.length - 1][1];
}

export function validarPerfil(perfil) {
  const p = { km_anio: 15000, anios: 5, seguro_mensual: 0, repuestos_originales: false, ...perfil };
  if (!(p.km_anio > 0)) throw new Error("km_anio tiene que ser positivo");
  if (!(p.anios > 0)) throw new Error("anios tiene que ser positivo");
  if (p.seguro_mensual < 0) throw new Error("seguro_mensual no puede ser negativo");
  return p;
}

// `c`: componentes de una version (como en mart_costo_componentes).
export function calcular(c, perfilParcial = {}) {
  const perfil = validarPerfil(perfilParcial);
  const faltantes = [];
  const falta = (v) => v === null || v === undefined;

  const porKm = (nombre) => {
    if (falta(c[nombre])) { faltantes.push(nombre.replace("_por_km", "")); return 0; }
    return c[nombre] * perfil.km_anio;
  };
  const combustible = porKm("combustible_por_km");
  const service = porKm("service_por_km");
  const nombreRep = perfil.repuestos_originales && !falta(c.repuestos_por_km_original)
    ? "repuestos_por_km_original" : "repuestos_por_km";
  let repuestos = c[nombreRep];
  if (falta(repuestos)) { faltantes.push("repuestos"); repuestos = 0; } else { repuestos *= perfil.km_anio; }
  let patente = c.patente_anual;
  if (falta(patente)) { faltantes.push("patente"); patente = 0; }
  const prop = proporcionConservada(c, perfil.anios);
  let depreciacion = 0;
  if (prop === null || falta(c.valor_0km)) faltantes.push("depreciacion");
  else depreciacion = c.valor_0km * (1 - prop) / perfil.anios;
  const seguro = perfil.seguro_mensual * 12;
  const anual = combustible + service + repuestos + patente + depreciacion + seguro;
  return {
    combustible_anual: combustible, service_anual: service, repuestos_anual: repuestos,
    patente_anual: patente, depreciacion_anual: depreciacion, seguro_anual: seguro,
    anual, mensual: anual / 12, por_km: anual / perfil.km_anio,
    faltantes, completo: faltantes.length === 0,
  };
}

// Componentes de una version del costo.json del sitio, para una provincia:
// el combustible por km sale del consumo y del precio por litro de la provincia.
export function componentes(version, provincia, precioLitro) {
  const precio = version.combustible === "electrico" ? null
    : (precioLitro[provincia] || {})[version.combustible === "diesel" ? "diesel" : "nafta"];
  const combustible_por_km = (version.consumo_l100km === null || precio === undefined || precio === null)
    ? null : version.consumo_l100km / 100 * precio;
  const patente = (version.patente || {})[provincia];
  return { ...version, combustible_por_km, patente_anual: patente === undefined ? null : patente };
}
