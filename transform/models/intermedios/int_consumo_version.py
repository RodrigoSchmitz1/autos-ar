"""
Consumo (l/100 km, ciclo mixto) de cada version liviana, para el costo por km.

La fuente (etiqueta de eficiencia, copia de 2022) cubre poco version por
version: "Cronos Drive" cruza y "Cronos Like" no, aunque es el mismo auto con
otro equipamiento; la Strada esta en los ensayos y ninguna de sus 34 versiones
cruzaba. Y no tiene los modelos lanzados despues de 2022 (Territory, Tera,
Kardian, BYD). Por eso una cascada, de lo mas preciso a lo mas general, y cada
fila dice con que nivel se estimo (`consumo_estimacion`):

  'version'          el cruce por texto de int_mapeo_texto (Fase 2);
  'familia_motor'    mediana de los ensayos de la misma familia CCA, mismo
                     combustible y misma cilindrada ("STRADA", nafta, 1.3);
  'familia'          mediana de la familia y el combustible;
  'cilindrada'       mediana de TODOS los ensayos con ese combustible y esa
                     cilindrada: estimacion gruesa, para modelos sin ensayos;
  null               sin estimacion (electricos, o sin cilindrada en el nombre).

Combustible y cilindrada salen de la descripcion de DNRPA: "2.8 TDI", "1.8L",
"HEV", o de codigos de motor conocidos ("170 TSI" = 1.0 turbo, "T270" = 1.3). Los hibridos se tratan como nafta con sus propios ensayos
(NAFTA/ELECTRICIDAD); los electricos puros no tienen consumo de combustible.

Grano: version (llave DNRPA).
"""

import os
import re
import sys

import pandas as pd

DIESEL = re.compile(r"\b(TDI|TD|TDCI|HDI|DCI|CRDI|JTD|MULTIJET|DIESEL|DSL|D|TDDI|SDI|BLUEHDI|CDI|MWM)\b")
HIBRIDO = re.compile(r"\b(HEV|HIBRID[OA]?|HYBRID|PHEV|DM I|MHEV|E TECH)\b")
ELECTRICO = re.compile(r"\b(EV|ELECTRIC[OA]?|BEV)\b")
CILINDRADA = re.compile(r"\b(\d)[.,](\d)\s*L?\b")


def limpio(texto):
    """Mayusculas, sin tildes y solo letras, numeros, punto y coma."""
    import unicodedata
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9.,]+", " ", t).split())


def combustible_de(texto):
    if ELECTRICO.search(texto) and not HIBRIDO.search(texto):
        return "electrico"
    if HIBRIDO.search(texto):
        return "hibrido"
    if DIESEL.search(texto):
        return "diesel"
    return "nafta"


# Motores que las versiones nombran por codigo y no por cilindrada.
CODIGOS_MOTOR = [
    (re.compile(r"\b(170|200) ?TSI\b"), "1.0"),   # VW 1.0 turbo (Tera, Nivus, Polo)
    (re.compile(r"\b250 ?TSI\b"), "1.4"),         # VW 1.4 turbo (Taos)
    (re.compile(r"\bMSI\b"), "1.6"),              # VW 1.6 (Polo Track, Tera MSI)
    (re.compile(r"\bT200\b"), "1.0"),             # Peugeot/Fiat 1.0 turbo
    (re.compile(r"\b(T270|TURBO 270)\b"), "1.3"), # Fiat/Jeep 1.3 turbo
]


