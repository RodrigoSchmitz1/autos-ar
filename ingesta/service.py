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



def es_pdf(contenido, url):
    """El contenido tiene que ser un PDF; si no (pagina de bloqueo o de error), un mensaje claro."""
    if not contenido.startswith(b"%PDF"):
        inicio = " ".join(contenido[:120].decode("utf-8", "ignore").split())
        raise ValueError(f"{url} no devolvio un PDF (posible bloqueo o pagina de error): {inicio!r}")
    return contenido


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


# ---------- Volkswagen: lista nacional en PDF, publicada por un concesionario ----------
MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}

# Encabezados con una barra de menos en el PDF: "Scirocco" y "Sharan" quedan
# en lineas distintas sin "/" entre ellos. No se puede partir por salto de
# linea en general porque otros nombres ocupan dos lineas ("The / Beetle").
SEPARAR_VW = {"Scirocco Sharan": ["Scirocco", "Sharan"]}


def volkswagen():
    """Lista trimestral de VW (solo nafta) en el PDF de Alperovich, que la
    copia de la lista nacional. La grilla del PDF tiene rectangulos, asi que
    pdfplumber arma la tabla: una columna por grupo de modelos y una fila por
    service (cada 15.000 km). El titulo trae la vigencia ("Q3 - Julio a
    Septiembre 2026"). Cada grupo se abre en una fila por modelo: el cruce con
    el catalogo es por modelo, y el grupo queda en `grupo_fuente`.
    """
    import calendar
    import io

    import pdfplumber
    url = "https://www.alperovichsa.com.ar/assets/precios-servicios-mantenimiento.pdf"
    contenido = pedir(url)
    tablas = pdfplumber.open(io.BytesIO(es_pdf(contenido, url))).pages[0].extract_tables()
    tabla = [[(c or "").replace("\n", " ").strip() for c in fila] for fila in max(tablas, key=len)]

    vig = re.search(r"Q[1-4] - (\w+) a (\w+) (\d{4})", tabla[0][0])
    if not vig:
        raise ValueError(f"volkswagen: titulo sin vigencia {tabla[0][0]!r}")
    anio, mes_desde, mes_hasta = int(vig[3]), MESES[vig[1].lower()], MESES[vig[2].lower()]
    desde = date(anio, mes_desde, 1)
    hasta = date(anio, mes_hasta, calendar.monthrange(anio, mes_hasta)[1])

    encabezado = next(f for f in tabla if f[0].upper().startswith("MOTOR"))
    if "NAFTA" not in encabezado[0].upper():
        raise ValueError(f"volkswagen: se esperaba la lista de nafta, vino {encabezado[0]!r}")
    filas = []
    for fila in tabla:
        servicio = re.match(r"\d+\w+\. Servicio ([\d.]+) km", fila[0])
        if not servicio:
            continue
        km = a_pesos(servicio[1])
        for grupo, celda in zip(encabezado[1:], fila[1:]):
            precio = PRECIO_ESTRICTO.search(celda)
            if not precio:
                raise ValueError(f"volkswagen {grupo} {km} km: precio ilegible {celda!r}")
            modelos = []
            for parte in (p.strip() for p in grupo.split("/")):
                modelos += SEPARAR_VW.get(parte, [parte] if parte else [])
            for modelo in modelos:
                filas.append({
                    "marca": "Volkswagen", "modelo_fuente": modelo, "km": km,
                    "precio": a_pesos(precio[1]), "tipo_precio": "lista",
                    "mano_obra_bonificada": "BONIFICADA" in fila[0].upper(),
                    "incluye_iva": None, "items_cambio": None, "precio_texto": celda,
                    "precio_corregido": False, "fuente_url": url,
                    "vigencia_desde": desde, "vigencia_hasta": hasta,
                    "grupo_fuente": grupo,
                })
    return contenido, filas


