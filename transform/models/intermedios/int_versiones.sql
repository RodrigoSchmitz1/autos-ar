{#
  Catalogo de versiones: una fila por codigo DNRPA (origen, marca, tipo, modelo).

  Es la columna vertebral del catalogo canonico. El codigo es estable y es el
  mismo en los microdatos y en la tabla de valuacion fiscal; las descripciones
  no (el mismo codigo aparece escrito de varias formas en los usados), asi que
  de cada una se toma la mas frecuente.

  "La mas frecuente" con desempate fijo (orden alfabetico): `mode()` elige
  cualquiera de las empatadas y cambiaba entre corridas, y con ella el cruce
  con la CCA de ~160 codigos (ej.: un codigo con "GOL" y "GOLF" empatados).

  `segmento` separa livianos (autos, pick-ups, SUV, furgones) de pesados y
  remolques, por la carroceria. Las guias de precios cubren solo livianos: la
  cobertura de los cruces se mide sobre ellos (cobertura_mapeos).

  Solo entran versiones con al menos un tramite desde 2018: es el parque que
  importa para el producto. La tabla de valuacion tiene ~18 mil codigos,
  muchos de motos, camiones o autos que nadie transfiere.
#}

with tramites as (
    select
        case when origen = 'nacional' then 'N' else 'I' end as origen_codigo,
        *
    from {{ ref('stg_dnrpa__tramites') }}
    where marca_codigo is not null and tipo_codigo is not null and modelo_codigo is not null
),

ultimo as (select max(periodo) as periodo from tramites),

{% set clave = "origen_codigo, marca_codigo, tipo_codigo, modelo_codigo" %}
{% for col in ["marca", "modelo", "tipo"] %}
{{ col }}_frecuente as (
    select {{ clave }}, first({{ col }} order by n desc, {{ col }}) as {{ col }}
    from (select {{ clave }}, {{ col }}, count(*) as n from tramites where {{ col }} is not null group by all)
    group by all
),
{% endfor %}

agregado as (

select
    origen_codigo,
    marca_codigo,
    tipo_codigo,
    modelo_codigo,
    count(distinct modelo) as descripciones_distintas,
    min(anio_modelo) as anio_modelo_min,
    max(anio_modelo) as anio_modelo_max,
    count(*) as tramites,
    count(*) filter (where tramite = 'inscripcion') as inscripciones,
    count(*) filter (where periodo > (select periodo from ultimo) - interval 12 month) as tramites_12m,
    count(*) filter (where tramite = 'inscripcion'
                     and periodo > (select periodo from ultimo) - interval 12 month) as inscripciones_12m,
    max(tramite_fecha) as ultimo_tramite
from tramites
group by 1, 2, 3, 4
)

select
    a.origen_codigo,
    a.marca_codigo,
    a.tipo_codigo,
    a.modelo_codigo,
    ma.marca,
    mo.modelo,
    ti.tipo,
    case when regexp_matches(ti.tipo,
        '^(SEDAN|RURAL|PICK-UP|TODO TERRENO|FURGON|FURGONETA|COUPE|DESCAPOTABLE|CONVERTIBLE|UTILITARIO|ARENERO|MULTIPROPOSITO|MONOVOLUMEN|LIMUSINA)')
         then 'liviano' else 'pesado_u_otro' end as segmento,
    a.* exclude (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
from agregado a
left join marca_frecuente ma using ({{ clave }})
left join modelo_frecuente mo using ({{ clave }})
left join tipo_frecuente ti using ({{ clave }})
