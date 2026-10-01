"""
Fase 0.5 - Extrae la guia de precios de la CCA (PDF) a Parquet.

La guia no tiene codigos: es marca -> modelo -> versiones en texto. Se
distinguen por tipografia y contenido:
  - marca:   negrita, sin precios
  - modelo:  negrita italica
  - version: negrita, con precios al final

Los precios no siempre arrancan en 0 km (un modelo discontinuado empieza en un
anio anterior), asi que el anio de cada precio sale de la POSICION horizontal
de su columna en el encabezado, no del orden. Algunos precios traen coma de
miles ("111,660") y otros no: se normalizan.

Uso: python fase0/parsear_cca.py datos/fuentes/cca_autos.pdf
"""

import re
import sys

import duckdb
import pandas as pd
import pdfplumber

# Tres formatos en la misma guia: "24259", "111,660" (coma de miles) y
# "36270,0" (coma decimal, aparece en algunos 0 km). Si un precio no se
# reconoce, el renglon queda sin precios y se confunde con una marca: eso
# contamina todo lo que viene debajo. Coma + 3 digitos = miles; + 1-2 = decimal.
PRECIO = re.compile(r"^\d{1,3}(,\d{3})+$|^\d+(,\d{1,2})?$")


def a_numero(texto):
    if re.fullmatch(r"\d+,\d{1,2}", texto):
        return round(float(texto.replace(",", ".")))
    return int(texto.replace(",", ""))


def columnas_de_anio(pagina):
    """Centro horizontal de cada columna de anio, leido del encabezado."""
    columnas = {}
    for w in pagina.extract_words(keep_blank_chars=False, use_text_flow=False):
        if re.fullmatch(r"20\d\d", w["text"]) and w["top"] < 145:
            columnas[int(w["text"])] = (w["x0"] + w["x1"]) / 2
        elif w["text"] == "Km" and w["top"] < 145:
            columnas[0] = (w["x0"] + w["x1"]) / 2 - 8  # "0 Km": el centro real esta a la izquierda
    return columnas


def renglones(pagina):
    """Agrupa palabras por renglon, con su tipografia."""
    palabras = pagina.extract_words(extra_attrs=["fontname"])
    por_renglon = {}
    for w in palabras:
        por_renglon.setdefault(round(w["top"]), []).append(w)
    for top in sorted(por_renglon):
        yield top, sorted(por_renglon[top], key=lambda w: w["x0"])


SALTO_DE_MARCA = 18  # puntos; entre renglones normales hay ~12,5


def renglones_utiles(pdf):
    """(pagina, cols, top, descripcion, precios, italica, salto) de cada renglon con contenido."""
    for pagina in pdf.pages:
        cols = columnas_de_anio(pagina)
        if not cols:
            continue
        borde_precios = min(cols.values()) - 25
        anterior = None
        for top, ws in renglones(pagina):
            if top < 145:  # encabezado de pagina
                continue
            texto = [w for w in ws if w["x1"] < borde_precios or not PRECIO.match(w["text"])]
            precios = [w for w in ws if w["x0"] >= borde_precios and PRECIO.match(w["text"])]
            salto = None if anterior is None else top - anterior
            anterior = top
            yield (cols, " ".join(w["text"] for w in texto).strip(), precios,
                   "Italic" in ws[0]["fontname"], salto)


def parsear(ruta):
    # Una version discontinuada puede no tener NINGUN precio, y entonces se ve
    # igual que una marca (negrita, sin numeros). Lo que las separa es el espacio
    # vertical: antes de cada marca nueva hay un salto mayor. Pero en el primer
    # renglon de una pagina no hay "anterior" con que medir. Por eso dos pasadas:
    # la primera junta los nombres de marca por el salto; la segunda solo acepta
    # como marca un renglon que este en esa lista.
    with pdfplumber.open(ruta) as pdf:
        # Primer renglon de pagina: sin salto para medir, se acepta si no tiene
        # digitos (una version casi siempre tiene cilindrada, "1,4"; una marca no).
        marcas = {d for _, d, p, it, s in renglones_utiles(pdf)
                  if not p and not it and (s > SALTO_DE_MARCA if s is not None
                                           else not re.search(r"\d", d))}
    filas, marca, modelo, sin_anio, sin_precio = [], None, None, 0, 0
    with pdfplumber.open(ruta) as pdf:
        for cols, descripcion, precios, italica, _ in renglones_utiles(pdf):
            if not precios:
                if italica:
                    modelo = descripcion
                elif descripcion in marcas:
                    marca, modelo = descripcion, None
                else:
                    sin_precio += 1  # version sin ningun precio publicado
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


def main():
    filas, sin_anio, sin_precio = parsear(sys.argv[1])
    con = duckdb.connect()
    con.register("df", pd.DataFrame(filas))
    con.sql("COPY df TO 'datos/fuentes/cca.parquet' (FORMAT parquet)")
    print(con.sql("""SELECT count(*) precios, count(DISTINCT marca) marcas, count(DISTINCT (marca, modelo)) modelos,
                     count(DISTINCT (marca, modelo, version)) versiones FROM df"""))
    print(f"precios sin columna de anio clara: {sin_anio}; versiones sin ningun precio: {sin_precio}")


if __name__ == "__main__":
    main()
