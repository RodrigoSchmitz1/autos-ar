-- La cuota fija de cada tramo tiene que ser lo acumulado por los anteriores:
-- cuota_fija(n) = cuota_fija(n-1) + (base_desde(n) - base_desde(n-1)) * alicuota(n-1).
-- Si no da, hay un error de tipeo en la tabla cargada a mano (o la ley tiene
-- saltos, y entonces hay que revisarla y documentarlo).
with e as (
    select *, lag(cuota_fija) over w as cuota_ant, lag(base_desde) over w as desde_ant, lag(alicuota_pct) over w as alic_ant
    from {{ ref('patente_escalas') }}
    window w as (partition by provincia_id, anio_fiscal, categoria, modelo_desde, modelo_hasta order by base_desde)
)
select provincia_id, anio_fiscal, base_desde, cuota_fija,
       cuota_ant + (base_desde - desde_ant) * alic_ant / 100 as cuota_esperada
from e
where cuota_ant is not null
  and abs(cuota_fija - (cuota_ant + (base_desde - desde_ant) * alic_ant / 100)) > 1