# ---------- Toyota: tabla HTML de un concesionario ----------
def toyota():
    """Plan de mantenimiento en la pagina de Toyota Federico (concesionario).

    toyota.com.ar carga los precios desde una API que su robots.txt prohibe;
    Federico publica la misma lista en HTML y su robots.txt permite todo. Que
    es la lista nacional y no precios propios se verifico el 2026-10-02: otro
    concesionario (Panamericana) publica exactamente los mismos montos.

    Por modelo, dos tablas: 10k-100k y "(desde 110.000 km)" 110k-200k. El
    titulo trae el modelo en <b>; "Corolla / Corolla Cross" se abre en dos.
    Sin fecha ni mencion del IVA: queda la fecha de captura.
    """
    import html as html_lib
    url = "https://www.toyotafederico.com/plan-mantenimiento.php"
    pagina = pedir(url).decode("utf-8", "replace")

    def celdas(fila):
        return [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"(?s)<td[^>]*>(.*?)</td>", fila)]

    filas = []
    for tabla in re.findall(r"(?s)<table.*?</table>", pagina):
        titulo = re.search(r"Precios de mantenimiento\s*<b>([^<]+)</b>", tabla)
        if not titulo:
            continue
        renglones = re.findall(r"(?s)<tr.*?</tr>", tabla)
        kms, precios = celdas(renglones[1]), celdas(renglones[2])
        if len(kms) != len(precios) or not all(re.fullmatch(r"\d+k", k) for k in kms):
            raise ValueError(f"toyota {titulo[1]}: tabla con otro formato {kms} {precios}")
        for k, celda in zip(kms, precios):
            precio = re.fullmatch(r"\$\s*(\d{1,3}(?:\.\d{3})+)", celda)
            if not precio:
                raise ValueError(f"toyota {titulo[1]} {k}: precio ilegible {celda!r}")
            for modelo in (m.strip() for m in titulo[1].split("/")):
                filas.append({
                    "marca": "Toyota", "modelo_fuente": modelo, "km": int(k[:-1]) * 1000,
                    "precio": a_pesos(precio[1]), "tipo_precio": "lista",
                    "mano_obra_bonificada": False, "incluye_iva": None, "items_cambio": None,
                    "precio_texto": celda, "precio_corregido": False, "fuente_url": url,
                    "vigencia_desde": None, "vigencia_hasta": None,
                    "grupo_fuente": titulo[1].strip(),
                })
    # La huella es de las filas, no de la pagina: el HTML trae los precios de
    # los 0 km del menu, que cambian seguido sin que cambie el service.
    return json.dumps(filas, sort_keys=True).encode(), filas


# ---------- Renault: planilla del concesionario Pourtau, en PDF ----------
PRECIO_RENAULT = re.compile(r"(\+\s?)?\$\s?(\d{1,3}(?:\.\d{3})+|\d+)")
# Que columna de precio va a cada km. El precio base (segun el aceite del
# motor) vale en los km que no tienen pack; las columnas de packs son el
# precio total de ese service: en todos los motores "20K" = base + ~$27.740.
KM_RENAULT = {10: 0, 20: 1, 30: 0, 40: 2, 50: 0, 60: 3, 70: 0, 80: 4,
              90: 0, 100: 1, 110: 0, 120: 5}
# Electricos (E-TECH): base cada 10.000 km mas un adicional explicito ("+ $18210")
# segun el km. Columnas de la tabla: 20/40/100, 30/90, 60/120 mil km.
ADICIONAL_ETECH = {20: 0, 40: 0, 100: 0, 30: 1, 90: 1, 60: 2, 120: 2}
# Renglones que valen para dos modelos. Lista explicita y no una regla: en
# "Megane III/ RS" y "Fluence Gt / Sport" la barra no separa modelos.
GRUPOS_RENAULT = {"Fluence/Megane III": ["Fluence", "Megane III"],
                  "Nuevo Logan-Sandero": ["Nuevo Logan", "Nuevo Sandero"],
                  "Logan-Sandero PH2": ["Logan PH2", "Sandero PH2"]}


