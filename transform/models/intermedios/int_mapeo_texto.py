"""
Cruce por texto de cada version con la guia CCA y con el consumo (etiqueta).

Ninguna de las dos fuentes tiene codigos: se cruza a nivel MODELO ("TERRITORY",
no "TERRITORY TREND 1.5 HIBRIDA") con la normalizacion y el prefijo de
ingesta/texto.py, medidos en la Fase 0 (fase0/05_matching.md).

Metodo por cruce:
  'alias'            la version empieza con un nombre de la tabla de alias
                     (seed alias_modelos: "SW4" -> "HILUX SW4"); pisa al prefijo
  'prefijo'          un solo modelo encaja
  'prefijo_ambiguo'  varios empatan ("HB 20" -> "HB20" y "HB20 SEDAN"); se
                     elige el nombre mas corto y se guardan los candidatos
  'excluido'         la tabla de alias dice "(sin familia)": el prefijo cruzaria
                     con otro auto ("MUSTANG MACH-E" con el Mustang V8)
  null               no cruza

Grano: una fila por version (llave DNRPA).
"""

import os
import sys

import pandas as pd


def model(dbt, session):
    dbt.config(materialized="table")
    # El modelo corre dentro del proceso de dbt, que se lanza desde la raiz del
    # repo: asi se usa la misma normalizacion que testea ingesta/test_texto.py.
    sys.path.insert(0, os.getcwd())
    from ingesta.texto import candidatos_por_prefijo, clave_marca, sin_marca, norm

    versiones = dbt.ref("int_versiones").df()
    cca = dbt.ref("stg_cca__precios").df()
    cca = cca[cca["periodo"] == cca["periodo"].max()]
    consumo = dbt.ref("stg_consumo__ensayos").df()

    def por_marca(df):
        indice = {}
        for marca, modelo in df[["marca", "modelo"]].drop_duplicates().itertuples(index=False):
            indice.setdefault(clave_marca(marca), (marca, set()))[1].add(modelo)
        return indice

    indices = {"cca": por_marca(cca), "consumo": por_marca(consumo)}
    alias = {}
    for a in dbt.ref("alias_modelos").df().itertuples(index=False):
        alias.setdefault((a.fuente, clave_marca(a.marca)), []).append((norm(a.modelo_dnrpa).split(), a.modelo_fuente))

    def por_alias(fuente, descripcion, marca):
        palabras = sin_marca(descripcion, marca).split()
        for prefijo, modelo_fuente in alias.get((fuente, clave_marca(marca)), []):
            if palabras[:len(prefijo)] == prefijo:
                return modelo_fuente
        return None
    filas = []
    for v in versiones.itertuples(index=False):
        fila = {c: getattr(v, c) for c in ("origen_codigo", "marca_codigo", "tipo_codigo", "modelo_codigo")}
        for fuente, indice in indices.items():
            marca_fuente, modelos = indice.get(clave_marca(v.marca), (None, set()))
            por_nombre = por_alias(fuente, v.modelo, v.marca)
            if por_nombre == "(sin familia)":
                candidatos = []
            elif por_nombre in modelos:
                candidatos = [por_nombre]
            else:
                candidatos = candidatos_por_prefijo(v.modelo, v.marca, modelos)
            fila[f"{fuente}_marca"] = marca_fuente if candidatos else None
            fila[f"{fuente}_modelo"] = candidatos[0] if candidatos else None
            fila[f"{fuente}_metodo"] = ("excluido" if por_nombre == "(sin familia)" else
                                        None if not candidatos else
                                        "alias" if por_nombre in modelos else
                                        "prefijo" if len(candidatos) == 1 else "prefijo_ambiguo")
            fila[f"{fuente}_candidatos"] = " | ".join(candidatos) if len(candidatos) > 1 else None
        filas.append(fila)
    return pd.DataFrame(filas)
