"""
Exporta los marts a archivos JSON estaticos para el sitio (sitio/datos/).

El sitio no tiene servidor: GitHub Pages sirve HTML, JavaScript y estos JSON,
que el pipeline regenera cada dia despues de dbt. La "API" son los archivos.

  meta.json        fecha de generacion y periodo de cada fuente
  home.json        rankings de la portada: 0 km mas vendidos, usados que mejor
                   conservan el valor, usados mas baratos de mantener, y nafta
                   y gasoil por provincia
  costo.json       componentes del costo de cada version 0 km (comparador)
  fichas.json      por familia: depreciacion, service, repuestos, mercado
  oficiales.json   pagina oficial de cada modelo (enlace al 360 y configurador)
  repuestos.json   precio de cada pieza por familia, gasto por km, comparables
  repuestos/<slug>.json  productos de cada pieza de una familia (tienda, enlace)
  miauto/          una por familia para la pantalla "Mi auto"
  equipamiento.json  por familia con ficha oficial: versiones en orden (con
                   precio 0 km), tabla de equipamiento y que suma cada version

Cada familia lleva su carroceria (hatch, sedan, suv, pickup, utilitario), el
tipo mas frecuente en DNRPA. Las fotos de los modelos van aparte: exportar/fotos.py.

Formato compacto (listas en vez de objetos repetidos) para que el sitio
cargue rapido en el celular; las claves de cada lista estan en "columnas".

Uso: python -m exportar.sitio
"""

import json
import math
import os
from datetime import date

import duckdb

BASE = os.path.join("datos", "autos.duckdb")
DESTINO = os.path.join("sitio", "datos")


