"""
Ingesta del consumo homologado por modelo (etiqueta de eficiencia vehicular).

Salida: datos/raw/consumo/ensayos_20220609.parquet

El dataset oficial ya no existe: el link de datos.gob.ar da 404 y el portal de
Ambiente que alojaba el CSV (datos.ambiente.gob.ar) fue dado de baja. Se usa la
ultima copia completa guardada en el Internet Archive (9 de junio de 2022):
811 ensayos, 489 modelos. Los modelos lanzados despues no estan; para eso queda
el pedido de acceso a la informacion publica (Ley 27.275). Ver fase0/02_acceso.md.

Es una fuente congelada: se ingiere una vez y no se vuelve a pedir.

Uso: python -m ingesta.consumo
"""

import csv
import io
import os

import duckdb
import pandas as pd

from ingesta.comun import pedir

URL = ("https://web.archive.org/web/20220615112830id_/https://datos.ambiente.gob.ar/dataset/"
       "501cb1f2-781d-44d0-9f91-4984587bbe35/resource/fc0039f7-bb75-4960-9a33-3a51955c8e9f/"
       "download/ensayos_co2_consumos_09062022.csv")
DESTINO = os.path.join("datos", "raw", "consumo", "ensayos_20220609.parquet")
COLUMNAS = ["vehiculo_marca", "vehiculo_modelo", "vehiculo_tipo", "vehiculo_traccion", "vehiculo_id_motor",
            "vehiculo_cilindrada", "vehiculo_potencia", "vehiculo_tipo_transmision", "vehiculo_tipo_combustible",
            "vehiculo_standard_emision", "lca_numero", "fecha_firma", "ensayo_gei_numero", "ensayo_gei_laboratorio",
            "emision_CO2", "consumo_urbano", "consumo_extraurbano", "consumo_mixto", "id_etiqueta",
            "eficiencia_categoria"]


def main():
    if os.path.exists(DESTINO):
        print("consumo: ya ingerido (fuente congelada)")
        return
    # latin-1 y con csv de Python: DuckDB rechaza la codificacion del archivo.
    texto = pedir(URL).decode("latin-1")
    sep = ";" if texto[:500].count(";") > texto[:500].count(",") else ","
    filas = [{c: (r.get(c) or "").strip() or None for c in COLUMNAS}
             for r in csv.DictReader(io.StringIO(texto), delimiter=sep) if (r.get("vehiculo_marca") or "").strip()]
    if len(filas) < 800:
        raise RuntimeError(f"La copia tiene {len(filas)} ensayos; se esperaban 811")
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    con = duckdb.connect()
    con.register("t", pd.DataFrame(filas))
    con.sql(f"COPY t TO '{DESTINO}' (FORMAT parquet)")
    print(f"consumo: {len(filas)} ensayos")


if __name__ == "__main__":
    main()
