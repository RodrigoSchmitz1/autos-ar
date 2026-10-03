{#
  Costo total de tener cada auto 0 km: la metrica estrella del proyecto.

  Perfil de uso por defecto (variables de dbt, se pueden cambiar):
    km_anio            {{ var('km_anio', 15000) }} km por anio
    anios_tenencia     {{ var('anios_tenencia', 5) }} anios (curva de depreciacion: 1, 5 o 10)

  costo anual = km_anio x (combustible + service + repuestos por km)
              + patente anual
              + depreciacion anual = valor 0 km x (1 - proporcion conservada) / anios
  costo mensual = costo anual / 12;  costo por km = costo anual / km_anio.

  Fuera del total: seguro (lo carga el usuario: no hay fuente publica),
  cocheras, peajes y lavados. La patente se toma la del 0 km todos los anios:
  es una cota alta, porque la valuacion baja con la edad.

  `componentes_faltantes` lista lo que no se pudo calcular; el total se publica
  solo si no falta nada (`completo`), para no comparar autos con distintas
  piezas sumadas.

  Grano: version x provincia.
#}

{% set anios = var('anios_tenencia', 5) %}
{% set km = var('km_anio', 15000) %}

with c as (
    select *,
        {% if anios == 1 %} proporcion_conservada_1
        {% elif anios == 10 %} proporcion_conservada_10
        {% else %} proporcion_conservada_5 {% endif %} as proporcion_conservada
    from {{ ref('mart_costo_componentes') }}
),

calculo as (
    select *,
        {{ km }} * combustible_por_km as combustible_anual,
        {{ km }} * service_por_km as service_anual,
        {{ km }} * repuestos_por_km as repuestos_anual,
        valor_0km * (1 - proporcion_conservada) / {{ anios }} as depreciacion_anual,
        concat_ws(', ',
            case when combustible_por_km is null then 'combustible' end,
            case when service_por_km is null then 'service' end,
            case when repuestos_por_km is null then 'repuestos' end,
            case when patente_anual is null then 'patente' end,
            case when proporcion_conservada is null then 'depreciacion' end
        ) as componentes_faltantes
    from c
)

select
    origen_codigo, marca_codigo, tipo_codigo, modelo_codigo, provincia_id,
    marca, modelo, cca_marca, cca_modelo, inscripciones_12m, valor_0km, combustible,
    {{ km }} as km_anio,
    {{ anios }} as anios_tenencia,
    round(combustible_anual) as combustible_anual,
    round(service_anual) as service_anual,
    round(repuestos_anual) as repuestos_anual,
    patente_anual,
    round(depreciacion_anual) as depreciacion_anual,
    round(combustible_anual + service_anual + repuestos_anual + patente_anual + depreciacion_anual) as costo_anual,
    round((combustible_anual + service_anual + repuestos_anual + patente_anual + depreciacion_anual) / 12) as costo_mensual,
    round((combustible_anual + service_anual + repuestos_anual + patente_anual + depreciacion_anual) / {{ km }}, 1) as costo_por_km,
    consumo_estimacion,
    patente_precision,
    service_fuente,
    repuestos_fuente,
    depreciacion_fuente,
    -- Cuantos componentes salen de un respaldo general en vez de la familia.
    (service_fuente <> 'familia')::int + (repuestos_fuente <> 'familia')::int + (depreciacion_fuente <> 'familia')::int as componentes_con_respaldo,
    nullif(componentes_faltantes, '') as componentes_faltantes,
    componentes_faltantes = '' as completo
from calculo
