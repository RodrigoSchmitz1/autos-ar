"""
Fase 0.4 - Perfil de un mes de DNRPA (lo que baja bajar_muestra.py).

Cada chequeo responde una pregunta que cambia como se cuenta o se guarda. De
las columnas del titular nunca se imprimen valores sueltos, solo conteos: no
traen nombre ni documento, pero localidad + genero + anio de nacimiento +
registro + fecha alcanzan para reconocer a alguien en un pueblo chico.

Uso: python fase0/perfilar_muestra.py   (desde la raiz, con .venv)
"""

import os

import duckdb

MUESTRA = "datos/muestra"
DATASETS = {
    "inscripciones": "inscripciones-iniciales-de-autos",
    "transferencias": "transferencias-de-autos",
    "prendas": "prendas-de-autos",
    "robos": "robos-y-recuperos-de-autos",
}
# Lo unico del titular que podria quedar: provincia y persona fisica/juridica.
# El resto se descarta en la ingesta.
COLUMNAS_TITULAR_DESCARTADAS = [
    "titular_domicilio_localidad", "titular_genero", "titular_anio_nacimiento",
    "titular_pais_nacimiento", "titular_pais_nacimiento_id", "titular_porcentaje_titularidad",
]

con = duckdb.connect()
for vista, archivo in DATASETS.items():
    con.sql(f"CREATE VIEW {vista} AS SELECT * FROM read_csv('{MUESTRA}/{archivo}.csv', sample_size=-1)")


def titulo(texto):
    print(f"\n=== {texto}")


titulo("Filas y esquema")
for vista in DATASETS:
    rel = con.sql(f"SELECT * FROM {vista}")
    n = con.sql(f"SELECT count(*) FROM {vista}").fetchone()[0]
    print(f"  {vista}: {n:,} filas, {len(rel.columns)} columnas")

titulo("Una fila = un auto? Las filas con 50% de titularidad, vienen de a pares?")
# Si cada fila fuera un titular, un auto con dos duenos al 50% apareceria dos
# veces con todo lo del tramite igual. Si casi siempre aparece una sola vez,
# la fila es el auto y el porcentaje es el del PRIMER titular.
print(con.sql("""
    WITH g AS (
        SELECT tramite_fecha, fecha_inscripcion_inicial, registro_seccional_codigo,
               automotor_marca_codigo, automotor_modelo_codigo, automotor_anio_modelo,
               tramite_tipo, automotor_uso_codigo, count(*) filas
        FROM inscripciones WHERE titular_porcentaje_titularidad = 50 GROUP BY ALL)
    SELECT filas AS filas_al_50_por_grupo, count(*) grupos FROM g GROUP BY 1 ORDER BY 1"""))

titulo("Contra la estadistica oficial de DNRPA (estadistica-de-tramites-de-automotores)")
if os.path.exists(f"{MUESTRA}/estadistica_inscripciones.csv"):
    print(con.sql(f"""
        SELECT (SELECT sum(cantidad_inscripciones_iniciales)
                FROM read_csv('{MUESTRA}/estadistica_inscripciones.csv', sample_size=-1)
                WHERE anio_inscripcion_inicial = 2026 AND mes_inscripcion_inicial = 8) AS oficial,
               (SELECT count(*) FROM inscripciones) AS filas,
               (SELECT round(sum(titular_porcentaje_titularidad) / 100) FROM inscripciones) AS suma_porcentajes"""))
else:
    print("  (falta estadistica_inscripciones.csv)")

titulo("Provincia del registro vs provincia del domicilio del titular")
# Normalizado (minusculas, sin tildes). Lo que sigue difiriendo, es otro lugar
# o es otra forma de escribir el mismo?
print(con.sql("""
    SELECT registro_seccional_provincia AS registro, titular_domicilio_provincia AS domicilio, count(*) n
    FROM inscripciones
    WHERE lower(strip_accents(registro_seccional_provincia)) <> lower(strip_accents(titular_domicilio_provincia))
    GROUP BY ALL ORDER BY n DESC"""))

titulo("Codigos vs descripciones de modelo")
for vista in ("inscripciones", "transferencias"):
    print(f"  {vista}:", con.sql(f"""
        SELECT count(DISTINCT (automotor_marca_codigo, automotor_modelo_codigo)) AS marca_modelo_codigos,
               count(DISTINCT (automotor_marca_descripcion, automotor_modelo_descripcion)) AS descripciones,
               round(100.0 * count(*) FILTER (WHERE automotor_modelo_codigo IS NULL) / count(*), 1) AS pct_sin_codigo
        FROM {vista}""").fetchone())

titulo("Espacio: CSV vs Parquet sin columnas del titular")
os.makedirs("datos/parquet_prueba", exist_ok=True)
excluir = ", ".join(COLUMNAS_TITULAR_DESCARTADAS)
for vista, archivo in DATASETS.items():
    destino = f"datos/parquet_prueba/{vista}.parquet"
    con.sql(f"COPY (SELECT * EXCLUDE ({excluir}) FROM {vista}) TO '{destino}' (FORMAT parquet, COMPRESSION zstd)")
    csv_mib = os.path.getsize(f"{MUESTRA}/{archivo}.csv") / 2**20
    pq_mib = os.path.getsize(destino) / 2**20
    print(f"  {vista}: CSV {csv_mib:.1f} MiB -> Parquet {pq_mib:.2f} MiB ({csv_mib / pq_mib:.0f}x)")
