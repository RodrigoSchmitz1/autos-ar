{#
  Los cuatro tramites de DNRPA en una sola tabla: tienen exactamente el mismo
  esquema, y casi todo lo de arriba (mercado, robos por modelo, prendas) los
  cruza por modelo y provincia.

  Grano: UNA FILA POR TRAMITE (un auto). El porcentaje de titularidad que traen
  los CSV es del primer titular y no se usa: contar filas coincide con la
  estadistica oficial de DNRPA (ver fase0/04_volumen.md).

  La provincia es la del REGISTRO. La "del domicilio del titular" replica la del
  registro en el 100% de las filas, asi que no aporta nada y no se ingiere.
#}

{# Cada bloque nombra la columna literal: en UNION ALL BY NAME, una columna sin
   alias se llama como su valor ('prenda') y queda como columna aparte. #}
with fuente as (
    select *, 'inscripcion' as tramite from read_parquet('{{ var("raw") }}/dnrpa/inscripciones/*.parquet')
    union all by name
    select *, 'transferencia' as tramite from read_parquet('{{ var("raw") }}/dnrpa/transferencias/*.parquet')
    union all by name
    select *, 'prenda' as tramite from read_parquet('{{ var("raw") }}/dnrpa/prendas/*.parquet')
    union all by name
    select *, 'robo_recupero' as tramite from read_parquet('{{ var("raw") }}/dnrpa/robos/*.parquet')
)

select
    tramite,
    trim(tramite_tipo) as tramite_tipo,
    tramite_fecha,
    date_trunc('month', tramite_fecha)::date as periodo,
    fecha_inscripcion_inicial,

    registro_seccional_codigo,
    trim(registro_seccional_descripcion) as registro_seccional,
    {{ provincia_id('registro_seccional_provincia') }} as provincia_id,

    case trim(automotor_origen)
        when 'Nacional' then 'nacional'
        when 'Importado' then 'importado'
        when 'Protocolo 21' then 'protocolo_21'
    end as origen,
    automotor_anio_modelo as anio_modelo,
    trim(automotor_marca_codigo) as marca_codigo,
    trim(automotor_tipo_codigo) as tipo_codigo,
    trim(automotor_modelo_codigo) as modelo_codigo,
    trim(automotor_marca_descripcion) as marca,
    trim(automotor_modelo_descripcion) as modelo,
    trim(automotor_tipo_descripcion) as tipo,
    trim(automotor_uso_descripcion) as uso,

    case trim(titular_tipo_persona)
        when 'Física' then 'fisica'
        when 'Jurídica' then 'juridica'
    end as titular_tipo_persona
from fuente
