"""
Comparador: el costo total de varias versiones para el perfil del usuario.

Lee mart_costo_componentes (datos/autos.duckdb, armada por dbt) y aplica
costo.calculo. Las versiones se buscan por texto ("cronos drive", "yaris xs");
si un texto encuentra varias, entran todas.

Uso:
  python -m costo.comparador --provincia 06 --km 20000 --anios 3 --seguro 60000 "cronos drive 1.3" "yaris xs"
"""

import argparse
import os

import duckdb

from costo.calculo import Perfil, calcular

BASE = os.path.join("datos", "autos.duckdb")


def buscar(con, textos, provincia_id, limite=20):
    """Filas de componentes de las versiones cuyo modelo contiene todas las palabras del texto."""
    filas = []
    for texto in textos:
        palabras = texto.upper().split()
        condicion = " and ".join(["upper(marca || ' ' || modelo) like ?"] * len(palabras))
        cursor = con.execute(
            f"""select * from mart_costo_componentes
                where provincia_id = ? and {condicion}
                order by inscripciones_12m desc nulls last limit {int(limite)}""",
            [provincia_id, *[f"%{p}%" for p in palabras]])
        columnas = [d[0] for d in cursor.description]
        filas += [dict(zip(columnas, f)) for f in cursor.fetchall()]
    vistos, unicas = set(), []
    for f in filas:
        clave = (f["origen_codigo"], f["marca_codigo"], f["tipo_codigo"], f["modelo_codigo"])
        if clave not in vistos:
            vistos.add(clave)
            unicas.append(f)
    return unicas


def comparar(componentes, perfil):
    """Lista de (fila, costo), de la mas barata a la mas cara; las incompletas al final."""
    resultado = [(c, calcular(c, perfil)) for c in componentes]
    return sorted(resultado, key=lambda x: (not x[1].completo, x[1].anual))


def pesos(x, ancho):
    """Separador de miles con punto, como se escribe en Argentina."""
    return f"{x:>{ancho},.0f}".replace(",", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("versiones", nargs="+")
    ap.add_argument("--provincia", default="06", help="codigo INDEC (02 CABA, 06 Buenos Aires, 14 Cordoba...)")
    ap.add_argument("--km", type=float, default=15000)
    ap.add_argument("--anios", type=float, default=5)
    ap.add_argument("--seguro", type=float, default=0, help="seguro mensual en pesos")
    ap.add_argument("--originales", action="store_true", help="repuestos originales en vez de alternativos")
    args = ap.parse_args()
    perfil = Perfil(args.km, args.anios, args.seguro, args.originales)
    con = duckdb.connect(BASE, read_only=True)
    filas = buscar(con, args.versiones, args.provincia)
    if not filas:
        raise SystemExit("ninguna version encontrada")
    print(f"Provincia {args.provincia}, {pesos(args.km, 0)} km por anio, {args.anios:g} anios, "
          f"seguro ${pesos(args.seguro, 0)} por mes\n")
    print(f"{'version':42s} {'por mes':>11s} {'por km':>7s}  combustible  service  repuestos  patente  depreciacion")
    for c, k in comparar(filas, perfil):
        nombre = f"{c['marca']} {c['modelo']}"[:42]
        if not k.completo:
            print(f"{nombre:42s} {'incompleto: falta ' + ', '.join(k.faltantes)}")
            continue
        print(f"{nombre:42s} {pesos(k.mensual(), 11)} {pesos(k.por_km(perfil.km_anio), 7)}  "
              f"{pesos(k.combustible_anual / 12, 11)} {pesos(k.service_anual / 12, 8)} {pesos(k.repuestos_anual / 12, 10)} "
              f"{pesos(k.patente_anual / 12, 8)} {pesos(k.depreciacion_anual / 12, 13)}")


if __name__ == "__main__":
    main()
