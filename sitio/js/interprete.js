// Interprete del asistente sin IA: saca los parametros de un pedido en texto
// libre ("cronos o polo? hago 15000 km por anio en cordoba") con reglas y el
// catalogo de modelos. Lo que no reconoce lo deja afuera: no inventa. Los
// pedidos de prueba estan en asistente/casos_interprete.json.

export function normalizar(t) {
  return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// Provincias por nombre y por ciudades que la gente nombra en vez de la provincia.
const PROVINCIAS = {
  "02": ["caba", "capital federal", "ciudad de buenos aires", "ciudad autonoma"],
  "06": ["buenos aires", "provincia de buenos aires", "pba", "gba", "conurbano", "la plata", "mar del plata", "bahia blanca"],
  "10": ["catamarca"], "14": ["cordoba"], "18": ["corrientes"], "22": ["chaco", "resistencia"],
  "26": ["chubut", "comodoro rivadavia", "comodoro", "trelew", "puerto madryn"],
  "30": ["entre rios", "parana"], "34": ["formosa"], "38": ["jujuy"], "42": ["la pampa"],
  "46": ["la rioja"], "50": ["mendoza"], "54": ["misiones", "posadas"], "58": ["neuquen"],
  "62": ["rio negro", "bariloche"], "66": ["salta"], "70": ["san juan"], "74": ["san luis"],
  "78": ["santa cruz", "rio gallegos"], "82": ["santa fe", "rosario"], "86": ["santiago del estero"],
  "90": ["tucuman"], "94": ["tierra del fuego", "ushuaia", "rio grande"],
};

const CARROCERIAS = {
  pickup: ["pick up", "pickup", "pick-up", "camioneta", "chata"],
  suv: ["suv", "rural", "todoterreno"],
  sedan: ["sedan", "4 puertas", "cuatro puertas"],
  hatch: ["hatchback", "hatch", "auto chico", "chiquito"],
  utilitario: ["utilitario", "furgon", "furgoneta"],
};

const COMBUSTIBLES = {
  diesel: ["diesel", "gasolero", "gasolera", "gasoil"],
  nafta: ["naftero", "naftera", "nafta"],
  hibrido: ["hibrido", "hibrida"],
  electrico: ["electrico", "electrica"],
};

const PERIODO = { dia: 365, diario: 365, diarios: 365, semana: 52, semanal: 52, mes: 12, mensual: 12, mensuales: 12,
                  ano: 1, anio: 1, anual: 1, anuales: 1 };

// "30.000" -> 30000; "25 mil" -> 25000; "45M" / "45 millones" / "50 palos" -> 45000000.
function numero(cifra, multiplicador) {
  const n = Number(cifra.replace(/\./g, "").replace(",", "."));
  if (!multiplicador) return n;
  if (multiplicador === "mil" || multiplicador.startsWith("luca")) return n * 1000;
  return n * 1_000_000;
}

// Distancia de edicion (Damerau-Levenshtein, version restringida): cuantas letras
// hay que agregar, sacar, cambiar o dar vuelta para pasar de una palabra a otra.
function distancia(a, b) {
  if (Math.abs(a.length - b.length) > 1) return 2;
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const costo = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + costo);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

// Busca la frase como palabra entera y la "consume" (la tapa con espacios) para
// que una frase mas corta no la vuelva a encontrar: "corolla cross" antes que "corolla".
function consumir(texto, frase) {
  const re = new RegExp(`(^|[^a-z0-9])${frase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?=$|[^a-z0-9])`);
  const m = re.exec(texto.valor);
  if (!m) return false;
  const inicio = m.index + m[1].length;
  texto.valor = texto.valor.slice(0, inicio) + " ".repeat(frase.length) + texto.valor.slice(inicio + frase.length);
  return true;
}

// Variantes con las que la gente escribe un modelo: "C 3" -> c3, "T-CROSS" -> t cross / tcross,
// "S-10 PICK - UP" -> s10, "HILUX SW4" -> sw4 tambien.
function alias(familia) {
  const base = normalizar(familia).replace(/\s*pick\s*-?\s*up\b/g, "").replace(/\s+/g, " ").trim();
  const variantes = new Set([base, base.replace(/-/g, " "), base.replace(/[- ]/g, ""), base.replace(/ (\d)/g, "$1"),
                             base.replace(/([a-z])(\d)/g, "$1 $2")]);
  const partes = base.split(" ");
  // "HILUX SW4" tambien es "sw4"; "KANGOO II EXPRESS" no se acorta (seria ambiguo).
  if (partes.length === 2 && /\d/.test(partes[1]) && partes[1].length >= 3) variantes.add(partes[1]);
  return [...variantes].filter((v) => v.length >= 2);
}

// Palabras comunes que tambien son nombres de modelo: solo cuentan con la marca adelante.
// Tambien los que se llaman como una provincia o ciudad ("santa fe"): "en santa fe" es el lugar.
const COMUNES = new Set(["uno", "punto", "idea", "up", "ka", "one", "go", "move", "cross"]);

const LUGARES = new Set(Object.values(PROVINCIAS).flat());

export function prepararCatalogo(familias) {
  // familias: [{marca, familia, inscripciones}]; un alias repetido queda para la mas vendida.
  const porAlias = new Map();
  for (const f of [...familias].sort((a, b) => (b.inscripciones || 0) - (a.inscripciones || 0))) {
    for (const a of alias(f.familia)) {
      const marca = normalizar(f.marca);
      for (const clave of COMUNES.has(a) || LUGARES.has(a) ? [`${marca} ${a}`] : [a, `${marca} ${a}`]) {
        if (!porAlias.has(clave)) porAlias.set(clave, `${f.marca}|${f.familia}`);
      }
    }
  }
  // Mas largos primero: "corolla cross" antes que "corolla", "toyota yaris" antes que "yaris".
  return [...porAlias.entries()].sort((a, b) => b[0].length - a[0].length);
}

export function interpretar(textoOriginal, catalogo) {
  const r = {};
  const texto = { valor: " " + normalizar(textoOriginal)
    .replace(/(\d)\.(\d{3})/g, "$1$2").replace(/(\d)\.(\d{3})/g, "$1$2")  // 30.000.000 -> 30000000
    .replace(/(\d)\s*k\b/g, "$1 mil")                                     // 15k -> 15 mil
    .replace(/[?!¿¡,;:()]/g, " ").replace(/\s+/g, " ") + " " };

  // Km: "20 km por dia", "1500 km por mes", "30000 km anuales", "20000km/ano", "25 mil km al ano".
  const reKm = /(\d+(?:[.,]\d+)?)\s*(mil)?\s*(?:km|kms|kilometros)?\s*(?:por|al|a la|x|\/|de)?\s*(dia|diarios|diario|semana|semanal|mes|mensuales|mensual|ano|anio|anual|anuales)\b/;
  const km = reKm.exec(texto.valor);
  if (km && (/km|kilometro|diario/.test(km[0]) || /hago|manejo|recorro|uso/.test(texto.valor.slice(Math.max(0, km.index - 25), km.index)))) {
    r.km_anio = Math.round(numero(km[1], km[2]) * PERIODO[km[3]]);
    texto.valor = texto.valor.replace(km[0], " ");
  }
  // El periodo antes del numero: "por ano hago 22 mil kilometros".
  const kmAntes = /(?:por|al|a la)?\s*\b(dia|diario|diarios|semana|semanal|mes|mensual|ano|anio|anual)\s*(?:hago|manejo|recorro|son)?\s*(?:unos|como)?\s*(\d+(?:[.,]\d+)?)\s*(mil)?\s*(?:km|kms|kilometros)\b/.exec(texto.valor);
  if (r.km_anio === undefined && kmAntes) {
    r.km_anio = Math.round(numero(kmAntes[2], kmAntes[3]) * PERIODO[kmAntes[1]]);
    texto.valor = texto.valor.replace(kmAntes[0], " ");
  }
  // Sin periodo ("hago 12000 km"): si es una cifra de un anio, se toma como anual.
  const kmSolo = /(?:hago|manejo|recorro)\s*(?:unos|como|mas o menos)?\s*(\d+(?:[.,]\d+)?)\s*(mil)?\s*(?:km|kms|kilometros)\b/.exec(texto.valor);
  if (r.km_anio === undefined && kmSolo && numero(kmSolo[1], kmSolo[2]) >= 3000) {
    r.km_anio = Math.round(numero(kmSolo[1], kmSolo[2]));
    texto.valor = texto.valor.replace(kmSolo[0], " ");
  }

  // Seguro: "seguro de 90 mil".
  const seg = /seguro\s*(?:de|por)?\s*\$?\s*(\d+(?:[.,]\d+)?)\s*(mil|lucas?|millones?|m\b)?/.exec(texto.valor);
  if (seg) { r.seguro_mensual = numero(seg[1], seg[2]); texto.valor = texto.valor.replace(seg[0], " "); }

  // Plata: "hasta 30 millones", "50 palos", "45M", "$35000000". Si es por mes no es el precio del auto.
  const rePlata = /\$?\s*(\d+(?:[.,]\d+)?)\s*(millones|millon|palos|palo|mill|m|mil|lucas|luca)?\b(\s*(?:pesos|\$))?(\s*(?:por mes|al mes|mensuales?))?/g;
  for (const p of texto.valor.matchAll(rePlata)) {
    const valor = numero(p[1], p[2] && p[2] !== "mil" && !p[2].startsWith("luca") ? "millones" : p[2]);
    if (p[4]) { texto.valor = texto.valor.replace(p[0], " "); continue; }
    if (valor >= 1_000_000 && (p[2] || p[3] || /\$/.test(p[0]))) {
      r.presupuesto_max = valor;
      texto.valor = texto.valor.replace(p[0], " ");
      break;
    }
  }

  // Anios de tenencia: "5 anios", "lo tengo 10 anios".
  const anios = /\b(\d{1,2})\s*(?:anos|anios|ano|anio)\b/.exec(texto.valor);
  if (anios && Number(anios[1]) >= 1 && Number(anios[1]) <= 15) {
    r.anios = Number(anios[1]);
    texto.valor = texto.valor.replace(anios[0], " ");
  }

  // Modelos (antes que provincias: "cordoba" no es un modelo, pero si hubiera choque gana el modelo).
  const modelos = [];
  for (const [a, clave] of catalogo) {
    // Un modelo que es un numero ("208") no puede ir pegado a una unidad ("500 km").
    if (/^\d+$/.test(a) && new RegExp(`(^|[^a-z0-9])${a}\\s*(km|mil|millones|palos|pesos|\\$)`).test(texto.valor)) continue;
    while (consumir(texto, a)) if (!modelos.includes(clave)) modelos.push(clave);
  }
  // Errores de tipeo ("hillux", "cronnos", "corola cross"): una letra de diferencia
  // (incluida una cambiada de lugar), solo con nombres de 5 letras o mas: con
  // nombres cortos "solo" seria Polo y "algo" seria Argo.
  for (const [a, clave] of catalogo) {
    if (a.length < 5 || /\d/.test(a) || modelos.includes(clave)) continue;
    const n = a.split(" ").length;
    const palabras = texto.valor.trim().split(/\s+/);
    for (let k = 0; k + n <= palabras.length; k++) {
      const trozo = palabras.slice(k, k + n).join(" ");
      if (trozo.length >= 5 && trozo !== a && distancia(trozo, a) === 1 && !LUGARES.has(trozo)) {
        modelos.push(clave);
        consumir(texto, trozo);
        break;
      }
    }
  }
  // Orden en que aparecen en el texto original: "cronos o polo" -> [cronos, polo].
  const t = normalizar(textoOriginal);
  const pos = (clave) => {
    const exactas = catalogo.filter(([, c]) => c === clave).map(([a]) => t.indexOf(a)).filter((i) => i >= 0);
    if (exactas.length) return Math.min(...exactas);
    // Encontrado con un error de tipeo: la palabra mas parecida del texto.
    const palabras = [...t.matchAll(/[a-z0-9]+/g)];
    const nombre = catalogo.find(([, c]) => c === clave)[0].split(" ")[0];
    return palabras.reduce((m, p) => (distancia(p[0], nombre) <= 1 ? Math.min(m, p.index) : m), Infinity);
  };
  if (modelos.length) r.modelos = modelos.sort((a, b) => pos(a) - pos(b));

  // Provincia: la frase mas larga primero ("ciudad de buenos aires" antes que "buenos aires").
  const frases = Object.entries(PROVINCIAS).flatMap(([id, fs]) => fs.map((f) => [f, id])).sort((a, b) => b[0].length - a[0].length);
  for (const [f, id] of frases) if (consumir(texto, f)) { r.provincia_id = id; break; }

  // Tambien en plural: "electricos", "camionetas", "sedanes".
  const listas = (tabla) => Object.entries(tabla)
    .filter(([, fs]) => fs.some((f) => [f, `${f}s`, `${f}es`].some((v) => consumir(texto, v)))).map(([k]) => k);
  const carro = listas(CARROCERIAS);
  if (carro.length) r.carroceria = carro;
  const comb = listas(COMBUSTIBLES);
  if (comb.length) r.combustible = comb;

  if (/\b(automatic[oa]s?|caja automatica|cvt)\b/.test(texto.valor)) r.automatica = true;
  else if (/\b(manual|mecanic[oa]|caja manual)\b/.test(texto.valor)) r.automatica = false;
  if (/\boriginales\b/.test(texto.valor)) r.originales = true;
  else if (/\balternativos\b/.test(texto.valor)) r.originales = false;
  return r;
}
