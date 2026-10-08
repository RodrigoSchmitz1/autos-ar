"""
Ingesta del equipamiento por version de los 0 km (fichas tecnicas oficiales).

Las marcas publican la ficha de cada modelo como un PDF con una tabla: una
columna por version y una fila por item ("Climatizador automatico: - - X X").
De ahi sale "que suma cada version" y la comparacion de equipamiento entre
modelos. Los datos de equipamiento son hechos, no tienen derechos; las fotos
y videos de las marcas si, y no se copian.

La lista de fichas esta en ingesta/fichas_equipamiento.csv, elegida a mano
como las fotos: solo sitios oficiales cuyo robots.txt lo permite (se verifica
en cada corrida, con comodines: ver permitido_por_robots en ingesta/comun.py).
Toyota y Fiat rechazan las consultas (403) y Citroen lo prohibe: no estan.
Fuera por ahora: Amarok (la tabla sale desalineada, marcas sueltas en 27
columnas), Partner (una sola version: no hay "que suma cada version") y Jeep
(las tildes son dibujos, no texto).

Cinco formatos:
  matriz  tabla con las versiones como columnas (VW, Chevrolet, Ford). Cada
          marca marca distinto y lo explica en una leyenda del PDF ("X" =
          disponible); si la leyenda cambia, falla en vez de leer mal.
  lineas  el nombre del item queda fuera de la tabla al extraerla (Peugeot):
          se lee el texto renglon por renglon ("Control de estabilidad SI SI").
  unica     una sola version (nombre en la columna versiones): los renglones
          con marca o, si la ficha no marca, todo lo que lista.
  dibujo    la marca es un dibujo (Nissan, Jeep): columnas por la posicion de
          los nombres de version (columna versiones) y un dibujo chico en el
          renglon = lo tiene.
  catalogo  catalogo de la marca (Renault), sin encabezado de tabla: las
          versiones se anotan en la lista (columna versiones, separadas por |)
          y, si la tabla viene en dos columnas por pagina, columnas = 2.

Una fila que no cierra (marcas sueltas que no coinciden con las versiones) se
descarta y se cuenta, en vez de adivinar a que version va. Si solo le falta
alguna celda ("- - X [vacio]"), se guardan las marcas conocidas y la vacia
queda sin dato.

Salida: datos/raw/equipamiento/<AAAAMMDD>.parquet, con una fila por marca,
familia, version e item; se escribe solo si el contenido cambio (huella, como
en ingesta/repuestos.py). Como maximo una consulta cada 7 dias, salvo que
cambie la lista de fichas.

Uso: python -m ingesta.equipamiento [--forzar] [--familia TERA]
"""

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import re
import unicodedata
from datetime import date

import duckdb
import pandas as pd
import pdfplumber

from ingesta.comun import pedir, permitido_por_robots

LISTA = os.path.join("ingesta", "fichas_equipamiento.csv")
# Fichas de marcas que no dejan consultar su sitio (Toyota, Fiat, Citroen, Nissan...):
# el PDF lo baja una persona a MANUALES (no se sube al repo) y en la lista va como
# "local:<archivo>.pdf". Al leerlo se guardan los datos en EXTRAIDAS (si se suben),
# y el pipeline usa esos datos.
MANUALES = "fichas_manuales"
EXTRAIDAS = os.path.join("ingesta", "equipamiento_manual")
RAIZ = os.path.join("datos", "raw", "equipamiento")
ESTADO = os.path.join(RAIZ, "_estado.json")
DIAS_ENTRE_CONSULTAS = 7
MIN_ITEMS = 20  # menos que esto en una ficha: casi seguro cambio el formato

