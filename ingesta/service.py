"""
Ingesta de precios oficiales de service programado, marca por marca.

Salida: datos/raw/service/<marca>/<AAAAMMDD>.parquet, una foto por cada vez que
la fuente CAMBIA (fecha de captura). Si el contenido es el mismo que la ultima
foto (mismo SHA-256), no se guarda nada.

Por que fotos por fecha de captura: casi ninguna fuente dice desde cuando rige
el precio, y los concesionarios actualizan cuando quieren (la pagina de VW
Mataderos seguia con el 2do trimestre cuando la lista nacional ya era del 3ro).
La fecha de captura es lo unico seguro; `vigencia_desde`/`vigencia_hasta` se
llenan solo cuando la fuente las publica. Ver docs/service_relevamiento.md.

Esquema comun para todas las marcas (una fila por modelo y service):
  marca, modelo_fuente, km, precio, tipo_precio ('lista'),
  mano_obra_bonificada, incluye_iva, items_cambio, precio_texto,
  precio_corregido, fuente_url, vigencia_desde, vigencia_hasta, capturado

Uso: python -m ingesta.service [--marcas fiat,jeep]
"""

import argparse
import collections
import hashlib
import json
import os
import re
from datetime import date

import duckdb
import pandas as pd

from ingesta.comun import pedir

RAIZ = os.path.join("datos", "raw", "service")
ESTADO = os.path.join(RAIZ, "_estado.json")

PRECIO_ESTRICTO = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})+)\s*$")
PRECIO_CON_CERO_DE_MAS = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})*\.\d{3})0\s*$")


def a_pesos(texto):
    return int(texto.replace(".", ""))


# ---------- Stellantis: Fiat y Jeep (Mopar) ----------
def mopar(marca):
    """Un JSON estatico por marca: modelos -> services por km -> precio de lista.

    Precio en texto ("Precio de Lista: $ 434.000"). Dos errores conocidos de
    tipeo ("$ 434.0000"): se corrigen solo si, sin el cero de mas, coinciden con
    el precio habitual del modelo, y quedan marcados en `precio_corregido`. Si
    no coinciden, falla: mejor un pipeline en rojo que un precio inventado.
    """
    url = f"https://mantenimientomopar.com.ar/{marca}/js/db.json"
    contenido = pedir(url)
    modelos = json.loads(contenido.decode("utf-8"))
    filas = []
    for m in modelos:
        servicios = m["kilometro"]
        validos = [a_pesos(x[1]) for x in (PRECIO_ESTRICTO.search(s["servicio"]) for s in servicios) if x]
        habitual = collections.Counter(validos).most_common(1)[0][0] if validos else None
        for s in servicios:
            texto = s["servicio"].strip()
            estricto = PRECIO_ESTRICTO.search(texto)
            corregido = False
            if estricto:
                precio = a_pesos(estricto[1])
            else:
                sin_cero = PRECIO_CON_CERO_DE_MAS.search(texto)
                if sin_cero and a_pesos(sin_cero[1]) == habitual:
                    precio, corregido = habitual, True
                else:
                    raise ValueError(f"{marca} {m['name']} {s['miles']} km: precio ilegible {texto!r}")
            filas.append({
                "marca": marca.capitalize(), "modelo_fuente": m["name"].strip(),
                "km": a_pesos(s["miles"]), "precio": precio, "tipo_precio": "lista",
                "mano_obra_bonificada": False, "incluye_iva": None,
                "items_cambio": " | ".join(s.get("cambio") or []),
                "precio_texto": texto, "precio_corregido": corregido,
                "fuente_url": url, "vigencia_desde": None, "vigencia_hasta": None,
            })
    return contenido, filas


