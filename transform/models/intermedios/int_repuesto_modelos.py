"""
Cruce de cada repuesto con las familias de modelo de la guia CCA (las mismas
con las que cruzan patentamientos y service), leyendo el TITULO.

Los titulos nombran la compatibilidad en texto libre y suelen listar varios
modelos ("Filtro Habitaculo Hilux/corolla/yaris", "Kit Lara Filtros
Pal/siena 1.0/1.3"): sale una fila por cada familia encontrada.

Reglas (medidas en la Fase 0, fase0/06_repuestos.md):
  - Una familia se encuentra si TODAS sus palabras aparecen seguidas en el
    titulo (con barra y guion como separadores), con la normalizacion de ingesta/texto.py ("C 3" y "C3" cruzan).
    Si una familia esta contenida en otra en el mismo lugar ("GOL" dentro de
    "GOL TREND"), queda solo la mas larga.
  - Si el producto trae la marca del auto (78%), se busca solo entre sus
    familias ('marca_auto'). Si no la trae, se acepta una familia solo cuando su
    nombre existe en una unica marca ('sin_marca'): "Corsa" es Chevrolet, pero
    "Sport" o "Classic" podrian ser de varias. Ademas, sin marca la familia
    tiene que tener una palabra de 4 letras o mas: "D20" o "X 30" cruzaban con
    medidas y codigos de pieza.
  - Palabras que en un repuesto significan otra cosa ("PLUS", "SPORT",
    "ORIGINAL"...) no cuentan como familia de una sola palabra.

Lo que no resuelve (abreviaturas "Hil", "Meg", palabras pegadas "Vwpolo") queda
para el paso con IA. Grano: sku x familia, solo productos de mantenimiento.
"""

import os
import re
import sys

import pandas as pd

NO_SON_MODELO = {"PLUS", "SPORT", "FULL", "PACK", "SERIE", "SE", "S", "GL", "GLS", "XL", "LX", "EX", "SR",
                 "CARGO", "VAN", "D", "TD", "TDI", "HDI", "DIESEL", "NAFTA", "MAX", "PRO", "CITY", "TOP",
                 "AT", "MT", "CVT", "4X4", "4X2", "BASE", "ORIGINAL", "ACTIVE", "TREND", "SPORTLINE",
                 "KIT", "CLASSIC", "UP"}


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.getcwd())
    from ingesta.texto import clave_marca, norm, sin_marca

    productos = dbt.ref("stg_repuestos__productos").df()
    productos = productos[productos["es_vigente"] & (productos["tipo_pieza"] != "otro")]
    cca = dbt.ref("stg_cca__precios").df()
    cca = cca[cca["periodo"] == cca["periodo"].max()]

    # familia -> palabras normalizadas, por marca
    familias = {}
    for marca, modelo in cca[["marca", "modelo"]].drop_duplicates().itertuples(index=False):
        palabras = tuple(sin_marca(modelo, marca).split())
        if not palabras or (len(palabras) == 1 and (palabras[0] in NO_SON_MODELO or len(palabras[0]) < 2)):
            continue
        familias.setdefault(clave_marca(marca), (marca, {}))[1][palabras] = modelo
    marcas_por_familia = {}
    for clave, (_, fams) in familias.items():
        for palabras in fams:
            marcas_por_familia.setdefault(palabras, set()).add(clave)

    def buscar(titulo_palabras, fams):
        """(posicion, largo, palabras) de cada familia presente en el titulo."""
        hallazgos = []
        n = len(titulo_palabras)
        for palabras in fams:
            k = len(palabras)
            for i in range(n - k + 1):
                if tuple(titulo_palabras[i:i + k]) == palabras:
                    hallazgos.append((i, k, palabras))
        # Quitar las contenidas en otra mas larga en el mismo tramo.
        return [h for h in hallazgos
                if not any(o[0] <= h[0] and h[0] + h[1] <= o[0] + o[1] and o[1] > h[1] for o in hallazgos)]

    filas = []
    for p in productos.itertuples(index=False):
        # En los titulos la barra y el guion separan modelos ("Vento/passat", "C3-c4");
        # norm() conserva la barra, asi que se pasan a espacio antes.
        palabras = norm(re.sub(r"[/\-+*=]", " ", p.titulo)).split()
        if isinstance(p.marca_auto, str) and clave_marca(p.marca_auto) in familias:
            marca, fams = familias[clave_marca(p.marca_auto)]
            for _, _, f in buscar(palabras, fams):
                filas.append({"sku": p.sku, "cca_marca": marca, "familia": fams[f], "metodo": "marca_auto"})
        elif not isinstance(p.marca_auto, str):
            # Sin marca, los nombres tipo codigo ("D20", "X 30", "118", "X2") cruzan con
            # medidas y codigos de pieza: se exige una palabra de 4 letras o mas.
            unicas = {f: next(iter(m)) for f, m in marcas_por_familia.items()
                      if len(m) == 1 and any(w.isalpha() and len(w) >= 4 for w in f)}
            vistos = set()
            for _, _, f in buscar(palabras, unicas):
                marca, fams = familias[unicas[f]]
                if (marca, fams[f]) not in vistos:
                    vistos.add((marca, fams[f]))
                    filas.append({"sku": p.sku, "cca_marca": marca, "familia": fams[f], "metodo": "sin_marca"})
    return pd.DataFrame(filas, columns=["sku", "cca_marca", "familia", "metodo"]).drop_duplicates()
