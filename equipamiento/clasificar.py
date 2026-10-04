"""
Clasificacion de los items de las fichas de equipamiento en las
caracteristicas comunes (transform/seeds/equipamiento_caracteristicas.csv),
para comparar modelos de marcas distintas.

Cada marca nombra distinto lo mismo ("Climatizador automatico 1 zona",
"Aire acondicionado digital automatico") y un item puede ser varias cosas
("6 airbags: frontales, laterales y de cortina"). Primero reglas (palabras
clave, deterministas y revisables); lo que no clasifican, Gemini (free tier),
con las mismas caracteristicas como unica opcion posible. El resultado se
guarda como seed revisable: transform/seeds/equipamiento_clasificacion.csv.

Medicion: equipamiento/casos_clasificacion.json, 80 items al azar etiquetados
a mano antes de escribir las reglas.

Uso:
  python -m equipamiento.clasificar --medir     mide las reglas (y Gemini con --ia)
  python -m equipamiento.clasificar             escribe el seed (reglas + Gemini)
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata

CARACTERISTICAS = os.path.join("transform", "seeds", "equipamiento_caracteristicas.csv")
SALIDA = os.path.join("transform", "seeds", "equipamiento_clasificacion.csv")
CASOS = os.path.join("equipamiento", "casos_clasificacion.json")


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t.replace("”", '"').replace("''", '"')).strip()


# Datos tecnicos y medidas: no son equipamiento comparable.
TECNICO = re.compile(r"\((mm|kg|l|litros|cv|nm|km/h|cm3|lts?)\b|\bmm\)|capacidad|peso|torque|potencia|cilindr|valvulas|"
                     r"distancia entre|ancho|alto\b|largo|despeje|tanque|relacion de compresion|velocidad max")

# (caracteristica, regla que tiene que cumplir, regla que no tiene que cumplir)
REGLAS = [
    ("airbags_frontales", r"airbag.*(frontal|delanteros? (para )?conductor|conductor y (acompanante|pasajero))|^airbag para conductor", None),
    ("airbags_laterales", r"airbag.*lateral", r"tipo cortina|laterales? traseros?|^airbags laterales traseros"),
    ("airbags_cortina", r"airbag.*cortina|cortina.*airbag", None),
    ("airbag_rodilla", r"airbag.*rodilla|rodilla.*airbag", None),
    ("airbags_traseros", r"airbags? laterales? traseros?", None),
    ("control_estabilidad", r"control (electronico )?de estabilidad|\b(esc|esp)\b", r"descenso"),
    ("frenado_autonomo", r"frenado (autonomo|automatico) de emergencia|frenado autonomo|asistencia (previa|pre) a la colision|pre.?colision|\baeb\b", None),
    ("crucero_adaptativo", r"crucero adaptativo|crucero.*adaptativ|\bacc\b", None),
    ("crucero", r"control (de )?crucero|velocidad crucero|piloto automatico", r"adaptativ"),
    ("limitador_velocidad", r"limitador de velocidad", None),
    ("mantenimiento_carril", r"(mantenimiento|permanencia|centrado) (de|en el|del) carril|lane keep", None),
    ("punto_ciego", r"punto ciego|angulo muerto|\bblis\b", None),
    ("trafico_cruzado", r"trafico cruzado", None),
    ("luces_altas_automaticas", r"(luces|luz) altas? automatic|altas automatic|cambio automatico de (luces|luz) alta", None),
    ("alerta_fatiga", r"fatiga|somnolencia|cansancio", None),
    ("presion_neumaticos", r"presion de (los )?neumaticos|\btpms\b", None),
    ("arranque_pendiente", r"arranque en pendiente|\b(hsa|hla)\b|asistente de arranque", None),
    ("isofix", r"isofix", None),
    ("camara_360", r"camara.*360|360.*camara|multiview|vision 360", None),
    ("camara_trasera", r"camara.*(trasera|retroceso|vision trasera|estacionamiento)", r"360|multiview"),
    ("sensores_traseros", r"sensor(es)? de estacionamiento.*trasero|sensor(es)? (de estacionamiento )?traseros", None),
    ("sensores_delanteros", r"sensor(es)? de estacionamiento.*delanter|sensor(es)? delanteros", None),
    ("estacionamiento_asistido", r"estacionamiento (asistido|automatico|semiautomatico)|park assist", None),
    ("climatizador_automatico", r"climatizador|climatronic|aire acondicionado.*automatic", r"manual|salida de aire.*plazas traseras$"),
    ("aire_acondicionado", r"^aire acondicionado( manual| digital)?$", None),
    ("climatizador_bizona", r"bi.?zona|2 zonas|dos zonas|doble zona", None),
    ("salidas_aire_traseras", r"salidas? (de aire )?(para |en )?(las )?(plazas )?traseras|salida de aire para plazas traseras|salidas de aire traseras", None),
    ("llave_presencia", r"(apertura|acceso).*sin llave|keyless|llave (inteligente|de presencia)|acceso inteligente", None),
    ("arranque_boton", r"(arranque|encendido) (por boton|sin llave)|boton de (arranque|encendido)|push.?(button|start)", r"apertura|acceso"),
    ("sensor_lluvia", r"sensor de lluvia", None),
    ("luces_automaticas", r"sensor crepuscular|encendido automatico de (luces|faros)|(luces|faros) automatic", r"altas"),
    ("espejo_electrocromico", r"electrocromic|(espejo|retrovisor) interior.*(antiencandilamiento|anti-encandilamiento|antideslumbr).*automatic|fotocromatic", None),
    ("espejos_rebatibles", r"(rebatibles?|plegables?|rebatimiento).*electric|electric.*(rebatibles?|plegables?)", None),
    ("volante_cuero", r"volante.*cuero", None),
    ("levas", r"\blevas\b|paddle", None),
    ("asientos_cuero", r"(tapizado|asientos?).*(cuero|simil cuero|eco.?cuero|ecocuero)", r"volante|palanca|parcialmente en tela"),
    ("asiento_electrico", r"asiento.*(regulacion|ajuste|ajustes) electric|asiento.*electric", None),
    ("asientos_calefaccionados", r"calefaccion.*asiento|asientos?.*calefaccion", None),
    ("freno_mano_electrico", r"freno de (mano|estacionamiento) electric|\bepb\b", None),
    ("techo_solar", r"techo (solar|panoramico)|sunroof", None),
    ("porton_electrico", r"porton.*electric", None),
    ("carplay_android", r"carplay|car play|android auto", None),
    ("carplay_inalambrico", r"(carplay|car play|android auto|app connect).*(inalambric|sin cable|wireless)|(inalambric|sin cable|wireless).*(carplay|car play|android auto|app connect)", None),
    ("cargador_inalambrico", r"(cargador|carga|carga).*(inalambric|inductiv)|inalambric.*cargador", None),
    ("usb_traseros", r"usb.*traser|traser.*usb", None),
    ("conectividad_remota", r"mi vw connect|onstar|fordpass|ford pass|conectividad remota|remot.*app|app.*remot", None),
    ("audio_premium", r"\b(beats|bose|harman|jbl|sony|focal)\b|audio premium|sistema de audio premium", None),
    ("navegador", r"navegador|\bgps\b|navegacion", None),
    ("llantas_aleacion", r"llantas? de aleacion", None),
    ("faros_led", r"(faros|opticas|luces)( principales| delanteros| delanteras)?( vw| full)? led|faros principales.*led|(faros|opticas) delanter.*led", r"traser|antiniebla|diurn|giro|stop|interior"),
    ("luces_diurnas", r"diurna|\bdrl\b", None),
    ("faros_antiniebla", r"antiniebla", None),
    ("barras_techo", r"(barras?|rack|portaequipaje).*techo|techo.*(barras|rack)|barras longitudinales", None),
    ("techo_bitono", r"bitono|bi-tono|bi tono|techo (en |color )?(negro|contrastante)", r"rack|barra"),
    ("traccion_4x4", r"^traccion|4x4|4wd|\bawd\b|traccion integral", None),
]
REGLAS = [(c, re.compile(si), re.compile(no) if no else None) for c, si, no in REGLAS]

PULGADAS = re.compile(r'(?<![\d.,])(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:"|pulgadas|pulg)')


def pulgadas(t):
    m = PULGADAS.search(norm(t))
    return float(m.group(1).replace(",", ".")) if m else None


def por_reglas(item):
    """{caracteristica: valor del item o None}. Vacio si no es ninguna (o es un dato tecnico)."""
    t = norm(item)
    if TECNICO.search(t):
        return {}
    salida = {}
    for c, si, no in REGLAS:
        if si.search(t) and not (no and no.search(t)):
            salida[c] = None
    # Pantallas y llantas: el numero de pulgadas, del nombre si lo dice.
    if re.search(r"multimedia|pantalla|display|mylink|\bsync\b|vw play|uconnect|touch", t) and \
            not re.search(r"instrumentos|cluster|tablero|cuadro|panel", t):
        salida["pantalla_multimedia"] = pulgadas(item)
    if re.search(r"(panel|cuadro|tablero|cluster) de instrumentos|active info display|instrumentos digital|"
                 r"tablero (100% )?digital|digital cockpit", t):
        salida["tablero_digital"] = pulgadas(item)
        # Un display chico dentro de un tablero analogico no es un tablero digital.
        if salida["tablero_digital"] is not None and salida["tablero_digital"] < 5:
            del salida["tablero_digital"]
    if re.search(r"\bllantas?\b", t):
        salida["llantas"] = pulgadas(item)
    return salida


# ---------- Gemini (free tier) para lo que las reglas no clasifican ----------
CACHE = os.path.join("datos", "cache_gemini_equipamiento.json")  # datos/ no se versiona
LOTE = 40


def catalogo():
    with open(CARACTERISTICAS, encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def instrucciones(cat):
    lista = "\n".join(f"- {c}: {r['nombre']}" + (" (valor: pulgadas)" if r["tipo"] == "numero" else "") for c, r in cat.items())
    return ("Clasificas items de fichas tecnicas de autos 0 km de Argentina en una lista fija de caracteristicas.\n"
            "Para cada item numerado devolves las caracteristicas que el item ES, solo de esta lista:\n" + lista + "\n\n"
            "Reglas:\n"
            "- Si el item no es ninguna (datos tecnicos, medidas, motor, colores, molduras, cromados, parasoles, "
            "levantacristales, alarma, frenos ABS, etc.), la lista va vacia. Ante la duda, vacia.\n"
            "- Un item puede ser varias: '6 airbags (frontales, laterales y de cortina)' son airbags_frontales, "
            "airbags_laterales y airbags_cortina.\n"
            "- No deduzcas: 'climatizador' no es tambien aire_acondicionado; 'entrada remota sin llave' es el control "
            "remoto de puertas, no llave_presencia; un display de menos de 5 pulgadas en un tablero analogico no es tablero_digital.\n"
            "- valor: solo para las que dicen pulgadas, el numero que figura en el item (o null si no figura).")


def formato(cat):
    return {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "n": {"type": "INTEGER"},
        "caracteristicas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "id": {"type": "STRING", "enum": list(cat)},
            "valor": {"type": "NUMBER", "nullable": True}}, "required": ["id"]}}},
        "required": ["n", "caracteristicas"]}}


def gemini_lote(items, cat, clave, modelo):
    from ingesta.comun import pedir_json_post
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    cuerpo = {
        "systemInstruction": {"parts": [{"text": instrucciones(cat)}]},
        "contents": [{"role": "user", "parts": [{"text": "\n".join(f"{i}. {t}" for i, t in enumerate(items))}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": formato(cat)},
    }
    respuesta = pedir_json_post(url, cuerpo, {"x-goog-api-key": clave})
    salida = json.loads(respuesta["candidates"][0]["content"]["parts"][0]["text"])
    resultado = {}
    for r in salida:
        if not 0 <= r["n"] < len(items):
            continue
        d = {}
        for c in r["caracteristicas"]:
            if c["id"] not in cat:  # el formato ya lo impide; se valida igual
                continue
            v = c.get("valor")
            d[c["id"]] = float(v) if cat[c["id"]]["tipo"] == "numero" and v is not None and 3 <= v <= 30 else None
        resultado[items[r["n"]]] = d
    return resultado


def por_gemini(items):
    """{item: {caracteristica: valor}} para los items, con cache local."""
    import time
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    faltan = [t for t in dict.fromkeys(items) if t not in cache]
    if faltan:
        clave = os.environ.get("GEMINI_API_KEY") or (
            os.path.exists(".env") and re.search(r"^GEMINI_API_KEY=(.+)$", open(".env", encoding="utf-8").read(), re.M).group(1).strip())
        if not clave:
            raise SystemExit("falta GEMINI_API_KEY (variable de entorno o .env)")
        modelo = re.search(r'GEMINI_MODELO = "(.+)"', open(os.path.join("asistente", "worker", "wrangler.toml"), encoding="utf-8").read()).group(1)
        cat = catalogo()
        for i in range(0, len(faltan), LOTE):
            lote = faltan[i:i + LOTE]
            cache.update(gemini_lote(lote, cat, clave, modelo))
            for t in lote:
                cache.setdefault(t, {})  # sin respuesta para ese numero: ninguna
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  gemini: {min(i + LOTE, len(faltan))}/{len(faltan)} items", file=sys.stderr)
            time.sleep(5)
    return {t: cache[t] for t in items}


def combinado(items):
    """Reglas primero; Gemini solo para lo que las reglas dejan sin clasificar."""
    reglas = {t: por_reglas(t) for t in items}
    vacios = [t for t, d in reglas.items() if not d and not TECNICO.search(norm(t))]
    ia = por_gemini(vacios) if vacios else {}
    return {t: (reglas[t] or ia.get(t, {})) for t in items}, {t: ("reglas" if reglas[t] else "gemini") for t in items}


def medir(clasificador, casos):
    exactos, falsos, faltantes = 0, 0, 0
    detalle = []
    for c in casos:
        esperado = {k: (float(v) if v is not None else None) for k, v in c["esperado"].items()}
        obtenido = clasificador(c["item"])
        if obtenido == esperado:
            exactos += 1
            continue
        falsos += len(set(obtenido) - set(esperado))
        faltantes += len(set(esperado) - set(obtenido))
        detalle.append((c["item"], esperado, obtenido))
    return exactos, falsos, faltantes, detalle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--casos", default=CASOS, help="archivo de casos para medir")
    ap.add_argument("--ia", action="store_true", help="medir reglas + Gemini")
    args = ap.parse_args()
    casos = json.load(open(args.casos, encoding="utf-8"))["casos"]
    if args.medir:
        if args.ia:
            resultado, _ = combinado([c["item"] for c in casos])
            clasificador, nombre = resultado.get, "reglas + gemini"
        else:
            clasificador, nombre = por_reglas, "reglas"
        exactos, falsos, faltantes, detalle = medir(clasificador, casos)
        for item, e, o in detalle:
            print(f"MAL: {item[:90]}\n  esperado {e}\n  obtenido {o}")
        print(f"{nombre}: {exactos}/{len(casos)} items exactos; {falsos} caracteristicas de mas, {faltantes} faltantes")
        return
    escribir_seed()


def escribir_seed():
    """Clasifica todos los items de las fichas y escribe el seed. Las filas corregidas a
    mano (metodo = manual) se respetan: al regenerar, ese item queda como estaba."""
    import duckdb
    con = duckdb.connect(os.path.join("datos", "autos.duckdb"), read_only=True)
    items = con.sql("select distinct marca, item from stg_equipamiento__items order by 1, 2").fetchall()
    manuales = {}
    if os.path.exists(SALIDA):
        for r in csv.DictReader(open(SALIDA, encoding="utf-8")):
            if r["metodo"] == "manual":
                manuales.setdefault((r["marca"], r["item"]), []).append(r)
    resultado, metodo = combinado(sorted({t for _, t in items}))
    filas = []
    for marca, item in items:
        if (marca, item) in manuales:
            filas += [[r["marca"], r["item"], r["caracteristica"], r["valor_item"], "manual"] for r in manuales[(marca, item)]]
            continue
        clases = resultado[item]
        # Un item sin caracteristica tambien va: asi un item nuevo (sin fila) se detecta.
        for c, v in (clases.items() if clases else [("", None)]):
            filas.append([marca, item, c, "" if v is None else f"{v:g}", metodo[item] if clases else "ninguna"])
    with open(SALIDA, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["marca", "item", "caracteristica", "valor_item", "metodo"])
        w.writerows(filas)
    con_clase = sum(1 for f in filas if f[2])
    print(f"{len(items)} items -> {con_clase} clasificaciones "
          f"({sum(1 for f in filas if f[4] == 'reglas')} por reglas, {sum(1 for f in filas if f[4] == 'gemini')} por Gemini, "
          f"{sum(1 for f in filas if f[4] == 'manual')} a mano) en {SALIDA}")


if __name__ == "__main__":
    main()
