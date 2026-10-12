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
    # Toyota: "O" (o un cero, segun la ficha) = de serie, "X" = no tiene.
    # El "-" es "no corresponde" en datos tecnicos (bateria en una version naftera): no es marca.
    "TOYOTA": ({"o": "si", "0": "si", "x": "no"}, None),
    # Fiat: "S" de serie, "O" opcional, "-" no disponible (a veces el guion es un icono: U+F6BA).
    "FIAT": ({"s": "si", "o": "opcional", "-": "no", "\uf6ba": "no"}, r"(?i)S ?: ?DE SERIE"),
    "CITROEN": ({"si": "si", "-": "no", "no": "no", "opcional": "opcional"}, None),
    "MG": ({"-": "no"}, None),  # tildes (se agregan solas) = de serie
    "JAC": ({"●": "si", "-": "no"}, None),
    "CHANGAN": ({"■": "si", "-": "no"}, None),
    # Chery: vinieta (en algunas fichas una "l" de la fuente Wingdings) = de serie.
    "CHERY": ({"•": "si", "l": "si", "-": "no"}, None),
    "JETOUR": ({"●": "si", "◉": "si", "-": "no"}, None),
    "BMW": ({"x": "si", "-": "no"}, None),
    "MERCEDES BENZ": ({"•": "si", "x": "si", "×": "si", "-": "no"}, None),
    # Marcas dibujadas (formato dibujo): no hay texto que traducir.
    "RAM": ({}, None),
    "NISSAN": ({"•": "si", "••": "si", "-": "no"}, None),
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
                    # Salvo que antes de la marca haya un valor de otra version ("plegado
                    # electrico Manual ✓": Manual en una, la marca en la otra).
                    palabras_item = m.group(1).split()
                    if len(palabras_item) > 1 and re.fullmatch(r"[A-ZÁ-Ú][a-zá-ú]+", palabras_item[-1])                             and palabras_item[-2][:1].islower():
                        continue
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


