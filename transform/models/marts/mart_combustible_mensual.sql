{#
  Precio y volumen de combustible por mes, provincia, producto y bandera
  (Res. 1104, venta al publico).

  Grano: periodo x provincia x producto x bandera.

  Que entra al precio:
    - venta al publico, no exenta (los exentos son otro precio: Patagonia,
      clientes especiales);
    - sin las declaraciones duplicadas de staging;
    - sin valores atipicos: menos de la mitad o mas del doble de la mediana de su
      provincia y producto ese mes (~0,4% de las filas en julio 2026).
  La mediana es la referencia (robusta); el promedio ponderado por volumen dice
  lo que realmente pago el mercado.

  `periodo_completo` = false en el ultimo mes publicado: llegan declaraciones
  tardias y no se compara de igual a igual con los anteriores.
#}

with base as (
    select p.*, coalesce(b.bandera, p.bandera) as bandera_display,
           median(p.precio_surtidor) over (partition by p.periodo, p.provincia_id, p.producto) as mediana_provincia
    from {{ ref('stg_combustible__precios') }} p
    left join {{ ref('banderas') }} b on b.bandera_fuente = p.bandera
    where p.canal = 'Al público' and not p.exentos and not p.declaracion_duplicada
      and not p.sin_movimientos and p.precio_surtidor > 0
)

select
    periodo,
    provincia_id,
    producto,
    bandera_display as bandera,
    count(distinct nro_inscripcion) as estaciones,
    round(sum(volumen), 1) as volumen_m3,
    round(median(precio_surtidor), 2) as precio_mediano,
    round(sum(precio_surtidor * volumen) / nullif(sum(volumen), 0), 2) as precio_ponderado,
    round(median(1 - precio_sin_impuestos / nullif(precio_con_impuestos, 0)), 3) as proporcion_impuestos,
    bool_and(periodo_completo) as periodo_completo
from base
where precio_surtidor between 0.5 * mediana_provincia and 2 * mediana_provincia
group by all
