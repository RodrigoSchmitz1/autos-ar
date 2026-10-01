{#
  Patente anual ESTIMADA por provincia, version y anio modelo.

  Es una estimacion y se publica como tal. Cada provincia fija su impuesto en su
  ley impositiva anual (escala, base, coeficiente, que modelos alcanza) y esos
  datos se curan a mano en dos seeds, con el articulo de ley de cada uno:
    patente_reglas   base oficial, coeficiente, ajustes, que queda afuera
    patente_escalas  tramos: cuota fija + alicuota sobre el excedente

  Por que estimada: la base oficial casi nunca es la valuacion de DNRPA. En
  Buenos Aires son los valores de ACARA x 0,95 (Ley 15.558 art. 35), y ACARA no
  es publica. Se usa la valuacion fiscal de DNRPA, que se arma con precios de
  ACARA y CCA, como aproximacion; `base_usada` lo dice en cada fila.
  Ademas, cada cuota se ajusta por inflacion durante el anio (art. 167): esto es
  el impuesto de la escala, sin ajustes.

  Grano: provincia x version x anio modelo. Solo livianos, solo provincias con
  reglas cargadas y solo los modelos que alcanza la escala.
#}

with valuacion as (
    -- anio 0 de la tabla es el 0 km: el modelo del anio de la vigencia
    select v.*, case when v.anio = 0 then year(v.vigencia) else v.anio end as anio_modelo
    from {{ ref('int_valuacion_version') }} v
    join {{ ref('dim_version') }} d using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
    where d.segmento = 'liviano'
),

base as (
    select r.provincia_id, r.anio_fiscal, r.precision, r.base_usada,
           v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo, v.anio_modelo,
           v.valor_fiscal,
           v.valor_fiscal * r.coeficiente_base as base_imponible
    from valuacion v
    cross join {{ ref('patente_reglas') }} r
)

select
    b.provincia_id, b.anio_fiscal,
    b.origen_codigo, b.marca_codigo, b.tipo_codigo, b.modelo_codigo, b.anio_modelo,
    b.valor_fiscal,
    round(b.base_imponible) as base_imponible,
    round(e.cuota_fija + (b.base_imponible - e.base_desde) * e.alicuota_pct / 100) as patente_anual,
    e.alicuota_pct as alicuota_marginal_pct,
    b.precision,
    b.base_usada,
    e.fuente
from base b
join {{ ref('patente_escalas') }} e
  on e.provincia_id = b.provincia_id and e.anio_fiscal = b.anio_fiscal and e.categoria = 'auto'
 and b.anio_modelo between e.modelo_desde and e.modelo_hasta
 and b.base_imponible > e.base_desde
 and (e.base_hasta is null or b.base_imponible <= e.base_hasta)
