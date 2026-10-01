{#
  Curva de depreciacion por modelo: cuanto vale un auto con N anios respecto de
  su 0 km, segun la valuacion fiscal y segun el mercado (guia CCA).

  Se comparan PROPORCIONES, no precios: en la Fase 0 el ratio CCA/fiscal salio
  bimodal (1,00 en unos modelos, ~0,70 en otros) porque las dos fuentes miden en
  fechas y niveles distintos. La proporcion dentro de cada fuente elimina eso y
  deja la pregunta limpia: el fisco, deprecia como el mercado?

  Metodo: INDICE ENCADENADO. La CCA le pone el anio al nombre de la version
  ("TITANIUM 2025"), asi que casi ninguna version tiene a la vez precio 0 km y de
  varios anios atras: comparar cada anio contra el 0 km dejaba curvas de 1 o 2
  puntos. En cambio, para cada salto de un anio (N-1 -> N) se toma la mediana,
  entre las versiones que tienen los dos precios, de precio(N) / precio(N-1); la
  curva es el producto de los saltos. Sirve cualquier version con dos anios
  seguidos. Se usa el mismo metodo para la valuacion fiscal, asi las dos curvas
  son comparables.

  Grano: marca x familia (modelo CCA) x antiguedad (1 a 14 anios).
  `versiones_*` es el respaldo del salto mas flojo de la cadena hasta ese anio.
  `con_respaldo`: la cadena completa hasta ese anio, de los dos lados, con al
  menos 3 versiones en cada salto. Sin respaldo se publica igual, pero no se destaca.
#}

{% set max_antiguedad = 14 %}

with fiscal_serie as (
    -- una serie por version: antiguedad 0 = 0 km
    select d.cca_marca as marca, d.cca_modelo as familia,
           v.origen_codigo || v.marca_codigo || v.tipo_codigo || v.modelo_codigo as version,
           case when v.anio = 0 then 0 else year(v.vigencia) - v.anio end as antiguedad,
           v.valor_fiscal as valor
    from {{ ref('int_valuacion_version') }} v
    join {{ ref('dim_version') }} d using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
    where d.cca_modelo is not null and d.segmento = 'liviano'
),

mercado_serie as (
    select marca, modelo as familia, version,
           case when anio = 0 then 0 else year(periodo) - anio end as antiguedad,
           precio as valor
    from {{ ref('stg_cca__precios') }}
    where periodo = (select max(periodo) from {{ ref('stg_cca__precios') }})
),

{% for lado in ['fiscal', 'mercado'] %}
{{ lado }}_saltos as (
    -- precio(N) / precio(N-1) de la misma version
    select a.marca, a.familia, a.antiguedad,
           median(a.valor / b.valor) as salto,
           count(*) as versiones
    from {{ lado }}_serie a
    join {{ lado }}_serie b
      on b.marca = a.marca and b.familia = a.familia and b.version = a.version
     and b.antiguedad = a.antiguedad - 1
    where a.antiguedad between 1 and {{ max_antiguedad }} and b.valor > 0
    group by all
),

{{ lado }}_curva as (
    select marca, familia, antiguedad,
           exp(sum(ln(salto)) over w) as proporcion,
           min(versiones) over w as versiones,
           -- la cadena esta completa si hay un salto por cada anio desde el 1
           count(*) over w = antiguedad as cadena_completa
    from {{ lado }}_saltos
    where salto > 0
    window w as (partition by marca, familia order by antiguedad rows between unbounded preceding and current row)
),
{% endfor %}

unidas as (
    select
        coalesce(f.marca, m.marca) as marca,
        coalesce(f.familia, m.familia) as familia,
        coalesce(f.antiguedad, m.antiguedad) as antiguedad,
        case when f.cadena_completa then f.proporcion end as proporcion_fiscal,
        case when m.cadena_completa then m.proporcion end as proporcion_mercado,
        coalesce(f.versiones, 0) as versiones_fiscal,
        coalesce(m.versiones, 0) as versiones_mercado,
        coalesce(f.cadena_completa, false) and coalesce(m.cadena_completa, false)
            and coalesce(f.versiones, 0) >= 3 and coalesce(m.versiones, 0) >= 3 as con_respaldo
    from fiscal_curva f
    full join mercado_curva m on m.marca = f.marca and m.familia = f.familia and m.antiguedad = f.antiguedad
)

select
    marca, familia, antiguedad,
    round(proporcion_fiscal, 3) as proporcion_fiscal,
    round(proporcion_mercado, 3) as proporcion_mercado,
    round(proporcion_fiscal - proporcion_mercado, 3) as diferencia,
    versiones_fiscal, versiones_mercado, con_respaldo
from unidas
