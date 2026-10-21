"""
Ingesta de precios de repuestos de desgaste de ARG Autopartes (segunda tienda,
para tener mas modelos y mas precios por pieza que con una sola).

Alcance: las mismas piezas que Repuestos Express (frenos, filtros, bujias,
distribucion, correas, amortiguadores y embragues), solo de autos y camionetas
(no la linea pesada).

Scraping responsable:
  - solo las paginas de categoria y su paginado (/page/N/), que robots.txt
    permite (prohibe admin, cuenta y checkout); se verifica en cada corrida;
  - el listado trae 50 productos por pagina con nombre y precio: ~100 pedidos
    en vez de un pedido por producto;
  - 1 pedido cada 2,5 s, User-Agent identificable (ingesta/comun.py);
  - como maximo una consulta cada 7 dias;
  - si la primera pagina de una categoria trae 0 productos, falla: casi seguro
    cambio el HTML.

Los titulos traen el modelo ("Kit Distribucion Completo Vw Fox Suran Gol Trend
1.6") y, a veces, la marca del repuesto o "original": la calidad se deduce en
staging (stg_repuestos__productos).

Salida: datos/raw/repuestos_arg/<AAAAMMDD>.parquet, una foto por cada vez que el
contenido cambia (huella de las filas, como en ingesta/repuestos.py).

Uso: python -m ingesta.repuestos_arg [--forzar]
"""

import argparse
import hashlib
import html
import json
import os
import re
from datetime import date

import duckdb
import pandas as pd

from ingesta.comun import pedir, permitido_por_robots

BASE = "https://www.argautopartes.com.ar/accesorios-para-vehiculos/"
RAIZ = os.path.join("datos", "raw", "repuestos_arg")
ESTADO = os.path.join(RAIZ, "_estado.json")
DIAS_ENTRE_CONSULTAS = 7
MAX_PAGINAS = 60  # por categoria: un tope por si el paginado no termina nunca

# Categorias del sitio (ruta debajo de accesorios-para-vehiculos/).
ALCANCE = [
    "frenos/pastillas-de-freno",
    "frenos/discos-de-freno",
    "frenos/campanas-de-freno",
    "filtros",
    "encendido/bujias",
    "motor/distribucion",
    "motor/correas-de-accesorios",
    "suspension-y-direccion/amortiguadores",
    "transmision/embragues/kits-de-embrague",
]

# Cada producto del listado: su id, el enlace con el titulo y el precio que se ve.
PRODUCTO = re.compile(r'data-product-id="(?P<id>\d+)"(?P<cuerpo>.*?)(?=data-product-id="\d+"|$)', re.S)
TITULO = re.compile(r'class="js-item-name[^"]*"[^>]*>\s*([^<]+?)\s*<')
ENLACE = re.compile(r'href="(https://www\.argautopartes\.com\.ar/productos/[^"]+)"')
PRECIO = re.compile(r'class="js-price-display[^"]*"[^>]*>\s*\$([\d.]+)(?:,(\d+))?')


def precio(entero, decimales):
    return float(entero.replace(".", "") + "." + (decimales or "0"))


def parsear(texto, categoria):
    productos, vistos = [], set()
    for m in PRODUCTO.finditer(texto):
        if m["id"] in vistos:
            continue  # el id se repite dentro de la misma tarjeta
        titulo, enlace, p = TITULO.search(m["cuerpo"]), ENLACE.search(m["cuerpo"]), PRECIO.search(m["cuerpo"])
        if not titulo or not p:
            continue
        vistos.add(m["id"])
        productos.append({
            "sku": f"ARG-{m['id']}",
            "titulo": html.unescape(titulo[1]).strip(),
            "precio": precio(p[1], p[2]),
            "url": enlace[1] if enlace else None,
            "categoria": categoria.split("/")[0],
            "subcategoria": categoria,
        })
    return productos


def url(categoria, pagina):
    return f"{BASE}{categoria}/" + (f"page/{pagina}/" if pagina > 1 else "")


def bajar_alcance():
    filas = []
    for categoria in ALCANCE:
        if not permitido_por_robots(url(categoria, 2)):
            raise PermissionError(f"repuestos_arg: robots.txt no permite {url(categoria, 2)}")
        total = 0
        for pagina in range(1, MAX_PAGINAS + 1):
            texto = pedir(url(categoria, pagina)).decode("utf-8", "ignore")
            productos = parsear(texto, categoria)
            if not productos:
                if pagina == 1:
                    raise RuntimeError(f"repuestos_arg: {categoria} sin productos: revisar si cambio el HTML")
                break
            filas += productos
            total = pagina
            if f"/page/{pagina + 1}/" not in texto:
                break
        print(f"  {categoria}: {total} paginas")
    return filas


def validar(df):
    """Controles minimos: si fallan, el sitio cambio o trae basura."""
    errores = []
    if len(df) < 1500:
        errores.append(f"solo {len(df)} productos")
    for columna in ("sku", "titulo", "precio"):
        nulos = df[columna].isna().mean()
        if nulos > 0.01:
            errores.append(f"{nulos:.1%} de {columna} vacios")
    if (df["precio"] <= 0).mean() > 0.01:
        errores.append("precios no positivos")
    if errores:
        raise RuntimeError("repuestos_arg: " + "; ".join(errores))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true", help="consultar aunque no hayan pasado 7 dias")
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    hoy = date.today()
    if not args.forzar and "consultado" in estado and (hoy - date.fromisoformat(estado["consultado"])).days < DIAS_ENTRE_CONSULTAS:
        print(f"repuestos_arg: consultado el {estado['consultado']}, se vuelve a consultar cada {DIAS_ENTRE_CONSULTAS} dias")
        return
    df = pd.DataFrame(bajar_alcance())
    # Un producto puede estar en dos categorias (filtros y kits): queda la primera.
    repetidos = int(df.duplicated("sku").sum())
    df = df.drop_duplicates("sku")
    df = df[df["precio"] > 0]  # "consultar precio"
    validar(df)
    estado["consultado"] = hoy.isoformat()
    huella = hashlib.sha256(df.sort_values("sku").to_json(orient="records").encode()).hexdigest()
    if estado.get("huella") == huella:
        print(f"repuestos_arg: sin cambios ({len(df)} productos)")
    else:
        con = duckdb.connect()
        con.register("t", df)
        destino = os.path.join(RAIZ, hoy.strftime("%Y%m%d") + ".parquet")
        con.sql(f"COPY (SELECT *, DATE '{hoy.isoformat()}' AS capturado FROM t) TO '{destino}' (FORMAT parquet)")
        estado["huella"] = huella
        print(f"repuestos_arg: {len(df)} productos ({repetidos} repetidos descartados)")
    json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