def renault():
    """Programa de mantenimiento Renault, planilla de Excel exportada a PDF que
    publica el concesionario Pourtau. Se regenera todos los dias (la fecha de
    creacion del PDF cambia), asi que la huella es de las filas extraidas.

    Una fila por motor ("Duster K4M - 1,6l 16v"): el motor cambia el precio.
    Los nombres salen de la grilla de la tabla; los precios, del texto de cada
    renglon, porque la tabla junta celdas en algunos renglones y pierde un
    precio (Boreal). Un renglon trae 6 precios (base, 20K/100K, 40K, 60K, 80K,
    120K) o 7 si el base se repite en dos columnas de aceite.
    """
    import io

    import pdfplumber
    url = "https://premiumconsulting.com.ar/pourtau/quiter/ldp/Lista%20de%20precios.pdf"
    pagina = pdfplumber.open(io.BytesIO(es_pdf(pedir(url), url))).pages[0]
    tablas = pagina.extract_tables()
    nombres = {}
    for tabla in tablas:
        for fila in tabla:
            modelo, motor = ((c or "").replace("\n", " ").strip() for c in fila[:2])
            con_precio = any("$" in (c or "") for c in fila[2:])
            if modelo and motor and con_precio and "$" not in modelo + motor:
                nombres[f"{modelo} {motor}"] = (modelo.lstrip("*").strip(), motor)

    filas = []

    def agregar(grupo, motor, km, precio, texto):
        for modelo in GRUPOS_RENAULT.get(grupo, [grupo]):
            filas.append({
                "marca": "Renault", "modelo_fuente": f"{modelo} {motor}", "km": km * 1000,
                "precio": precio, "tipo_precio": "lista", "mano_obra_bonificada": False,
                "incluye_iva": None, "items_cambio": None, "precio_texto": texto,
                "precio_corregido": False, "fuente_url": url,
                "vigencia_desde": None, "vigencia_hasta": None, "grupo_fuente": grupo,
            })

    vistos = set()
    for renglon in pagina.extract_text().splitlines():
        inicio = PRECIO_RENAULT.search(renglon)
        clave = renglon[:inicio.start()].strip() if inicio else None
        if clave not in nombres:
            continue
        vistos.add(clave)
        modelo, motor = nombres[clave]
        tokens = PRECIO_RENAULT.findall(renglon)
        precios = [a_pesos(p) for _, p in tokens]
        if "E-TECH" in modelo.upper():
            if len(precios) != 4 or not all(mas for mas, _ in tokens[1:]):
                raise ValueError(f"renault {clave}: renglon E-TECH inesperado {renglon!r}")
            for km in range(10, 130, 10):
                extra = precios[1 + ADICIONAL_ETECH[km]] if km in ADICIONAL_ETECH else 0
                agregar(modelo, motor, km, precios[0] + extra, renglon)
            continue
        if len(precios) == 7 and precios[0] == precios[1]:
            precios = precios[1:]
        if len(precios) != 6:
            raise ValueError(f"renault {clave}: {len(precios)} precios en {renglon!r}")
        for km, col in KM_RENAULT.items():
            agregar(modelo, motor, km, precios[col], renglon)
    faltan = set(nombres) - vistos
    if faltan:
        raise ValueError(f"renault: modelos de la tabla sin renglon de precios: {sorted(faltan)}")
    return json.dumps(filas, sort_keys=True).encode(), filas


