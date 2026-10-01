"""
Fase 0.6 - Que se puede extraer de los repuestos relevados.

Dos preguntas del plan:
  1. De que porcentaje de titulos se puede sacar el modelo del auto.
     Catalogo de modelos por marca = nombres de DNRPA (0 km y usados del mes)
     + modelos de la guia CCA. Se busca cada palabra del titulo en el catalogo
     de la marca del auto (o en todos, si el producto no trae marca).
  2. Que porcentaje de SKUs sirve como llave para comparar original vs
     alternativo. El SKU es codigo base + sufijo del proveedor ("-H" Mahle,
     "O" original, "-E"/"-M"/"-T" importadores). Base compartida entre
     calidades distintas = pieza comparable.

Uso: python fase0/medir_repuestos.py [categoria]   (desde la raiz, con .venv)
"""

import re
import sys
import unicodedata

import duckdb

con = duckdb.connect()
categoria = sys.argv[1] if len(sys.argv) > 1 else "Filtros"
con.sql(f"CREATE VIEW r AS SELECT * FROM 'datos/repuestos/{categoria}.parquet'")

# Palabras que coinciden con nombres de modelo pero en un titulo de repuesto
# significan otra cosa ("FILTRO AIRE ... PLUS", "CLASSIC" es modelo de
# Chevrolet pero tambien aparece como linea de producto).
NO_SON_MODELO = {"PLUS", "SPORT", "FULL", "PACK", "SERIE", "SE", "S", "GL", "GLS", "XL", "LX", "EX", "SR",
                 "CARGO", "VAN", "D", "TD", "TDI", "HDI", "DIESEL", "NAFTA", "MAX", "PRO", "CITY", "TOP",
                 "AT", "MT", "CVT", "4X4", "4X2", "BASE", "ORIGINAL", "ACTIVE", "TREND", "SPORTLINE"}


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def marca_clave(m):
    return norm(m).replace(" ", "")


# ---------- Catalogo de modelos por marca: primera palabra del modelo ----------
catalogo = {}
for archivo in ("inscripciones-iniciales-de-autos", "transferencias-de-autos"):
    for marca, modelo in con.sql(f"""
            SELECT DISTINCT automotor_marca_descripcion, automotor_modelo_descripcion
            FROM read_csv('datos/muestra/{archivo}.csv', sample_size=-1)""").fetchall():
        palabras = norm(modelo).split()
        if palabras and palabras[0] == norm(marca).split()[0]:  # "VOLKSWAGEN VENTO" -> "VENTO"
            palabras = palabras[len(norm(marca).split()):]
        if palabras:
            catalogo.setdefault(marca_clave(marca), set()).add(palabras[0])
for marca, modelo in con.sql("SELECT DISTINCT marca, modelo FROM 'datos/fuentes/cca.parquet'").fetchall():
    p = norm(modelo).split()
    if p:
        catalogo.setdefault(marca_clave(marca), set()).add(p[0])
for marca in catalogo:
    catalogo[marca] -= NO_SON_MODELO
    catalogo[marca] = {m for m in catalogo[marca] if len(m) > 1 and not re.fullmatch(r"\d{1,2}", m)}
todos = set().union(*catalogo.values())

ANIOS = re.compile(r"\b(\d{2}|\d{4})\s*/\s*(\d{2}|\d{4})?\b|/\s*(\d{2}|\d{4})\b")
MOTOR = re.compile(r"\b\d[.,]\d\b|\b\d{3,4}\s?CC\b", re.I)

filas = con.sql("SELECT sku, titulo, calidad, marca_auto FROM r").fetchall()
resultado = []
for sku, titulo, calidad, marca_auto in filas:
    palabras = set(norm(titulo).split())
    universo = catalogo.get(marca_clave(marca_auto), set()) if marca_auto else todos
    modelos = sorted(palabras & universo)
    resultado.append((sku, titulo, calidad, marca_auto, modelos,
                      bool(ANIOS.search(titulo)), bool(MOTOR.search(titulo))))

n = len(resultado)
con_modelo = [x for x in resultado if x[4]]
print(f"### {categoria}: {n} productos")
print(f"  con marca del auto:           {100 * sum(1 for x in resultado if x[3]) / n:5.1f}%")
print(f"  con al menos un modelo:       {100 * len(con_modelo) / n:5.1f}%")
print(f"    con marca y modelo:         {100 * sum(1 for x in con_modelo if x[3]) / n:5.1f}%")
print(f"    con varios modelos:         {100 * sum(1 for x in con_modelo if len(x[4]) > 1) / n:5.1f}%")
print(f"  con rango de anios:           {100 * sum(1 for x in resultado if x[5]) / n:5.1f}%")
print(f"  con motor (1.6, 2.0...):      {100 * sum(1 for x in resultado if x[6]) / n:5.1f}%")

# Llave de comparacion por SKU
con.sql("""CREATE VIEW b AS SELECT *,
  CASE WHEN sku LIKE '%-%' THEN split_part(sku, '-', 1)
       WHEN regexp_matches(sku, '[0-9][OHEMNKTPCA]$') THEN left(sku, length(sku) - 1)
       ELSE sku END base FROM r""")
print(con.sql("""WITH g AS (SELECT base, count(*) n, count(DISTINCT calidad) calidades,
                               bool_or(calidad = 'Original') hay_original FROM b GROUP BY 1)
  SELECT round(100.0 * sum(n) FILTER (WHERE calidades > 1) / sum(n), 1) pct_comparable,
         round(100.0 * sum(n) FILTER (WHERE calidades > 1 AND hay_original) / sum(n), 1) pct_comparable_con_original
  FROM g"""))

print("\nMuestra sin modelo detectado:")
for x in [x for x in resultado if not x[4]][:15]:
    print(f"  [{x[3] or '-':10}] {x[1]}")
