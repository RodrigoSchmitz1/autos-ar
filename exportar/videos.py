"""
Videos de los modelos para el sitio, de YouTube.

Los videos de las marcas y de los canales de autos tienen derechos: no se
copian, se insertan con el reproductor de YouTube, que es la forma que YouTube
permite (cada video dice si se puede insertar; el chequeo usa oEmbed, que
responde 401 si no se puede). El reproductor muestra el canal del autor.

La lista (exportar/videos_modelos.csv) se eligio a mano: el canal oficial de
la marca en Argentina cuando tiene un video del modelo actual; si no, una
resena argentina del modelo que se vende aca (TN Autos, Argentina Motor,
Autocosmos...). Ojo con los "Hilux 2026" de YouTube: son la generacion nueva
de Tailandia, no la de Zarate.

Se corre a mano cuando cambia la lista, como exportar/fotos.py:

  sitio/img/autos/videos.json   "MARCA|FAMILIA" -> id, titulo, canal

Uso: python -m exportar.videos
"""

import csv
import json
import os
import time
import urllib.error
import urllib.parse

from ingesta.comun import pedir

LISTA = os.path.join("exportar", "videos_modelos.csv")
DESTINO = os.path.join("sitio", "img", "autos", "videos.json")


def main():
    with open(LISTA, encoding="utf-8") as f:
        lista = list(csv.DictReader(f))
    videos, fallas = {}, []
    for fila in lista:
        url = "https://www.youtube.com/watch?v=" + fila["video_id"]
        try:
            datos = json.loads(pedir("https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": url, "format": "json"})))
        except urllib.error.HTTPError as e:
            fallas.append(f"{fila['familia']} ({fila['video_id']}): HTTP {e.code}, no existe o no se puede insertar")
            continue
        videos[f"{fila['marca']}|{fila['familia']}"] = {
            "id": fila["video_id"], "titulo": datos["title"], "canal": datos["author_name"], "url_canal": datos["author_url"],
        }
        time.sleep(1)
    if fallas:
        raise SystemExit("videos que fallan:\n  " + "\n  ".join(fallas))
    with open(DESTINO, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{len(videos)} videos en {DESTINO}")


if __name__ == "__main__":
    main()