def limpio(v):
    """JSON no admite NaN; los decimales se recortan para achicar el archivo."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, date):
        return v.isoformat()
    return v


def filas(con, sql):
    cur = con.execute(sql)
    columnas = [d[0] for d in cur.description]
    return columnas, [[limpio(v) for v in f] for f in cur.fetchall()]


def escribir(nombre, contenido):
    ruta = os.path.join(DESTINO, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(contenido, f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(ruta)


# Carroceria de DNRPA -> tipo de carroceria del sitio.
CARROCERIA = """
    case when tipo like 'PICK-UP%' then 'pickup'
         when tipo like 'FURGON%' then 'utilitario'
         when tipo like 'RURAL%' or tipo = 'TODO TERRENO' then 'suv'
         when tipo like 'SEDAN 4%' then 'sedan'
         else 'hatch' end"""

# Ventana de 12 meses y familias con mercado de usados suficiente para rankear.
ULTIMOS_12 = "periodo > (select max(periodo) from mart_mercado_mensual) - interval 12 month"
MIN_TRANSFERENCIAS = 5000


def carrocerias(con):
    """{(MARCA, familia): carroceria}, el tipo con mas tramites de la familia."""
    return {(m, f): c for m, f, c in con.sql(f"""
        select upper(cca_marca), cca_modelo, arg_max({CARROCERIA}, tramites)
        from dim_version where segmento = 'liviano' and cca_modelo is not null group by all""").fetchall()}


MIN_TRAMITES_MI_AUTO = 50   # familias con menos tramites en el anio no entran en "Mi auto"
VERSIONES_POR_FAMILIA = 40  # las mas tramitadas; el resto usa la mas parecida


def slug(marca, familia):
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", f"{marca} {familia}").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def exportar_repuestos(con):
    """Pagina de repuestos: precio de cada pieza por modelo (original y alternativo),
    el gasto en repuestos de desgaste por km de cada modelo y la comparacion de la
    misma pieza original contra alternativa (mismo codigo, distinta calidad)."""
    piezas = [{"tipo": t, "modelos": int(n), "alternativo": limpio(a), "original": limpio(o)} for t, n, a, o in con.sql("""
        select tipo_pieza, count(distinct cca_marca || familia), median(precio_mediano_alternativo), median(precio_mediano_original)
        from mart_repuestos group by 1 order by 2 desc""").fetchall()]
    intervalos = {t: {"unidades": u, "km": km, "solo_manual": sm} for t, u, km, sm in con.sql(
        "select tipo_pieza, unidades, intervalo_km, solo_manual from costo_repuestos_intervalos").fetchall()}
    familias = {}
    for marca, familia, tipo, orig, alt, n in con.sql("""
            select upper(cca_marca), familia, tipo_pieza, precio_mediano_original, precio_mediano_alternativo, productos
            from mart_repuestos order by 1, 2, 3""").fetchall():
        f = familias.setdefault((marca, familia), {"marca": marca, "familia": familia, "slug": slug(marca, familia), "piezas": {}})
        f["piezas"][tipo] = [limpio(orig), limpio(alt), int(n)]
    # Gasto por km en repuestos de desgaste (caja manual: con embrague) y cuantas piezas
    # tienen precio propio; y cuantos tramites tiene la familia (para no rankear rarezas).
    for marca, familia, alt, orig, propias, total, tramites in con.sql("""
            select m.marca, m.familia, m.repuestos_con_embrague, m.repuestos_original_con_embrague,
                   m.piezas_propias_con_embrague, m.piezas_con_embrague,
                   (select sum(tramites_12m) from mart_mantenimiento_version v
                     where upper(v.cca_marca) = m.marca and v.cca_modelo = m.familia)
            from int_mantenimiento_familia m where m.repuestos_con_embrague is not null""").fetchall():
        f = familias.get((marca, familia))
        if f:
            f.update({"por_km": limpio(alt), "por_km_original": limpio(orig), "propias": int(propias), "de": int(total),
                      "tramites": int(tramites or 0)})
    exportar_ofertas(con, {f["slug"]: f for f in familias.values()})
    comparables = con.sql("""
        select median(veces_mas_caro_original), count(*) from mart_repuestos_comparables where not revisar""").fetchone()
    ejemplos = [{"titulo": t, "tipo": tp, "original": limpio(o), "alternativo": limpio(a), "calidad": c, "veces": limpio(v)}
                for t, tp, o, a, c, v in con.sql("""
        select titulo_original, tipo_pieza, precio_original, precio_alternativo_min, calidad_alternativa, veces_mas_caro_original
        from mart_repuestos_comparables where not revisar order by veces_mas_caro_original desc limit 12""").fetchall()]
    # Precio de cada marca contra el tipico de la misma pieza y modelo; solo las
    # piezas con 3 marcas o mas para comparar (sin contar los originales).
    marcas = {}
    for tipo, marca, indice, productos, n in con.sql("""
            select tipo_pieza, marca, indice, productos, familias from mart_repuestos_marcas
            qualify count(*) filter (where marca <> 'Original') over (partition by tipo_pieza) >= 3
            order by tipo_pieza, indice""").fetchall():
        marcas.setdefault(tipo, []).append([marca, limpio(indice), int(productos), int(n)])
    return escribir("repuestos.json", {
        "piezas": piezas, "intervalos": intervalos, "familias": list(familias.values()), "marcas": marcas,
        "comparables": {"veces_mediana": limpio(comparables[0]), "piezas": int(comparables[1]), "ejemplos": ejemplos},
        "capturado": con.sql("select max(capturado) from mart_repuestos").fetchone()[0].isoformat()})


OFERTAS_ALTERNATIVAS = 8
OFERTAS_ORIGINALES = 4


def exportar_ofertas(con, por_slug):
    """repuestos/<slug>.json: los productos de cada pieza de una familia, para
    ver de donde sale el precio mediano y donde comprarlo. Por pieza, los
    alternativos y los originales mas baratos (precio por unidad), con la
    tienda y el enlace al producto. Se baja solo el del modelo elegido."""
    import urllib.parse
    carpeta = os.path.join(DESTINO, "repuestos")
    os.makedirs(carpeta, exist_ok=True)
    ofertas = {}
    for marca, familia, tipo, tienda, sku, titulo, calidad, precio, unidades, url in con.sql(f"""
            with p as (
                select upper(m.cca_marca) marca, m.familia, r.tipo_pieza, r.tienda, r.sku, r.titulo, r.calidad,
                       r.precio, r.unidades, r.url, r.es_original,
                       row_number() over (partition by m.cca_marca, m.familia, r.tipo_pieza, r.es_original
                                          order by r.precio, r.sku) n
                from stg_repuestos__productos r join int_repuesto_modelos m using (sku)
                where r.es_vigente and r.tipo_pieza <> 'otro')
            select marca, familia, tipo_pieza, tienda, sku, titulo, calidad, precio, unidades, url from p
            where n <= case when es_original then {OFERTAS_ORIGINALES} else {OFERTAS_ALTERNATIVAS} end
            order by marca, familia, tipo_pieza, precio""").fetchall():
        if tienda == "rex":
            # Repuestos Express no publica el enlace aparte: es /producto/<sku>.
            url = "https://repuestos-express.com/producto/" + urllib.parse.quote(sku, safe="")
        piezas = ofertas.setdefault(slug(marca, familia), {})
        piezas.setdefault(tipo, []).append([tienda, titulo, calidad, limpio(precio), int(unidades), url])
    for s, piezas in ofertas.items():
        if s in por_slug:
            escribir(os.path.join("repuestos", f"{s}.json"), piezas)


def exportar_mi_auto(con, provincias, precio_litro, carro):
    """Datos de la pantalla "Mi auto" (cualquier auto que circula, nuevo o usado):

      miauto/indice.json   las familias (para elegir el auto), los intervalos de
                           cambio de los repuestos, el precio del litro por provincia
      miauto/<slug>.json   una por familia: versiones (consumo, service y repuestos
                           por km), y por version y anio la patente de cada provincia
                           y la valuacion fiscal; el plan de service km por km y el
                           precio de cada repuesto. Se baja solo la del auto elegido.
    """
    carpeta = os.path.join(DESTINO, "miauto")
    os.makedirs(carpeta, exist_ok=True)
    # Anios del modelo: los de la valuacion fiscal de sus versiones (el rango de anio
    # modelo de DNRPA tiene ruido: un Cronos "desde 2001"). El 0 km cuenta como este anio.
    familias = con.sql(f"""
        with anios as (select v.cca_marca, v.cca_modelo,
                              min(nullif(a.anio, 0)) anio_min,
                              max(case when a.anio = 0 then year(current_date) else a.anio end) anio_max
                       from mart_mantenimiento_version v join int_valuacion_version a using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
                       group by all)
        select upper(m.cca_marca) marca, m.cca_modelo familia, sum(m.tramites_12m) tramites, sum(m.inscripciones_12m) inscripciones,
               any_value(a.anio_min) anio_min, any_value(a.anio_max) anio_max
        from mart_mantenimiento_version m left join anios a using (cca_marca, cca_modelo)
        group by all
        having sum(m.tramites_12m) >= {MIN_TRAMITES_MI_AUTO}
        order by tramites desc""").fetchall()
    indice = []
    total = 0
    for marca, familia, tramites, inscripciones, amin, amax in familias:
        s = slug(marca, familia)
        indice.append({"marca": marca, "familia": familia, "slug": s, "tramites": int(tramites),
                       "inscripciones": int(inscripciones or 0), "anios": [amin, amax],
                       "carroceria": carro.get((marca, familia), "hatch")})
        clave = f"upper(cca_marca) = '{marca.replace(chr(39), chr(39) * 2)}' and cca_modelo = '{familia.replace(chr(39), chr(39) * 2)}'"
        columnas, versiones = filas(con, f"""
            with v as (select *, origen_codigo || marca_codigo || '-' || tipo_codigo || '-' || modelo_codigo as id
                       from mart_mantenimiento_version where {clave}
                       order by tramites_12m desc, modelo limit {VERSIONES_POR_FAMILIA}),
                 -- Sin consumo propio: la mediana de la familia con el mismo combustible.
                 med as (select combustible, median(consumo_l100km) c from mart_mantenimiento_version
                         where {clave} and consumo_l100km is not null group by all)
            select v.id, v.modelo, v.anio_modelo_min as anio_min, v.anio_modelo_max as anio_max, v.tramites_12m as tramites,
                   v.combustible, v.automatica,
                   coalesce(v.consumo_l100km, med.c) as consumo_l100km,
                   case when v.consumo_l100km is null and med.c is not null then 'familia' else v.consumo_estimacion end as consumo_estimacion,
                   v.service_por_km, v.service_fuente, v.repuestos_por_km, v.repuestos_por_km_original, v.repuestos_fuente
            from v left join med using (combustible)
            order by v.tramites_12m desc, v.modelo""")
        ids = [v[0] for v in versiones]
        lista_ids = ", ".join(f"'{i}'" for i in ids) or "''"
        # Patente por version, provincia y anio modelo; valuacion fiscal por version y anio.
        patente, anios = {}, {}
        for vid, prov, anio, valor in con.sql(f"""
                select origen_codigo || marca_codigo || '-' || tipo_codigo || '-' || modelo_codigo, provincia_id, anio_modelo, patente_anual
                from mart_patente_estimada
                where origen_codigo || marca_codigo || '-' || tipo_codigo || '-' || modelo_codigo in ({lista_ids})
                  and patente_anual is not null
                order by 1, 2, 3""").fetchall():
            patente.setdefault(vid, {}).setdefault(prov, {})[anio] = round(valor / 100) * 100
            anios.setdefault(vid, set()).add(anio)
        valor = {}
        for vid, anio, v in con.sql(f"""
                select origen_codigo || marca_codigo || '-' || tipo_codigo || '-' || modelo_codigo, anio, valor_fiscal
                from int_valuacion_version
                where origen_codigo || marca_codigo || '-' || tipo_codigo || '-' || modelo_codigo in ({lista_ids})
                order by 1, 2""").fetchall():
            valor.setdefault(vid, {})[str(anio)] = round(v / 1000) * 1000
        # Patente compacta: por version, la lista de anios y por provincia los valores en ese orden.
        patente_compacta = {}
        for vid, provs in patente.items():
            lista = sorted(anios[vid])
            patente_compacta[vid] = {"anios": lista, "valores": {p: [x.get(a) for a in lista] for p, x in provs.items()}}
        # Plan de service km por km (mediana entre los motores de la familia) y repuestos.
        service = [[km, limpio(p), items] for km, p, items in con.sql(f"""
            select p.km, median(p.precio), any_value(p.items_cambio)
            from stg_service__precios p
            join mart_service s on upper(s.marca) = upper(p.marca) and s.modelo_fuente = p.modelo_fuente
            where p.es_vigente and upper(s.marca) = '{marca.replace(chr(39), chr(39) * 2)}'
              and s.familia = '{familia.replace(chr(39), chr(39) * 2)}'
            group by p.km order by p.km""").fetchall()]
        repuestos = [[t, limpio(o), limpio(a)] for t, o, a in con.sql(f"""
            select tipo_pieza, precio_mediano_original, precio_mediano_alternativo from mart_repuestos
            where upper(cca_marca) = '{marca.replace(chr(39), chr(39) * 2)}' and familia = '{familia.replace(chr(39), chr(39) * 2)}'
            order by tipo_pieza""").fetchall()]
        total += escribir(os.path.join("miauto", f"{s}.json"), {
            "marca": marca, "familia": familia, "columnas": columnas, "versiones": versiones,
            "patente": patente_compacta, "valor": valor, "service": service, "repuestos": repuestos})
    # Intervalos de cambio y precio mediano de cada pieza en todas las familias (el que
    # usa el costo cuando la familia no tiene precio de esa pieza: int_mantenimiento_familia).
    intervalos = {t: {"unidades": u, "km": km, "solo_manual": sm, "mediana": [limpio(o), limpio(a)]}
                  for t, u, km, sm, o, a in con.sql("""
        select i.tipo_pieza, i.unidades, i.intervalo_km, i.solo_manual,
               median(coalesce(r.precio_mediano_original, r.precio_mediano_alternativo)),
               median(coalesce(r.precio_mediano_alternativo, r.precio_mediano_original))
        from costo_repuestos_intervalos i join mart_repuestos r using (tipo_pieza) group by all""").fetchall()}
    tam_indice = escribir(os.path.join("miauto", "indice.json"), {
        "familias": indice, "intervalos": intervalos, "precio_litro": precio_litro, "provincias": provincias})
    return {"miauto/indice.json": tam_indice, f"miauto/ ({len(indice)} familias)": total}


def main():
    os.makedirs(DESTINO, exist_ok=True)
    con = duckdb.connect(BASE, read_only=True)
    tamanios = {}

    provincias = {p: n for p, n in con.sql("select provincia_id, provincia_nombre from provincias").fetchall()}

    # ---------- costo.json ----------
    precio = {}
    for prov, comb, valor, periodo in con.sql("""
            select provincia_id, case when combustible = 'diesel' then 'diesel' else 'nafta' end, any_value(precio_litro), any_value(periodo_combustible)
            from mart_costo_componentes where precio_litro is not null group by all""").fetchall():
        precio.setdefault(prov, {})[comb] = round(valor, 2)
    columnas, versiones = filas(con, f"""
        select origen_codigo || marca_codigo || '-' || tipo_codigo || '-' || modelo_codigo as id,
               any_value(marca) as marca, any_value(modelo) as modelo, any_value(cca_modelo) as familia, any_value(carroceria) as carroceria,
               any_value(inscripciones_12m) as inscripciones_12m, any_value(valor_0km) as valor_0km,
               any_value(combustible) as combustible, any_value(automatica) as automatica, any_value(consumo_l100km) as consumo_l100km,
               any_value(consumo_estimacion) as consumo_estimacion,
               any_value(service_por_km) as service_por_km, any_value(service_fuente) as service_fuente,
               any_value(repuestos_por_km) as repuestos_por_km, any_value(repuestos_por_km_original) as repuestos_por_km_original,
               any_value(repuestos_fuente) as repuestos_fuente,
               any_value(proporcion_conservada_1) as proporcion_conservada_1,
               any_value(proporcion_conservada_5) as proporcion_conservada_5,
               any_value(proporcion_conservada_10) as proporcion_conservada_10,
               any_value(depreciacion_fuente) as depreciacion_fuente,
               map_from_entries(list((provincia_id, patente_anual)) filter (where patente_anual is not null)) as patente
        from mart_costo_componentes
        join (select origen_codigo, marca_codigo, tipo_codigo, modelo_codigo, {CARROCERIA} as carroceria from dim_version)
          using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
        group by origen_codigo, marca_codigo, tipo_codigo, modelo_codigo
        order by inscripciones_12m desc nulls last""")
    i_pat = columnas.index("patente")
    for v in versiones:
        v[i_pat] = {k: round(x) for k, x in (v[i_pat] or {}).items()}
    tamanios["costo.json"] = escribir("costo.json", {
        "provincias": provincias, "precio_litro": precio, "columnas": columnas, "versiones": versiones})

    # ---------- home.json ----------
    carro = carrocerias(con)
    vendidos = [{"marca": m, "familia": f, "unidades": int(n), "carroceria": carro.get((m, f), "hatch"),
                 "precio_desde": limpio(p)} for m, f, n, p in con.sql(f"""
        with v as (select upper(marca) marca, familia, sum(unidades) n from mart_mercado_mensual
                   where tramite = 'inscripcion' and segmento = 'liviano' and familia is not null and {ULTIMOS_12}
                   group by all),
             precio as (select upper(cca_marca) marca, cca_modelo familia, min(valor_0km) p from mart_costo_componentes group by all)
        select v.marca, v.familia, v.n, precio.p from v left join precio using (marca, familia)
        order by v.n desc limit 12""").fetchall()]
    conservan = [{"marca": m, "familia": f, "conserva_5": limpio(p5), "conserva_10": limpio(p10), "transferencias": int(t),
                  "carroceria": carro.get((m, f), "hatch")} for m, f, p5, p10, t in con.sql(f"""
        with t as (select upper(marca) marca, familia, sum(unidades) transf from mart_mercado_mensual
                   where tramite = 'transferencia' and segmento = 'liviano' and {ULTIMOS_12} group by all)
        select upper(d.marca), d.familia,
               max(d.proporcion_mercado) filter (where d.antiguedad = 5),
               max(d.proporcion_mercado) filter (where d.antiguedad = 10), any_value(t.transf)
        from mart_depreciacion d join t on upper(d.marca) = t.marca and d.familia = t.familia
        where d.con_respaldo and t.transf >= {MIN_TRANSFERENCIAS}
        group by all
        having max(d.proporcion_mercado) filter (where d.antiguedad = 5) is not null
        order by 3 desc limit 10""").fetchall()]
    # Usado de 5 anios (modelo 2021) en Buenos Aires, 15.000 km por anio: combustible,
    # service, repuestos y patente; sin depreciacion (el usado ya la tuvo). Solo
    # familias con todos los componentes propios (sin respaldos).
    mantener = [{"marca": m, "familia": f, "mensual": limpio(t), "combustible": limpio(c), "service": limpio(sv),
                 "repuestos": limpio(r), "patente": limpio(p), "transferencias": int(n), "carroceria": carro.get((m, f), "hatch")}
                for m, f, n, t, c, sv, r, p in con.sql(f"""
        with transf as (select upper(marca) marca, familia, sum(unidades) n from mart_mercado_mensual
                        where tramite = 'transferencia' and segmento = 'liviano' and {ULTIMOS_12} group by all),
             fam as (select upper(cca_marca) marca, cca_modelo familia, median(combustible_por_km) c,
                            median(service_por_km) s, median(repuestos_por_km) r
                     from mart_costo_componentes
                     where provincia_id = '06' and service_fuente = 'familia' and repuestos_fuente <> 'mediana_general'
                       and combustible_por_km is not null
                     group by all),
             pat as (select upper(d.cca_marca) marca, d.cca_modelo familia, median(p.patente_anual) p
                     from mart_patente_estimada p join dim_version d using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
                     where p.provincia_id = '06' and p.anio_modelo = 2021 group by all)
        select fam.marca, fam.familia, transf.n,
               (15000 * (c + s + r) + coalesce(p, 0)) / 12, 15000 * c / 12, 15000 * s / 12, 15000 * r / 12, coalesce(p, 0) / 12
        from fam join transf using (marca, familia) left join pat using (marca, familia)
        where transf.n >= {MIN_TRANSFERENCIAS}
        order by 4 limit 10""").fetchall()]
    # Directo del mart de combustible (las 24 provincias), ponderado por volumen.
    periodo_combustible = con.sql("select max(periodo) from mart_combustible_mensual where periodo_completo").fetchone()[0]
    combustible = [{"provincia_id": prov, "provincia": provincias[prov], "nafta": limpio(n), "diesel": limpio(d)}
                   for prov, n, d in con.sql(f"""
        select provincia_id,
               sum(precio_ponderado * volumen_m3) filter (where producto like 'Nafta (súper)%')
                 / sum(volumen_m3) filter (where producto like 'Nafta (súper)%'),
               sum(precio_ponderado * volumen_m3) filter (where producto like 'Gas Oil Grado 2%')
                 / sum(volumen_m3) filter (where producto like 'Gas Oil Grado 2%')
        from mart_combustible_mensual where periodo = DATE '{periodo_combustible}'
        group by 1 order by 2""").fetchall()]
    tamanios["home.json"] = escribir("home.json", {"vendidos": vendidos, "conservan": conservan, "mantener": mantener,
                                                   "combustible": combustible})

    # ---------- fichas.json ----------
    fichas = {}
    for marca, familia, antig, fiscal, mercado in con.sql("""
            select upper(marca), familia, antiguedad, proporcion_fiscal, proporcion_mercado
            from mart_depreciacion order by 1, 2, 3""").fetchall():
        f = fichas.setdefault(f"{marca}|{familia}", {"marca": marca, "familia": familia})
        f.setdefault("depreciacion", []).append([antig, limpio(fiscal), limpio(mercado)])
    for marca, modelo, familia, costo_km, precio_med, hasta in con.sql("""
            select upper(marca), modelo_fuente, familia, costo_por_km, precio_mediano, plan_hasta_km
            from mart_service where familia is not null""").fetchall():
        f = fichas.setdefault(f"{marca}|{familia}", {"marca": marca, "familia": familia})
        f.setdefault("service", []).append([modelo, limpio(costo_km), limpio(precio_med), hasta])
    for marca, familia, tipo, orig, alt, n in con.sql("""
            select cca_marca, familia, tipo_pieza, precio_mediano_original, precio_mediano_alternativo, productos
            from mart_repuestos""").fetchall():
        f = fichas.setdefault(f"{marca}|{familia}", {"marca": marca, "familia": familia})
        f.setdefault("repuestos", []).append([tipo, limpio(orig), limpio(alt), n])
    for marca, familia, periodo, insc, transf in con.sql("""
            select upper(marca), familia, periodo,
                   sum(unidades) filter (where tramite = 'inscripcion'),
                   sum(unidades) filter (where tramite = 'transferencia')
            from mart_mercado_mensual
            where segmento = 'liviano' and familia is not null
              and periodo > (select max(periodo) from mart_mercado_mensual) - interval 12 month
            group by all order by periodo""").fetchall():
        f = fichas.get(f"{marca}|{familia}")
        if f is not None:
            f.setdefault("mercado", []).append([periodo.isoformat()[:7], limpio(insc), limpio(transf)])
    for f in fichas.values():
        f["carroceria"] = carro.get((f["marca"], f["familia"]), "hatch")
    tamanios["fichas.json"] = escribir("fichas.json", {"fichas": list(fichas.values())})

    # ---------- equipamiento.json ----------
    # Versiones de cada ficha, con la version DNRPA que les corresponde (id del
    # comparador y precio 0 km, si DNRPA ya la registro).
    versiones_eq = {}
    for m, f, v, orden, vid, valor in con.sql("""
            select e.marca, e.familia, e.version_fuente, e.orden_version,
                   e.origen_codigo || e.marca_codigo || '-' || e.tipo_codigo || '-' || e.modelo_codigo,
                   (select any_value(valor_0km) from mart_costo_componentes c
                     where (c.origen_codigo, c.marca_codigo, c.tipo_codigo, c.modelo_codigo)
                         = (e.origen_codigo, e.marca_codigo, e.tipo_codigo, e.modelo_codigo))
            from int_equipamiento_version e order by e.marca, e.familia, e.orden_version""").fetchall():
        versiones_eq.setdefault((m, f), []).append({"nombre": v, "id": vid, "valor_0km": limpio(valor)})
    equipamiento = {}
    for m, f, seccion, item, valores, fuente in con.sql("""
            select marca, familia, seccion, item, list(valor order by orden_version), any_value(fuente_url)
            from stg_equipamiento__items group by marca, familia, seccion, item
            order by marca, familia, min(orden_item)""").fetchall():
        e = equipamiento.setdefault(f"{m}|{f}", {"fuente": fuente, "versiones": versiones_eq.get((m, f), []), "secciones": []})
        if not e["secciones"] or e["secciones"][-1]["nombre"] != seccion:
            e["secciones"].append({"nombre": seccion, "items": []})
        e["secciones"][-1]["items"].append([item, valores])
    for m, f, orden, cambio, item, antes, despues in con.sql("""
            select marca, familia, orden_version, cambio, item, valor_anterior, valor
            from mart_equipamiento_suma order by marca, familia, orden_version, cambio, item""").fetchall():
        sumas = equipamiento[f"{m}|{f}"].setdefault("suma", {})
        sumas.setdefault(str(orden), {"agrega": [], "mejora": [], "quita": []})[cambio].append(
            item if cambio != "mejora" else [item, antes, despues])
    # Caracteristicas comunes entre marcas (para comparar modelos lado a lado):
    # en cada version, id -> 'si' / 'no' / 'opcional' o las pulgadas.
    for m, f, v, car, tiene, pulg in con.sql("""
            select marca, familia, version_fuente, caracteristica, tiene, pulgadas
            from mart_equipamiento_comparable""").fetchall():
        for ver in equipamiento.get(f"{m}|{f}", {}).get("versiones", []):
            if ver["nombre"] == v:
                ver.setdefault("comparable", {})[car] = limpio(pulg) if pulg is not None else tiene
    caracteristicas = [{"id": i, "nombre": n, "grupo": g, "tipo": t} for i, n, g, t in con.sql(
        "select id, nombre, grupo, tipo from equipamiento_caracteristicas order by orden").fetchall()]
    tamanios["equipamiento.json"] = escribir("equipamiento.json", {"caracteristicas": caracteristicas, "familias": equipamiento})

    # ---------- oficiales.json ----------
    # Pagina oficial de cada modelo (o de la marca, si su sitio no deja
    # verificar las de modelo): el sitio enlaza ahi para el 360 y el
    # configurador, que tienen derechos y no se copian.
    import csv
    with open(os.path.join("exportar", "sitios_oficiales.csv"), encoding="utf-8") as f:
        oficiales = {f"{r['marca']}|{r['familia']}": {"alcance": r["alcance"], "url": r["url"]} for r in csv.DictReader(f)}
    tamanios["oficiales.json"] = escribir("oficiales.json", oficiales)

    # ---------- repuestos.json ----------
    tamanios["repuestos.json"] = exportar_repuestos(con)

    # ---------- miauto/ ----------
    tamanios.update(exportar_mi_auto(con, provincias, precio, carro))

    # ---------- meta.json ----------
    meta = {
        "generado": date.today().isoformat(),
        "periodos": {
            "combustible": periodo_combustible.isoformat(),
            "mercado": con.sql("select max(periodo) from mart_mercado_mensual").fetchone()[0].isoformat(),
            "guia_cca": con.sql("select max(periodo) from stg_cca__precios").fetchone()[0].isoformat(),
            "service": con.sql("select max(capturado) from mart_service").fetchone()[0].isoformat(),
            "repuestos": con.sql("select max(capturado) from mart_repuestos").fetchone()[0].isoformat(),
        },
        "perfil_por_defecto": {"km_anio": 15000, "anios": 5},
    }
    tamanios["meta.json"] = escribir("meta.json", meta)
    for nombre, t in tamanios.items():
        print(f"{nombre:16s} {t / 1024:8.0f} KiB")


if __name__ == "__main__":
    main()
