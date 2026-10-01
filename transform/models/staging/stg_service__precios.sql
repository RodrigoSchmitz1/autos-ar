{#
  Precios oficiales de service programado, todas las fotos capturadas.

  Grano: marca x modelo de la fuente x km x fecha de captura.
  Cada foto se guardo porque la fuente cambio; la vigente es la ultima captura
  de cada marca (`es_vigente`). Ver ingesta/service.py y docs/service_relevamiento.md.
#}

with fuente as (
    select * from read_parquet('{{ var("raw") }}/service/*/*.parquet', union_by_name = true)
)

select
    marca,
    trim(modelo_fuente) as modelo_fuente,
    km,
    precio,
    tipo_precio,
    mano_obra_bonificada,
    incluye_iva,
    items_cambio,
    precio_corregido,
    fuente_url,
    vigencia_desde,
    vigencia_hasta,
    capturado,
    capturado = max(capturado) over (partition by marca) as es_vigente
from fuente
