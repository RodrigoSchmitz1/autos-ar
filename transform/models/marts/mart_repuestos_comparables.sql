{#
  La MISMA pieza en calidad original y alternativa, comparada por precio.

  La llave es `sku_base` (codigo de la pieza sin el sufijo del proveedor, ver
  stg_repuestos__productos): en la Fase 0 los grupos revisados eran la misma
  pieza. Riesgo conocido: cuando el SKU no tiene guion, quitar la ultima letra
  puede unir dos piezas distintas; por eso se exige ademas el mismo tipo de
  pieza, y se marca `revisar` cuando la original sale mas barata.

  Grano: sku_base x tipo de pieza, solo los que tienen original y alternativo.
#}

with p as (
    select * from {{ ref('stg_repuestos__productos') }}
    where es_vigente and tipo_pieza <> 'otro'
)

select
    sku_base,
    tipo_pieza,
    any_value(titulo) filter (where es_original) as titulo_original,
    min(precio) filter (where es_original) as precio_original,
    min(precio) filter (where not es_original) as precio_alternativo_min,
    arg_min(calidad, precio) filter (where not es_original) as calidad_alternativa,
    round(min(precio) filter (where es_original) / min(precio) filter (where not es_original), 2) as veces_mas_caro_original,
    count(*) as productos,
    -- Original mas barata que el alternativo: casi seguro dos piezas distintas con
    -- el mismo codigo base (un kit con bomba de agua contra uno sin). Se marca,
    -- no se borra: el sitio no la muestra como comparacion.
    min(precio) filter (where es_original) < min(precio) filter (where not es_original) as revisar
from p
group by all
having bool_or(es_original) and bool_or(not es_original)