# Que significa cada marca, por marca de auto, y la leyenda del PDF que lo dice.
MARCAS = {
    "VOLKSWAGEN": ({"x": "si", "-": "no", "o": "opcional"}, r'"X" = disponible'),
    "CHEVROLET": ({"s": "si", "x": "si", "-": "no", "o": "opcional"}, None),  # sin leyenda: S (o X, en la S10) = de serie
    "FORD": ({"■": "si", "n": "si", "-": "no", "o": "opcional"}, r"(?i)(de serie|disponible de serie)"),
    "PEUGEOT": ({"si": "si", "no": "no", "-": "no", "opc": "opcional", "opcional": "opcional"}, None),
    # Catalogos de Renault: "X" o vinietas ("••") = de serie, "-" = no tiene.
    "RENAULT": ({"x": "si", "-": "no", "•": "si", "••": "si"}, None),
    "HYUNDAI": ({"•": "si", "-": "no"}, None),
    "KIA": ({"s": "si", "-": "no", "o": "opcional"}, None),
    "HAVAL": ({"●": "si", "•": "si", "-": "no", "—": "no"}, None),
    "BYD": ({"●": "si", "—": "no", "-": "no", "○": "opcional"}, None),
    "HONDA": ({"si": "si", "no": "no", "-": "no"}, None),
    # Marcas dibujadas (formato dibujo): no hay texto que traducir.
    "RAM": ({}, None),
    "NISSAN": ({}, None),
    "JEEP": ({}, None),
}


def limpio(t):
    return re.sub(r"\s+", " ", (t or "").replace("\n", " ")).strip()


def es_marca(valor, marcas):
    return limpio(valor).lower() in marcas


def es_encabezado(celdas, marcas):
    """Nombres de version: al menos 2, con letras, ninguno es una marca."""
    llenas = [c for c in celdas if limpio(c)]
    return len(llenas) >= 2 and len(llenas) == len(celdas) and all(
        re.search("[A-Za-z]", c) and not es_marca(c, marcas) for c in llenas)


