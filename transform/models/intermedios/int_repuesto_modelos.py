"""
Cruce de cada repuesto con las familias de modelo, leyendo el TITULO.

Los titulos nombran la compatibilidad en texto libre y suelen listar varios
modelos ("Filtro Habitaculo Hilux/corolla/yaris"): sale una fila por familia.

Catalogo de nombres por marca (columna `origen`):
  'cca'    familias de la guia CCA, las mismas con las que cruzan
           patentamientos y service;
  'dnrpa'  raices de modelo de DNRPA con 1.000 tramites o mas que la guia ya no
           lista o lista solo "con apellido" (Corsa, Duna, Escort; "Megane"
           a secas, porque la CCA solo tiene "MEGANE III"). Solo raices con 3
           letras o mas: "19" o "12" (Renault) cruzarian con cualquier numero;
  'alias'  abreviaturas de los titulos (seed alias_modelos, fuente
           'repuestos'): "Hil" = Hilux, "Xsa" = Xsara, "R19" = 19.

Reglas (medidas en la Fase 0 y en los casos fallidos, ver README):
  - Una familia se encuentra si todas sus palabras aparecen seguidas en el
    titulo, con barra y guion como separadores ("Vento/passat/tiguan") y la
    normalizacion de ingesta/texto.py ("C 3" y "C3" cruzan). Si una esta
    contenida en otra en el mismo tramo ("GOL" en "GOL TREND"), queda la mas
    larga.
  - Con marca del auto (78% de los productos) se busca entre sus nombres
    ('marca_auto'). Si no aparece nada, o el producto no trae marca, se acepta
    un nombre solo si existe en una unica marca ('sin_marca'), no es una
    palabra que en un repuesto significa otra cosa ("PLUS", "SPORT") y tiene
    una palabra con 3 letras o mas y largo 4 o mas: "D20", "X 30" o "118"
    cruzaban con medidas y codigos de pieza; "RAV4" si pasa. El caso
    "con marca y sin cruce" existe: hay productos con la marca mal cargada
    ("Corolla" etiquetado como Peugeot).

Grano: sku x familia, solo productos de mantenimiento de la foto vigente.
"""

import os
import re
import sys

import pandas as pd

NO_SON_MODELO = {"PLUS", "SPORT", "FULL", "PACK", "SERIE", "SE", "S", "GL", "GLS", "XL", "LX", "EX", "SR",
                 "CARGO", "VAN", "D", "TD", "TDI", "HDI", "DIESEL", "NAFTA", "MAX", "PRO", "CITY", "TOP",
                 "AT", "MT", "CVT", "4X4", "4X2", "BASE", "ORIGINAL", "ACTIVE", "TREND", "SPORTLINE",
                 "KIT", "CLASSIC", "UP", "SUPER", "ULTRA", "MOTOR", "FIRE"}
MIN_TRAMITES_DNRPA = 1000


def letras(palabra):
    return sum(ch.isalpha() for ch in palabra)


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.getcwd())
    from ingesta.texto import clave_marca, norm, sin_marca

    productos = dbt.ref("stg_repuestos__productos").df()
    productos = productos[productos["es_vigente"] & (productos["tipo_pieza"] != "otro")]
    cca = dbt.ref("stg_cca__precios").df()
    cca = cca[cca["periodo"] == cca["periodo"].max()]
    versiones = dbt.ref("int_versiones").df()
    alias = dbt.ref("alias_modelos").df()

    # catalogo[clave_marca] = (marca_mostrada, {palabras: (familia, origen)})
    catalogo = {}

    def agregar(marca, palabras, familia, origen):
        nombres = catalogo.setdefault(clave_marca(marca), (marca, {}))[1]
        nombres.setdefault(palabras, (familia, origen))

    for marca, modelo in cca[["marca", "modelo"]].drop_duplicates().itertuples(index=False):
        palabras = tuple(sin_marca(modelo, marca).split())
        if palabras and not (len(palabras) == 1 and len(palabras[0]) < 2):
            agregar(marca, palabras, modelo, "cca")
    for a in alias[alias["fuente"] == "repuestos"].itertuples(index=False):
        agregar(a.marca, tuple(norm(a.modelo_dnrpa).split()), a.modelo_fuente, "alias")
    raices = (versiones[versiones["segmento"] == "liviano"]
              .assign(raiz=lambda d: [(sin_marca(m or "", ma or "").split() or [""])[0]
                                      for m, ma in zip(d["modelo"], d["marca"])])
              .groupby(["marca", "raiz"], as_index=False)["tramites"].sum())
    for r in raices[raices["tramites"] >= MIN_TRAMITES_DNRPA].itertuples(index=False):
        if letras(r.raiz) >= 3 and r.raiz not in NO_SON_MODELO:
            # Se muestra con la marca de la CCA si existe, para agrupar bien.
            marca = catalogo.get(clave_marca(r.marca), (r.marca, {}))[0]
            agregar(marca, (r.raiz,), r.raiz, "dnrpa")

    # Nombres que existen en una sola marca y no parecen codigos: los unicos que
    # se aceptan sin marca del auto.
    marcas_por_nombre = {}
    for clave, (_, nombres) in catalogo.items():
        for palabras in nombres:
            marcas_por_nombre.setdefault(palabras, set()).add(clave)
    sin_marca_ok = {p: next(iter(m)) for p, m in marcas_por_nombre.items()
                    if len(m) == 1 and not (len(p) == 1 and p[0] in NO_SON_MODELO)
                    and any(letras(w) >= 3 and len(w) >= 4 for w in p)}

    def buscar(titulo, nombres):
        hallazgos = []
        n = len(titulo)
        for palabras in nombres:
            k = len(palabras)
            for i in range(n - k + 1):
                if tuple(titulo[i:i + k]) == palabras:
                    hallazgos.append((i, k, palabras))
        return [h for h in hallazgos
                if not any(o[0] <= h[0] and h[0] + h[1] <= o[0] + o[1] and o[1] > h[1] for o in hallazgos)]

    filas = []
    for p in productos.itertuples(index=False):
        # norm() conserva la barra: en los titulos separa modelos, se pasa a espacio.
        titulo = norm(re.sub(r"[/\-+*=]", " ", p.titulo)).split()
        encontrados = []
        if isinstance(p.marca_auto, str) and clave_marca(p.marca_auto) in catalogo:
            marca, nombres = catalogo[clave_marca(p.marca_auto)]
            encontrados = [(marca, *nombres[f], "marca_auto") for _, _, f in buscar(titulo, nombres)]
        if not encontrados:
            for _, _, f in buscar(titulo, sin_marca_ok):
                marca, nombres = catalogo[sin_marca_ok[f]]
                encontrados.append((marca, *nombres[f], "sin_marca"))
        for marca, familia, origen, metodo in encontrados:
            filas.append({"sku": p.sku, "cca_marca": marca, "familia": familia, "origen": origen, "metodo": metodo})
    return (pd.DataFrame(filas, columns=["sku", "cca_marca", "familia", "origen", "metodo"])
            .drop_duplicates(["sku", "cca_marca", "familia"]))
