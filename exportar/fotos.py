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
import urllib.parse

from PIL import Image

from ingesta.comun import pedir

LISTA = os.path.join("exportar", "fotos_modelos.csv")
DESTINO = os.path.join("sitio", "img", "autos")
API = "https://commons.wikimedia.org/w/api.php"
ANCHO, ALTO = 480, 320
# Commons genera miniaturas en anchos fijos; pedir uno de esos evita que tenga
# que crear una nueva para nosotros.
ANCHO_PEDIDO = 960


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def sin_html(texto):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", texto or "")).strip()


def metadatos(archivos):
    """URL de la miniatura, autor y licencia de cada archivo (hasta 50 por pedido)."""
    datos = {}
    for i in range(0, len(archivos), 50):
        parametros = urllib.parse.urlencode({
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": ANCHO_PEDIDO,
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
            "titles": "|".join("File:" + a for a in archivos[i:i + 50]),
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
                "miniatura": info["thumburl"],
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


def main():
    with open(LISTA, encoding="utf-8") as f:
        lista = list(csv.DictReader(f))
    os.makedirs(DESTINO, exist_ok=True)
    meta = metadatos([fila["archivo_commons"] for fila in lista])
    fotos = {}
    for fila in lista:
        m = meta[fila["archivo_commons"]]
        nombre = f"{slug(fila['marca'])}-{slug(fila['familia'])}.webp"
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
    with open(os.path.join(DESTINO, "fotos.json"), "w", encoding="utf-8") as f:
        json.dump(fotos, f, ensure_ascii=False, indent=1, sort_keys=True)
    peso = sum(os.path.getsize(os.path.join(DESTINO, v["imagen"])) for v in fotos.values())
    print(f"{len(fotos)} fotos, {peso / 1024:.0f} KiB en {DESTINO}")


if __name__ == "__main__":
    main()