def primera_tanda(nombres):
    """Dos tablas lado a lado: "v1 v2 v3 CONFORT v1 v2 v3" -> [v1, v2, v3]."""
    for k in range(2, len(nombres) // 2 + 1):
        if nombres[k + 1:k + 1 + k] == nombres[:k]:
            return nombres[:k]
    return nombres


def sin_repetir(nombres):
    """"XL", "XL" -> "XL #1", "XL #2": despues se distinguen con un dato (ver distinguir)."""
    return [f"{n} #{nombres[:i].count(n) + 1}" if nombres.count(n) > 1 else n for i, n in enumerate(nombres)]


def distinguir(df):
    """Versiones con el mismo nombre (Ranger: XL 4x2 y XL 4x4): se les agrega el primer
    dato de la ficha que las diferencia ("Traccion: 4x2 / 4x4")."""
    for base in sorted({v.rsplit(" #", 1)[0] for v in df["version_fuente"] if " #" in v}):
        grupo = sorted(v for v in df["version_fuente"].unique() if v.rsplit(" #", 1)[0] == base)
        nuevos = None
        for item in df["item"].unique():  # en el orden de la ficha
            vals = df[(df["item"] == item) & df["version_fuente"].isin(grupo)].set_index("version_fuente")["valor"]
            if len(vals) == len(grupo) and vals.notna().all() and vals.nunique() == len(grupo) \
                    and not set(vals) & {"si", "no", "opcional"}:
                # Si el dato ya trae el nombre ("WT 4X2 MT (CS)", en la S10), va solo.
                nuevos = {v: vals[v] if vals[v].startswith(base) else f"{base} {vals[v]}" for v in grupo}
                break
        df["version_fuente"] = df["version_fuente"].replace(nuevos or {v: v.replace(" #", " (") + ")" for v in grupo})
    return df


def bloques(fila, versiones):
    """Posiciones donde empieza un bloque etiqueta + versiones (dos tablas lado a lado)."""
    n = len(versiones)
    return [i for i in range(len(fila) - n) if [limpio(c) for c in fila[i + 1:i + 1 + n]] == versiones]


TILDES = {"✔", "✓", "✔️"}


def valor(celda, marcas):
    t = limpio(celda)
    return marcas.get(t.lower(), t) if t else None


def filas_matriz(pdf, marcas):
    """(seccion, item, version, valor) de las tablas con versiones como columnas; y descartadas."""
    salida, descartadas, versiones, unicos, seccion = [], 0, None, None, ""
    for pagina in pdf.pages:
        for tabla in pagina.extract_tables():
            for fila in tabla:
                fila = [c or "" for c in fila]
                # Encabezado nuevo: define las versiones (y la seccion, la primera celda).
                if versiones is None and len(fila) >= 3 and es_encabezado(fila[1:], marcas):
                    versiones = primera_tanda([limpio(c) for c in fila[1:]])
                    unicos = sin_repetir(versiones)
                if versiones is None:
                    continue
                inicios = bloques(fila, versiones)
                if inicios:  # fila de encabezado (una o mas tablas lado a lado)
                    seccion = limpio(fila[inicios[0]]) or seccion
                    continue
                n = len(versiones)
                # Tabla sin encabezado propio (o con otro ancho): se usa si tiene etiqueta + n columnas.
                anchos = [0] if len(fila) == n + 1 else (list(range(0, len(fila), n + 1)) if len(fila) % (n + 1) == 0 else [])
                if not anchos:
                    continue
                for b in anchos:
                    etiqueta, celdas = fila[b], fila[b + 1:b + 1 + n]
                    salida_bloque, ok = expandir(etiqueta, celdas, marcas)
                    if salida_bloque == "seccion":
                        seccion = limpio(etiqueta)
                    elif ok:
                        salida += [(seccion, item, v, val) for item, vals in salida_bloque for v, val in zip(unicos, vals)]
                    else:
                        descartadas += 1
    return unicos, salida, descartadas


def expandir(etiqueta, celdas, marcas):
    """Una fila (o varias pegadas con saltos de linea) -> [(item, [valor por version])]."""
    if not limpio(etiqueta):
        return [], not any(limpio(c) for c in celdas)
    if not any(limpio(c) for c in celdas):
        # Titulo de seccion ("CONFORT", "SEGURIDAD"): en mayusculas y sin valores.
        return ("seccion", True) if limpio(etiqueta).upper() == limpio(etiqueta) else ([], True)
    # Fichas con tildes ("✔" = tiene, vacio = no tiene): una fila que solo tiene tildes
    # y vacios no deja dudas. Si hay texto en la fila, el vacio sigue siendo "sin dato".
    if TILDES & set(marcas) and all(limpio(c) in TILDES or not limpio(c) for c in celdas):
        return [(limpio(etiqueta), ["si" if limpio(c) else "no" for c in celdas])], True
    lineas =[l for l in etiqueta.split("\n") if l.strip()]
    partes = [[p for p in (c or "").split("\n") if p.strip()] for c in celdas]
    # Dos items pegados en una celda: "Item A\nItem B" con "X\n-" en cada version.
    if len(lineas) > 1 and all(len(p) in (0, len(lineas)) for p in partes) and any(len(p) == len(lineas) for p in partes) \
            and all(es_marca(x, marcas) for p in partes for x in p):
        return [(limpio(l), [valor(p[i], marcas) if p else None for p in partes]) for i, l in enumerate(lineas)], True
    vals = [valor(c, marcas) for c in celdas]
    llenas = [v for v in vals if v is not None]
    if len(llenas) == len(vals):
        return [(limpio(etiqueta), vals)], True
    # Celda combinada: un solo valor en la primera columna vale para todas.
    if len(llenas) == 1 and vals[0] is not None:
        return [(limpio(etiqueta), [vals[0]] * len(vals))], True
    # Marcas con alguna celda vacia ("- - X [vacio]"): se guardan las marcas conocidas y
    # el vacio queda sin dato para esa version, en vez de perder la fila entera.
    if len(llenas) >= 2 and all(es_marca(c, marcas) for c in celdas if limpio(c)):
        return [(limpio(etiqueta), vals)], True
    # Datos de texto (motor, potencia) con celdas combinadas sobre varias versiones:
    # el vacio vale lo de su izquierda ("2.0L Turbo" para las 4 primeras). Con marcas
    # (X / -) el vacio es ambiguo y la fila se descarta.
    if vals[0] is not None and not any(es_marca(c, marcas) for c in celdas if limpio(c)):
        relleno, ultimo = [], None
        for v in vals:
            ultimo = v if v is not None else ultimo
            relleno.append(ultimo)
        return [(limpio(etiqueta), relleno)], True
    return [], False


def filas_lineas(pdf, marcas):
    """Formato Peugeot: versiones del encabezado de la tabla, items del texto."""
    versiones = None
    for pagina in pdf.pages:
        for tabla in pagina.extract_tables():
            for fila in tabla:
                if versiones is None and fila and len(fila) >= 3 and es_encabezado([c or "" for c in fila[1:]], marcas):
                    versiones = [limpio(c) for c in fila[1:]]
    if not versiones:
        return None, [], 0
    n, salida, seccion = len(versiones), [], ""
    fichas = "|".join(re.escape(m) for m in sorted(marcas, key=len, reverse=True))
    renglon = re.compile(rf"^(.*?\S)((?:\s+(?:{fichas}))+)\s*$", re.I)
    for pagina in pdf.pages:
        for linea in (pagina.extract_text() or "").splitlines():
            m = renglon.match(linea.strip())
            if m:
                vals = m.group(2).split()
                if len(vals) == n:
                    salida += [(seccion, limpio(m.group(1)), v, marcas[x.lower()]) for v, x in zip(versiones, vals)]
            elif linea.strip().isupper() and len(linea.strip()) > 3:
                seccion = linea.strip()
    return versiones, salida, 0


def filas_catalogo(pdf, marcas, versiones, columnas):
    """Catalogos (Renault): tabla de equipamiento sin encabezado de tabla y, a veces,
    dos tablas por pagina lado a lado. Las versiones vienen de la lista de fichas
    (anotadas a mano mirando el catalogo); cada renglon que termina en una marca por
    version es un item. Con dos columnas, cada mitad de la pagina se lee aparte."""
    n, salida = len(versiones), []
    fichas = "|".join(re.escape(m) for m in sorted(marcas, key=len, reverse=True))
    renglon = re.compile(rf"^(.*?\S)((?:\s+(?:{fichas}))+)\s*$", re.I)
    for pagina in pdf.pages:
        mitades = [pagina] if columnas == 1 else [
            pagina.crop((0, 0, pagina.width / 2, pagina.height)), pagina.crop((pagina.width / 2, 0, pagina.width, pagina.height))]
        for parte in mitades:
            for linea in (parte.extract_text() or "").splitlines():
                m = renglon.match(linea.strip())
                if not m or not re.search("[a-z]", m.group(1), re.I):
                    continue
                vals = m.group(2).split()
                # Una sola "X" en una tabla de varias versiones: celda combinada, la tienen todas
                # (Kangoo Express). Un "-" solo no se interpreta.
                if len(vals) == 1 and n > 1 and marcas[vals[0].lower()] == "si":
                    vals = vals * n
                if len(vals) == n:
                    item = limpio(m.group(1)).lstrip("•·- ").strip()
                    salida += [("", item, v, marcas[x.lower()]) for v, x in zip(versiones, vals)]
    return versiones, salida, 0


def filas_unica(pdf, marcas, versiones):
    """Fichas de una sola version (Trailblazer, Spark EUV, Partner): no hay columnas que
    comparar. Si la ficha marca ("Alerta de punto ciego S"), cuentan los renglones con
    marca; si solo lista lo que trae, cada renglon es un item que tiene. Los titulos en
    mayusculas son secciones."""
    fichas = "|".join(re.escape(m) for m in sorted(marcas, key=len, reverse=True))
    renglon = re.compile(rf"^(.*?\S)\s+({fichas})\s*$", re.I)
    lineas = [l.strip() for p in pdf.pages for l in (p.extract_text() or "").splitlines() if l.strip()]
    con_marca = [renglon.match(l) for l in lineas]
    marca_items = sum(1 for m in con_marca if m) >= MIN_ITEMS
    salida, seccion = [], ""
    for l, m in zip(lineas, con_marca):
        if l.isupper() and len(l) > 3:
            seccion = l
        elif marca_items and m:
            salida.append((seccion, limpio(m.group(1)), versiones[0], marcas[m.group(2).lower()]))
        elif not marca_items and re.search("[a-z]", l) and len(l) <= 120:
            salida.append((seccion, limpio(l), versiones[0], "si"))
    return versiones, salida, 0


def filas_dibujo(pdf, versiones, columnas=1):
    """Fichas donde la marca es un dibujo (Nissan, Jeep): un circulo o tilde vectorial,
    no texto. Las columnas salen del encabezado (la palabra de cada version, en la
    lista de fichas); un renglon tiene el item si hay un dibujo chico a la altura del
    renglon y cerca de la columna. Sin dibujo en una columna: no lo tiene."""
    claves = [normalizar_v(v.split()[0]) for v in versiones]
    salida, seccion, xs = [], "", None
    mitades = lambda p: [p] if columnas == 1 else [p.crop((0, 0, p.width / 2, p.height)), p.crop((p.width / 2, 0, p.width, p.height))]
    for pagina in [m for p in pdf.pages for m in mitades(p)]:
        # Tolerancia chica: en algunas fichas los nombres de version vienen pegados.
        palabras = pagina.extract_words(keep_blank_chars=False, x_tolerance=1.5)
        renglones = {}
        for w in palabras:
            renglones.setdefault(round(w["top"] / 3), []).append(w)
        # Columnas: el renglon donde aparecen las palabras de todas las versiones.
        for ws in renglones.values():
            textos = [normalizar_v(w["text"]) for w in ws]
            if all(k in textos for k in claves):
                # Cada version toma la siguiente palabra con su nombre, de izquierda a
                # derecha (dos versiones pueden empezar igual: "Laramie", "Laramie Night").
                libres = sorted(ws, key=lambda w: w["x0"])
                xs = []
                for k in claves:
                    w = next(w for w in libres if normalizar_v(w["text"]) == k)
                    libres.remove(w)
                    xs.append((w["x0"] + w["x1"]) / 2)
                break
        else:
            # Encabezado con nombres pegados ("REBELLARAMIELARAMIE", RAM): si esta la primera
            # version, las columnas son las de la otra mitad corridas lo mismo.
            if xs and columnas == 2:
                for ws in renglones.values():
                    primera = [w for w in ws if normalizar_v(w["text"]) == claves[0]]
                    if primera and not (pagina.bbox[0] <= xs[0] <= pagina.bbox[2]):
                        corrimiento = (primera[0]["x0"] + primera[0]["x1"]) / 2 - xs[0]
                        xs = [x + corrimiento for x in xs]
                        break
        if not xs:
            continue
        # Con dos tablas por pagina, cada mitad tiene su encabezado: las columnas de esta mitad.
        if columnas == 2 and not (pagina.bbox[0] <= min(xs) <= pagina.bbox[2]):
            continue
        # La marca es una curva rellena (tilde o circulo); el cuadradito vacio de cada
        # celda (Jeep) es un rectangulo solo con borde y no cuenta.
        dibujos = [o for o in pagina.curves + pagina.images
                   if o["width"] <= 14 and o["height"] <= 14 and o["x0"] > min(xs) - 40 and o.get("fill", True)]
        # Solo los del tamanio de la marca (el mas comun): letras dibujadas como curvas
        # (textos legales, datos tecnicos) tienen otros tamanios.
        if dibujos:
            tam = collections.Counter((round(o["width"]), round(o["height"])) for o in dibujos).most_common(1)[0][0]
            dibujos = [o for o in dibujos if abs(o["width"] - tam[0]) <= 1.5 and abs(o["height"] - tam[1]) <= 1.5]
        borde = min(xs) - 30
        # Renglones con texto a la izquierda de las columnas (los items candidatos).
        items = []
        for clave_r in sorted(renglones):
            ws = sorted(renglones[clave_r], key=lambda w: w["x0"])
            texto = limpio(" ".join(w["text"] for w in ws if w["x1"] < borde))
            if texto and re.search("[a-z]", texto, re.I):
                centro = (min(w["top"] for w in ws) + max(w["bottom"] for w in ws)) / 2
                items.append([texto, centro, set()])
        if not items:
            continue
        # Cada dibujo va al renglon mas cercano (no a todos los que toca: los renglones
        # estan pegados) y a la columna mas cercana.
        for o in dibujos:
            cy, cx = (o["top"] + o["bottom"]) / 2, (o["x0"] + o["x1"]) / 2
            fila = min(items, key=lambda it: abs(it[1] - cy))
            col = min(range(len(xs)), key=lambda k: abs(cx - xs[k]))
            if abs(fila[1] - cy) <= 6 and abs(cx - xs[col]) < 30:
                fila[2].add(col)
        for texto, _, cols in items:
            if not cols:
                # Sin ningun dibujo: titulo de seccion, dato de texto o nota; no se usa
                # (un item que no tiene ninguna version queda "sin dato").
                if texto.isupper() or len(texto) < 25:
                    seccion = texto
                continue
            salida += [(seccion, texto, v, "si" if k in cols else "no") for k, v in enumerate(versiones)]
    return versiones, salida, 0


def normalizar_v(t):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower())


