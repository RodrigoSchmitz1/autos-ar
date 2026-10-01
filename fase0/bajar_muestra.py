"""
Fase 0.4 - Baja el ultimo CSV mensual de cada dataset de DNRPA.

La URL se descubre con package_show (cambia con cada publicacion) y se elige el
recurso CSV mas nuevo. Los archivos van a datos/muestra/, que esta en
.gitignore: traen datos del titular y no pueden terminar en el repo.

Uso: python fase0/bajar_muestra.py
"""

import json
import os
import time
import urllib.request

USER_AGENT = "autos-ar-fase0/0.1 (proyecto de portfolio; github.com/RodrigoSchmitz1)"
BASE = "https://datos.jus.gob.ar"
DATASETS = [
    "inscripciones-iniciales-de-autos",
    "transferencias-de-autos",
    "prendas-de-autos",
    "robos-y-recuperos-de-autos",
]
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "datos", "muestra")


def pedir(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120)


def ultimo_csv(nombre):
    paquete = json.load(pedir(f"{BASE}/api/3/action/package_show?id={nombre}"))["result"]
    csvs = [r for r in paquete["resources"] if (r.get("format") or "").upper() == "CSV"]
    return max(csvs, key=lambda r: r.get("last_modified") or r.get("created") or "")


def main():
    os.makedirs(DESTINO, exist_ok=True)
    for nombre in DATASETS:
        recurso = ultimo_csv(nombre)
        archivo = os.path.join(DESTINO, f"{nombre}.csv")
        time.sleep(2.5)
        inicio = time.monotonic()
        with pedir(recurso["url"]) as r, open(archivo, "wb") as f:
            while bloque := r.read(1 << 20):
                f.write(bloque)
        mib = os.path.getsize(archivo) / 2**20
        print(f"{nombre}: {recurso['name']} -> {mib:.1f} MiB en {time.monotonic() - inicio:.0f} s")


if __name__ == "__main__":
    main()
