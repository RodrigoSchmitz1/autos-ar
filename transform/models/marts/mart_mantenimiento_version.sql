{#
  Costo de mantenimiento por km de cada version que circula, nueva o usada
  (la pantalla "Mi auto"): consumo, service y repuestos. La patente depende del
  anio del auto y de la provincia, y el valor de la version y el anio: van
  aparte (mart_patente_estimada, int_valuacion_version).

  Mismo calculo que mart_costo_componentes (que es solo para los 0 km):
  service y repuestos de int_mantenimiento_familia, con la mediana de todas las
  familias de respaldo y la columna *_fuente que lo dice. El combustible por km
  no esta aca porque depende del precio de la provincia: el sitio lo calcula con
  el consumo.

  Grano: version (llave DNRPA) liviana, con familia de la guia CCA y algun
  tramite en los ultimos 12 meses.
#}

with version as (
    select v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo,
           v.marca, v.modelo, v.cca_marca, v.cca_modelo, v.anio_modelo_min, v.anio_modelo_max,
           v.tramites_12m, v.inscripciones_12m,
           c.combustible, c.cilindrada, c.consumo_l100km, c.consumo_estimacion,
           regexp_matches(upper(v.modelo), '\b(AT\d*|CVT|ECVT|AUT|AUTOMATIC[OA]|TIPTRONIC|DSG|DCT|EDC|IVT|E-?CVT)\b') as automatica
    from {{ ref('dim_version') }} v
    left join {{ ref('int_consumo_version') }} c using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
    where v.segmento = 'liviano' and v.cca_modelo is not null and v.tramites_12m > 0
),

familia as (
    select * from {{ ref('int_mantenimiento_familia') }}
),

general as (
    select median(service_por_km) as service_por_km,
           median(repuestos_sin_embrague) as sin_embrague, median(repuestos_con_embrague) as con_embrague
    from familia
)

select
    v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo,
    v.marca, v.modelo, v.cca_marca, v.cca_modelo, v.anio_modelo_min, v.anio_modelo_max,
    v.tramites_12m, v.inscripciones_12m,
    v.combustible, v.cilindrada, v.automatica, v.consumo_l100km, v.consumo_estimacion,
    coalesce(s.service_por_km, (select service_por_km from general)) as service_por_km,
    case when s.service_por_km is not null then 'familia' else 'mediana_general' end as service_fuente,
    coalesce(case when v.automatica then r.repuestos_sin_embrague else r.repuestos_con_embrague end,
             (select case when v.automatica then sin_embrague else con_embrague end from general)) as repuestos_por_km,
    case when r.repuestos_con_embrague is null then 'mediana_general'
         when (case when v.automatica then r.piezas_propias_sin_embrague = r.piezas_sin_embrague
                    else r.piezas_propias_con_embrague = r.piezas_con_embrague end) then 'familia'
         else 'parcial' end as repuestos_fuente,
    case when v.automatica then r.repuestos_original_sin_embrague else r.repuestos_original_con_embrague end as repuestos_por_km_original
from version v
left join familia s on s.marca = upper(v.marca) and s.familia = v.cca_modelo and s.service_por_km is not null
left join familia r on r.marca = upper(v.cca_marca) and r.familia = v.cca_modelo and r.repuestos_con_embrague is not null
