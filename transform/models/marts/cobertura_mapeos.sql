{#
  Que parte del mercado cruza con cada fuente: la metrica de calidad del
  catalogo, para publicarla (ver fase0/05_matching.md, donde se fijo el piso
  del 70%).

  Solo sobre versiones LIVIANAS: las guias de precios no cubren camiones ni
  remolques, y contarlos como "no cruza" bajaba la cobertura sin que fuera un
  problema del cruce.

  Se mide de tres formas, porque cuentan cosas distintas:
    versiones         todas las versiones por igual (muchas casi no se venden)
    tramites_12m      ponderado por todo lo que se movio en el ultimo anio
    inscripciones_12m ponderado por 0 km del ultimo anio (el mercado nuevo)
#}

with base as (
    select *,
        valuacion_metodo is not null as cruza_valuacion,
        cca_modelo is not null as cruza_cca,
        consumo_modelo is not null as cruza_consumo
    from {{ ref('dim_version') }}
    where segmento = 'liviano'
),

largo as (
    select 'valuacion' as fuente, cruza_valuacion as cruza, tramites_12m, inscripciones_12m from base
    union all
    select 'cca', cruza_cca, tramites_12m, inscripciones_12m from base
    union all
    select 'consumo', cruza_consumo, tramites_12m, inscripciones_12m from base
)

select
    fuente,
    count(*) as versiones,
    round(100.0 * count(*) filter (where cruza) / count(*), 1) as pct_versiones,
    round(100.0 * sum(tramites_12m) filter (where cruza) / sum(tramites_12m), 1) as pct_tramites_12m,
    round(100.0 * sum(inscripciones_12m) filter (where cruza) / sum(inscripciones_12m), 1) as pct_inscripciones_12m
from largo
group by 1
order by 1
