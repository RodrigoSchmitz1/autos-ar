"""
Ingesta de los microdatos de DNRPA: inscripciones iniciales, transferencias,
prendas y robos/recuperos de autos.

Salida: datos/raw/dnrpa/<dataset>/<AAAAMM>.parquet, un archivo por mes.

Decisiones:
- Fuente: los ZIP anuales, que traen un CSV por mes. DNRPA REVISA anios
  cerrados (el ZIP de 2025 se modifico en agosto de 2026), asi que no alcanza
  con bajar "el mes nuevo": se guarda la fecha de modificacion de cada ZIP y,
  si cambia, se reprocesa el anio entero. Rehacer un mes pisa su archivo:
  correr dos veces da el mismo resultado.
- Privacidad: lista BLANCA de columnas. Se guarda lo del tramite y el auto, y
  del titular solo si es persona fisica o juridica. Cualquier columna nueva que
  DNRPA agregue queda afuera sola, sin depender de acordarse de excluirla.
- El periodo sale de los datos (tramite_fecha), no del nombre del archivo, que
  es irregular ("...2018-09.csv"). Si un CSV mezcla meses, falla.
- Todo se lee como texto: los codigos ("05", "D85") no son numeros.

Uso: python -m ingesta.dnrpa [--datasets inscripciones,transferencias] [--anios 2025,2026]
"""

import argparse
import io
import json
import os
import re
import zipfile

import duckdb

from ingesta.comun import pedir, recursos_ckan

BASE = "https://datos.jus.gob.ar"
DATASETS = {
    "inscripciones": "inscripciones-iniciales-de-autos",
    "transferencias": "transferencias-de-autos",
    "prendas": "prendas-de-autos",
    "robos": "robos-y-recuperos-de-autos",
}
COLUMNAS = [
    "tramite_tipo", "tramite_fecha", "fecha_inscripcion_inicial",
    "registro_seccional_codigo", "registro_seccional_descripcion", "registro_seccional_provincia",
    "automotor_origen", "automotor_anio_modelo",
    "automotor_tipo_codigo", "automotor_tipo_descripcion",
    "automotor_marca_codigo", "automotor_marca_descripcion",
    "automotor_modelo_codigo", "automotor_modelo_descripcion",
    "automotor_uso_codigo", "automotor_uso_descripcion",
    "titular_tipo_persona",
]
RAIZ = os.path.join("datos", "raw", "dnrpa")
ESTADO = os.path.join(RAIZ, "_estado.json")


def leer_estado():
    if os.path.exists(ESTADO):
        return json.load(open(ESTADO, encoding="utf-8"))
    return {}


def guardar_estado(estado):
    os.makedirs(RAIZ, exist_ok=True)
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, sort_keys=True)


def anio_del_zip(nombre):
    m = re.search(r"(20\d\d)\s*$", nombre)
    return int(m[1]) if m else None


def procesar_csv(con, contenido, destino_dir):
    """Un CSV mensual -> Parquet con la lista blanca. Devuelve (periodo, filas)."""
    tmp = os.path.join(destino_dir, "_tmp.csv")
    with open(tmp, "wb") as f:
        f.write(contenido)
    try:
        presentes = con.sql(f"SELECT * FROM read_csv('{tmp}', all_varchar=true, header=true) LIMIT 0").columns
        faltan = [c for c in COLUMNAS if c not in presentes]
        if faltan:
            raise ValueError(f"faltan columnas obligatorias: {faltan}")
        con.sql(f"""CREATE OR REPLACE TEMP TABLE mes AS
            SELECT * REPLACE (
                     try_cast(tramite_fecha AS DATE) AS tramite_fecha,
                     try_cast(fecha_inscripcion_inicial AS DATE) AS fecha_inscripcion_inicial,
                     try_cast(automotor_anio_modelo AS INTEGER) AS automotor_anio_modelo)
            FROM (SELECT {', '.join(COLUMNAS)} FROM read_csv('{tmp}', all_varchar=true, header=true))""")
    finally:
        os.remove(tmp)
    meses = con.sql("SELECT DISTINCT strftime(tramite_fecha, '%Y%m') FROM mes WHERE tramite_fecha IS NOT NULL").fetchall()
    if len(meses) != 1:
        raise ValueError(f"el CSV no corresponde a un solo mes: {sorted(m[0] for m in meses)}")
    periodo = meses[0][0]
    filas = con.sql("SELECT count(*) FROM mes").fetchone()[0]
    con.sql(f"COPY mes TO '{os.path.join(destino_dir, periodo + '.parquet')}' (FORMAT parquet, COMPRESSION zstd)")
    return periodo, filas


def ingerir(datasets, anios=None):
    estado = leer_estado()
    con = duckdb.connect()
    for corto in datasets:
        destino = os.path.join(RAIZ, corto)
        os.makedirs(destino, exist_ok=True)
        zips = [r for r in recursos_ckan(BASE, DATASETS[corto]) if r["formato"] == "ZIP" and anio_del_zip(r["nombre"])]
        for r in sorted(zips, key=lambda r: anio_del_zip(r["nombre"])):
            anio = anio_del_zip(r["nombre"])
            if anios and anio not in anios:
                continue
            clave = f"{corto}/{anio}"
            if estado.get(clave) == r["modificado"]:
                print(f"{clave}: sin cambios ({r['modificado'][:10]})")
                continue
            zf = zipfile.ZipFile(io.BytesIO(pedir(r["url"])))
            resumen = []
            for info in sorted(zf.infolist(), key=lambda i: i.filename):
                if not info.filename.lower().endswith(".csv"):
                    continue
                periodo, filas = procesar_csv(con, zf.read(info), destino)
                resumen.append(f"{periodo}:{filas}")
            estado[clave] = r["modificado"]
            guardar_estado(estado)  # despues de cada anio: si se corta, no se pierde lo hecho
            print(f"{clave}: {len(resumen)} meses ({', '.join(resumen)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default=",".join(DATASETS))
    ap.add_argument("--anios", default="")
    args = ap.parse_args()
    anios = {int(a) for a in args.anios.split(",") if a}
    ingerir(args.datasets.split(","), anios or None)


if __name__ == "__main__":
    main()
