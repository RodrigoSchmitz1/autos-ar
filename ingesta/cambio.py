"""
Ingesta del tipo de cambio minorista (promedio vendedor, pesos por dolar) del
BCRA, para pasar a pesos las fuentes que publican en dolares (service de BYD).

Por que el minorista y no el mayorista: es lo que paga una persona. La serie es
el promedio vendedor de los bancos (Com. B 9791), no solo el Banco Nacion.

Salida: datos/raw/cambio/usd_minorista.parquet (fecha, valor), la serie entera
desde 2018. Se reescribe en cada corrida: son ~2.100 filas, y asi se corrigen
solas las revisiones que publique el BCRA.

Uso: python -m ingesta.cambio
"""

import json
import os
from datetime import date

import duckdb
import pandas as pd

from ingesta.comun import pedir

API = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/4"
DESDE = "2018-01-01"
POR_PAGINA = 1000
DESTINO = os.path.join("datos", "raw", "cambio", "usd_minorista.parquet")


def bajar():
    filas, offset = [], 0
    while True:
        d = json.loads(pedir(f"{API}?desde={DESDE}&hasta={date.today()}&limit={POR_PAGINA}&offset={offset}"))
        pagina = d["results"][0]["detalle"] if d["results"] else []
        filas += pagina
        offset += len(pagina)
        if not pagina or offset >= d["metadata"]["resultset"]["count"]:
            return filas


def validar(df):
    """La serie tiene que llegar hasta hace pocos dias y no tener saltos absurdos."""
    errores = []
    if len(df) < 1500:
        errores.append(f"solo {len(df)} dias")
    atraso = (pd.Timestamp(date.today()) - df["fecha"].max()).days
    if atraso > 7:
        errores.append(f"el ultimo dato es de hace {atraso} dias")
    if df["fecha"].duplicated().any():
        errores.append("fechas repetidas")
    salto = df.sort_values("fecha")["valor"].pct_change().abs().max()
    # La devaluacion de diciembre de 2023 fue de ~118% en un dia.
    if salto > 1.5:
        errores.append(f"salto diario de {salto:.0%}")
    if errores:
        raise RuntimeError("tipo de cambio: " + "; ".join(errores))


def main():
    df = pd.DataFrame(bajar())
    df["fecha"] = pd.to_datetime(df["fecha"])
    validar(df)
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    con = duckdb.connect()
    con.register("t", df)
    con.sql(f"COPY (SELECT fecha::DATE AS fecha, valor FROM t ORDER BY fecha) TO '{DESTINO}' (FORMAT parquet)")
    print(f"tipo de cambio: {len(df)} dias, ultimo {df['fecha'].max():%Y-%m-%d} = {df['valor'].iloc[df['fecha'].argmax()]}")


if __name__ == "__main__":
    main()
