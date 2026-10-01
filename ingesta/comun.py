"""Utilidades compartidas por las ingestas: HTTP responsable y catalogos CKAN."""

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "autos-ar/0.1 (proyecto de portfolio; github.com/RodrigoSchmitz1)"
PAUSA_SEGUNDOS = 2.5
REINTENTOS = 3

_ultimo_pedido = 0.0


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
            with urllib.request.urlopen(pedido, timeout=timeout) as r:
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