# ---------- BYD: guia de servicio oficial, JSON dentro de la pagina, en dolares ----------
def byd():
    """Guia de servicio de byd.com/ar: los datos vienen en un JSON dentro del
    atributo `:app-property` de la pagina (modelo -> km/meses -> precio).

    Precios en dolares con IVA ("USD 92 (IVA Incluido)"): se guardan en
    dolares (`moneda` = 'USD') y se pasan a pesos en dbt con el tipo de cambio
    minorista del BCRA (ingesta/cambio.py). La vigencia sale del texto legal
    ("valido desde el 01/05/2026 hasta el 30/06/2026").
    """
    import html as html_lib
    url = "https://www.byd.com/ar/service-guide"
    pagina = pedir(url).decode("utf-8", "replace")
    datos = re.search(r':app-property="([^"]*packageList[^"]*)"', pagina)
    if not datos:
        raise ValueError("byd: la pagina no trae el JSON de la guia de servicio")
    guia = json.loads(html_lib.unescape(datos[1]))
    texto = re.sub(r"<[^>]+>", " ", html_lib.unescape(pagina))
    vig = re.search(r"desde el (\d{2})/(\d{2})/(\d{4}) hasta el (\d{2})/(\d{2})/(\d{4})", texto)
    if not vig:
        raise ValueError("byd: no se encontro la vigencia en el texto legal")
    d = [int(x) for x in vig.groups()]
    desde, hasta = date(d[2], d[1], d[0]), date(d[5], d[4], d[3])
    filas = []
    for modelo in guia["packageList"]:
        for s in modelo["category"]:
            km = re.match(r"\s*([\d.]+)\s*K", s["name"], re.I)
            precio = re.fullmatch(r"USD\s*(\d+)\s*\(IVA Incluido\)", s["price"].strip())
            if not (km and precio):
                raise ValueError(f"byd {modelo['name']}: service ilegible {s['name']!r} {s['price']!r}")
            items = [html_lib.unescape(re.sub(r"<[^>]+>", "", i)).strip()
                     for i in re.findall(r"(?s)<li[^>]*>(.*?)</li>", s.get("service") or "")]
            filas.append({
                "marca": "BYD", "modelo_fuente": re.sub(r"^BYD\s+", "", modelo["name"].strip()),
                "km": a_pesos(km[1]), "precio": int(precio[1]), "moneda": "USD",
                "tipo_precio": "lista", "mano_obra_bonificada": False, "incluye_iva": True,
                "items_cambio": " | ".join(i for i in items if i), "precio_texto": s["price"].strip(),
                "precio_corregido": False, "fuente_url": url,
                "vigencia_desde": desde, "vigencia_hasta": hasta,
            })
    return json.dumps(filas, sort_keys=True, default=str).encode(), filas


# ---------- Ford: pagina oficial por version, lista nacional sugerida ----------
ETIQUETAS_FORD = {"Precio Fidelidad Ford", "Precio Ford Protect Mantenimiento Prepago"}
MAX_PAGINAS_FORD = 150


def nombre_ford(ruta):
    """Nombre de la version a partir de la URL: los titulos de las paginas no
    sirven (las E-Transit dicen "Bronco sport", una Ranger diesel dice "2.5L
    Nafta"). ".../territory/territory-1-5-l.html" -> "territory 1.5L"; si la
    carpeta agrega el modelo ("transit-chasis/chasis-2-0-l-panther"), se le
    antepone ("transit chasis 2.0L panther").
    """
    partes = ruta.split("/mantenimiento-garantia/")[1][:-5].split("/")
    nombre = re.sub(r"^nuev[oa]-", "", partes[-1].lower())  # "nuevo-fiesta" -> "fiesta"
    if len(partes) > 1:
        modelo = partes[-2].replace("-picker", "").replace("nueva-", "").replace("nuevo-", "")
        if not nombre.replace("-", "").startswith(modelo.split("-")[0]):  # "s-max" en "smax"
            nombre = modelo.split("-")[0] + "-" + nombre
    nombre = nombre.replace("-", " ")
    nombre = re.sub(r"\b(\d) (\d) l\b", r"\1.\2L", nombre)  # "1 5 l" -> "1.5L"
    return re.sub(r"\b(\d) l\b", r"\1L", nombre)  # "2 l" -> "2L"


