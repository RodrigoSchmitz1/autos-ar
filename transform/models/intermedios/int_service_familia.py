"""
Cruce de cada modelo de las listas de service con su familia (modelo de la
guia CCA), para unirlo con el resto del catalogo.

Las listas de service nombran por familia y a veces por motor ("Nueva Strada
1.0T", "Toro Diesel", "Grand Cherokee SRT"); la CCA, por familia ("STRADA PICK -
UP", "TORO PICK UP"). Se usa la misma normalizacion y prefijo que el catalogo
(ingesta/texto.py) y la misma tabla de alias (fuente = 'service').

Grano: marca x modelo de la fuente.
"""

import os
import sys

import pandas as pd


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.getcwd())
    from ingesta.texto import candidatos_por_prefijo, clave_marca, norm, sin_marca

    # La llamada a dbt.ref va sola: encadenada con [[...]] dbt no la detectaba
    # al armar las dependencias y el modelo fallaba con KeyError.
    service = dbt.ref("stg_service__precios").df()
    service = service[["marca", "modelo_fuente"]].drop_duplicates()
    cca = dbt.ref("stg_cca__precios").df()
    cca = cca[cca["periodo"] == cca["periodo"].max()]
    modelos = {}
    for marca, modelo in cca[["marca", "modelo"]].drop_duplicates().itertuples(index=False):
        modelos.setdefault(clave_marca(marca), (marca, set()))[1].add(modelo)

    alias = {}
    for a in dbt.ref("alias_modelos").df().itertuples(index=False):
        if a.fuente == "service":
            alias.setdefault(clave_marca(a.marca), []).append((norm(a.modelo_dnrpa).split(), a.modelo_fuente))

    filas = []
    for s in service.itertuples(index=False):
        marca_cca, candidatos_marca = modelos.get(clave_marca(s.marca), (None, set()))
        palabras = sin_marca(s.modelo_fuente, s.marca).split()
        por_alias = next((m for p, m in alias.get(clave_marca(s.marca), []) if palabras[:len(p)] == p), None)
        candidatos = [por_alias] if por_alias in candidatos_marca else candidatos_por_prefijo(s.modelo_fuente, s.marca, candidatos_marca)
        filas.append({
            "marca": s.marca, "modelo_fuente": s.modelo_fuente,
            "cca_marca": marca_cca if candidatos else None,
            "familia": candidatos[0] if candidatos else None,
            "metodo": (None if not candidatos else "alias" if por_alias in candidatos_marca
                       else "prefijo" if len(candidatos) == 1 else "prefijo_ambiguo"),
        })
    return pd.DataFrame(filas)