def cilindrada_de(texto):
    m = CILINDRADA.search(texto)
    if m:
        return f"{m[1]}.{m[2]}"
    for patron, cil in CODIGOS_MOTOR:
        if patron.search(texto):
            return cil
    return None


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.getcwd())
    from ingesta.texto import candidatos_por_prefijo, clave_marca, norm

    versiones = dbt.ref("dim_version").df()
    versiones = versiones[versiones["segmento"] == "liviano"]
    ensayos = dbt.ref("stg_consumo__ensayos").df()
    cca = dbt.ref("stg_cca__precios").df()
    cca = cca[cca["periodo"] == cca["periodo"].max()]

    familias = {}
    for marca, modelo in cca[["marca", "modelo"]].drop_duplicates().itertuples(index=False):
        familias.setdefault(clave_marca(marca), set()).add(modelo)

    # Cada ensayo: familia CCA, combustible normalizado y cilindrada.
    def comb_ensayo(c):
        c = (c or "").upper()
        if "ELECTRICIDAD" in c and "NAFTA" in c:
            return "hibrido"
        if "ELECTRICIDAD" in c:
            return "electrico"
        if "GAS OIL" in c or "DIESEL" in c:
            return "diesel"
        return "nafta"

    filas_e = []
    for e in ensayos.itertuples(index=False):
        if pd.isna(e.consumo_mixto):
            continue
        cand = candidatos_por_prefijo(e.modelo, e.marca, familias.get(clave_marca(e.marca), set()))
        cil = f"{round(e.cilindrada_cc / 1000, 1):.1f}" if pd.notna(e.cilindrada_cc) and e.cilindrada_cc > 0 else cilindrada_de(limpio(e.modelo))
        filas_e.append({"marca": clave_marca(e.marca), "familia": cand[0] if cand else None,
                        "combustible": comb_ensayo(e.combustible), "cilindrada": cil,
                        "modelo": e.modelo, "consumo": float(e.consumo_mixto)})
    e = pd.DataFrame(filas_e)
    por_modelo = e.groupby(["marca", "modelo"])["consumo"].median().to_dict()
    por_fam_motor = e.dropna(subset=["familia", "cilindrada"]).groupby(["marca", "familia", "combustible", "cilindrada"])["consumo"].median().to_dict()
    por_fam = e.dropna(subset=["familia"]).groupby(["marca", "familia", "combustible"])["consumo"].median().to_dict()
    por_cil = e.dropna(subset=["cilindrada"]).groupby(["combustible", "cilindrada"])["consumo"].agg(["median", "count"])
    por_cil = {k: v["median"] for k, v in por_cil.iterrows() if v["count"] >= 5}

    filas = []
    for v in versiones.itertuples(index=False):
        # Sin norm(): pega "TDI 6" en "TDI6" y la diesel quedaba como nafta.
        texto = limpio(v.modelo)
        comb = combustible_de(texto)
        cil = cilindrada_de(texto)
        marca = clave_marca(v.marca or "")
        # Los hibridos se buscan con sus ensayos (nafta/electricidad) y, si no
        # hay, como nafta: el consumo de etiqueta del hibrido es menor.
        clave_comb = comb
        consumo, metodo = None, None
        if isinstance(v.consumo_modelo, str) and (marca, v.consumo_modelo) in por_modelo and comb != "electrico":
            consumo, metodo = por_modelo[(marca, v.consumo_modelo)], "version"
        elif comb != "electrico" and isinstance(v.cca_modelo, str):
            for c in ([clave_comb, "nafta"] if comb == "hibrido" else [clave_comb]):
                if cil and (marca, v.cca_modelo, c, cil) in por_fam_motor:
                    consumo, metodo = por_fam_motor[(marca, v.cca_modelo, c, cil)], "familia_motor"
                    break
            if consumo is None and (marca, v.cca_modelo, clave_comb) in por_fam:
                consumo, metodo = por_fam[(marca, v.cca_modelo, clave_comb)], "familia"
        if consumo is None and comb != "electrico" and cil and (clave_comb, cil) in por_cil:
            consumo, metodo = por_cil[(clave_comb, cil)], "cilindrada"
        filas.append({"origen_codigo": v.origen_codigo, "marca_codigo": v.marca_codigo,
                      "tipo_codigo": v.tipo_codigo, "modelo_codigo": v.modelo_codigo,
                      "combustible": comb, "cilindrada": cil,
                      "consumo_l100km": round(consumo, 2) if consumo is not None else None,
                      "consumo_estimacion": metodo})
    return pd.DataFrame(filas)
