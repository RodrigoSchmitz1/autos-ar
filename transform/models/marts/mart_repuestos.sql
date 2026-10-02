{#
  Precio de los repuestos de desgaste por familia de modelo y tipo de pieza,
  original contra alternativo. Foto vigente de Repuestos Express.

  Grano: familia (CCA) x tipo de pieza.

  Se usa la MEDIANA: un mismo tipo de pieza mezcla motores y versiones (el
  filtro de aire de un Gol 1.6 y el de un Gol diesel), y la mediana no se mueve
  por un caso raro. Los conjuntos y soportes ya quedaron afuera en staging.
  Un repuesto compatible con varias familias ("Palio/Siena") cuenta en cada una.
#}

with p as (
    select r.*, m.cca_marca, m.familia, m.metodo
    from {{ ref('stg_repuestos__productos') }} r
    join {{ ref('int_repuesto_modelos') }} m using (sku)
    where r.es_vigente and r.tipo_pieza <> 'otro'
)

select
    cca_marca,
    familia,
    tipo_pieza,
    count(*) as productos,
    count(*) filter (where es_original) as originales,
    count(*) filter (where not es_original) as alternativos,
    round(median(precio) filter (where es_original)) as precio_mediano_original,
    round(median(precio) filter (where not es_original)) as precio_mediano_alternativo,
    min(precio) as precio_min,
    max(precio) as precio_max,
    max(capturado) as capturado
from p
group by all
