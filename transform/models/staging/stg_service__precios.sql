{#
  Precios oficiales de service programado, todas las fotos capturadas.

  Grano: marca x modelo de la fuente x km x fecha de captura.
  Cada foto se guardo porque la fuente cambio; la vigente es la ultima captura
  de cada marca (`es_vigente`). Ver ingesta/service.py y docs/service_relevamiento.md.

  `precio` esta siempre en pesos. Las fuentes en dolares (BYD) guardan el
  monto publicado en `precio_original` y se convierten con el tipo de cambio
  minorista del BCRA:
    - foto vigente: el ultimo tipo de cambio publicado, porque una lista en
      dolares cuesta hoy lo que dice el dolar de hoy;
    - fotos viejas: el del dia en que se capturaron.
  El asof join toma el ultimo dia habil con dato (fines de semana, feriados).
#}

with fuente as (
    select * from read_parquet('{{ var("raw") }}/service/*/*.parquet', union_by_name = true)
),

precios as (
    select
        marca,
        trim(modelo_fuente) as modelo_fuente,
        km,
        precio as precio_original,
        coalesce(moneda, 'ARS') as moneda,
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
),

con_fecha as (
    select
        *,
        case when es_vigente then current_date else capturado end as fecha_cambio
    from precios
)

select
    p.* exclude (fecha_cambio),
    case when p.moneda = 'USD' then round(p.precio_original * c.pesos_por_dolar)
         else p.precio_original end as precio,
    case when p.moneda = 'USD' then c.pesos_por_dolar end as tipo_cambio,
    case when p.moneda = 'USD' then c.fecha end as tipo_cambio_fecha
from con_fecha p
asof left join {{ ref('stg_cambio__usd_minorista') }} c
    on p.fecha_cambio >= c.fecha
