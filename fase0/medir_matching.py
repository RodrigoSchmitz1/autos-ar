"""
Fase 0.5 - Matching: que porcentaje de los autos de DNRPA se puede cruzar con
cada fuente.

  DNRPA <-> valuacion fiscal: por codigo (marca, tipo, modelo) y anio. Exacto.
  DNRPA <-> guia CCA, en dos niveles:
      modelo  ("TERRITORY"): por texto. Alcanza para depreciacion y comparador.
      version ("5P 1,5 GTDI HIBRIDA TREND"): por PRECIO. La valuacion fiscal se
          arma con precios de ACARA y CCA (Disp. 160/2026), y ya esta cruzada
          por codigo exacto. Dentro del modelo, la version correcta de la CCA es
          la que guarda con el valor fiscal la misma proporcion que el resto del
          mercado. El texto solo desempata.
  DNRPA <-> consumo (copia 2022): por texto, a nivel modelo.

La cobertura cuenta el ANIO del auto: la CCA publica precios desde 2012 y la
valuacion desde 2002. Un F-100 de 1985 cruza con "F-100" por nombre pero no
tiene precio, y contarlo como cubierto inflaria el resultado.

Se mide sobre los 50 codigos mas patentados (0 km) y mas transferidos (usados),
y ponderado por unidades sobre todo el mes. Deja un CSV con los 50 cruces de
cada universo para revisarlos a mano.

Uso: python fase0/medir_matching.py   (desde la raiz, con .venv)
"""

import csv
import math
import re
import statistics
import unicodedata

import duckdb
from rapidfuzz import fuzz

con = duckdb.connect()

# Palabras que una fuente pone y la otra no, y que no distinguen versiones.
RUIDO = {"SEDAN", "PUERTAS", "PUERTA", "PTAS", "RURAL", "FURGON", "FURGONETA", "PICK", "UP",
         "PICKUP", "CABINA", "TODO", "TERRENO", "COUPE", "HATCHBACK", "NUEVO", "NUEVA"}