def filas_dibujo(pdf, versiones, columnas=1, marcas=None):
    """Fichas donde la marca es un dibujo (Nissan, Jeep): un circulo o tilde vectorial,
    no texto. Las columnas salen del encabezado (la palabra de cada version, en la
    lista de fichas); un renglon tiene el item si hay un dibujo chico a la altura del
    renglon y cerca de la columna. Sin dibujo en una columna: no lo tiene.
    Con marcas de texto (Fiat: la marca y el item no quedan en la misma tabla) se
    hace lo mismo con las palabras que son marcas ("S", "O", "-"); sin marca en una
    columna queda sin dato."""
    # "1.3 MT CS=FREEDOM 1.3 CS": a la izquierda lo que dice el encabezado de la ficha
    # (para ubicar la columna), a la derecha el nombre de la version.
    encabezados = [v.split("=")[0] for v in versiones]
    versiones = [v.split("=")[-1] for v in versiones]
    claves = [normalizar_v(v.split()[0]) for v in encabezados]
    salida, seccion, xs = [], "", None
    mitades = lambda p: [p] if columnas == 1 else [p.crop((0, 0, p.width / 2, p.height)), p.crop((p.width / 2, 0, p.width, p.height))]
    for pagina in [m for p in pdf.pages for m in mitades(p)]:
        # Tolerancia chica: en algunas fichas dibujadas los nombres de version vienen
        # pegados (RAM). Las de marcas de texto (Fiat) tienen letras espaciadas.
        palabras = pagina.extract_words(keep_blank_chars=False, x_tolerance=3 if marcas else 1.5)
        renglones = {}
        for w in palabras:
            renglones.setdefault(round(w["top"] / 3), []).append(w)
        # Columnas: el renglon donde aparecen las palabras de todas las versiones (con el
        # de abajo: a veces unos nombres estan un par de puntos mas abajo, Titano).
        for ws in [renglones[k] + renglones.get(k + 1, []) for k in sorted(renglones)]:
            textos = collections.Counter(normalizar_v(w["text"]) for w in ws)
            # Cada palabra tantas veces como versiones empiezan con ella ("C3" x4; el
            # titulo "CITROEN C3" tiene una sola).
            if all(textos[k] >= n for k, n in collections.Counter(claves).items()):
                # Cada version toma la siguiente palabra con su nombre, de izquierda a
                # derecha (dos versiones pueden empezar igual: "Laramie", "Laramie Night").
                libres = sorted(ws, key=lambda w: w["x0"])
                xs = []
                for k, v in zip(claves, encabezados):
                    w = next(w for w in libres if normalizar_v(w["text"]) == k)
                    fin = w
                    # La marca va centrada bajo el nombre entero ("FREEDOM PLUS AT8 AWD",
                    # "EXCLUSIVE CVT 3R AWD"): se siguen las palabras del nombre.
                    resto = [normalizar_v(t) for t in v.split()[1:]]
                    siguientes = [x for x in libres if x["x0"] > w["x0"]]
                    for t, x in zip(resto, siguientes):
                        if normalizar_v(x["text"]) != t or x["x0"] - fin["x1"] > 15:
                            break
                        fin = x
                        libres.remove(x)
                    libres.remove(w)
                    xs.append((w["x0"] + fin["x1"]) / 2)
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
        if marcas:
            dibujos = [dict(w, valor=marcas[w["text"].lower()]) for w in palabras
                       if w["text"].lower() in marcas and w["x0"] > min(xs) - 40]
        else:
            dibujos = [dict(o, valor="si") for o in pagina.curves + pagina.images
                       if o["width"] <= 14 and o["height"] <= 14 and o["x0"] > min(xs) - 40 and o.get("fill", True)]
        # Solo los del tamanio de la marca (el mas comun): letras dibujadas como curvas
        # (textos legales, datos tecnicos) tienen otros tamanios.
        if dibujos and not marcas:
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
                # Item en dos renglones ("Sistema de monitoreo de presion / de neumaticos"):
                # el segundo empieza en minuscula y va pegado; la marca queda en el medio.
                if items and texto[0].islower() and centro - items[-1][1] < 18:
                    items[-1] = [items[-1][0] + " " + texto, (items[-1][1] + centro) / 2, {}]
                else:
                    items.append([texto, centro, {}])
        if not items:
            continue
        # Cada dibujo va al renglon mas cercano (no a todos los que toca: los renglones
        # estan pegados) y a la columna mas cercana.
        for o in dibujos:
            cy, cx = (o["top"] + o["bottom"]) / 2, (o["x0"] + o["x1"]) / 2
            fila = min(items, key=lambda it: abs(it[1] - cy))
            col = min(range(len(xs)), key=lambda k: abs(cx - xs[k]))
            if abs(fila[1] - cy) <= 6 and abs(cx - xs[col]) < 30:
                fila[2][col] = o["valor"]
        for texto, _, cols in items:
            if not cols:
                # Sin ningun dibujo: titulo de seccion, dato de texto o nota; no se usa
                # (un item que no tiene ninguna version queda "sin dato").
                if texto.isupper() or len(texto) < 25:
                    seccion = texto
                continue
            # Con marcas de texto, un renglon con marca en pocas columnas es otra cosa
            # (tabla de colores: "249 - BLANCO").
            if marcas and len(cols) < len(versiones) / 2:
                continue
            salida += [(seccion, texto, v, cols.get(k, None if marcas else "no")) for k, v in enumerate(versiones)
                       if k in cols or not marcas]
    return versiones, salida, 0


