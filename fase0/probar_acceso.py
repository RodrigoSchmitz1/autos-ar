"""
Fase 0.2 - Acceso a las fuentes.

Prueba cada portal y registra codigo HTTP, tiempo, tipo de contenido y host
final (despues de redirecciones). Se corre igual desde la PC y desde un runner
de GitHub Actions: la comparacion entre los dos es el resultado que importa,
porque en SEPA datos.produccion.gob.ar respondia 200 desde casa y 403 desde la
nube.

Solo usa la biblioteca estandar, para que corra en cualquier lado sin instalar
nada. De los archivos grandes pide solo los primeros KB (header Range): se
mide el acceso, no se descarga nada.

Uso:
    python probar_acceso.py --origen pc
    python probar_acceso.py --origen actions
Escribe resultados_acceso_<origen>.csv al lado del script.
"""

import argparse
import csv
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "autos-ar-fase0/0.1 (proyecto de portfolio; github.com/RodrigoSchmitz1)"
PAUSA_SEGUNDOS = 2.5  # entre pedidos, scraping responsable
TIMEOUT = 30
BYTES_MUESTRA = 4096

# (fuente, descripcion, url). Las URLs de descarga de DNRPA y combustible no se
# escriben a mano: se descubren abajo con la API CKAN de cada portal, porque
# cambian con cada publicacion.
URLS = [
    ("dnrpa", "catalogo datos.jus.gob.ar",
     "https://datos.jus.gob.ar/dataset?organization=dnrpa-direccion-nacional-del-registro-de-la-propiedad-automotor-y-creditos-prendarios"),
    ("dnrpa", "catalogo datos.gob.ar (tag dnrpa)", "https://datos.gob.ar/dataset?tags=dnrpa"),
    ("dnrpa", "portal DNRPA", "https://www.dnrpa.gov.ar/portal_dnrpa/"),
    ("combustible", "dataset precios en surtidor", "http://datos.energia.gob.ar/dataset/precios-en-surtidor"),
    ("consumo", "pagina etiqueta vehicular",
     "https://www.argentina.gob.ar/economia/energia/eficiencia-energetica/etiqueta-vehicular/datos-abiertos"),
    ("consumo", "dataset etiqueta (link que daba 404)",
     "https://datos.gob.ar/dataset/ambiente-certificaciones-emisiones-gases-efecto-invernadero-consumo-vehiculos-livianos"),
    ("acara", "guia ACARA (acaramotos)", "https://www.acaramotos.org.ar/guia-oficial-de-precios.php"),
    ("acara", "ACARA autos", "https://www.acara.org.ar/guia-oficial-de-precios.php"),
    ("cca", "guia CCA (PDF)", "https://www.cca.org.ar/descargas/precios/Autos.pdf"),
    ("consumo", "portal datos.ambiente (dado de baja?)", "https://datos.ambiente.gob.ar/"),
    ("consumo", "CSV etiqueta archivado (Wayback, jun-2022)",
     "https://web.archive.org/web/20220615112830id_/https://datos.ambiente.gob.ar/dataset/501cb1f2-781d-44d0-9f91-4984587bbe35/resource/fc0039f7-bb75-4960-9a33-3a51955c8e9f/download/ensayos_co2_consumos_09062022.csv"),
    # La pagina institucional manda la cadena SSL incompleta y Python la rechaza;
    # la API en si (api.bcra.gob.ar) no tiene ese problema. Se prueban las dos.
    ("bcra", "BCRA pagina institucional", "https://www.bcra.gob.ar/apis-banco-central/"),
    ("bcra", "API transparencia: prendarios", "https://api.bcra.gob.ar/transparencia/v1.0/Prestamos/Prendarios"),
    ("repuestos", "repuestos-express robots", "https://repuestos-express.com/robots.txt"),
    ("repuestos", "repuestos-express sitemap", "https://repuestos-express.com/sitemap.xml"),
    ("repuestos", "repuestos-express busqueda", "https://repuestos-express.com/buscar?cat=filtros"),
    ("repuestos", "repuestos-express producto", "https://repuestos-express.com/producto/030115561K-H"),
    ("service", "precios de service VW Mataderos",
     "https://vwmataderos.com.ar/institucional/postventa/precios-de-servicio.htm"),
]

