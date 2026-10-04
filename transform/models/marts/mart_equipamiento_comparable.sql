{#
  Equipamiento comparable entre marcas: cada version de las fichas con las
  caracteristicas comunes (seeds/equipamiento_caracteristicas.csv), a partir
  de la clasificacion de sus items (seeds/equipamiento_clasificacion.csv:
  reglas, Gemini y correcciones a mano; ver equipamiento/clasificar.py).

  Grano: version de la ficha x caracteristica que la ficha menciona.

  - si_no: 'si' si algun item que la representa dice 'si' para esa version;
    'opcional' si solo como opcional; 'no' si todos dicen 'no'. Un dato de
    texto en la celda ("Disco ventilado", "4x4") cuenta como 'si', salvo la
    traccion 4x4, que se lee del texto.
  - numero (pulgadas de pantalla, tablero y llantas): el del nombre del item
    ("pantalla de 12''") para las versiones que lo tienen, o el de la celda
    ("7''" / "12''"). Si hay varios, el mayor.
  - Deducciones seguras: climatizador implica aire acondicionado; CarPlay
    inalambrico implica CarPlay; camara 360 implica camara trasera; crucero
    adaptativo implica crucero (la ficha marca "-" en la basica porque la
    version tiene la completa).
  Lo que la ficha no menciona no tiene fila: es "sin dato", no "no" (muchas
  fichas no listan lo obligatorio, como ISOFIX).
#}

with items as (
    select * from {{ ref('stg_equipamiento__items') }}
),

clasif as (
    select marca, item, caracteristica, try_cast(valor_item as double) as valor_item
    from {{ ref('equipamiento_clasificacion') }}
    where caracteristica is not null and caracteristica <> ''
),

catalogo as (
    select * from {{ ref('equipamiento_caracteristicas') }}
),

base as (
    select i.marca, i.familia, i.version_fuente, i.orden_version, c.caracteristica, k.tipo,
           i.valor, i.es_marca, c.valor_item,
           try_cast(replace(regexp_extract(i.valor, '(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:"|''|pulg)', 1), ',', '.') as double) as valor_celda
    from items i
    join clasif c on c.marca = i.marca and c.item = i.item
    join catalogo k on k.id = c.caracteristica
),

por_version as (
    select
        marca, familia, version_fuente, orden_version, caracteristica, tipo,
        case
            when caracteristica = 'traccion_4x4' then
                case when bool_or(valor = 'si' or regexp_matches(lower(valor), '4x4|4wd|awd')) then 'si'
                     when bool_or(valor = 'opcional') then 'opcional' else 'no' end
            when bool_or(valor = 'si' or (not es_marca and valor is not null)) then 'si'
            when bool_or(valor = 'opcional') then 'opcional'
            when bool_or(valor = 'no') then 'no'
        end as tiene,
        max(case when tipo = 'numero' and (valor = 'si' or not es_marca)
                 then coalesce(valor_celda, valor_item) end) as pulgadas
    from base
    group by marca, familia, version_fuente, orden_version, caracteristica, tipo
),

deducidas as (
    select marca, familia, version_fuente, orden_version, 'aire_acondicionado' as caracteristica, 'si_no' as tipo, tiene, null::double as pulgadas
    from por_version where caracteristica = 'climatizador_automatico' and tiene = 'si'
    union all
    select marca, familia, version_fuente, orden_version, 'carplay_android', 'si_no', tiene, null
    from por_version where caracteristica = 'carplay_inalambrico' and tiene = 'si'
    -- La version completa reemplaza a la basica en la ficha ("camara trasera: -" porque
    -- tiene la de 360): la de 360 incluye la trasera, el crucero adaptativo al comun.
    union all
    select marca, familia, version_fuente, orden_version, 'camara_trasera', 'si_no', tiene, null
    from por_version where caracteristica = 'camara_360' and tiene = 'si'
    union all
    select marca, familia, version_fuente, orden_version, 'crucero', 'si_no', tiene, null
    from por_version where caracteristica = 'crucero_adaptativo' and tiene = 'si'
),

todas as (
    select * from por_version
    union all
    -- La deduccion no pisa lo que la ficha dice explicitamente.
    select d.* from deducidas d
    where not exists (select 1 from por_version p
                      where (p.marca, p.familia, p.version_fuente, p.caracteristica)
                          = (d.marca, d.familia, d.version_fuente, d.caracteristica) and p.tiene = 'si')
)

select
    t.marca, t.familia, t.version_fuente, t.orden_version,
    t.caracteristica, k.nombre, k.grupo, k.orden as orden_caracteristica, t.tipo,
    -- Un numero de pulgadas implica que la caracteristica esta.
    case when t.pulgadas is not null then 'si' else t.tiene end as tiene,
    t.pulgadas
from todas t
join catalogo k on k.id = t.caracteristica
-- Celdas vacias para esa version (la ficha no la cubre): sin dato, sin fila.
where t.tiene is not null or t.pulgadas is not null
qualify row_number() over (partition by t.marca, t.familia, t.version_fuente, t.caracteristica
                           order by (t.tiene = 'si') desc) = 1
