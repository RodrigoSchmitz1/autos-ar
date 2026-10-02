"""
Ingesta de precios de repuestos de desgaste (Repuestos Express).

Alcance: solo las piezas que se cambian en el mantenimiento (filtros, pastillas
y discos de freno, bujias, distribucion, correas, amortiguadores, embragues),
no el catalogo entero. ~5.400 productos, ~115 paginas del listado.

Scraping responsable (como en la Fase 0, fase0/06_repuestos.md):
  - solo /buscar, que robots.txt permite;
  - el listado trae 48 productos por pagina con los mismos datos que la ficha:
    ~115 pedidos en vez de ~5.400;
  - 1 pedido cada 2,5 s, User-Agent identificable (ingesta/comun.py);
  - como maximo una consulta cada 7 dias: los precios no cambian a diario;
  - si una pagina trae 0 productos, falla: casi seguro cambio el HTML.

Salida: datos/raw/repuestos/<AAAAMMDD>.parquet, una foto por cada vez que el
contenido cambia (huella de las filas, como en ingesta/service.py).

Uso: python -m ingesta.repuestos [--forzar]
"""

import argparse
import hashlib
import html
import json
import os
import re
import urllib.parse
from datetime import date

import duckdb
import pandas as pd

from ingesta.comun import pedir

BASE = "https://repuestos-express.com/buscar"
RAIZ = os.path.join("datos", "raw", "repuestos")
ESTADO = os.path.join(RAIZ, "_estado.json")
DIAS_ENTRE_CONSULTAS = 7

# (categoria, subcategoria); None = la categoria entera.
ALCANCE = [
    ("Filtros", None),
    ("Frenos", "Pastillas de Freno"),
    ("Frenos", "Discos de Freno"),
    ("Frenos", "Campanas de Freno"),
    ("Encendido", "Bujías"),
    ("Motor", "Distribución"),
    ("Motor", "Correas de Accesorios"),
    ("Suspensión y Dirección", "Amortiguadores"),
    ("Transmisión", "Embragues"),
]

TARJETA = re.compile(r'<a class="group flex[^"]*" href="/producto/(?P<sku>[^"]+)">(?P<cuerpo>.*?)</a>', re.S)
TITULO = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
ETIQUETAS = re.compile(r'<span class="rounded [^"]*">(.*?)</span>', re.S)
PRECIO_FINAL = re.compile(r'<p class="[^"]*tabular">\$([\d.]+)</p>')
PRECIO_LISTA = re.compile(r'line-through tabular">\$([\d.]+)</span>')
PAGINAS = re.compile(r"página 1 de (\d+)")


def limpiar(t):
    return html.unescape(re.sub(r"<!--.*?-->|<[^>]+>", "", t)).strip()


def parsear(texto, categoria, subcategoria):
    productos = []
    for m in TARJETA.finditer(texto):
        cuerpo = m["cuerpo"]
        titulo = TITULO.search(cuerpo)
        etiquetas = [limpiar(e) for e in ETIQUETAS.findall(cuerpo)]
        final = PRECIO_FINAL.search(cuerpo)
        lista = PRECIO_LISTA.search(cuerpo)
        productos.append({
            "sku": urllib.parse.unquote(m["sku"]),
            "titulo": limpiar(titulo[1]) if titulo else None,
            "calidad": etiquetas[0] if etiquetas else None,
            "marca_auto": etiquetas[1] if len(etiquetas) > 1 else None,
            "etiquetas": "|".join(etiquetas),
            "precio": int(final[1].replace(".", "")) if final else None,
            "precio_lista": int(lista[1].replace(".", "")) if lista else None,
            "categoria": categoria,
            "subcategoria": subcategoria,
        })
    return productos


def url(categoria, subcategoria, pagina):
    parametros = {"cat": categoria}
    if subcategoria:
        parametros["sub"] = subcategoria
    parametros["pagina"] = pagina
    return f"{BASE}?{urllib.parse.urlencode(parametros)}"


def bajar_alcance():
    filas = []
    for categoria, subcategoria in ALCANCE:
        texto = pedir(url(categoria, subcategoria, 1)).decode("utf-8")
        paginas = PAGINAS.search(texto)
        total = int(paginas[1]) if paginas else 1
        for pagina in range(1, total + 1):
            if pagina > 1:
                texto = pedir(url(categoria, subcategoria, pagina)).decode("utf-8")
            productos = parsear(texto, categoria, subcategoria)
            if not productos:
                raise RuntimeError(f"repuestos: {categoria}/{subcategoria} pagina {pagina} sin productos: revisar si cambio el HTML")
            filas += productos
        print(f"  {categoria} / {subcategoria or '(todas)'}: {total} paginas")
    return filas


def validar(df):
    """Controles minimos: si fallan, el sitio cambio o trae basura."""
    errores = []
    if len(df) < 3000:
        errores.append(f"solo {len(df)} productos")
    for columna in ("sku", "titulo", "precio"):
        nulos = df[columna].isna().mean()
        if nulos > 0.01:
            errores.append(f"{nulos:.1%} de {columna} vacios")
    if (df["precio"] <= 0).any():
        errores.append("precios no positivos")
    if errores:
        raise RuntimeError("repuestos: " + "; ".join(errores))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true", help="consultar aunque no hayan pasado 7 dias")
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    hoy = date.today()
    if not args.forzar and "consultado" in estado and (hoy - date.fromisoformat(estado["consultado"])).days < DIAS_ENTRE_CONSULTAS:
        print(f"repuestos: consultado el {estado['consultado']}, se vuelve a consultar cada {DIAS_ENTRE_CONSULTAS} dias")
        return
    filas = bajar_alcance()
    df = pd.DataFrame(filas)
    # Un producto puede aparecer en dos subcategorias o repetido entre paginas
    # si el sitio reordena mientras se recorre: queda la primera aparicion.
    repetidos = int(df.duplicated("sku").sum())
    df = df.drop_duplicates("sku")
    validar(df)
    estado["consultado"] = hoy.isoformat()
    huella = hashlib.sha256(df.sort_values("sku").to_json(orient="records").encode()).hexdigest()
    if estado.get("huella") == huella:
        print(f"repuestos: sin cambios ({len(df)} productos)")
    else:
        con = duckdb.connect()
        con.register("t", df)
        destino = os.path.join(RAIZ, hoy.strftime("%Y%m%d") + ".parquet")
        con.sql(f"COPY (SELECT *, DATE '{hoy.isoformat()}' AS capturado FROM t) TO '{destino}' (FORMAT parquet)")
        estado["huella"] = huella
        print(f"repuestos: {len(df)} productos ({repetidos} repetidos descartados)")
    json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
