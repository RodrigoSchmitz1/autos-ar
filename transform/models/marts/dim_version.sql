{#
  Catalogo canonico de versiones con sus cruces a cada fuente.

  Grano: una version (codigo DNRPA: origen, marca, tipo, modelo).

  Cada cruce dice COMO se hizo (`*_metodo`), para poder filtrar por confianza:
    valuacion: 'codigo' (exacto) o 'codigo_desempate_texto'
    cca, consumo: 'alias', 'prefijo', 'prefijo_ambiguo' o 'revision_manual'
  Las revisiones manuales (seed revisiones_mapeo) pisan al cruce automatico.
#}

with valuacion as (
    select origen_codigo, marca_codigo, tipo_codigo, modelo_codigo,
           any_value(metodo) as valuacion_metodo,
           any_value(descripcion_valuacion) as descripcion_valuacion,
           max(valor_fiscal) filter (where anio = 0) as valor_fiscal_0km
    from {{ ref('int_valuacion_version') }}
    group by 1, 2, 3, 4
),

revision as (
    select * from {{ ref('revisiones_mapeo') }}
)

select
    v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo,
    v.marca, v.modelo, v.tipo, v.segmento,
    v.anio_modelo_min, v.anio_modelo_max,
    v.tramites, v.inscripciones, v.tramites_12m, v.inscripciones_12m, v.ultimo_tramite,

    val.valuacion_metodo,
    val.descripcion_valuacion,
    val.valor_fiscal_0km,

    m.cca_marca,
    coalesce(rc.modelo_asignado, m.cca_modelo) as cca_modelo,
    case when rc.modelo_asignado is not null then 'revision_manual' else m.cca_metodo end as cca_metodo,
    m.cca_candidatos,

    m.consumo_marca,
    coalesce(rk.modelo_asignado, m.consumo_modelo) as consumo_modelo,
    case when rk.modelo_asignado is not null then 'revision_manual' else m.consumo_metodo end as consumo_metodo,
    m.consumo_candidatos
from {{ ref('int_versiones') }} v
left join valuacion val using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
left join {{ ref('int_mapeo_texto') }} m using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
left join revision rc
    on rc.fuente = 'cca' and rc.origen_codigo = v.origen_codigo and rc.marca_codigo = v.marca_codigo
   and rc.tipo_codigo = v.tipo_codigo and rc.modelo_codigo = v.modelo_codigo
left join revision rk
    on rk.fuente = 'consumo' and rk.origen_codigo = v.origen_codigo and rk.marca_codigo = v.marca_codigo
   and rk.tipo_codigo = v.tipo_codigo and rk.modelo_codigo = v.modelo_codigo
