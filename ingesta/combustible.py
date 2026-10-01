"""
Ingesta de combustible.

1. Precios y volumenes por estacion y mes (Res. 1104/2004)
   -> datos/raw/combustible/precios_1104/<AAAAMM>.parquet
   Es la fuente principal: la Res. 717/2025 derogo la obligacion de informar en
   tiempo real (Res. 314) y desde julio de 2025 casi nadie lo hace. La 1104 sigue
   vigente y la declaran ~4.500 estaciones por mes, YPF incluida.

2. Estaciones con coordenadas (Res. 314/2016, vigentes + historico)
   -> datos/raw/combustible/estaciones.parquet
   La 1104 no trae coordenadas; el numero de estacion es el mismo en las dos.

Decisiones:
- Dos esquemas: los archivos anuales (hasta 2024) traen anio/mes, "no_novimientos"
  (sic) y "exentos"; el de "desde diciembre 2024" trae periodo, "no_movimientos",
  "excentos" y el desglose de impuestos. Se llevan a un esquema comun; los
  impuestos quedan nulos donde no existen.
- Diciembre 2024 esta en los dos. Se procesan los anuales primero y el reciente
  al final, asi gana el que trae impuestos.
- Un archivo por mes, que se pisa al reprocesar: correr dos veces da lo mismo.
  Se reprocesa un recurso solo si cambio su fecha de modificacion en el catalogo.

Uso: python -m ingesta.combustible [--desde 2018]
"""

import argparse
import json
import os
import re

import duckdb

from ingesta.comun import pedir, recursos_ckan

BASE = "http://datos.energia.gob.ar"
DATASET_1104 = "708f9ab4-829b-4f02-b507-f303c5bc4800"
DATASET_314 = "precios-en-surtidor"
RAIZ = os.path.join("datos", "raw", "combustible")
ESTADO = os.path.join(RAIZ, "_estado.json")
IMPUESTOS = ["impuesto_combustible_liquidos", "impuesto_dioxido_carbono", "tasa_vial",
             "tasa_municipal", "ingresos_brutos", "iva", "fondo_fiduciario_GNC"]


def leer_estado():
    return json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}


def guardar_estado(estado):
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, sort_keys=True)


def bajar(url, nombre):
    """Baja a un temporal en disco (son archivos de hasta ~120 MiB)."""
    ruta = os.path.join(RAIZ, f"_tmp_{nombre}.csv")
    with open(ruta, "wb") as f:
        f.write(pedir(url, timeout=900))
    return ruta


def normalizar_1104(con, csv):
    """Lleva cualquiera de los dos esquemas a uno comun, en la tabla temporal t."""
    cols = con.sql(f"SELECT * FROM read_csv('{csv}', all_varchar=true) LIMIT 0").columns
    cols = [c.lstrip("﻿") for c in cols]
    if "periodo" in cols:
        periodo = "replace(periodo, '/', '')"
    else:
        periodo = "anio || lpad(mes, 2, '0')"
    no_mov = "no_movimientos" if "no_movimientos" in cols else "no_novimientos"
    exentos = "excentos" if "excentos" in cols else "exentos"
    impuestos = ", ".join(
        f"try_cast({c} AS DOUBLE) AS {c}" if c in cols else f"CAST(NULL AS DOUBLE) AS {c}" for c in IMPUESTOS)
    con.sql(f"""CREATE OR REPLACE TEMP TABLE t AS
        SELECT {periodo} AS periodo, operador, try_cast(nro_inscripcion AS BIGINT) AS nro_inscripcion, bandera,
               fecha_de_baja, cuit, tipo_negocio, direccion, localidad, provincia, producto, canal_de_comercializacion,
               try_cast(precio_sin_impuestos AS DOUBLE) AS precio_sin_impuestos,
               try_cast(precio_con_impuestos AS DOUBLE) AS precio_con_impuestos,
               try_cast(volumen AS DOUBLE) AS volumen,
               try_cast(precio_surtidor AS DOUBLE) AS precio_surtidor,
               {no_mov} AS no_movimientos, {exentos} IN ('t', 'true', 'True', '1') AS exentos,
               {impuestos}
        FROM read_csv('{csv}', all_varchar=true, normalize_names=false)""")


