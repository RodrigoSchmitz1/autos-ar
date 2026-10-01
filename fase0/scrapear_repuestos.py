"""
Fase 0.6 - Releva una categoria de Repuestos Express (por defecto, Filtros).

Scraping responsable:
  - solo rutas que robots.txt permite (/buscar);
  - 1 pedido cada 2,5 s y User-Agent identificable;
  - cache en disco: una pagina ya bajada no se vuelve a pedir;
  - si una pagina trae 0 productos, falla: casi seguro cambio el HTML, y un
    scraper que devuelve vacio en silencio es peor que uno que se rompe.

Usa el listado (48 productos por pagina) y no la pagina de cada producto: 52
pedidos en vez de 1.243 para los mismos datos.

Uso: python fase0/scrapear_repuestos.py [categoria]
"""

import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import duckdb
import pandas as pd

USER_AGENT = "autos-ar-fase0/0.1 (proyecto de portfolio; github.com/RodrigoSchmitz1)"
BASE = "https://repuestos-express.com/buscar"
PAUSA = 2.5
CACHE = "datos/repuestos/cache"

TARJETA = re.compile(r'<a class="group flex[^"]*" href="/producto/(?P<sku>[^"]+)">(?P<cuerpo>.*?)</a>', re.S)
TITULO = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
ETIQUETAS = re.compile(r'<span class="rounded [^"]*">(.*?)</span>', re.S)
PRECIO_FINAL = re.compile(r'<p class="[^"]*tabular">\$([\d.]+)</p>')
PRECIO_LISTA = re.compile(r'line-through tabular">\$([\d.]+)</span>')
PAGINAS = re.compile(r"página 1 de (\d+)")


def bajar(categoria, pagina):
    os.makedirs(CACHE, exist_ok=True)
    archivo = os.path.join(CACHE, f"{categoria}_{pagina:03d}.html")
    if os.path.exists(archivo):
        return open(archivo, encoding="utf-8").read(), False
    url = f"{BASE}?{urllib.parse.urlencode({'cat': categoria, 'pagina': pagina})}"
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        texto = r.read().decode("utf-8")
    open(archivo, "w", encoding="utf-8").write(texto)
    return texto, True


def limpiar(t):
    return html.unescape(re.sub(r"<!--.*?-->|<[^>]+>", "", t)).strip()


def parsear(texto, categoria, pagina):
    productos = []
    for m in TARJETA.finditer(texto):
        cuerpo = m["cuerpo"]
        etiquetas = [limpiar(e) for e in ETIQUETAS.findall(cuerpo)]
        final = PRECIO_FINAL.search(cuerpo)
        lista = PRECIO_LISTA.search(cuerpo)
        productos.append({
            "sku": m["sku"], "titulo": limpiar(TITULO.search(cuerpo)[1]) if TITULO.search(cuerpo) else None,
            "calidad": etiquetas[0] if etiquetas else None,
            "marca_auto": etiquetas[1] if len(etiquetas) > 1 else None,
            "etiquetas": "|".join(etiquetas),
            "precio": int(final[1].replace(".", "")) if final else None,
            "precio_lista": int(lista[1].replace(".", "")) if lista else None,
            "categoria": categoria, "pagina": pagina,
        })
    return productos


def main():
    categoria = sys.argv[1] if len(sys.argv) > 1 else "Filtros"
    texto, _ = bajar(categoria, 1)
    total_paginas = int(PAGINAS.search(texto)[1])
    productos, pedidos = [], 1
    for pagina in range(1, total_paginas + 1):
        if pagina > 1:
            texto, pedido_nuevo = bajar(categoria, pagina)
            if pedido_nuevo:
                pedidos += 1
                time.sleep(PAUSA)
        filas = parsear(texto, categoria, pagina)
        if not filas:
            raise SystemExit(f"Pagina {pagina} sin productos: revisar si cambio el HTML")
        productos.extend(filas)
    con = duckdb.connect()
    con.register("df", pd.DataFrame(productos))
    con.sql(f"COPY df TO 'datos/repuestos/{categoria}.parquet' (FORMAT parquet)")
    print(con.sql("""SELECT count(*) productos, count(DISTINCT sku) skus, count(*) FILTER (WHERE precio IS NULL) sin_precio,
                     count(*) FILTER (WHERE titulo IS NULL) sin_titulo FROM df"""))
    print(f"{total_paginas} paginas, {pedidos} pedidos nuevos (el resto salio de la cache)")


if __name__ == "__main__":
    main()