def filas_grilla(pdf, marcas):
    """Tablas con bordes y celdas combinadas (Toyota y otras): una marca que abarca
    varias columnas vale para todas esas versiones. Se usa la grilla del PDF: cada
    version es una columna de la tabla y cada celda cubre las columnas que ocupa.
    El nombre de la version junta los renglones del encabezado ("CABINA DOBLE DX",
    "4X2", "6AT"). Una tabla sin encabezado (sigue la de arriba) usa el ultimo."""
    salida, seccion, versiones, encabezados = [], "", [], []
    for pagina in pdf.pages:
        for tabla in pagina.find_tables():
            # Texto de la celda: las letras con el centro adentro (crop corta renglones que
            # rozan el borde; within_bbox mezcla titulos superpuestos).
            texto = lambda c: limpio(pagina.filter(
                lambda o: o.get("object_type") != "char" or (c[0] <= (o["x0"] + o["x1"]) / 2 <= c[2] and c[1] <= (o["top"] + o["bottom"]) / 2 <= c[3])
            ).crop(c, strict=False).extract_text()) if c else ""
            # Columnas de la grilla: entre cada par de bordes verticales de las celdas.
            bordes = sorted({round(x) for c in tabla.cells for x in (c[0], c[2])})
            bordes = [b for i, b in enumerate(bordes) if i == 0 or b - bordes[i - 1] > 3]
            centros = [(a + b) / 2 for a, b in zip(bordes, bordes[1:])]
            filas = [[(c, texto(c)) for c in r.cells if c] for r in tabla.rows]
            cubre = lambda celda, x: celda[0] - 1 <= x <= celda[2] + 1
            # Titulo de seccion: letra clara (sobre fondo oscuro).
            def clara(c):
                letras = [o for o in pagina.chars if c[0] <= (o["x0"] + o["x1"]) / 2 <= c[2] and c[1] <= (o["top"] + o["bottom"]) / 2 <= c[3]
                          and o["text"].strip()]
                def blanca(o):
                    k = o.get("non_stroking_color")
                    k = k if isinstance(k, (tuple, list)) else (k,) if k is not None else (0,)
                    return max(k) < 0.2 if len(k) == 4 else min(k) > 0.8  # CMYK: blanco es (0, 0, 0, 0)
                return bool(letras) and all(blanca(o) for o in letras)
            # Encabezado: los renglones de arriba sin nada en la columna de los items
            # (Hilux) o un primer renglon con un nombre (no una marca) en cada columna,
            # sin celdas combinadas (Corolla: "Corolla Cross | 2.0 XLI CVT | 2.0 XEI CVT").
            n_enc = 0
            for fila in filas:
                if any(t for c, t in fila if cubre(c, centros[0])) or not any(t for _, t in fila):
                    break
                n_enc += 1
            primera = [(c, t) for c, t in filas[0] if not cubre(c, centros[0])] if filas else []
            if not n_enc and len(primera) >= 2 and all(t and not es_marca(t, marcas) and re.search("[A-Za-z]", t) for _, t in primera) \
                    and all(sum(cubre(c, x) for x in centros) == 1 for c, _ in primera):
                n_enc = 1
            claves = {normalizar_v(v): v for v in versiones}
            if n_enc:
                cols = [x for x in centros[1:] if any(t for c, t in filas[0] if cubre(c, x) and not cubre(c, centros[0]))]
                nombres = [limpio(" ".join(t for fila in filas[:n_enc] for c, t in fila if cubre(c, x) and not cubre(c, centros[0])))
                           for x in cols]
            elif len(centros) == 1 and filas and len(filas[0]) == 1 and clara(filas[0][0][0]) and re.search("[0-9]", filas[0][0][1]) \
                    and (not versiones or normalizar_v(filas[0][0][1]) in claves):
                # Tabla de una columna con el nombre de la version arriba (SW4: una version por ficha).
                n_enc, cols, nombres = 1, [centros[0]], [filas[0][0][1]]
            if n_enc:
                # El mismo nombre escrito con otros caracteres es la misma version.
                nombres = [claves.get(normalizar_v(n), n) for n in nombres]
                encabezados.append((pagina.page_number, list(zip(cols, nombres))))
                versiones += [n for n in dict.fromkeys(nombres) if n not in versiones]
            # Tabla sin encabezado: el ultimo de la misma pagina y a la misma altura horizontal
            # (con dos paginas por hoja, cada mitad tiene el suyo).
            x0, x1 = tabla.bbox[0], tabla.bbox[2]
            candidatos = [e for p, e in encabezados if any(x0 <= x <= x1 for x, _ in e)]
            mismos = [e for p, e in encabezados if p == pagina.page_number and any(x0 <= x <= x1 for x, _ in e)]
            encabezado = (mismos or candidatos or [None])[-1]
            if not encabezado:
                continue
            for fila in filas[n_enc:]:
                etiqueta = " ".join(t for c, t in fila if cubre(c, centros[0]) and t)
                if not etiqueta:
                    continue
                vals = {}
                for c, t in fila:
                    if t and not cubre(c, centros[0]):
                        for x, nombre in encabezado:
                            if cubre(c, x):
                                vals[nombre] = valor(t, marcas)
                if not vals:
                    celda = next(c for c, t in fila if t and cubre(c, centros[0]))
                    if clara(celda) or (etiqueta.isupper() and len(etiqueta) > 3):
                        seccion = etiqueta
                    elif len(encabezado) == 1 and cubre(celda, encabezado[0][0]):
                        # Ficha de una sola version (SW4): lista lo que trae, sin marcas.
                        salida.append((seccion, etiqueta, encabezado[0][1], "si"))
                    continue
                salida += [(seccion, etiqueta, n, v) for n, v in vals.items()]
    # Tablas sueltas con otro encabezado (notas, "Imagen correspondiente a..."): quedan
    # las versiones con marcas en buena parte de los items.
    marcadas = collections.Counter(n for _, _, n, v in salida if v in ("si", "no", "opcional"))
    versiones = [n for n in versiones if marcadas[n] >= 0.4 * max(marcadas.values(), default=0)]
    salida = [f for f in salida if f[2] in versiones]
    return versiones, salida, 0