def norm(texto):
    """Mayusculas, sin tildes, 1.5L -> 1,5, F-100 -> F100, HB 20 -> HB20, + -> PLUS."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    t = t.replace("+", " PLUS ")  # "KA +" es otro auto que "KA": no borrar el +
    t = re.sub(r"(\d)[.,](\d)\s*L\b", r"\1,\2", t)          # 1.5L / 1,5 L -> 1,5
    t = re.sub(r"(\d)\.(\d)", r"\1,\2", t)                   # 1.5 -> 1,5
    t = re.sub(r"(?<=[A-Z])-(?=\d)|(?<=\d)-(?=[A-Z])", "", t)  # F-100 -> F100
    # HB 20 -> HB20, S 10 -> S10. Pero no "GOL 1,6" -> "GOL1,6": si al numero
    # le sigue una coma es una cilindrada, no parte del nombre.
    t = re.sub(r"\b([A-Z]{1,3}) (\d{1,3})\b(?!,)", r"\1\2", t)
    t = re.sub(r"[^A-Z0-9, /]", " ", t)
    return " ".join(w for w in t.split() if w not in RUIDO)


def norm_marca(m):
    return norm(m).replace(" ", "")


def sin_marca(descripcion, marca):
    """'VOLKSWAGEN VENTO 2.5' -> 'VENTO 2.5': algunas descripciones repiten la marca."""
    d, m = norm(descripcion).split(), norm(marca).split()
    return " ".join(d[len(m):]) if d[:len(m)] == m else " ".join(d)


# ---------- DNRPA: una fila por codigo y anio modelo ----------
def universo(archivo):
    return con.sql(f"""
        SELECT CASE WHEN automotor_origen = 'Nacional' THEN 'N' ELSE 'I' END o,
               automotor_marca_codigo, automotor_tipo_codigo, automotor_modelo_codigo,
               any_value(automotor_marca_descripcion), any_value(automotor_modelo_descripcion),
               automotor_anio_modelo, count(*) n
        FROM read_csv('datos/muestra/{archivo}.csv', sample_size=-1)
        GROUP BY 1, 2, 3, 4, 7""").fetchall()


# ---------- Valuacion: valor por (llave, anio) ----------
valuacion = {}
for o, marca, tipo, modelo, anio, valor in con.sql("""
        SELECT origen, marca, tipo, modelo, anio, max(valor)
        FROM 'datos/fuentes/valuacion.parquet' GROUP BY ALL""").fetchall():
    valuacion[(o, marca, tipo, modelo, anio)] = valor
llaves_valuacion = {k[:4] for k in valuacion}

# ---------- CCA: precio por (marca, modelo, version, anio) ----------
cca_modelos, cca_precios = {}, {}
for marca, modelo, version, anio, precio in con.sql(
        "SELECT marca, modelo, version, anio, precio_miles FROM 'datos/fuentes/cca.parquet'").fetchall():
    cca_modelos.setdefault(norm_marca(marca), set()).add(modelo)
    cca_precios.setdefault((norm_marca(marca), modelo), {}).setdefault(version, {})[anio] = precio * 1000

# ---------- Consumo (copia 2022) ----------
# Se lee con csv y no con DuckDB: el archivo mezcla codificaciones y DuckDB lo
# rechaza como latin-1, mientras que Python lo decodifica sin errores.
consumo_modelos = {}
with open("datos/fuentes/consumo_2022.csv", encoding="latin-1") as fh:
    primera = fh.readline()
    fh.seek(0)
    for r in csv.DictReader(fh, delimiter=";" if primera.count(";") > primera.count(",") else ","):
        if r.get("vehiculo_marca"):
            consumo_modelos.setdefault(norm_marca(r["vehiculo_marca"]), set()).add(r["vehiculo_modelo"])


def modelo_por_prefijo(descripcion, marca, modelos):
    """El modelo mas largo cuyas palabras son el comienzo de la descripcion.

    Una palabra con digitos acepta prefijo ("BJ30" con "BJ30E"); una sin
    digitos tiene que ser igual, si no "KA" cruzaria con "KANGOO".
    """
    palabras = sin_marca(descripcion, marca).split()
    mejor, largo = None, 0
    for m in modelos or ():
        mp = sin_marca(m, marca).split()
        if not mp or len(mp) > len(palabras):
            continue
        if all(a == b or (re.search(r"\d", b) and a.startswith(b)) for a, b in zip(palabras, mp)):
            if len(mp) > largo:
                mejor, largo = m, len(mp)
    return mejor


def anio_cca(anio_modelo, anio_dnrpa_0km):
    """En la CCA y en la valuacion, el 0 km es la columna 0."""
    return 0 if anio_dnrpa_0km else anio_modelo


def calcular(archivo, es_0km):
    filas = []
    for o, mc, tc, moc, marca, desc, anio, n in universo(archivo):
        nm = norm_marca(marca)
        a = anio_cca(anio, es_0km)
        llave = (o, mc, tc, moc)
        mod_cca = modelo_por_prefijo(desc, marca, cca_modelos.get(nm))
        versiones = cca_precios.get((nm, mod_cca), {}) if mod_cca else {}
        con_precio = {v: p[a] for v, p in versiones.items() if a in p}
        filas.append({
            "o": o, "llave": llave, "marca": marca, "descripcion": desc, "anio": anio, "n": n,
            "valuacion_codigo": llave in llaves_valuacion,
            "valor_fiscal": valuacion.get(llave + (a,)),
            "cca_modelo": mod_cca, "cca_versiones_con_precio": con_precio,
            "consumo_modelo": modelo_por_prefijo(desc, marca, consumo_modelos.get(nm)),
        })
    return filas


def elegir_versiones(filas):
    """Version de la CCA por proporcion de precio con el valor fiscal.

    1. Ratio de mercado: en los modelos con UNA sola version con precio, no hay
       ambiguedad; la mediana de precio_cca / valor_fiscal es la proporcion
       tipica entre las dos fuentes (inflacion entre una y otra, mas metodo).
    2. Para cada auto, la version cuyo ratio queda mas cerca de esa mediana.
       El texto desempata entre versiones con precio casi igual.
    """
    ratios = [next(iter(f["cca_versiones_con_precio"].values())) / f["valor_fiscal"]
              for f in filas if len(f["cca_versiones_con_precio"]) == 1 and f["valor_fiscal"]]
    mediana = statistics.median(ratios)
    for f in filas:
        f["cca_version"], f["desvio_precio"] = None, None
        if not (f["cca_versiones_con_precio"] and f["valor_fiscal"]):
            continue
        texto = sin_marca(f["descripcion"], f["marca"])
        def costo(item):
            version, precio = item
            desvio = abs(math.log(precio / f["valor_fiscal"] / mediana))
            return (round(desvio, 2), -fuzz.token_sort_ratio(texto, norm(version)))
        version, precio = min(f["cca_versiones_con_precio"].items(), key=costo)
        f["cca_version"] = version
        f["desvio_precio"] = abs(precio / f["valor_fiscal"] / mediana - 1)
    return mediana, len(ratios)


def medir(nombre, archivo, es_0km):
    filas = calcular(archivo, es_0km)
    mediana, base = elegir_versiones(filas)
    total = sum(f["n"] for f in filas)

    # Top 50 por codigo (sumando anios)
    por_llave = {}
    for f in filas:
        por_llave.setdefault(f["llave"], []).append(f)
    top_llaves = sorted(por_llave, key=lambda k: -sum(f["n"] for f in por_llave[k]))[:50]
    top = [f for k in top_llaves for f in por_llave[k]]

    def pct(cond, conjunto):
        return 100 * sum(f["n"] for f in conjunto if cond(f)) / sum(f["n"] for f in conjunto)

    criterios = {
        "valuacion: codigo": lambda f: f["valuacion_codigo"],
        "valuacion: codigo + anio": lambda f: f["valor_fiscal"] is not None,
        "CCA: modelo": lambda f: f["cca_modelo"] is not None,
        "CCA: modelo con precio": lambda f: bool(f["cca_versiones_con_precio"]),
        "CCA: version x precio (descartado)": lambda f: f["desvio_precio"] is not None and f["desvio_precio"] < 0.15,
        "consumo 2022: modelo": lambda f: f["consumo_modelo"] is not None,
    }
    print(f"\n### {nombre}: {len(por_llave):,} codigos, {total:,} unidades")
    print(f"    ratio de mercado CCA/fiscal: {mediana:.2f} (de {base} autos sin ambiguedad)")
    print(f"  {'cobertura en unidades':28} {'top 50':>7} {'todo':>7}")
    for etiqueta, cond in criterios.items():
        print(f"  {etiqueta:28} {pct(cond, top):6.1f}% {pct(cond, filas):6.1f}%")

    salida = f"fase0/matching_top50_{nombre}.csv"
    campos = ["marca", "descripcion", "anio", "n", "valuacion_codigo", "valor_fiscal",
              "cca_modelo", "cca_version", "desvio_precio", "consumo_modelo"]
    principales = [max(por_llave[k], key=lambda f: f["n"]) for k in top_llaves]
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(principales)


if __name__ == "__main__":
    medir("0km", "inscripciones-iniciales-de-autos", es_0km=True)
    medir("usados", "transferencias-de-autos", es_0km=False)
