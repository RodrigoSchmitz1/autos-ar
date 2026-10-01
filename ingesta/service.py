"""
Ingesta de precios oficiales de service programado, marca por marca.

Salida: datos/raw/service/<marca>/<AAAAMMDD>.parquet, una foto por cada vez que
la fuente CAMBIA (fecha de captura). Si el contenido es el mismo que la ultima
foto (mismo SHA-256), no se guarda nada.

Por que fotos por fecha de captura: casi ninguna fuente dice desde cuando rige
el precio, y los concesionarios actualizan cuando quieren (la pagina de VW
Mataderos seguia con el 2do trimestre cuando la lista nacional ya era del 3ro).
La fecha de captura es lo unico seguro; `vigencia_desde`/`vigencia_hasta` se
llenan solo cuando la fuente las publica. Ver docs/service_relevamiento.md.

Esquema comun para todas las marcas (una fila por modelo y service):
  marca, modelo_fuente, km, precio, tipo_precio ('lista'),
  mano_obra_bonificada, incluye_iva, items_cambio, precio_texto,
  precio_corregido, fuente_url, vigencia_desde, vigencia_hasta, capturado

Uso: python -m ingesta.service [--marcas fiat,jeep]
"""

import argparse
import collections
import hashlib
import json
import os
import re
from datetime import date

import duckdb
import pandas as pd

from ingesta.comun import pedir

RAIZ = os.path.join("datos", "raw", "service")
ESTADO = os.path.join(RAIZ, "_estado.json")

PRECIO_ESTRICTO = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})+)\s*$")
PRECIO_CON_CERO_DE_MAS = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})*\.\d{3})0\s*$")


def a_pesos(texto):
    return int(texto.replace(".", ""))


# ---------- Stellantis: Fiat y Jeep (Mopar) ----------
def mopar(marca):
    """Un JSON estatico por marca: modelos -> services por km -> precio de lista.

    Precio en texto ("Precio de Lista: $ 434.000"). Dos errores conocidos de
    tipeo ("$ 434.0000"): se corrigen solo si, sin el cero de mas, coinciden con
    el precio habitual del modelo, y quedan marcados en `precio_corregido`. Si
    no coinciden, falla: mejor un pipeline en rojo que un precio inventado.
    """
    url = f"https://mantenimientomopar.com.ar/{marca}/js/db.json"
    contenido = pedir(url)
    modelos = json.loads(contenido.decode("utf-8"))
    filas = []
    for m in modelos:
        servicios = m["kilometro"]
        validos = [a_pesos(x[1]) for x in (PRECIO_ESTRICTO.search(s["servicio"]) for s in servicios) if x]
        habitual = collections.Counter(validos).most_common(1)[0][0] if validos else None
        for s in servicios:
            texto = s["servicio"].strip()
            estricto = PRECIO_ESTRICTO.search(texto)
            corregido = False
            if estricto:
                precio = a_pesos(estricto[1])
            else:
                sin_cero = PRECIO_CON_CERO_DE_MAS.search(texto)
                if sin_cero and a_pesos(sin_cero[1]) == habitual:
                    precio, corregido = habitual, True
                else:
                    raise ValueError(f"{marca} {m['name']} {s['miles']} km: precio ilegible {texto!r}")
            filas.append({
                "marca": marca.capitalize(), "modelo_fuente": m["name"].strip(),
                "km": a_pesos(s["miles"]), "precio": precio, "tipo_precio": "lista",
                "mano_obra_bonificada": False, "incluye_iva": None,
                "items_cambio": " | ".join(s.get("cambio") or []),
                "precio_texto": texto, "precio_corregido": corregido,
                "fuente_url": url, "vigencia_desde": None, "vigencia_hasta": None,
            })
    return contenido, filas


RECOLECTORES = {
    "fiat": lambda: mopar("fiat"),
    "jeep": lambda: mopar("jeep"),
}


def validar(marca, filas):
    """Controles minimos: si fallan, la fuente cambio de formato o trae basura."""
    errores = []
    if len(filas) < 20:
        errores.append(f"solo {len(filas)} filas")
    fuera = [f for f in filas if not 100_000 <= f["precio"] <= 5_000_000]
    if fuera:
        errores.append(f"{len(fuera)} precios fuera de $100.000-$5.000.000 (ej.: {fuera[0]['modelo_fuente']} {fuera[0]['km']} km ${fuera[0]['precio']:,})")
    if len({(f["modelo_fuente"], f["km"]) for f in filas}) != len(filas):
        errores.append("modelo y km repetidos")
    if errores:
        raise RuntimeError(f"service {marca}: " + "; ".join(errores))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marcas", default=",".join(RECOLECTORES))
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    hoy = date.today()
    for marca in args.marcas.split(","):
        contenido, filas = RECOLECTORES[marca]()
        huella = hashlib.sha256(contenido).hexdigest()
        if estado.get(marca) == huella:
            print(f"service {marca}: sin cambios")
            continue
        validar(marca, filas)
        destino = os.path.join(RAIZ, marca)
        os.makedirs(destino, exist_ok=True)
        con = duckdb.connect()
        con.register("t", pd.DataFrame(filas))
        con.sql(f"""COPY (SELECT *, DATE '{hoy.isoformat()}' AS capturado FROM t)
                    TO '{os.path.join(destino, hoy.strftime('%Y%m%d') + '.parquet')}' (FORMAT parquet)""")
        estado[marca] = huella
        json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)
        corregidos = sum(f["precio_corregido"] for f in filas)
        print(f"service {marca}: {len(filas)} services de {len({f['modelo_fuente'] for f in filas})} modelos"
              + (f" ({corregidos} precios con un cero de mas, corregidos)" if corregidos else ""))


if __name__ == "__main__":
    main()
