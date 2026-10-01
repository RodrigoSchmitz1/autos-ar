"""
Fase 0.5 - Extrae la tabla de valuacion fiscal de DNRPA (PDF) a Parquet.

Cada renglon del PDF es:
    I/N  MTM/FMM  T  cod1 cod2 cod3  descripcion (marca modelo tipo)  valores...

Por que por POSICION y no por texto: en los vehiculos de mas de 100 millones
las columnas quedan tan juntas que extract_text pega los valores
("270270000243100000..." son varios anios en un solo numero). Partirlos a mano
seria adivinar. Con extract_words a tolerancia 1,5 pt se separan, y cada valor
se asigna a la columna de anio que tiene encima. Ademas, un modelo que no se
vendia en un anio no tiene ese valor: la posicion dice cual falta, el orden no.

Uso: python fase0/parsear_valuacion.py datos/fuentes/valuacion_2026-10-01.pdf
"""

import re
import sys

import duckdb
import pandas as pd
import pdfplumber

TOLERANCIA_X = 1.5
# Lo normal es "MTM T cod1 cod2 cod3". A veces el PDF pega la letra T al
# codigo ("M7922001A M79 22 001"). No alcanza con hacer el espacio opcional:
# en "03934AA A 03934 18 AA" el codigo termina en letra y un patron flexible
# toma esa A como la T. Por eso primero se prueba el patron estricto y solo si
# falla, el de la T pegada.
#
# Las columnas son "Fab Marca Tipo Mod". Los importados no tienen fabricante
# (marca de 3, tipo de 2, modelo de 3); los nacionales si (fabricante de 3,
# marca de 2, tipo de 2, modelo de 2). La llave contra los microdatos de DNRPA
# es (marca, tipo, modelo) en los dos casos.
_COMUN = r"^(?P<origen>{o}) (?P<mtm>\S+){sep}(?P<t>[A-Z]) "
_IMPORTADO = r"(?P<marca>\S+) (?P<tipo>\S+) (?P<modelo>\S+) (?P<resto>.+)$"
_NACIONAL = r"(?P<fab>\d{{3}}) (?P<marca>\S{{2}}) (?P<tipo>\S+) (?P<modelo>\S+) (?P<resto>.+)$"
PATRONES = [
    re.compile(_COMUN.format(o="N", sep=" ") + _NACIONAL.replace("{{", "{").replace("}}", "}")),
    re.compile(_COMUN.format(o="N", sep="") + _NACIONAL.replace("{{", "{").replace("}}", "}")),
    re.compile(_COMUN.format(o="I", sep=" ") + _IMPORTADO),
    re.compile(_COMUN.format(o="I", sep="") + _IMPORTADO),
]


def reconocer(texto):
    for patron in PATRONES:
        m = patron.match(texto)
        if m:
            return m
    return None


def columnas(palabras):
    """{anio: centro x} leido del encabezado ('0Km 2025 2024 ...')."""
    cols = {}
    for w in palabras:
        if w["text"] == "0Km":
            cols[0] = (w["x0"] + w["x1"]) / 2
        elif re.fullmatch(r"20\d\d", w["text"]) and w["top"] < 80:
            cols[int(w["text"])] = (w["x0"] + w["x1"]) / 2
    return cols


def parsear(ruta):
    filas, descartados, fuera_de_columna = [], [], 0
    with pdfplumber.open(ruta) as pdf:
        for pagina in pdf.pages:
            palabras = pagina.extract_words(x_tolerance=TOLERANCIA_X)
            cols = columnas(palabras)
            if not cols:
                continue
            inicio_valores = min(cols.values()) - 12
            por_renglon = {}
            for w in palabras:
                por_renglon.setdefault(round(w["top"]), []).append(w)
            for top in sorted(por_renglon):
                ws = sorted(por_renglon[top], key=lambda w: w["x0"])
                valores = [w for w in ws if w["x0"] >= inicio_valores and w["text"].isdigit()]
                texto = " ".join(w["text"] for w in ws if w not in valores)
                m = reconocer(texto)
                if not m:
                    if texto and not texto.startswith(("Vigencia", "Página", "I/N")):
                        descartados.append(texto)
                    continue
                for w in valores:
                    centro = (w["x0"] + w["x1"]) / 2
                    anio, x = min(cols.items(), key=lambda kv: abs(kv[1] - centro))
                    if abs(x - centro) > 12:
                        fuera_de_columna += 1
                        continue
                    filas.append({
                        "origen": m["origen"], "mtm": m["mtm"], "t": m["t"],
                        "fab": m.groupdict().get("fab"), "marca": m["marca"],
                        "tipo": m["tipo"], "modelo": m["modelo"],
                        "descripcion": m["resto"], "anio": anio, "valor": int(w["text"]),
                    })
    return filas, descartados, fuera_de_columna


def main():
    filas, descartados, fuera = parsear(sys.argv[1])
    con = duckdb.connect()
    con.register("df", pd.DataFrame(filas))
    con.sql("COPY df TO 'datos/fuentes/valuacion.parquet' (FORMAT parquet)")
    print(con.sql("""SELECT count(*) valores, count(DISTINCT mtm) vehiculos,
                     max(length(CAST(valor AS VARCHAR))) max_digitos FROM df"""))
    # Control: el codigo completo (MTM/FMM) tiene que ser la suma de sus partes.
    print(con.sql("""SELECT origen, count(*) codigos,
                     count(*) FILTER (WHERE mtm = coalesce(fab, '') || marca || CASE origen WHEN 'I' THEN tipo ELSE '' END || modelo) consistentes
                     FROM (SELECT DISTINCT origen, mtm, fab, marca, tipo, modelo FROM df) GROUP BY 1"""))
    print(f"renglones no reconocidos: {len(descartados)}; valores fuera de columna: {fuera}")
    for d in descartados[:5]:
        print("   ", d[:120])


if __name__ == "__main__":
    main()
