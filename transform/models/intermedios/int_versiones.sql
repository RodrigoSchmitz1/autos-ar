{#
  Catalogo de versiones: una fila por codigo DNRPA (origen, marca, tipo, modelo).

  Es la columna vertebral del catalogo canonico. El codigo es estable y es el
  mismo en los microdatos y en la tabla de valuacion fiscal; las descripciones
  no (el mismo codigo aparece escrito de varias formas en los usados), asi que
  de cada una se toma la mas frecuente.

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

ultimo as (select max(periodo) as periodo from tramites)

select
    origen_codigo,
    marca_codigo,
    tipo_codigo,
    modelo_codigo,
    mode(marca) as marca,
    mode(modelo) as modelo,
    mode(tipo) as tipo,
    case when regexp_matches(mode(tipo),
        '^(SEDAN|RURAL|PICK-UP|TODO TERRENO|FURGON|FURGONETA|COUPE|DESCAPOTABLE|CONVERTIBLE|UTILITARIO|ARENERO|MULTIPROPOSITO|MONOVOLUMEN|LIMUSINA)')
         then 'liviano' else 'pesado_u_otro' end as segmento,
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