# Datasets CKAN por nombre exacto. Se prueban sus recursos mas nuevos: la URL
# real de descarga a veces vive en otro host que el catalogo, y es la que
# importa para la ingesta. (Una busqueda por texto elegia recursos de 2018 o
# datasets que no tenian nada que ver.)
CKAN = [
    ("dnrpa", "https://datos.jus.gob.ar", "inscripciones-iniciales-de-autos"),
    ("dnrpa", "https://datos.jus.gob.ar", "transferencias-de-autos"),
    ("dnrpa", "https://datos.jus.gob.ar", "prendas-de-autos"),
    ("dnrpa", "https://datos.jus.gob.ar", "robos-y-recuperos-de-autos"),
    ("dnrpa", "https://datos.jus.gob.ar", "listado-de-registros-seccionales-de-la-dnrnpa"),
    ("dnrpa", "https://datos.jus.gob.ar", "estadistica-de-tramites-de-automotores"),
    ("combustible", "http://datos.energia.gob.ar", "precios-en-surtidor"),
]
RECURSOS_POR_DATASET = 2

_ultimo_pedido = {}


def esperar_turno(url):
    """Respeta la pausa por host, no global: dos portales distintos no se esperan."""
    host = urllib.parse.urlsplit(url).netloc
    transcurrido = time.monotonic() - _ultimo_pedido.get(host, 0)
    if transcurrido < PAUSA_SEGUNDOS:
        time.sleep(PAUSA_SEGUNDOS - transcurrido)
    _ultimo_pedido[host] = time.monotonic()


def probar(url, leer_todo=False):
    """GET con muestra corta. Devuelve un dict; nunca levanta excepcion."""
    esperar_turno(url)
    encabezados = {"User-Agent": USER_AGENT}
    if not leer_todo:
        encabezados["Range"] = f"bytes=0-{BYTES_MUESTRA - 1}"
    pedido = urllib.request.Request(url, headers=encabezados)
    inicio = time.monotonic()
    resultado = {"url": url, "codigo": None, "segundos": None, "tipo": "",
                 "url_final": "", "bytes_leidos": 0, "error": "", "cuerpo": b""}
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT) as r:
            cuerpo = r.read() if leer_todo else r.read(BYTES_MUESTRA)
            resultado.update(codigo=r.status, tipo=r.headers.get("Content-Type", ""),
                             url_final=r.geturl(), bytes_leidos=len(cuerpo), cuerpo=cuerpo)
    except urllib.error.HTTPError as e:
        resultado.update(codigo=e.code, tipo=e.headers.get("Content-Type", "") if e.headers else "",
                         url_final=e.geturl() or "", error=str(e.reason))
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as e:
        resultado["error"] = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
    resultado["segundos"] = round(time.monotonic() - inicio, 2)
    return resultado


def fecha_recurso(recurso):
    return recurso.get("last_modified") or recurso.get("created") or ""


def descubrir_ckan(fuente, base, nombre, filas):
    """Lee el dataset con package_show y prueba la descarga de sus recursos mas nuevos."""
    url = f"{base}/api/3/action/package_show?" + urllib.parse.urlencode({"id": nombre})
    r = probar(url, leer_todo=True)
    filas.append(fila(fuente, f"API CKAN: {nombre}", r))
    if r["codigo"] != 200:
        return
    try:
        paquete = json.loads(r["cuerpo"])["result"]
    except (ValueError, KeyError):
        return
    filas[-1]["ultima_modificacion"] = paquete.get("metadata_modified", "")[:10]
    # Solo archivos: un recurso HTML es un link a una pagina, no datos.
    recursos = [x for x in paquete.get("resources", []) if (x.get("format") or "").upper() != "HTML"]
    for recurso in sorted(recursos, key=fecha_recurso, reverse=True)[:RECURSOS_POR_DATASET]:
        rr = probar(recurso.get("url", ""))
        f = fila(fuente, f"descarga: {recurso.get('name', '')}"[:120], rr)
        f["ultima_modificacion"] = fecha_recurso(recurso)[:10]
        filas.append(f)


def fila(fuente, descripcion, r):
    return {
        "fuente": fuente, "descripcion": descripcion, "codigo": r["codigo"],
        "segundos": r["segundos"], "tipo": r["tipo"][:40],
        "host_final": urllib.parse.urlsplit(r["url_final"]).netloc if r["url_final"] else "",
        "bytes_leidos": r["bytes_leidos"], "error": r["error"][:80],
        "ultima_modificacion": "", "url": r["url"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origen", required=True, help="pc o actions: va al nombre del CSV")
    args = ap.parse_args()

    filas = []
    for fuente, descripcion, url in URLS:
        filas.append(fila(fuente, descripcion, probar(url)))
        print(f"{filas[-1]['codigo']!s:>5}  {fuente:12} {descripcion}")
    for fuente, base, nombre in CKAN:
        antes = len(filas)
        descubrir_ckan(fuente, base, nombre, filas)
        for f in filas[antes:]:
            print(f"{f['codigo']!s:>5}  {fuente:12} {f['descripcion']}")

    salida = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"resultados_acceso_{args.origen}.csv")
    with open(salida, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"\n{len(filas)} pruebas -> {salida}")


if __name__ == "__main__":
    main()
