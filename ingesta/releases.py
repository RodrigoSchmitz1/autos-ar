"""
Persistencia de datos/raw en GitHub Releases.

Cada corrida de GitHub Actions arranca en una maquina vacia: los Parquet tienen
que vivir en algun lado entre una corrida y la siguiente. Van como archivos
adjuntos de releases del propio repo: gratis, publicos y separados del codigo.

Organizacion:
  datos-AAAA     los Parquet mensuales de ese anio (dnrpa__inscripciones__202608.parquet)
  datos-general  todo lo que no es mensual: estaciones, archivos de estado y el
                 manifiesto
Un release por anio y no uno solo: GitHub admite hasta 1.000 archivos por
release, y con ~60 archivos nuevos por anio uno solo se llenaria.

El manifiesto (manifiesto.json) guarda el SHA-256 de cada archivo publicado.
`subir` compara contra el y sube solo lo que cambio: un mes normal son unos
pocos archivos. Se sube al final, cuando todo lo demas ya subio: si la corrida
se corta a la mitad, el manifiesto viejo hace que la proxima reintente.

Uso:
  python -m ingesta.releases bajar   # publico; con GITHUB_TOKEN evita el limite de la API
  python -m ingesta.releases subir   # necesita la CLI gh y permiso de escritura (Actions)
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "RodrigoSchmitz1/autos-ar")
RAIZ = os.path.join("datos", "raw")
GENERAL = "datos-general"
MANIFIESTO = "manifiesto.json"                         # nombre del asset
MANIFIESTO_LOCAL = os.path.join("datos", MANIFIESTO)   # copia local, fuera de git


def nombre_asset(ruta_relativa):
    """dnrpa/inscripciones/202608.parquet -> dnrpa__inscripciones__202608.parquet"""
    return ruta_relativa.replace("\\", "/").replace("/", "__")


def ruta_de_asset(nombre):
    return os.path.join(RAIZ, *nombre.split("__"))


def release_de(nombre):
    """El anio sale del periodo AAAAMM del nombre; lo que no es mensual va a general."""
    m = re.search(r"__(20\d\d)\d\d\.parquet$", nombre)
    return f"datos-{m[1]}" if m else GENERAL


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def archivos_locales():
    for carpeta, _, archivos in os.walk(RAIZ):
        for a in archivos:
            if a.startswith("_tmp"):
                continue
            ruta = os.path.join(carpeta, a)
            yield nombre_asset(os.path.relpath(ruta, RAIZ)), ruta


# ---------- lectura (API publica) ----------
def _api(url):
    encabezados = {"Accept": "application/vnd.github+json", "User-Agent": "autos-ar"}
    if os.environ.get("GITHUB_TOKEN"):
        encabezados["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=encabezados), timeout=120) as r:
        return json.loads(r.read())


def assets_publicados():
    """{nombre_de_asset: url_de_descarga} de todos los releases datos-*."""
    assets, pagina = {}, 1
    while True:
        releases = _api(f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={pagina}")
        if not releases:
            return assets
        for rel in releases:
            if rel["tag_name"].startswith("datos-"):
                for a in rel["assets"]:
                    assets[a["name"]] = a["browser_download_url"]
        pagina += 1


def descargar(url, reintentos=4):
    """Descarga un asset. Reintenta: GitHub devuelve 500 de vez en cuando (paso
    en la primera verificacion) y sin reintento se caeria el pipeline del dia."""
    for intento in range(1, reintentos + 1):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": "autos-ar"})
            with urllib.request.urlopen(pedido, timeout=600) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if intento == reintentos or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
                raise
            time.sleep(5 * intento)


def bajar():
    assets = assets_publicados()
    if not assets:
        print("No hay datos publicados todavia: la ingesta arranca de cero.")
        return
    for nombre, url in sorted(assets.items()):
        destino = MANIFIESTO_LOCAL if nombre == MANIFIESTO else ruta_de_asset(nombre)
        os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
        contenido = descargar(url)
        with open(destino, "wb") as f:
            f.write(contenido)
    print(f"Bajados {len(assets)} archivos de los releases.")


# ---------- escritura (CLI gh, en Actions) ----------
def _gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def asegurar_release(tag, existentes):
    if tag in existentes:
        return
    _gh("release", "create", tag, "--repo", REPO, "--title", tag, "--latest=false",
        "--notes", "Datos generados por el pipeline (ver README). No editar a mano.")
    existentes.add(tag)


def subir():
    publicado = json.load(open(MANIFIESTO_LOCAL, encoding="utf-8")) if os.path.exists(MANIFIESTO_LOCAL) else {}
    actual = {nombre: sha256(ruta) for nombre, ruta in archivos_locales()}
    cambiados = sorted(n for n, h in actual.items() if publicado.get(n) != h)
    if not cambiados:
        print("Nada nuevo para subir.")
        return
    existentes = {r["tagName"] for r in json.loads(
        _gh("release", "list", "--repo", REPO, "--limit", "200", "--json", "tagName"))}
    por_release = {}
    for nombre in cambiados:
        por_release.setdefault(release_de(nombre), []).append(nombre)
    with tempfile.TemporaryDirectory() as tmp:
        for tag, nombres in sorted(por_release.items()):
            asegurar_release(tag, existentes)
            # El asset se sube con su nombre plano: se copia a un temporal con ese nombre.
            rutas = []
            for n in nombres:
                ruta = os.path.join(tmp, n)
                with open(ruta_de_asset(n), "rb") as origen, open(ruta, "wb") as copia:
                    copia.write(origen.read())
                rutas.append(ruta)
            _gh("release", "upload", tag, *rutas, "--repo", REPO, "--clobber")
            print(f"{tag}: {len(nombres)} archivos")
        # El manifiesto va ultimo: si algo fallo antes, la proxima corrida reintenta.
        ruta = os.path.join(tmp, MANIFIESTO)
        json.dump(actual, open(ruta, "w", encoding="utf-8"), indent=1, sort_keys=True)
        asegurar_release(GENERAL, existentes)
        _gh("release", "upload", GENERAL, ruta, "--repo", REPO, "--clobber")
    json.dump(actual, open(MANIFIESTO_LOCAL, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print(f"Subidos {len(cambiados)} archivos y el manifiesto.")


if __name__ == "__main__":
    {"bajar": bajar, "subir": subir}[sys.argv[1]]()
