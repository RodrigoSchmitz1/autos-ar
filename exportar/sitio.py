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
                     where provincia_id = '06' and service_fuente = 'familia' and repuestos_fuente = 'familia'
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