def filas_configurador(pdf, versiones):
    """Impresion del configurador del sitio (Renault): una version por archivo y las
    paginas "Equipamiento incluido" / "Look Interior" con lo que trae, en dos columnas.
    Los titulos de seccion ("Confort") van solos en el renglon y con mayuscula; los
    items, en minuscula."""
    salida, seccion = [], ""
    for pagina in pdf.pages:
        texto = pagina.extract_text() or ""
        if "Equipamiento incluido" not in texto and "Look Interior" not in texto:
            continue
        palabras = pagina.extract_words(extra_attrs=["size"])
        titulo = max((w["bottom"] for w in palabras if w["size"] > 12), default=0)
        pie = min((w["top"] for w in palabras if w["text"] == "Encontrá"), default=pagina.height)
        renglones = {}
        for w in palabras:
            if titulo < w["top"] < pie and w["size"] < 12:
                renglones.setdefault(round(w["top"] / 3), []).append(w)
        for clave in sorted(renglones):
            mitad = pagina.width / 2
            izq = limpio(" ".join(w["text"] for w in sorted(renglones[clave], key=lambda w: w["x0"]) if w["x0"] < mitad))
            der = limpio(" ".join(w["text"] for w in sorted(renglones[clave], key=lambda w: w["x0"]) if w["x0"] >= mitad))
            if izq and not der and izq[0].isupper() and re.search("[a-z]", izq) and len(izq) < 30:
                seccion = izq
                continue
            salida += [(seccion, t, versiones[0], "si") for t in (izq, der) if t]
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
        if leyenda and formato not in ("unica", "configurador") and not re.search(leyenda, texto):
            raise ValueError("no esta la leyenda de las marcas: puede haber cambiado el formato")
        if TILDES & set(texto):
            marcas = {**marcas, **{t: "si" for t in TILDES}}
        if formato == "catalogo":
            versiones, filas, descartadas = filas_catalogo(pdf, marcas, versiones_lista, columnas)
        elif formato == "dibujo":
            versiones, filas, descartadas = filas_dibujo(pdf, versiones_lista, columnas)
        elif formato == "posiciones":
            versiones, filas, descartadas = filas_dibujo(pdf, versiones_lista, columnas, marcas)
        elif formato == "configurador":
            versiones, filas, descartadas = filas_configurador(pdf, versiones_lista)
        elif formato == "grilla":
            versiones, filas, descartadas = filas_grilla(pdf, marcas)
            # Nombres como los dice DNRPA ("CABINA DOBLE DX" -> "DC DX"), en el orden de la
            # ficha. Si la ficha cambio la cantidad de versiones, mejor fallar que cruzar mal.
            if versiones_lista:
                if len(versiones_lista) != len(versiones):
                    raise ValueError(f"la ficha tiene {len(versiones)} versiones y la lista {len(versiones_lista)}: {versiones}")
                nuevo = dict(zip(versiones, versiones_lista))
                versiones, filas = versiones_lista, [(s, i, nuevo[v], x) for s, i, v, x in filas]
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
            archivo = r["url"][len("local:"):]
            # Sin la extension .pdf (algunos PDF bajados no la tienen y llevan puntos en el nombre).
            extraida = os.path.join(EXTRAIDAS, re.sub(r"(?i)\.pdf$", "", archivo) + ".csv") if local else None
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
