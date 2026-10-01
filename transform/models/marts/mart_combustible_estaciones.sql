{#
  Ultimo mes COMPLETO por estacion y producto, con ubicacion: la base del mapa
  "la estacion mas barata cerca".

  No es tiempo real: desde que la Res. 717/2025 derogo la obligacion de informar
  al momento, el unico dato con todas las estaciones es la declaracion mensual
  de la Res. 1104 (ver fase0/07_combustible.md). Por eso el mes va explicito.

  Grano: estacion x producto. Solo estaciones con coordenadas (~91%).
  `diferencia_vs_provincia`: precio de la estacion contra la mediana de su
  provincia ese mes (-0,05 = 5% mas barata).
#}

with ultimo_completo as (
    select max(periodo) as periodo from {{ ref('stg_combustible__precios') }} where periodo_completo
),

base as (
    select p.*, coalesce(b.bandera, p.bandera) as bandera_display,
           median(p.precio_surtidor) over (partition by p.provincia_id, p.producto) as mediana_provincia
    from {{ ref('stg_combustible__precios') }} p
    left join {{ ref('banderas') }} b on b.bandera_fuente = p.bandera
    where p.periodo = (select periodo from ultimo_completo)
      and p.canal = 'Al público' and not p.exentos and not p.declaracion_duplicada
      and not p.sin_movimientos and p.precio_surtidor > 0
)

select
    b.periodo,
    b.nro_inscripcion,
    b.bandera_display as bandera,
    b.operador,
    b.direccion,
    b.localidad,
    b.provincia_id,
    e.latitud,
    e.longitud,
    b.producto,
    b.precio_surtidor as precio,
    round(b.volumen, 1) as volumen_m3,
    round(b.precio_surtidor / b.mediana_provincia - 1, 4) as diferencia_vs_provincia
from base b
join {{ ref('stg_combustible__estaciones') }} e using (nro_inscripcion)
where b.precio_surtidor between 0.5 * b.mediana_provincia and 2 * b.mediana_provincia