# ---------- Stellantis: Peugeot y Citroen (tiendas online, mismo sistema) ----------
class Tienda:
    """Cliente de las tiendas de service de Peugeot y Citroen.

    Formulario con combos encadenados (modelo -> version -> service) que se
    llenan por AJAX. Necesita la cookie de sesion y el token CSRF de la pagina.
    El precio se pide para un concesionario; la respuesta es codigo JavaScript
    que la pagina ejecuta, y de ahi se extraen "PRECIO LISTA" y el total.
    """

    def __init__(self, base):
        import http.cookiejar
        import urllib.request
        self.base = base
        self.abrir = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())).open
        html = self._pedido("/mantenimientos-programados")
        self.token = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)[1]
        self.modelos = re.findall(
            r'<option value="(\d+)">([^<]+)</option>',
            re.search(r'id="servicio-id_gama".*?</select>', html, re.S)[0])

    def _pedido(self, ruta, datos=None):
        import time
        import urllib.error
        import urllib.parse
        import urllib.request
        from ingesta.comun import PAUSA_SEGUNDOS, USER_AGENT
        time.sleep(PAUSA_SEGUNDOS)
        encabezados = {"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"}
        cuerpo = None
        if datos is not None:
            encabezados.update({"X-CSRF-Token": self.token,
                                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            cuerpo = urllib.parse.urlencode(dict(datos, _csrf=self.token)).encode()
        pedido = urllib.request.Request(self.base + ruta, data=cuerpo, headers=encabezados)
        # Reintentos con espera creciente: el 2026-10-01 la tienda de Peugeot
        # corto la conexion a mitad de una recoleccion. Si sigue cortando despues
        # de 3 intentos, se frena: puede ser una proteccion contra volumen.
        for intento in range(1, 4):
            try:
                self.pedidos = getattr(self, "pedidos", 0) + 1
                return self.abrir(pedido, timeout=60).read().decode("utf-8", "replace")
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if intento == 3:
                    raise
                time.sleep(10 * intento)

    def versiones(self, id_modelo):
        return json.loads(self._pedido("/cargarmantenimientoauto", {"id": id_modelo, "tipo": 1}))

    def services(self, id_version):
        return json.loads(self._pedido("/cargarmantenimiento", {"id": id_version, "tipo": 1}))

    def concesionarios(self, id_provincia=1):
        import urllib.parse
        return json.loads(self._pedido("/servicio-cargar-concesionario?" + urllib.parse.urlencode(
            {"id_provincia": id_provincia, "id_localidad": 0})))

    def precio(self, id_service, id_concesionario):
        js = self._pedido("/cargardatosmantenimiento",
                          {"id_mantenimiento": id_service, "id_concesionario": id_concesionario})
        lista = re.search(r"PRECIO LISTA: <span>\$([\d.]+),\d\d</span>", js)
        total = re.search(r'#hidTotal"\)\.val\((\d+)\)', js)
        if not (lista and total):
            raise ValueError(f"respuesta sin precio para el service {id_service}: {js[:200]!r}")
        return a_pesos(lista[1]), int(total[1])


def tienda_stellantis(marca, base):
    """Todos los modelos, versiones y services de la tienda, con un concesionario
    de referencia (el primero de CABA).

    Control de uniformidad: el precio se supone el mismo en toda la red (asi dio
    en la prueba: $460.000 el 208 1.6 N a 10.000 km en dos concesionarios). En
    cada corrida se compara un service contra otros dos concesionarios; si
    difieren, falla, porque entonces "el precio" deja de ser uno solo.
    """
    t = Tienda(base)
    conces = t.concesionarios()
    referencia = conces[0]["id_concesionario"]
    filas, primero = [], None
    for id_modelo, nombre_modelo in t.modelos:
        for v in t.versiones(id_modelo):
            for s in t.services(v["id"]):
                km = int(re.sub(r"\D", "", s["name"]))  # "10.000KM" -> 10000
                lista, total = t.precio(s["id"], referencia)
                primero = primero or s["id"]
                filas.append({
                    "marca": marca.capitalize(), "modelo_fuente": v["name"].strip(),
                    "km": km, "precio": lista, "tipo_precio": "lista",
                    "mano_obra_bonificada": False, "incluye_iva": None,
                    "items_cambio": None, "precio_texto": f"lista {lista} / total {total}",
                    "precio_corregido": False, "fuente_url": base + "/mantenimientos-programados",
                    "vigencia_desde": None, "vigencia_hasta": None,
                    "id_service_fuente": s["id"], "modelo_familia_fuente": nombre_modelo.strip(),
                })
    # La tienda a veces carga dos veces el mismo service (208 1.6 N, 50.000 km:
    # ids 544 y 224, ambos $460.000). Mismo precio: es una carga duplicada y
    # queda una sola fila. Precio distinto: no hay forma de saber cual vale, falla.
    unicas = {}
    for f in filas:
        clave = (f["modelo_fuente"], f["km"])
        if clave in unicas and unicas[clave]["precio"] != f["precio"]:
            raise RuntimeError(f"{marca} {clave}: service repetido con precios distintos "
                               f"({unicas[clave]['precio']} vs {f['precio']})")
        unicas.setdefault(clave, f)
    filas = list(unicas.values())
    precio_ref = next(f["precio"] for f in filas if f["id_service_fuente"] == primero)
    for c in conces[1:3]:
        otro, _ = t.precio(primero, c["id_concesionario"])
        if otro != precio_ref:
            raise RuntimeError(f"{marca}: el precio cambia entre concesionarios ({precio_ref} vs {otro} en {c['nombre']})")
    contenido = json.dumps(filas, sort_keys=True, default=str).encode()
    return contenido, filas


RECOLECTORES = {
    "fiat": lambda: mopar("fiat"),
    "jeep": lambda: mopar("jeep"),
    "peugeot": lambda: tienda_stellantis("peugeot", "https://www.peugeotstore.com.ar"),
    "citroen": lambda: tienda_stellantis("citroen", "https://www.citroenstore.com.ar"),
}

# Las tiendas cuestan ~180 pedidos por marca (~8 minutos con la pausa de
# cortesia). Los precios cambian una vez por mes: consultarlas todos los dias
# seria abusar del sitio. Se consultan como maximo una vez cada 7 dias.
DIAS_ENTRE_CONSULTAS = {"peugeot": 7, "citroen": 7}


def validar(marca, filas):
    """Controles minimos: si fallan, la fuente cambio de formato o trae basura."""
    errores = []
    if len(filas) < 20:
        errores.append(f"solo {len(filas)} filas")
    fuera = [f for f in filas if not 100_000 <= f["precio"] <= 5_000_000]
    if fuera:
        errores.append(f"{len(fuera)} precios fuera de $100.000-$5.000.000 (ej.: {fuera[0]['modelo_fuente']} {fuera[0]['km']} km ${fuera[0]['precio']:,})")
    if len({(f["modelo_fuente"], f["km"]) for f in filas}) != len(filas):
        errores.append("modelo y km repetidos")
    if errores:
        raise RuntimeError(f"service {marca}: " + "; ".join(errores))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marcas", default=",".join(RECOLECTORES))
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    hoy = date.today()
    consultado = estado.setdefault("consultado", {})
    for marca in args.marcas.split(","):
        espera = DIAS_ENTRE_CONSULTAS.get(marca)
        if espera and marca in consultado and (hoy - date.fromisoformat(consultado[marca])).days < espera:
            print(f"service {marca}: consultado el {consultado[marca]}, se vuelve a consultar cada {espera} dias")
            continue
        contenido, filas = RECOLECTORES[marca]()
        huella = hashlib.sha256(contenido).hexdigest()
        validar(marca, filas)
        # La fecha se registra solo si la consulta y los controles terminaron
        # bien: si algo fallo, se reintenta al dia siguiente.
        if espera:
            consultado[marca] = hoy.isoformat()
            json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)
        if estado.get(marca) == huella:
            print(f"service {marca}: sin cambios")
            continue
        destino = os.path.join(RAIZ, marca)
        os.makedirs(destino, exist_ok=True)
        con = duckdb.connect()
        con.register("t", pd.DataFrame(filas))
        con.sql(f"""COPY (SELECT *, DATE '{hoy.isoformat()}' AS capturado FROM t)
                    TO '{os.path.join(destino, hoy.strftime('%Y%m%d') + '.parquet')}' (FORMAT parquet)""")
        estado[marca] = huella
        json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)
        corregidos = sum(f["precio_corregido"] for f in filas)
        print(f"service {marca}: {len(filas)} services de {len({f['modelo_fuente'] for f in filas})} modelos"
              + (f" ({corregidos} precios con un cero de mas, corregidos)" if corregidos else ""))


if __name__ == "__main__":
    main()
