"""
Baja las fotos de los modelos desde Wikimedia Commons para el sitio.

Las fotos de las automotrices tienen derechos; las de Commons tienen licencia
libre (CC BY, CC BY-SA, dominio publico) y se pueden usar citando autor y
licencia. Cada foto se eligio a mano (exportar/fotos_modelos.csv) para que sea
la generacion que se vende en Argentina: la foto principal de Wikipedia suele
ser la europea o de otro anio.

Se corre a mano cuando cambia la lista, no en el pipeline: las fotos quedan en
el repo (sitio/img/autos/) y el sitio no depende de Commons para mostrarlas.

  sitio/img/autos/<marca>-<familia>.webp   480x320, recortada al centro (3:2)
  sitio/img/autos/<marca>-<familia>-interior.webp   idem, el interior
                                           (exportar/fotos_interior.csv)
  sitio/img/autos/<marca>-<familia>-g<n>.webp   mas fotos del modelo (frente,
                                           cola, perfil, tablero...) para la
                                           galeria de la ficha, sin recortar,
                                           960 de ancho (exportar/fotos_galeria.csv)
  sitio/img/autos/fotos.json               "MARCA|FAMILIA" -> archivo, autor,
                                           licencia y pagina de la foto

Uso: python -m exportar.fotos
"""

import csv
import io
import json
import os
import re
import unicodedata
import time
import urllib.error
import urllib.parse

from PIL import Image

from ingesta.comun import pedir as _pedir

LISTA = os.path.join("exportar", "fotos_modelos.csv")
LISTA_INTERIOR = os.path.join("exportar", "fotos_interior.csv")
LISTA_GALERIA = os.path.join("exportar", "fotos_galeria.csv")
DESTINO = os.path.join("sitio", "img", "autos")
API = "https://commons.wikimedia.org/w/api.php"
ANCHO, ALTO = 480, 320
# Commons genera miniaturas en anchos fijos; pedir uno de esos evita que tenga
# que crear una nueva para nosotros.
ANCHO_PEDIDO = 960


def pedir(url):
    """pedir, pero ante un 429 de Commons (pide bajar el ritmo) espera y reintenta."""
    for espera in (60, 180, 600):
        try:
            return _pedir(url)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            print(f"  Commons pide esperar (429): {espera} s", flush=True)
            time.sleep(espera)
    return _pedir(url)


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def sin_html(texto):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", texto or "")).strip()


def miniatura(info, ancho=ANCHO_PEDIDO):
    """URL de la miniatura de `ancho` (uno estandar de Wikimedia) de un archivo, armada a partir de su URL.

    Pedirle a la API la miniatura (iiurlwidth) le hace generarla en el momento,
    y en tandas Commons responde 429; la URL de una miniatura en un ancho
    estandar se puede armar (es la misma que devuelve la API).
    """
    original = info["url"].split("?")[0]
    if info["width"] <= ancho:
        return original
    carpeta, nombre = original.rsplit("/", 1)
    carpeta = carpeta.replace("upload.wikimedia.org/wikipedia/commons/", "thumb.wikimedia.org/wikipedia/commons/thumb/")
    extra = ".jpg" if nombre.lower().endswith((".tif", ".tiff")) else ""
    return f"{carpeta}/{nombre}/{ancho}px-{nombre}{extra}"


def metadatos(archivos):
    """URL de la miniatura, autor y licencia de cada archivo (de a 20 por pedido)."""
    datos = {}
    for i in range(0, len(archivos), 20):
        parametros = urllib.parse.urlencode({
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
            "titles": "|".join("File:" + a for a in archivos[i:i + 20]),
        })
        respuesta = json.loads(pedir(f"{API}?{parametros}"))["query"]
        # La API normaliza los titulos (espacios, mayusculas): hay que volver al nombre pedido.
        normalizado = {n["to"]: n["from"] for n in respuesta.get("normalized", [])}
        for pagina in respuesta["pages"].values():
            titulo = normalizado.get(pagina["title"], pagina["title"])
            if "imageinfo" not in pagina:
                raise ValueError(f"no existe en Commons: {titulo}")
            info = pagina["imageinfo"][0]
            meta = info.get("extmetadata", {})
            datos[titulo[len("File:"):]] = {
                "miniatura": miniatura(info),
                "pagina": info["descriptionurl"],
                "autor": sin_html(meta.get("Artist", {}).get("value")) or "autor desconocido",
                "licencia": meta.get("LicenseShortName", {}).get("value", ""),
                "url_licencia": meta.get("LicenseUrl", {}).get("value", ""),
            }
    return datos


