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

Dos formatos:
  matriz  tabla con las versiones como columnas (VW, Chevrolet, Ford). Cada
          marca marca distinto y lo explica en una leyenda del PDF ("X" =
          disponible); si la leyenda cambia, falla en vez de leer mal.
  lineas  el nombre del item queda fuera de la tabla al extraerla (Peugeot):
          se lee el texto renglon por renglon ("Control de estabilidad SI SI").

Una fila que no cierra (marcas sueltas que no coinciden con las versiones) se
descarta y se cuenta, en vez de adivinar a que version va.

Salida: datos/raw/equipamiento/<AAAAMMDD>.parquet, con una fila por marca,
familia, version e item; se escribe solo si el contenido cambio (huella, como
en ingesta/repuestos.py). Como maximo una consulta cada 7 dias.

Uso: python -m ingesta.equipamiento [--forzar] [--familia TERA]
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
from datetime import date

import duckdb
import pandas as pd
import pdfplumber

from ingesta.comun import pedir, permitido_por_robots

LISTA = os.path.join("ingesta", "fichas_equipamiento.csv")
RAIZ = os.path.join("datos", "raw", "equipamiento")
ESTADO = os.path.join(RAIZ, "_estado.json")
DIAS_ENTRE_CONSULTAS = 7
MIN_ITEMS = 25  # menos que esto en una ficha: casi seguro cambio el formato

# Que significa cada marca, por marca de auto, y la leyenda del PDF que lo dice.
MARCAS = {
    "VOLKSWAGEN": ({"x": "si", "-": "no", "o": "opcional"}, r'"X" = disponible'),
    "CHEVROLET": ({"s": "si", "-": "no", "o": "opcional"}, None),  # sin leyenda: S = de serie
    "FORD": ({"■": "si", "n": "si", "-": "no", "o": "opcional"}, r"(?i)(de serie|disponible de serie)"),
    "PEUGEOT": ({"si": "si", "no": "no", "-": "no", "opc": "opcional", "opcional": "opcional"}, None),
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
                nuevos = {v: f"{base} {vals[v]}" for v in grupo}
                break
        df["version_fuente"] = df["version_fuente"].replace(nuevos or {v: v.replace(" #", " (") + ")" for v in grupo})
    return df


def bloques(fila, versiones):
    """Posiciones donde empieza un bloque etiqueta + versiones (dos tablas lado a lado)."""
    n = len(versiones)
    return [i for i in range(len(fila) - n) if [limpio(c) for c in fila[i + 1:i + 1 + n]] == versiones]


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
    lineas = [l for l in etiqueta.split("\n") if l.strip()]
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


def leer_ficha(marca, familia, formato, url):
    marcas, leyenda = MARCAS[marca]
    contenido = pedir(url)
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
        if leyenda and not re.search(leyenda, texto):
            raise ValueError("no esta la leyenda de las marcas: puede haber cambiado el formato")
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
    if not args.forzar and not args.familia and "consultado" in estado \
            and (hoy - date.fromisoformat(estado["consultado"])).days < DIAS_ENTRE_CONSULTAS:
        print(f"equipamiento: consultado el {estado['consultado']}, se vuelve a consultar cada {DIAS_ENTRE_CONSULTAS} dias")
        return
    with open(LISTA, encoding="utf-8") as f:
        lista = [r for r in csv.DictReader(f) if not args.familia or r["familia"] == args.familia]
    partes, fallas = [], {}
    for r in lista:
        nombre = f"{r['marca']} {r['familia']}"
        try:
            if not permitido_por_robots(r["url"]):
                raise PermissionError("robots.txt no lo permite")
            df, versiones, descartadas = leer_ficha(r["marca"], r["familia"], r["formato"], r["url"])
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
    json.dump(estado, open(ESTADO, "w", encoding="utf-8"), indent=2, sort_keys=True)
    if fallas:
        raise SystemExit(f"equipamiento: fallaron {len(fallas)} fichas: {', '.join(fallas)}")


if __name__ == "__main__":
    main()
