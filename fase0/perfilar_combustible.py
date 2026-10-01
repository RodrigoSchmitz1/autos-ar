"""
Fase 0.7 - Perfil de las fuentes de precios de combustible.

  vigentes.csv   Res. 314/2016, "precios vigentes en surtidor" (por estacion)
  historicos.csv Res. 314/2016, historico 2017-2025
  eess_1104_desde_2024-12.csv  Res. 1104/2004, declaracion mensual por estacion

La pregunta que termino importando no era cuantas filas hay sino cuantas
estaciones INFORMAN: la Res. 717/2025 (2 de junio de 2025) derogo la obligacion
de la 314 y desde ese mes casi toda YPF dejo de reportar. "Vigente" pasa a
querer decir "el ultimo precio que informo", que puede ser de 2017.

Uso: python fase0/perfilar_combustible.py   (desde la raiz, con .venv; los
CSV se bajan con las URLs de 07_combustible.md a datos/combustible/)
"""

import duckdb

D = "datos/combustible"
con = duckdb.connect()
con.sql(f"CREATE VIEW vig AS SELECT * FROM read_csv('{D}/vigentes.csv', sample_size=-1) WHERE tipohorario = 'Diurno'")
con.sql(f"""CREATE VIEW his AS SELECT * REPLACE (try_strptime(fecha_vigencia, '%d/%m/%Y %H:%M') AS fecha_vigencia)
            FROM read_csv('{D}/historicos.csv', sample_size=200000)""")
con.sql(f"""CREATE VIEW r1104 AS SELECT * FROM read_csv('{D}/eess_1104_desde_2024-12.csv', sample_size=-1)
            WHERE canal_de_comercializacion = 'Al público'""")


def titulo(t):
    print(f"\n=== {t}")


titulo("Vigentes: antiguedad del ultimo precio por estacion")
print(con.sql("""WITH e AS (SELECT idempresa, any_value(empresabandera) b, max(fecha_vigencia) ult FROM vig GROUP BY 1)
    SELECT count(*) estaciones,
           count(*) FILTER (WHERE ult >= TIMESTAMP '2026-09-01') desde_septiembre,
           count(*) FILTER (WHERE ult < TIMESTAMP '2026-01-01') antes_de_2026,
           count(*) FILTER (WHERE b = 'YPF') ypf,
           count(*) FILTER (WHERE b = 'YPF' AND ult >= TIMESTAMP '2026-09-01') ypf_desde_septiembre
    FROM e"""))

titulo("Vigentes: mediana con y sin precios congelados")
print(con.sql("""SELECT producto, round(median(precio)) todas,
           round(median(precio) FILTER (WHERE fecha_vigencia >= TIMESTAMP '2026-09-01')) solo_septiembre
    FROM vig GROUP BY 1 ORDER BY 1"""))

titulo("Vigentes: coordenadas por estacion")
print(con.sql("""WITH e AS (SELECT idempresa, any_value(latitud) lat, any_value(longitud) lon FROM vig GROUP BY 1)
    SELECT count(*) estaciones, count(*) FILTER (WHERE lat IS NULL OR lon IS NULL) nulas,
           count(*) FILTER (WHERE lat BETWEEN -56 AND -21 AND lon BETWEEN -74 AND -53) dentro_de_argentina FROM e"""))

titulo("Historico 314: estaciones que informan por mes, alrededor de la derogacion")
print(con.sql("""SELECT strftime(fecha_vigencia, '%Y-%m') mes, count(DISTINCT idempresa) estaciones,
           count(DISTINCT idempresa) FILTER (WHERE empresabandera = 'YPF') ypf
    FROM his WHERE fecha_vigencia BETWEEN TIMESTAMP '2025-03-01' AND TIMESTAMP '2025-12-31 23:59' GROUP BY 1 ORDER BY 1"""))

titulo("Historico 314: fechas imposibles")
print(con.sql("""SELECT count(*) filas, count(*) FILTER (WHERE year(fecha_vigencia) < 2016) antes_de_2016,
           count(*) FILTER (WHERE fecha_vigencia > TIMESTAMP '2026-10-01') futuras FROM his"""))

titulo("Historico 314: cambios de precio de la super por estacion en 2024")
print(con.sql("""WITH c AS (SELECT idempresa, count(DISTINCT fecha_vigencia) cambios FROM his
        WHERE year(fecha_vigencia) = 2024 AND tipohorario = 'Diurno' AND producto LIKE 'Nafta (s%per)%' GROUP BY 1)
    SELECT count(*) estaciones, median(cambios) mediana, quantile_cont(cambios, 0.1) p10, quantile_cont(cambios, 0.9) p90 FROM c"""))

titulo("Res. 1104: estaciones que declaran por mes")
print(con.sql("""SELECT periodo, count(DISTINCT nro_inscripcion) estaciones,
           count(DISTINCT nro_inscripcion) FILTER (WHERE bandera = 'YPF') ypf,
           round(median(precio_surtidor) FILTER (WHERE producto LIKE 'Nafta (s%per)%')) super_mediana
    FROM r1104 GROUP BY 1 ORDER BY 1"""))

titulo("Res. 1104 vs vigentes: estaciones de 1104 que tienen coordenadas en vigentes")
print(con.sql("""WITH a AS (SELECT DISTINCT nro_inscripcion id FROM r1104 WHERE periodo = '2026/07'),
                     b AS (SELECT DISTINCT idempresa id FROM vig WHERE latitud IS NOT NULL)
    SELECT count(*) estaciones_1104, count(*) FILTER (WHERE id IN (SELECT id FROM b)) con_coordenadas FROM a"""))