def recortar(contenido):
    """Recorte al centro en 3:2 y redimension: todas las tarjetas quedan parejas."""
    imagen = Image.open(io.BytesIO(contenido)).convert("RGB")
    ancho, alto = imagen.size
    objetivo = ANCHO / ALTO
    if ancho / alto > objetivo:
        nuevo = round(alto * objetivo)
        imagen = imagen.crop(((ancho - nuevo) // 2, 0, (ancho - nuevo) // 2 + nuevo, alto))
    else:
        nuevo = round(ancho / objetivo)
        imagen = imagen.crop((0, (alto - nuevo) // 2, ancho, (alto - nuevo) // 2 + nuevo))
    salida = io.BytesIO()
    imagen.resize((ANCHO, ALTO), Image.LANCZOS).save(salida, "WEBP", quality=78)
    return salida.getvalue()


def achicar(contenido):
    """Para la galeria: sin recortar (cada foto con su encuadre), a lo sumo ANCHO_PEDIDO de ancho."""
    imagen = Image.open(io.BytesIO(contenido)).convert("RGB")
    imagen.thumbnail((ANCHO_PEDIDO, ANCHO_PEDIDO))
    salida = io.BytesIO()
    imagen.save(salida, "WEBP", quality=80)
    return salida.getvalue()


def procesar_galeria(lista, meta):
    """Fotos extra de cada modelo, en el orden de la lista: "MARCA|FAMILIA" -> [foto, ...]."""
    galeria = {}
    for fila in lista:
        clave = f"{fila['marca']}|{fila['familia']}"
        m = meta[fila["archivo_commons"]]
        if not m["licencia"]:
            raise ValueError(f"foto sin licencia en Commons: {fila['archivo_commons']}")
        fotos = galeria.setdefault(clave, [])
        nombre = f"{slug(fila['marca'])}-{slug(fila['familia'])}-g{len(fotos) + 1}.webp"
        ruta = os.path.join(DESTINO, nombre)
        if not os.path.exists(ruta):
            with open(ruta, "wb") as f:
                f.write(achicar(pedir(m["miniatura"])))
            print(f"  {nombre}")
        with Image.open(ruta) as im:
            ancho, alto = im.size
        fotos.append({"imagen": nombre, "vista": fila["vista"], "ancho": ancho, "alto": alto,
                      "archivo": fila["archivo_commons"], "pagina": m["pagina"], "autor": m["autor"],
                      "licencia": m["licencia"], "url_licencia": m["url_licencia"]})
    return galeria


def procesar(lista, meta, sufijo=""):
    """Baja (si falta) y recorta cada foto; devuelve "MARCA|FAMILIA" -> datos y credito."""
    fotos = {}
    for fila in lista:
        m = meta[fila["archivo_commons"]]
        nombre = f"{slug(fila['marca'])}-{slug(fila['familia'])}{sufijo}.webp"
        ruta = os.path.join(DESTINO, nombre)
        if not os.path.exists(ruta):
            with open(ruta, "wb") as f:
                f.write(recortar(pedir(m["miniatura"])))
            print(f"  {nombre}")
        fotos[f"{fila['marca']}|{fila['familia']}"] = {
            "imagen": nombre, "archivo": fila["archivo_commons"], "pagina": m["pagina"],
            "autor": m["autor"], "licencia": m["licencia"], "url_licencia": m["url_licencia"],
        }
    sin_licencia = [k for k, v in fotos.items() if not v["licencia"]]
    if sin_licencia:
        raise ValueError(f"fotos sin licencia en Commons: {sin_licencia}")
    return fotos


def main():
    listas = {}
    for nombre, ruta in (("exterior", LISTA), ("interior", LISTA_INTERIOR), ("galeria", LISTA_GALERIA)):
        with open(ruta, encoding="utf-8") as f:
            listas[nombre] = list(csv.DictReader(f))
    os.makedirs(DESTINO, exist_ok=True)
    meta = metadatos([fila["archivo_commons"] for lista in listas.values() for fila in lista])
    fotos = procesar(listas["exterior"], meta)
    # El interior va dentro de la entrada del modelo; un modelo sin foto de
    # exterior no tiene ficha visual, asi que su interior no se usa.
    for clave, interior in procesar(listas["interior"], meta, "-interior").items():
        if clave in fotos:
            fotos[clave]["interior"] = interior
    for clave, galeria in procesar_galeria(listas["galeria"], meta).items():
        if clave in fotos:
            fotos[clave]["galeria"] = galeria
    with open(os.path.join(DESTINO, "fotos.json"), "w", encoding="utf-8") as f:
        json.dump(fotos, f, ensure_ascii=False, indent=1, sort_keys=True)
    imagenes = ([v["imagen"] for v in fotos.values()] + [v["interior"]["imagen"] for v in fotos.values() if "interior" in v]
                + [g["imagen"] for v in fotos.values() for g in v.get("galeria", [])])
    peso = sum(os.path.getsize(os.path.join(DESTINO, n)) for n in imagenes)
    print(f"{len(fotos)} modelos, {len(imagenes)} fotos, {peso / 1024:.0f} KiB en {DESTINO}")

if __name__ == "__main__":
    main()