def leer_ficha(marca, familia, formato, url, versiones_lista=None, columnas=1):
    marcas, leyenda = MARCAS[marca]
    if url.startswith("local:"):
        with open(os.path.join(MANUALES, url[len("local:"):]), "rb") as f:
            contenido = f.read()
    else:
        contenido = pedir(url)
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
        # En las de una sola version (revisadas a mano al agregarlas) la leyenda puede faltar.
        if leyenda and formato != "unica" and not re.search(leyenda, texto):
            raise ValueError("no esta la leyenda de las marcas: puede haber cambiado el formato")
        if TILDES & set(texto):
            marcas = {**marcas, **{t: "si" for t in TILDES}}
        if formato == "catalogo":
            versiones, filas, descartadas = filas_catalogo(pdf, marcas, versiones_lista, columnas)
        elif formato == "dibujo":
            versiones, filas, descartadas = filas_dibujo(pdf, versiones_lista, columnas)
        elif formato == "unica":
            versiones, filas, descartadas = filas_unica(pdf, marcas, versiones_lista)
        else:
            versiones, filas, descartadas = (filas_matriz if formato == "matriz" else filas_lineas)(pdf, marcas)
    if not versiones:
        raise ValueError("no se encontro el encabezado con las versiones")
    df = pd.DataFrame(filas, columns=["seccion", "item", "version_fuente", "valor"])
    df.insert(0, "familia", familia)
    df.insert(0, "marca", marca)
    df["orden_version"] = df["version_fuente"].map({v: i for i, v in enumerate(versiones)})
    df["fuente_url"] = url
    # Un item repetido (aparece en dos tablas): queda la primera vez.
    df = df.drop_duplicates(["item", "version_fuente"])
    df = distinguir(df)
    # Orden de los items como en la ficha (para mostrarla igual).
    df["orden_item"] = df["item"].map({it: i for i, it in enumerate(df["item"].unique())})
    items_con_marca = df[df["valor"].isin(["si", "no", "opcional"])]["item"].nunique()
    if items_con_marca < MIN_ITEMS:
        raise ValueError(f"solo {items_con_marca} items con marca por version (minimo {MIN_ITEMS})")
    return df, versiones, descartadas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true", help="consultar aunque no hayan pasado 7 dias")
    ap.add_argument("--familia", help="solo esta familia (para probar)")
    args = ap.parse_args()
    os.makedirs(RAIZ, exist_ok=True)
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    hoy = date.today()
    # Una ficha agregada o cambiada en la lista se consulta enseguida, sin esperar la semana.
    lista_hash = hashlib.sha256(open(LISTA, "rb").read()).hexdigest()
    if not args.forzar and not args.familia and "consultado" in estado and estado.get("lista") == lista_hash \
            and (hoy - date.fromisoformat(estado["consultado"])).days < DIAS_ENTRE_CONSULTAS:
        print(f"equipamiento: consultado el {estado['consultado']}, se vuelve a consultar cada {DIAS_ENTRE_CONSULTAS} dias")
        return
    with open(LISTA, encoding="utf-8") as f:
        lista = [r for r in csv.DictReader(f) if not args.familia or r["familia"] == args.familia]
    partes, fallas = [], {}
    for r in lista:
        nombre = f"{r['marca']} {r['familia']}"
        try:
            local = r["url"].startswith("local:")
            extraida = os.path.join(EXTRAIDAS, r["url"][len("local:"):].rsplit(".", 1)[0] + ".csv") if local else None
            if local and not os.path.exists(os.path.join(MANUALES, r["url"][len("local:"):])):
                # En el pipeline no estan los PDF bajados a mano: se usan los datos ya extraidos.
                if not os.path.exists(extraida):
                    raise FileNotFoundError(f"falta el PDF en {MANUALES}/ y no hay datos extraidos")
                df = pd.read_csv(extraida, keep_default_na=False, na_values=[""])
                versiones = list(dict.fromkeys(df.sort_values("orden_version")["version_fuente"]))
                descartadas = 0
            else:
                if not local and not permitido_por_robots(r["url"]):
                    raise PermissionError("robots.txt no lo permite")
                df, versiones, descartadas = leer_ficha(r["marca"], r["familia"], r["formato"], r["url"],
                                                        [v for v in (r.get("versiones") or "").split("|") if v],
                                                        int(r.get("columnas") or 1))
                if local:
                    os.makedirs(EXTRAIDAS, exist_ok=True)
                    df.to_csv(extraida, index=False)
            partes.append(df)
            con_marca = df[df["valor"].isin(["si", "no", "opcional"])]["item"].nunique()
            print(f"equipamiento {nombre}: {len(versiones)} versiones, {df['item'].nunique()} items "
                  f"({con_marca} con marca por version), {descartadas} filas descartadas")
        except Exception as e:
            fallas[nombre] = f"{type(e).__name__}: {e}"
            print(f"equipamiento {nombre}: FALLA {fallas[nombre]}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error title=equipamiento {nombre}::{fallas[nombre][:500]}")
    if args.familia:
        return
    if partes:
        df = pd.concat(partes, ignore_index=True)
        huella = hashlib.sha256(df.sort_values(["marca", "familia", "item", "version_fuente"])
                                .to_json(orient="records").encode()).hexdigest()
        if estado.get("huella") == huella:
            print(f"equipamiento: sin cambios ({len(df)} filas)")
        else:
            con = duckdb.connect()
            con.register("t", df)
            destino = os.path.join(RAIZ, hoy.strftime("%Y%m%d") + ".parquet")
            con.sql(f"COPY (SELECT *, DATE '{hoy.isoformat()}' AS capturado FROM t) TO '{destino}' (FORMAT parquet)")
            estado["huella"] = huella
            print(f"equipamiento: {len(df)} filas de {df.groupby(['marca', 'familia']).ngroups} modelos")
    # La fecha se registra aunque falle alguna ficha: las demas se leyeron bien.
    estado["consultado"] = hoy.isoformat()
    estado["lista"] = lista_hash
    json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)
    if fallas:
        raise SystemExit(f"equipamiento: fallaron {len(fallas)} fichas: {', '.join(fallas)}")


if __name__ == "__main__":
    main()
