"""
Ingesta de la tabla de valuacion fiscal de DNRPA (PDF).

Salida: datos/raw/valuacion/<AAAAMMDD>.parquet, una por vigencia
        (valor fiscal por codigo marca-tipo-modelo y anio).

Decisiones:
- El link cambia con cada tabla ("01-10-2026.pdf"): se busca en la pagina de
  valuaciones de DNRPA. Si la vigencia ya esta guardada, no se baja nada.
- Por POSICION, no por texto: en los vehiculos de mas de 100 millones las
  columnas quedan tan juntas que el texto pega los valores de varios anios.
  Cada valor se asigna a la columna de anio que tiene encima.
- Los codigos nacionales traen fabricante (Fab 3 + Marca 2 + Tipo + Mod), los
  importados no (Marca 3 + Tipo + Mod). La llave contra los microdatos de DNRPA
  es (marca, tipo, modelo) en los dos casos.
- Controles que hacen FALLAR la ingesta si el formato cambia: renglones no
  reconocidos, valores fuera de columna, codigos inconsistentes. Las tablas
  anteriores a ~2023 tienen otro formato (codigo y descripcion en renglones
  separados) y por eso no se ingieren todavia: este control las rechaza.

Uso: python -m ingesta.valuacion [--pdf ruta_local.pdf --vigencia AAAAMMDD]
"""

import argparse
import io
import os
import re

import duckdb
import pandas as pd
import pdfplumber

from ingesta.comun import pedir

PAGINA = "https://www.dnrpa.gov.ar/portal_dnrpa/valuaciones2.php"
BASE_PDF = "https://www.dnrpa.gov.ar/valuacion/informacion/"
RAIZ = os.path.join("datos", "raw", "valuacion")
TOLERANCIA_X = 1.5
# Renglones sueltos que el PDF parte en dos (una descripcion larga que sigue
# abajo, "FURGÓN"). En la tabla de octubre 2026 eran 5 de ~18.000.
MAX_RENGLONES_SUELTOS = 50

_COMUN = r"^(?P<origen>{o}) (?P<mtm>\S+){sep}(?P<t>[A-Z]) "
_IMPORTADO = r"(?P<marca>\S+) (?P<tipo>\S+) (?P<modelo>\S+) (?P<resto>.+)$"
_NACIONAL = r"(?P<fab>\d{3}) (?P<marca>\S{2}) (?P<tipo>\S+) (?P<modelo>\S+) (?P<resto>.+)$"
# Primero el patron estricto (con espacio antes de la T) y despues el de la T
# pegada al codigo ("M7922001A"): en "03934AA A ..." un patron flexible toma la
# segunda A del codigo como la T.
PATRONES = [re.compile(_COMUN.format(o=o, sep=sep) + cola)
            for o, cola in (("N", _NACIONAL), ("I", _IMPORTADO)) for sep in (" ", "")]


def vigencia_actual():
    """(url, AAAAMMDD) de la tabla vigente, leida de la pagina de DNRPA."""
    html = pedir(PAGINA).decode("latin-1")
    fechas = re.findall(r"valuacion/informacion/(\d{2})-(\d{2})-(\d{4})\.pdf", html)
    if not fechas:
        raise RuntimeError("No se encontro el link a la tabla vigente: cambio la pagina de DNRPA")
    d, m, a = max(fechas, key=lambda f: (f[2], f[1], f[0]))
    return f"{BASE_PDF}{d}-{m}-{a}.pdf", f"{a}{m}{d}"


def _columnas(palabras):
    cols = {}
    for w in palabras:
        if w["text"] == "0Km":
            cols[0] = (w["x0"] + w["x1"]) / 2
        elif re.fullmatch(r"20\d\d", w["text"]) and w["top"] < 80:
            cols[int(w["text"])] = (w["x0"] + w["x1"]) / 2
    return cols


def parsear(contenido_pdf):
    filas, sueltos, fuera = [], [], 0
    with pdfplumber.open(io.BytesIO(contenido_pdf)) as pdf:
        for pagina in pdf.pages:
            palabras = pagina.extract_words(x_tolerance=TOLERANCIA_X)
            cols = _columnas(palabras)
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
                m = next((p.match(texto) for p in PATRONES if p.match(texto)), None)
                if not m:
                    if texto and not texto.startswith(("Vigencia", "Página", "I/N")):
                        sueltos.append(texto)
                    continue
                for w in valores:
                    centro = (w["x0"] + w["x1"]) / 2
                    anio, x = min(cols.items(), key=lambda kv: abs(kv[1] - centro))
                    if abs(x - centro) > 12:
                        fuera += 1
                        continue
                    filas.append({
                        "origen": m["origen"], "mtm": m["mtm"], "fab": m.groupdict().get("fab"),
                        "marca": m["marca"], "tipo": m["tipo"], "modelo": m["modelo"],
                        "descripcion": m["resto"], "anio": anio, "valor": int(w["text"]),
                    })
    return filas, sueltos, fuera


def validar(con, sueltos, fuera):
    errores = []
    if len(sueltos) > MAX_RENGLONES_SUELTOS:
        errores.append(f"{len(sueltos)} renglones no reconocidos (ej.: {sueltos[:3]})")
    if fuera:
        errores.append(f"{fuera} valores fuera de columna")
    inconsistentes, total = con.sql("""
        SELECT count(*) FILTER (WHERE mtm <> coalesce(fab, '') || marca || CASE origen WHEN 'I' THEN tipo ELSE '' END || modelo),
               count(*)
        FROM (SELECT DISTINCT origen, mtm, fab, marca, tipo, modelo FROM t)""").fetchone()
    if total == 0 or inconsistentes / total > 0.01:
        errores.append(f"{inconsistentes} de {total} codigos no coinciden con sus partes")
    if errores:
        raise RuntimeError("La tabla de valuacion no paso los controles: " + "; ".join(errores))
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf")
    ap.add_argument("--vigencia")
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    if args.pdf:
        contenido, vigencia = open(args.pdf, "rb").read(), args.vigencia
    else:
        url, vigencia = vigencia_actual()
        if os.path.exists(os.path.join(RAIZ, f"{vigencia}.parquet")):
            print(f"valuacion {vigencia}: ya ingerida")
            return
        contenido = pedir(url)
    filas, sueltos, fuera = parsear(contenido)
    con = duckdb.connect()
    con.register("t", pd.DataFrame(filas))
    vehiculos = validar(con, sueltos, fuera)
    destino = os.path.join(RAIZ, f"{vigencia}.parquet")
    con.sql(f"COPY (SELECT strptime('{vigencia}', '%Y%m%d')::date AS vigencia, * FROM t) TO '{destino}' (FORMAT parquet)")
    print(f"valuacion {vigencia}: {len(filas):,} valores de {vehiculos:,} vehiculos")


if __name__ == "__main__":
    main()
