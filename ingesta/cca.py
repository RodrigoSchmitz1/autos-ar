"""
Ingesta de la guia de precios de autos de la CCA (PDF mensual).

Salida: datos/raw/cca/<AAAAMM>.parquet (precio en miles de pesos por marca,
        modelo, version y anio).

Por que es urgente capturarla: el PDF esta siempre en la misma URL y se pisa
cada mes. El mes que no se guarda se pierde. El pipeline corre todos los dias;
si la CCA corrige el PDF a mitad de mes (cambia su SHA-256), se reprocesa.

La guia no tiene codigos: marca -> modelo -> versiones en texto. Se distinguen
por tipografia y posicion (ver fase0/05_matching.md):
  - modelo:  negrita italica
  - marca:   sin precios y precedida por un salto vertical mayor; en el primer
             renglon de pagina (sin salto para medir), sin digitos
  - version: con precios; el anio de cada precio sale de la columna que tiene
             encima, no del orden (un modelo discontinuado empieza en 2023)
Tres formatos de precio en la misma guia: "24259", "111,660" (miles) y
"36270,0" (decimal). Si uno no se reconoce, el renglon parece una marca y
contamina todo lo de abajo: por eso hay controles que hacen fallar la ingesta.

Uso: python -m ingesta.cca
"""

import hashlib
import io
import json
import os
import re

import duckdb
import pandas as pd
import pdfplumber

from ingesta.comun import pedir

URL = "https://www.cca.org.ar/descargas/precios/Autos.pdf"
RAIZ = os.path.join("datos", "raw", "cca")
ESTADO = os.path.join(RAIZ, "_estado.json")
MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
PRECIO = re.compile(r"^\d{1,3}(,\d{3})+$|^\d+(,\d{1,2})?$")
SALTO_DE_MARCA = 18


def a_numero(texto):
    if re.fullmatch(r"\d+,\d{1,2}", texto):
        return round(float(texto.replace(",", ".")))
    return int(texto.replace(",", ""))


def periodo_del_pdf(pdf):
    texto = (pdf.pages[0].extract_text() or "").lower()
    m = re.search(r"(" + "|".join(MESES) + r")\s+(20\d\d)", texto)
    if not m:
        raise RuntimeError("No se encontro el mes en el encabezado de la guia CCA")
    return f"{m[2]}{MESES[m[1]]:02d}"


def _columnas(pagina):
    cols = {}
    for w in pagina.extract_words():
        if re.fullmatch(r"20\d\d", w["text"]) and w["top"] < 145:
            cols[int(w["text"])] = (w["x0"] + w["x1"]) / 2
        elif w["text"] == "Km" and w["top"] < 145:
            cols[0] = (w["x0"] + w["x1"]) / 2 - 8  # "0 Km": el centro real esta a la izquierda
    return cols


def _renglones(pdf):
    for pagina in pdf.pages:
        cols = _columnas(pagina)
        if not cols:
            continue
        borde = min(cols.values()) - 25
        por_renglon = {}
        for w in pagina.extract_words(extra_attrs=["fontname"]):
            por_renglon.setdefault(round(w["top"]), []).append(w)
        anterior = None
        for top in sorted(por_renglon):
            if top < 145:
                continue
            ws = sorted(por_renglon[top], key=lambda w: w["x0"])
            texto = [w for w in ws if w["x1"] < borde or not PRECIO.match(w["text"])]
            precios = [w for w in ws if w["x0"] >= borde and PRECIO.match(w["text"])]
            salto = None if anterior is None else top - anterior
            anterior = top
            yield cols, " ".join(w["text"] for w in texto).strip(), precios, "Italic" in ws[0]["fontname"], salto


def parsear(pdf):
    marcas = {d for _, d, p, it, s in _renglones(pdf)
              if not p and not it and (s > SALTO_DE_MARCA if s is not None else not re.search(r"\d", d))}
    filas, marca, modelo, sin_anio, sin_precio = [], None, None, 0, 0
    for cols, descripcion, precios, italica, _ in _renglones(pdf):
        if not precios:
            if italica:
                modelo = descripcion
            elif descripcion in marcas:
                marca, modelo = descripcion, None
            else:
                sin_precio += 1
            continue
        for w in precios:
            centro = (w["x0"] + w["x1"]) / 2
            anio, x = min(cols.items(), key=lambda kv: abs(kv[1] - centro))
            if abs(x - centro) > 20:
                sin_anio += 1
                continue
            filas.append({"marca": marca, "modelo": modelo, "version": descripcion,
                          "anio": anio, "precio_miles": a_numero(w["text"])})
    return filas, sin_anio, sin_precio


def validar(con, sin_anio, sin_precio):
    errores = []
    marcas, sin_marca, sin_modelo = con.sql(
        "SELECT count(DISTINCT marca), count(*) FILTER (WHERE marca IS NULL), count(*) FILTER (WHERE modelo IS NULL) FROM t").fetchone()
    if sin_anio:
        errores.append(f"{sin_anio} precios sin columna de anio")
    if sin_marca or sin_modelo:
        errores.append(f"{sin_marca} precios sin marca y {sin_modelo} sin modelo")
    if marcas < 50:
        errores.append(f"solo {marcas} marcas (eran 69 en octubre 2026)")
    if sin_precio > 50:
        errores.append(f"{sin_precio} versiones sin precio (eran 8): probablemente un formato de precio nuevo")
    if errores:
        raise RuntimeError("La guia CCA no paso los controles: " + "; ".join(errores))
    return marcas


def main():
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    contenido = pedir(URL)
    huella = hashlib.sha256(contenido).hexdigest()
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        periodo = periodo_del_pdf(pdf)
        if estado.get(periodo) == huella:
            print(f"cca {periodo}: sin cambios")
            return
        filas, sin_anio, sin_precio = parsear(pdf)
    con = duckdb.connect()
    con.register("t", pd.DataFrame(filas))
    marcas = validar(con, sin_anio, sin_precio)
    con.sql(f"COPY (SELECT strptime('{periodo}', '%Y%m')::date AS periodo, * FROM t) "
            f"TO '{os.path.join(RAIZ, periodo + '.parquet')}' (FORMAT parquet)")
    estado[periodo] = huella
    json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)
    print(f"cca {periodo}: {len(filas):,} precios de {marcas} marcas")


if __name__ == "__main__":
    main()
