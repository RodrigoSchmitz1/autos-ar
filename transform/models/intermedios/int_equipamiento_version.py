"""
Cruce de cada version de las fichas de equipamiento con su version DNRPA (la
que tiene precio, ventas y costo).

La ficha nombra la version corto ("HIGH 170 TSI", "XL 4x2") y DNRPA largo
("TERA HIGH 170 TSI AT", "RANGER DC XL 2.0L T 4X2 MT D"). Regla estricta:
TODAS las palabras de la version de la ficha tienen que estar en el nombre
DNRPA. Si no, "Trendline 170 TSI" se cruzaria con la "Trendline 200 TSI" por
compartir "Trendline", y el precio seria de otra version. Una version que DNRPA
todavia no registro (recien lanzada) queda sin cruce: es la respuesta correcta.

Antes de comparar: numeros y letras separados ("200TSI" = "200 TSI"), sin el
codigo de anio modelo ("AM27", "MY26", "G1": cambia todos los anios), sin
lo que esta entre parentesis ni asteriscos (notas al pie), y "LIMITED" = "LTD".
Si varias versiones DNRPA cumplen (la ficha no dice la caja y DNRPA tiene MT y
AT), queda la mas vendida.

Grano: marca x familia x version de la ficha.
"""

import re
import unicodedata

import pandas as pd

SINONIMOS = {"LIMITED": "LTD", "LIMITED+": "LTD+"}
SIN_VALOR = re.compile(r"^(AM\d+(\.\d+)?|MY\d+|G\d)$")


def palabras(texto, familia=""):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\(.*?\)|\*", " ", t)
    t = re.sub(r"(?<=[0-9])(?=[A-Z])|(?<=[A-Z])(?=[0-9])", " ", t)  # 200TSI -> 200 TSI
    t = t.replace("4 X 2", "4X2").replace("4 X 4", "4X4")
    fam = set(re.findall(r"[A-Z0-9+.]+", unicodedata.normalize("NFKD", familia).encode("ascii", "ignore").decode().upper()))
    return {SINONIMOS.get(p, p) for p in re.findall(r"[A-Z0-9+.]+", t)
            if not SIN_VALOR.match(p) and p not in fam and p not in {"PICK", "UP", "-"}}


def model(dbt, session):
    dbt.config(materialized="table")
    # Las llamadas a dbt.ref van solas (ver int_service_familia.py).
    fichas = dbt.ref("stg_equipamiento__items").df()
    fichas = fichas[["marca", "familia", "version_fuente", "orden_version"]].drop_duplicates()
    dim = dbt.ref("dim_version").df()
    dim = dim[dim["cca_modelo"].notna()].copy()
    dim["marca_cca"] = dim["cca_marca"].str.upper()

    filas = []
    for marca, familia, version, orden in fichas.itertuples(index=False):
        buscadas = palabras(version, familia)
        candidatas = dim[(dim["marca_cca"] == marca) & (dim["cca_modelo"] == familia)]
        cumplen = [r for r in candidatas.itertuples() if buscadas and buscadas <= palabras(r.modelo, familia)]
        elegida = max(cumplen, key=lambda r: r.inscripciones_12m or 0) if cumplen else None
        filas.append({
            "marca": marca, "familia": familia, "version_fuente": version, "orden_version": orden,
            "origen_codigo": elegida.origen_codigo if elegida else None,
            "marca_codigo": elegida.marca_codigo if elegida else None,
            "tipo_codigo": elegida.tipo_codigo if elegida else None,
            "modelo_codigo": elegida.modelo_codigo if elegida else None,
            "modelo_dnrpa": elegida.modelo if elegida else None,
            "candidatas": len(cumplen),
        })
    return pd.DataFrame(filas)