def ford():
    """Plan de mantenimiento de ford.com.ar: una pagina por version, con una
    solapa por service (10 mil km, 20 mil km...). Se recorren los enlaces desde
    /posventa/mantenimientos/ (tope de paginas por si el sitio cambia).

    De cada solapa se toma el "Precio Fidelidad Ford": su nota legal ("Posventa
    mantenimiento") dice que es el precio sugerido por Ford a toda la red, con
    IVA y de contado, con vigencia mensual. El "Ford Protect" es prepago y
    queda afuera. Si aparece otra etiqueta de precio, falla: puede ser un
    precio con descuento (Ford tiene uno, "Con vos", en otras paginas).
    """
    import html as html_lib
    base = "https://www.ford.com.ar"
    inicio = pedir(base + "/posventa/mantenimientos/").decode("utf-8", "replace")
    cola = sorted(set(re.findall(r'href="(/posventa/mantenimiento-garantia/[^"#?]+\.html)"', inicio)))
    vistos, filas = set(), []
    while cola:
        ruta = cola.pop(0)
        if ruta in vistos or ruta.endswith("/iolm.html"):
            continue
        if len(vistos) >= MAX_PAGINAS_FORD:
            raise RuntimeError(f"ford: mas de {MAX_PAGINAS_FORD} paginas, el sitio cambio de estructura")
        vistos.add(ruta)
        pagina = pedir(base + ruta).decode("utf-8", "replace")
        cola += sorted(set(re.findall(r'href="(' + re.escape(ruta[:-5]) + r'/[^"#?]+\.html)"', pagina)))
        if "Precio Fidelidad Ford" not in pagina:
            continue
        etiquetas = set(re.findall(r"<strong>(Precio [^<]+?)<sup", pagina))
        if etiquetas - ETIQUETAS_FORD:
            raise ValueError(f"ford {ruta}: etiquetas de precio nuevas {etiquetas - ETIQUETAS_FORD}")
        notas = {d["name"]: d["text"] for raw in re.findall(r'data-disclosures-json="([^"]*)"', pagina)
                 for d in json.loads(html_lib.unescape(raw))}
        nota = html_lib.unescape(re.sub(r"<[^>]+>", " ", notas.get("Posventa mantenimiento", "")))
        vig = re.search(r"DESDE EL\s*(\d{2})/(\d{2})/(\d{4}) AL (\d{2})/(\d{2})/(\d{4})", nota)
        if not vig:
            raise ValueError(f"ford {ruta}: sin vigencia en la nota legal")
        d = [int(x) for x in vig.groups()]
        desde, hasta = date(d[2], d[1], d[0]), date(d[5], d[4], d[3])
        # El id de la solapa a veces viene con mayuscula ("60K"): sin el [kK]
        # esa solapa se pegaba a la anterior.
        bloques = re.split(r'<a href="#tabs-\d+" id="(\d+)[kK]" class="mob-accordion-tab"', pagina)
        solapas = len(re.findall(r'<div id="tabs-\d+" class="tabs-content"', pagina))
        if len(bloques) // 2 != solapas:
            raise ValueError(f"ford {ruta}: {len(bloques) // 2} solapas leidas de {solapas}")
        for km, bloque in zip(bloques[1::2], bloques[2::2]):
            precios = re.findall(r"Precio Fidelidad Ford.*?\$\s*([\d.]+)", bloque, re.S)
            sin_iva = re.search(r"Sin IVA \$\s*([\d.]+)", bloque)
            # Cada solapa trae el precio dos veces (version escritorio y celular).
            if not precios or len(set(precios)) != 1:
                raise ValueError(f"ford {ruta} {km}k: precio ausente o distinto entre versiones {precios}")
            filas.append({
                "marca": "Ford", "modelo_fuente": nombre_ford(ruta), "km": int(km) * 1000,
                "precio": a_pesos(precios[0]), "tipo_precio": "lista",
                "mano_obra_bonificada": False, "incluye_iva": True, "items_cambio": None,
                "precio_texto": f"$ {precios[0]} (sin IVA $ {sin_iva[1] if sin_iva else '?'})",
                "precio_corregido": False, "fuente_url": base + ruta,
                "vigencia_desde": desde, "vigencia_hasta": hasta,
            })
    return json.dumps(filas, sort_keys=True, default=str).encode(), filas


