"""
Recortes de las fotos de los modelos: el auto sin el fondo, para mostrarlo
sobre un degradado como en las paginas de las marcas.

Parte de la misma foto de Wikimedia Commons que exportar/fotos.py (la de
exterior de fotos.json), en mas resolucion, y le quita el fondo con rembg
(modelo BiRefNet, corre local y gratis; la primera vez baja el modelo, unos
220 MB, a ~/.rembg). Las licencias de Commons (CC BY, CC BY-SA) permiten
modificar la foto citando autor y licencia e indicando el cambio: el credito
del sitio dice "fondo removido", y el recorte queda con la misma licencia.

Se corre a mano, como exportar/fotos.py (despues de ese, que arma fotos.json):

  sitio/img/autos/recortes/<marca>-<familia>.webp   auto sin fondo, 1400 de ancho
  sitio/img/autos/recortes/<marca>-<familia>-v<n>.webp  variantes: las fotos de
                                                    la galeria marcadas "frente"
                                                    (exportar/fotos_galeria.csv),
                                                    autos de otros colores para
                                                    las tarjetas de versiones
  sitio/img/autos/recortes.json                     "MARCA|FAMILIA" -> archivo,
                                                    ancho, alto y variantes

Un recorte que salio mal (se comio una rueda, dejo un pedazo de vereda) se
anota en exportar/recortes_descartados.csv (marca, familia, archivo_commons) y
no se usa: si es la foto principal, la ficha muestra la foto comun.

Uso: python -m exportar.recortes [MARCA|FAMILIA ...]
"""

import csv
import io
import json
import os
import sys
import urllib.parse

from PIL import Image

from exportar.fotos import API, DESTINO, miniatura, pedir, slug

FOTOS = os.path.join(DESTINO, "fotos.json")
CARPETA = os.path.join(DESTINO, "recortes")
INDICE = os.path.join(DESTINO, "recortes.json")
DESCARTADOS = os.path.join("exportar", "recortes_descartados.csv")
MODELO = "birefnet-general-lite"
ANCHO = 1400
# Commons tiene miniaturas en anchos fijos; 1920 es una de ellas.
ANCHO_PEDIDO = 1920
# Pixeles casi transparentes que deja el modelo en el borde (sombras, reflejos
# en el piso): por debajo de este alfa no cuentan para el encuadre.
ALFA_MINIMO = 40


def url_miniatura(archivo):
    parametros = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "imageinfo",
        "iiprop": "url|size", "titles": "File:" + archivo,
    })
    pagina = next(iter(json.loads(pedir(f"{API}?{parametros}"))["query"]["pages"].values()))
    return miniatura(pagina["imageinfo"][0], ANCHO_PEDIDO)


def recortar(imagen, sesion):
    from rembg import remove
    sin_fondo = remove(imagen, session=sesion)
    alfa = sin_fondo.getchannel("A").point(lambda a: 255 if a >= ALFA_MINIMO else 0)
    sin_fondo = sin_fondo.crop(alfa.getbbox())
    if sin_fondo.width > ANCHO:
        sin_fondo = sin_fondo.resize((ANCHO, round(sin_fondo.height * ANCHO / sin_fondo.width)), Image.LANCZOS)
    return sin_fondo


def guardar(ruta, imagen, sesion):
    recortar(imagen, sesion).save(ruta, "WEBP", quality=82, method=6)
    print(f"  {os.path.basename(ruta)}: {os.path.getsize(ruta) // 1024} KB", flush=True)


def medidas(ruta):
    with Image.open(ruta) as r:
        return r.width, r.height


def main():
    from rembg import new_session

    with open(FOTOS, encoding="utf-8") as f:
        fotos = json.load(f)
    descartados = set()
    if os.path.exists(DESCARTADOS):
        with open(DESCARTADOS, encoding="utf-8") as f:
            descartados = {(r["marca"], r["familia"], r["archivo_commons"]) for r in csv.DictReader(f)}
    pedidas = set(sys.argv[1:])
    os.makedirs(CARPETA, exist_ok=True)
    sesion = new_session(MODELO)
    indice = {}
    for clave, foto in sorted(fotos.items()):
        if pedidas and clave not in pedidas:
            continue
        marca, familia = clave.split("|")
        base = slug(clave.replace("|", " "))
        if (marca, familia, foto["archivo"]) in descartados:
            continue
        ruta = os.path.join(CARPETA, base + ".webp")
        if not os.path.exists(ruta):
            guardar(ruta, Image.open(io.BytesIO(pedir(url_miniatura(foto["archivo"])))).convert("RGB"), sesion)
        ancho, alto = medidas(ruta)
        entrada = {"imagen": f"recortes/{base}.webp", "ancho": ancho, "alto": alto, "variantes": []}
        # Las variantes salen de la foto de galeria ya bajada (960 de ancho alcanza para las tarjetas).
        for n, g in enumerate([g for g in foto.get("galeria", []) if g["vista"] == "frente"], 1):
            if (marca, familia, g["archivo"]) in descartados:
                continue
            ruta = os.path.join(CARPETA, f"{base}-v{n}.webp")
            if not os.path.exists(ruta):
                guardar(ruta, Image.open(os.path.join(DESTINO, g["imagen"])).convert("RGB"), sesion)
            ancho, alto = medidas(ruta)
            entrada["variantes"].append({"imagen": f"recortes/{base}-v{n}.webp", "ancho": ancho, "alto": alto, "archivo": g["archivo"]})
        indice[clave] = entrada
    if pedidas and os.path.exists(INDICE):
        with open(INDICE, encoding="utf-8") as f:
            indice = {**{k: v for k, v in json.load(f).items() if k not in pedidas}, **indice}
    with open(INDICE, "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{len(indice)} modelos con recorte, {sum(len(v['variantes']) for v in indice.values())} variantes de color")


if __name__ == "__main__":
    main()