def ingerir_1104(estado, desde):
    destino = os.path.join(RAIZ, "precios_1104")
    os.makedirs(destino, exist_ok=True)
    con = duckdb.connect()
    recursos = [r for r in recursos_ckan(BASE, DATASET_1104) if r["nombre"].startswith("Precios EESS")]

    def orden(r):
        """Anuales por anio, y el de "desde Diciembre2024" al final.

        Se reconoce por "desde" y no por el anio: su nombre TAMBIEN termina en
        2024 y empataba con el anual de 2024. Asi se proceso primero y el anual
        lo piso, dejando diciembre 2024 sin el desglose de impuestos.
        """
        if "desde" in r["nombre"].lower():
            return 9999
        m = re.search(r"(20\d\d)\s*$", r["nombre"])
        return int(m[1]) if m else 9999

    for r in sorted(recursos, key=orden):
        anio = orden(r)
        if anio != 9999 and anio < desde:
            continue
        clave = f"1104/{r['nombre']}"
        if estado.get(clave) == r["modificado"]:
            print(f"{clave}: sin cambios ({r['modificado'][:10]})")
            continue
        csv = bajar(r["url"], "1104")
        try:
            normalizar_1104(con, csv)
        finally:
            os.remove(csv)
        periodos = [p for (p,) in con.sql("SELECT DISTINCT periodo FROM t WHERE periodo IS NOT NULL ORDER BY 1").fetchall()]
        for p in periodos:
            con.sql(f"COPY (SELECT * FROM t WHERE periodo = '{p}') TO '{os.path.join(destino, p + '.parquet')}' "
                    "(FORMAT parquet, COMPRESSION zstd)")
        filas = con.sql("SELECT count(*) FROM t").fetchone()[0]
        estado[clave] = r["modificado"]
        guardar_estado(estado)
        print(f"{clave}: {filas:,} filas en {len(periodos)} meses ({periodos[0]}..{periodos[-1]})")


def ingerir_estaciones(estado):
    """Una fila por estacion: la ubicacion mas reciente que informo a la Res. 314."""
    recursos = [r for r in recursos_ckan(BASE, DATASET_314) if r["formato"] == "CSV"]
    clave = "314/" + "|".join(sorted(r["modificado"] for r in recursos))
    if estado.get("314") == clave:
        print("estaciones: sin cambios")
        return
    con = duckdb.connect()
    partes = []
    for r in recursos:
        csv = bajar(r["url"], "314_" + r["id"][:8])
        partes.append(csv)
    try:
        fuentes = " UNION ALL ".join(
            f"""SELECT try_cast(idempresa AS BIGINT) AS nro_inscripcion, empresa, direccion, localidad, provincia,
                       empresabandera AS bandera, try_cast(latitud AS DOUBLE) AS latitud, try_cast(longitud AS DOUBLE) AS longitud,
                       coalesce(try_strptime(fecha_vigencia, '%d/%m/%Y %H:%M'), try_cast(fecha_vigencia AS TIMESTAMP)) AS fecha
                FROM read_csv('{p}', all_varchar=true)""" for p in partes)
        con.sql(f"""COPY (
              SELECT * EXCLUDE (fecha), fecha AS ultima_informacion FROM ({fuentes})
              WHERE nro_inscripcion IS NOT NULL AND latitud BETWEEN -56 AND -21 AND longitud BETWEEN -74 AND -53
                AND fecha <= current_date
              QUALIFY row_number() OVER (PARTITION BY nro_inscripcion ORDER BY fecha DESC) = 1
            ) TO '{os.path.join(RAIZ, 'estaciones.parquet')}' (FORMAT parquet)""")
    finally:
        for p in partes:
            os.remove(p)
    n = con.sql(f"SELECT count(*) FROM '{os.path.join(RAIZ, 'estaciones.parquet')}'").fetchone()[0]
    estado["314"] = clave
    guardar_estado(estado)
    print(f"estaciones: {n:,} con coordenadas validas")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2018)
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = leer_estado()
    ingerir_1104(estado, args.desde)
    ingerir_estaciones(estado)


if __name__ == "__main__":
    main()