RECOLECTORES = {
    "fiat": lambda: mopar("fiat"),
    "jeep": lambda: mopar("jeep"),
    "peugeot": lambda: tienda_stellantis("peugeot", "https://www.peugeotstore.com.ar"),
    "citroen": lambda: tienda_stellantis("citroen", "https://www.citroenstore.com.ar"),
    "volkswagen": volkswagen,
    "toyota": toyota,
    "renault": renault,
    "byd": byd,
    "ford": ford,
}

# Las tiendas de Peugeot y Citroen cuestan ~180 pedidos por marca, y Ford ~65
# paginas de ~400 KB (~8 y ~4 minutos con la pausa de
# cortesia). Los precios cambian una vez por mes: consultarlas todos los dias
# seria abusar del sitio. Se consultan como maximo una vez cada 7 dias.
DIAS_ENTRE_CONSULTAS = {"peugeot": 7, "citroen": 7, "ford": 7}
# Las demas, como maximo una vez por dia: el pipeline tambien corre con cada
# push, y varias consultas el mismo dia a un concesionario no aportan nada (las
# listas cambian cada meses) y pueden hacer que bloquee a GitHub.
DIAS_MINIMO = 1


def validar(marca, filas):
    """Controles minimos: si fallan, la fuente cambio de formato o trae basura."""
    errores = []
    if len(filas) < 20:
        errores.append(f"solo {len(filas)} filas")
    rango = {"ARS": (100_000, 5_000_000), "USD": (30, 5_000)}
    fuera = [f for f in filas if not rango[f.get("moneda", "ARS")][0] <= f["precio"] <= rango[f.get("moneda", "ARS")][1]]
    if fuera:
        f = fuera[0]
        errores.append(f"{len(fuera)} precios fuera de rango (ej.: {f['modelo_fuente']} {f['km']} km {f.get('moneda', 'ARS')} {f['precio']:,})")
    if len({(f["modelo_fuente"], f["km"]) for f in filas}) != len(filas):
        errores.append("modelo y km repetidos")
    if errores:
        raise RuntimeError(f"service {marca}: " + "; ".join(errores))


def procesar(marca, estado, consultado, hoy):
    """Consulta, valida y guarda una marca; actualiza el estado (huella y fecha)."""
    espera = DIAS_ENTRE_CONSULTAS.get(marca, DIAS_MINIMO)
    if espera and marca in consultado and (hoy - date.fromisoformat(consultado[marca])).days < espera:
        print(f"service {marca}: consultado el {consultado[marca]}, se vuelve a consultar cada {espera} dias")
        return
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
        return
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marcas", default=",".join(RECOLECTORES))
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    hoy = date.today()
    consultado = estado.setdefault("consultado", {})
    fallas = {}
    for marca in args.marcas.split(","):
        # Cada marca es una fuente distinta: si una falla (sitio caido, formato
        # nuevo), las demas se procesan igual y la falla se informa al final.
        try:
            procesar(marca, estado, consultado, hoy)
        except Exception as e:
            fallas[marca] = f"{type(e).__name__}: {e}"
            print(f"service {marca}: FALLA {fallas[marca]}")
            if os.environ.get("GITHUB_ACTIONS"):
                # Anotacion: se ve en el resumen de la corrida sin abrir el log.
                print(f"::error title=service {marca}::{fallas[marca][:500]}")
    if fallas:
        raise SystemExit(f"service: fallaron {len(fallas)} marcas: {', '.join(fallas)}")


if __name__ == "__main__":
    main()
