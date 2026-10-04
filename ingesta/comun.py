"""Utilidades compartidas por las ingestas: HTTP responsable, robots.txt y catalogos CKAN."""

import glob
import json
import os
import re
import ssl
import urllib.parse
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


# ---------- robots.txt ----------
# urllib.robotparser no entiende comodines: lee "Disallow: /content/*" como el
# texto literal "/content/*" y deja pasar /content/dam/ficha.pdf. Esta version
# sigue el estandar (RFC 9309, como Google): "*" y "$", y si una regla Allow y
# una Disallow coinciden, gana la mas larga (con empate, Allow).
_robots = {}


def _reglas_robots(texto, agente="autos-ar"):
    """Reglas del grupo que aplica al agente (o al de "*"), como (allow, patron)."""
    grupos, actual, en_reglas = [], None, False
    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if ":" not in linea:
            continue
        campo, valor = (x.strip() for x in linea.split(":", 1))
        campo = campo.lower()
        if campo == "user-agent":
            if actual is None or en_reglas:
                actual = {"agentes": [], "reglas": []}
                grupos.append(actual)
                en_reglas = False
            actual["agentes"].append(valor.lower())
        elif campo in ("allow", "disallow") and actual is not None:
            en_reglas = True
            if valor:
                actual["reglas"].append((campo == "allow", valor))
    propio = [g for g in grupos if any(a != "*" and a in agente.lower() for a in g["agentes"])]
    elegidos = propio or [g for g in grupos if "*" in g["agentes"]]
    return [r for g in elegidos for r in g["reglas"]]


def _coincide(patron, ruta):
    regex = "".join(".*" if c == "*" else ("$" if c == "$" and i == len(patron) - 1 else re.escape(c))
                    for i, c in enumerate(patron))
    return re.match(regex, ruta) is not None


def permitido_por_robots(url, texto_robots=None):
    """True si robots.txt del sitio permite pedir esa URL a este proyecto."""
    partes = urllib.parse.urlsplit(url)
    if texto_robots is None:
        base = f"{partes.scheme}://{partes.netloc}"
        if base not in _robots:
            try:
                _robots[base] = pedir(base + "/robots.txt").decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                # Sin robots.txt (404) todo esta permitido. Si el sitio nos rechaza
                # (401/403, nos bloquea entero) o falla (5xx): nada.
                _robots[base] = "" if e.code in (404, 410) else "User-agent: *\nDisallow: /"
            except urllib.error.URLError:
                return False  # no se pudo leer (red, dominio): ante la duda, no
        texto_robots = _robots[base]
    ruta = urllib.parse.unquote(partes.path or "/") + (f"?{partes.query}" if partes.query else "")
    mejor = None
    for allow, patron in _reglas_robots(texto_robots):
        if _coincide(urllib.parse.unquote(patron), ruta):
            largo = len(patron)
            if mejor is None or largo > mejor[0] or (largo == mejor[0] and allow):
                mejor = (largo, allow)
    return True if mejor is None else mejor[1]


def pedir_json_post(url, cuerpo, encabezados=None, timeout=120):
    """POST con cuerpo JSON (APIs como Gemini); devuelve la respuesta JSON."""
    pedido = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
                                    headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(encabezados or {})})
    with urllib.request.urlopen(pedido, timeout=timeout, context=_SSL) as r:
        return json.loads(r.read())

