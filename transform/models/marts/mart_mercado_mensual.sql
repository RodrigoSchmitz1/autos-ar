{#
  Mercado automotor por mes: cuantos autos se patentan, transfieren, prendan y
  roban, por provincia, marca y modelo.

  Grano: periodo x provincia x tramite x segmento x marca x familia x origen.

  `familia` es el modelo comercial ("TERRITORY", no "TERRITORY TREND 1.5..."):
  el de la guia CCA cuando la version cruza; si no (autos viejos que la guia ya
  no lista), la primera palabra de la descripcion de DNRPA, y `familia_fuente`
  lo dice. Se cuentan TRAMITES: una fila de DNRPA es un auto (fase0/04_volumen.md).

  Los tramites sin codigo de modelo (~2,4%, casi todos usados viejos) no estan
  en el catalogo: entran igual, con segmento y familia 'sin_codigo'. Con un
  JOIN comun se perdian en silencio (en agosto 2026 faltaban 49 inscripciones).

  La antiguedad es la del auto al momento del tramite. Se descartan anios modelo
  imposibles: anteriores a 1950 o posteriores al anio del tramite + 1 (un 0 km
  puede venderse como modelo del anio siguiente).
#}

select
    t.periodo,
    t.provincia_id,
    t.tramite,
    coalesce(d.segmento, 'sin_codigo') as segmento,
    coalesce(d.marca, t.marca) as marca,
    case when d.marca is null then 'sin_codigo'
         else coalesce(d.cca_modelo, split_part(d.modelo, ' ', 1)) end as familia,
    case when d.marca is null then 'sin_codigo'
         when d.cca_modelo is not null then 'cca' else 'dnrpa_primera_palabra' end as familia_fuente,
    t.origen,
    count(*) as unidades,
    count(*) filter (where t.titular_tipo_persona = 'juridica') as unidades_empresas,
    round(avg(year(t.periodo) - t.anio_modelo) filter (
        where t.anio_modelo between 1950 and year(t.periodo) + 1), 2) as antiguedad_promedio
from {{ ref('stg_dnrpa__tramites') }} t
left join {{ ref('dim_version') }} d
    on d.origen_codigo = case when t.origen = 'nacional' then 'N' else 'I' end
   and d.marca_codigo = t.marca_codigo and d.tipo_codigo = t.tipo_codigo and d.modelo_codigo = t.modelo_codigo
group by all
