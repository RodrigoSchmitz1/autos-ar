{#
  Componentes del costo de tener cada auto 0 km, por version y provincia.

  Es la base de la metrica estrella (costo total por mes y por km). Aca van
  los costos UNITARIOS (por km o por anio) con el origen de cada uno; el total
  para un perfil de uso esta en mart_costo_total.

    combustible   consumo (int_consumo_version, con su nivel de estimacion) x
                  precio ponderado por volumen de la provincia en el ultimo mes
                  completo (Res. 1104). Nafta y hibridos: nafta super; diesel:
                  gasoil grado 2. Electricos: sin dato (seria electricidad).
    service       costo por km del plan oficial de la familia (mart_service);
                  si la familia tiene varios motores, la mediana. Incluye
                  filtros, aceite y bujias: por eso NO se suman como repuestos.
    repuestos     piezas de desgaste fuera del service (frenos, amortiguadores,
                  distribucion, embrague) con los intervalos SUPUESTOS del seed
                  costo_repuestos_intervalos y el precio mediano por familia
                  (mart_repuestos). Dos columnas: con repuesto alternativo (el
                  que se usa en el total) y con original.
    patente       mart_patente_estimada, modelo 0 km del anio fiscal.
    depreciacion  proporcion del valor que conserva la familia a cada edad
                  (mart_depreciacion, curva de mercado; si no hay, fiscal).

  Respaldos: si la familia no tiene service, repuestos o curva de
  depreciacion, se usa una mediana mas general (de la marca o de todas), y la
  columna *_fuente lo dice ('familia', 'mediana_marca', 'mediana_general').
  Combustible no tiene respaldo: si falta, falta.

  Grano: version (llave DNRPA) x provincia. Solo livianos con valor 0 km.
#}

with version as (
    select v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo,
           v.marca, v.modelo, v.cca_marca, v.cca_modelo, v.valor_fiscal_0km, v.inscripciones_12m,
           c.combustible, c.cilindrada, c.consumo_l100km, c.consumo_estimacion,
           regexp_matches(upper(v.modelo), '\b(AT\d*|CVT|ECVT|AUT|AUTOMATIC[OA]|TIPTRONIC|DSG|DCT|EDC|IVT|E-?CVT)\b') as automatica
    from {{ ref('dim_version') }} v
    join {{ ref('int_consumo_version') }} c using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
    where v.segmento = 'liviano' and v.valor_fiscal_0km is not null and v.anio_modelo_max >= {{ var('anio_costo', 2026) }} - 1
),

ultimo_mes as (
    select max(periodo) as periodo from {{ ref('mart_combustible_mensual') }} where periodo_completo
),

precio_combustible as (
    select provincia_id,
           case when producto like 'Gas Oil Grado 2%' then 'diesel' else 'nafta' end as combustible,
           sum(precio_ponderado * volumen_m3) / sum(volumen_m3) as precio_litro,
           any_value(periodo) as periodo_combustible
    from {{ ref('mart_combustible_mensual') }}
    where periodo = (select periodo from ultimo_mes)
      and (producto like 'Nafta (súper)%' or producto like 'Gas Oil Grado 2%')
    group by all
),

service as (
    select upper(marca) as marca, familia, median(costo_por_km) as service_por_km
    from {{ ref('mart_service') }}
    where familia is not null
    group by all
),

repuestos as (
    select r.cca_marca, r.familia, i.solo_manual,
           sum(coalesce(r.precio_mediano_alternativo, r.precio_mediano_original) * i.unidades / i.intervalo_km) as por_km_alternativo,
           sum(coalesce(r.precio_mediano_original, r.precio_mediano_alternativo) * i.unidades / i.intervalo_km) as por_km_original,
           string_agg(r.tipo_pieza, ', ' order by r.tipo_pieza) as piezas
    from {{ ref('mart_repuestos') }} r
    join {{ ref('costo_repuestos_intervalos') }} i using (tipo_pieza)
    group by all
),

provincias as (
    select distinct provincia_id from {{ ref('mart_patente_estimada') }}
),

-- Respaldos: cuando la familia no tiene el dato, una mediana mas general y
-- marcada en la columna *_fuente. Combustible no tiene respaldo: es el
-- componente mas directo y en los electricos seria inventarlo.
service_general as (
    select median(service_por_km) as service_por_km from service
),

repuestos_por_familia as (
    select cca_marca, familia,
           sum(por_km_alternativo) filter (where not solo_manual) as sin_embrague,
           sum(por_km_alternativo) as con_embrague
    from repuestos group by all
),

repuestos_general as (
    select median(sin_embrague) as sin_embrague, median(con_embrague) as con_embrague from repuestos_por_familia
),

curva as (
    select upper(marca) as marca, familia, antiguedad, coalesce(proporcion_mercado, proporcion_fiscal) as proporcion
    from {{ ref('mart_depreciacion') }}
),

curva_marca as (
    select marca, antiguedad, median(proporcion) as proporcion from curva group by all
),

curva_general as (
    select antiguedad, median(proporcion) as proporcion from curva group by all
)

select
    v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo,
    p.provincia_id,
    v.marca, v.modelo, v.cca_marca, v.cca_modelo,
    v.inscripciones_12m,
    v.valor_fiscal_0km as valor_0km,
    v.combustible, v.cilindrada, v.automatica,
    v.consumo_l100km, v.consumo_estimacion,
    pc.precio_litro, pc.periodo_combustible,
    round(v.consumo_l100km / 100 * pc.precio_litro, 2) as combustible_por_km,
    coalesce(s.service_por_km, (select service_por_km from service_general)) as service_por_km,
    case when s.service_por_km is not null then 'familia' else 'mediana_general' end as service_fuente,
    -- El embrague solo cuenta en cajas manuales.
    coalesce(case when v.automatica then rf.sin_embrague else rf.con_embrague end,
             (select case when v.automatica then sin_embrague else con_embrague end from repuestos_general)) as repuestos_por_km,
    case when rf.con_embrague is not null then 'familia' else 'mediana_general' end as repuestos_fuente,
    (select sum(r.por_km_original) from repuestos r
      where r.cca_marca = v.cca_marca and r.familia = v.cca_modelo and (not r.solo_manual or not v.automatica)) as repuestos_por_km_original,
    pt.patente_anual,
    pt.precision as patente_precision,
    coalesce(cf1.proporcion, cm1.proporcion, cg1.proporcion) as proporcion_conservada_1,
    coalesce(cf5.proporcion, cm5.proporcion, cg5.proporcion) as proporcion_conservada_5,
    coalesce(cf10.proporcion, cm10.proporcion, cg10.proporcion) as proporcion_conservada_10,
    case when cf5.proporcion is not null then 'familia'
         when cm5.proporcion is not null then 'mediana_marca'
         else 'mediana_general' end as depreciacion_fuente
from version v
cross join provincias p
left join precio_combustible pc
  on pc.provincia_id = p.provincia_id and pc.combustible = case when v.combustible = 'diesel' then 'diesel' else 'nafta' end
 and v.combustible <> 'electrico'
left join service s on s.marca = upper(v.marca) and s.familia = v.cca_modelo
left join repuestos_por_familia rf on rf.cca_marca = v.cca_marca and rf.familia = v.cca_modelo
left join {{ ref('mart_patente_estimada') }} pt
  on pt.provincia_id = p.provincia_id
 and (pt.origen_codigo, pt.marca_codigo, pt.tipo_codigo, pt.modelo_codigo) = (v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo)
 and pt.anio_modelo = {{ var('anio_costo', 2026) }}
left join curva cf1 on cf1.marca = upper(v.cca_marca) and cf1.familia = v.cca_modelo and cf1.antiguedad = 1
left join curva cf5 on cf5.marca = upper(v.cca_marca) and cf5.familia = v.cca_modelo and cf5.antiguedad = 5
left join curva cf10 on cf10.marca = upper(v.cca_marca) and cf10.familia = v.cca_modelo and cf10.antiguedad = 10
left join curva_marca cm1 on cm1.marca = upper(coalesce(v.cca_marca, v.marca)) and cm1.antiguedad = 1
left join curva_marca cm5 on cm5.marca = upper(coalesce(v.cca_marca, v.marca)) and cm5.antiguedad = 5
left join curva_marca cm10 on cm10.marca = upper(coalesce(v.cca_marca, v.marca)) and cm10.antiguedad = 10
cross join (select proporcion from curva_general where antiguedad = 1) cg1
cross join (select proporcion from curva_general where antiguedad = 5) cg5
cross join (select proporcion from curva_general where antiguedad = 10) cg10
