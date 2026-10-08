{#
  Registros seccionales de DNRPA: nombre y provincia de cada codigo.

  En la republicacion de octubre 2026 DNRPA dejo sin nombre ni provincia a ~23
  registros en algunos meses (y unas pocas filas traen el texto 'NULL'). El
  codigo si viene, y cada codigo es de una sola provincia: se toma lo que ese
  registro trae en todos los meses. stg_dnrpa__tramites lo cruza por codigo.

  Es tabla (no vista) para no recorrer todos los tramites en cada consulta.

  Grano: un registro seccional.
#}
{{ config(materialized='table') }}

with fuente as (
    select registro_seccional_codigo, registro_seccional_descripcion, registro_seccional_provincia
    from read_parquet('{{ var("raw") }}/dnrpa/*/*.parquet', union_by_name = true)
),

registros as (
    select
        registro_seccional_codigo,
        mode(nullif(trim(registro_seccional_descripcion), 'NULL')) as descripcion,
        mode(nullif(trim(registro_seccional_provincia), 'NULL')) as provincia
    from fuente
    group by 1
)

select *, {{ provincia_id('provincia') }} as provincia_id
from registros
