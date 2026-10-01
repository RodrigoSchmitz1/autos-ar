{#
  Valor fiscal vigente por version y anio, cruzado por codigo.

  El cruce es exacto salvo en ~400 codigos NACIONALES que comparten marca, tipo y
  modelo entre fabricantes distintos (los microdatos no traen fabricante). Ahi:
    - si todos los fabricantes tienen el mismo valor anio por anio (312 casos),
      da igual cual: metodo 'codigo';
    - si no (93 casos, ej. 17/12/97 es "FIAT SIENA EX FIRE" y "FIAT DUNA CSD"),
      se elige el fabricante cuya descripcion se parece mas a la del tramite:
      metodo 'codigo_desempate_texto', con la similitud en `similitud`.

  Grano: version x anio (anio = 0 es el 0 km). Usa la tabla de valuacion mas
  reciente.
#}

with vigente as (
    select * from {{ ref('stg_valuacion') }}
    where vigencia = (select max(vigencia) from {{ ref('stg_valuacion') }})
),

candidatos as (
    select
        v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo,
        v.fabricante_codigo, v.descripcion,
        jaro_winkler_similarity(upper(v.descripcion), upper(i.marca || ' ' || i.modelo)) as similitud
    from (select distinct origen_codigo, marca_codigo, tipo_codigo, modelo_codigo, fabricante_codigo, descripcion from vigente) v
    join {{ ref('int_versiones') }} i using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
),

valores_distintos as (
    -- cuantos valores distintos hay por llave y anio entre fabricantes
    select origen_codigo, marca_codigo, tipo_codigo, modelo_codigo,
           max(n) as max_valores_por_anio, count(distinct fabricante_codigo) as fabricantes
    from (
        select *, count(distinct valor) over (partition by origen_codigo, marca_codigo, tipo_codigo, modelo_codigo, anio) as n
        from vigente
    )
    group by 1, 2, 3, 4
),

elegido as (
    select c.*, d.fabricantes,
           case when d.max_valores_por_anio = 1 then 'codigo' else 'codigo_desempate_texto' end as metodo
    from candidatos c
    join valores_distintos d using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
    qualify row_number() over (
        partition by origen_codigo, marca_codigo, tipo_codigo, modelo_codigo
        order by similitud desc, fabricante_codigo
    ) = 1
)

select
    e.origen_codigo, e.marca_codigo, e.tipo_codigo, e.modelo_codigo,
    v.anio,
    v.valor as valor_fiscal,
    v.vigencia,
    e.descripcion as descripcion_valuacion,
    e.metodo,
    e.fabricantes,
    case when e.metodo = 'codigo_desempate_texto' then e.similitud end as similitud
from elegido e
join vigente v
    on v.origen_codigo = e.origen_codigo and v.marca_codigo = e.marca_codigo
   and v.tipo_codigo = e.tipo_codigo and v.modelo_codigo = e.modelo_codigo
   and v.fabricante_codigo is not distinct from e.fabricante_codigo
