"""Utilidades compartidas por las ingestas: HTTP responsable y catalogos CKAN."""

import glob
import json
import os
import ssl
import time
import urllib.error
import urllib.request

USER_AGENT = "autos-ar/0.1 (proyecto de portfolio; github.com/RodrigoSchmitz1)"
PAUSA_SEGUNDOS = 2.5
REINTENTOS = 3

_ultimo_pedido = 0.0

# Algunos servidores mandan mal la cadena de certificados (falta o sobra un
# intermedio). Windows busca el que falta solo; Linux (GitHub Actions) no, y
# falla. Los intermedios publicos que faltan se guardan en ingesta/certificados/
# y se suman a los del sistema: la verificacion sigue completa, nunca se apaga.
_SSL = ssl.create_default_context()
for _pem in glob.glob(os.path.join(os.path.dirname(__file__), "certificados", "*.pem")):
    _SSL.load_verify_locations(_pem)


def pedir(url, timeout=300):
    """GET con User-Agent identificable, pausa entre pedidos y reintentos.

    Reintenta errores de red y 5xx (los portales del Estado tienen caidas
    cortas); un 4xx no se reintenta porque no se arregla solo.
    """
    global _ultimo_pedido
    for intento in range(1, REINTENTOS + 1):
        espera = PAUSA_SEGUNDOS - (time.monotonic() - _ultimo_pedido)
        if espera > 0:
            time.sleep(espera)
        _ultimo_pedido = time.monotonic()
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(pedido, timeout=timeout, context=_SSL) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or intento == REINTENTOS:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if intento == REINTENTOS:
                raise
        time.sleep(10 * intento)


def recursos_ckan(base, dataset):
    """Recursos de un dataset CKAN (id, nombre, formato, url, ultima modificacion)."""
    paquete = json.loads(pedir(f"{base}/api/3/action/package_show?id={dataset}"))["result"]
    return [{
        "id": r["id"], "nombre": r["name"].strip(), "formato": (r.get("format") or "").upper(),
        "url": r["url"], "modificado": r.get("last_modified") or r.get("created") or "",
    } for r in paquete["resources"]]
