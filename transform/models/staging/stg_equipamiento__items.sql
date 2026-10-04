{#
  Equipamiento por version de los 0 km, de las fichas tecnicas oficiales.
  Ver ingesta/equipamiento.py.

  Grano: marca x familia x version x item, de la ultima foto capturada (cada
  archivo es la foto completa de todas las fichas).

  `valor`: 'si', 'no', 'opcional' o un texto ("10,1''", "2.0L Turbo") cuando
  la ficha da un dato en vez de una marca. `orden_version` es el orden de las
  columnas en la ficha: de la version de entrada a la mas equipada.
#}

with fuente as (
    select * from read_parquet('{{ var("raw") }}/equipamiento/*.parquet', union_by_name = true)
),

ultima as (
    select * from fuente where capturado = (select max(capturado) from fuente)
)

select
    marca, familia, version_fuente, orden_version, seccion, item, orden_item,
    valor,
    valor in ('si', 'no', 'opcional') as es_marca,
    fuente_url,
    capturado
from ultima
