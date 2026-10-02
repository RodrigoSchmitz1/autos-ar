{#
  Costo del service oficial por modelo, con la lista vigente de cada marca.

  Grano: marca x modelo de la fuente (Fiat "Toro Diesel" y "Toro" son filas
  distintas: el motor cambia el precio).

  La metrica comparable entre marcas es `costo_por_km`: la suma de todos los
  services del plan publicado dividida por los km que cubre. Hace falta porque
  las marcas no publican lo mismo:
    - Stellantis (Fiat, Jeep) cobra casi lo mismo en cada service;
    - VW, Toyota, Ford y Renault tienen un precio distinto en cada intervalo;
    - los intervalos tambien cambian (Fiat cada 10.000 km, Jeep cada 12.000).
  Comparar "el primer service" de una marca contra el de otra mezclaria cosas
  distintas; el costo por km del plan completo, no.

  Solo precio de lista. Los services con mano de obra bonificada (VW: 2do y
  3ro) ENTRAN al costo con su precio publicado, que es lo que se paga si se
  respetan los plazos; excluirlos sumaria menos services sobre los mismos km y
  subestimaria el costo. `services_bonificados` avisa cuantos hay.

  VW publica por grupo de modelos ("Polo / Tera / Virtus ..."): la ingesta
  abre cada grupo en una fila por modelo, con el mismo plan de precios.

  Todo en pesos: BYD publica en dolares y staging lo convierte con el tipo de
  cambio minorista del BCRA (`tipo_cambio`, `moneda_original`).
#}

with vigente as (
    select * from {{ ref('stg_service__precios') }}
    where es_vigente and tipo_precio = 'lista'
)

select
    v.marca,
    v.modelo_fuente,
    f.familia,
    f.metodo as familia_metodo,
    count(*) as services,
    min(v.km) as primer_service_km,
    max(v.km) as plan_hasta_km,
    round(median(v.precio)) as precio_mediano,
    min(v.precio) as precio_min,
    max(v.precio) as precio_max,
    round(sum(v.precio) / max(v.km), 2) as costo_por_km,
    count(*) filter (where v.mano_obra_bonificada) as services_bonificados,
    bool_or(v.precio_corregido) as tiene_precio_corregido,
    max(v.capturado) as capturado,
    max(v.vigencia_desde) as vigencia_desde,
    max(v.vigencia_hasta) as vigencia_hasta,
    -- Solo VW publica vigencia; el concesionario puede tardar en subir la
    -- lista nueva y la ultima captura queda vencida. Se muestra igual, avisando.
    coalesce(max(v.vigencia_hasta) < current_date, false) as lista_vencida,
    any_value(v.moneda) as moneda_original,
    -- Para las listas en dolares: el costo en pesos se mueve con el dolar.
    max(v.tipo_cambio) as tipo_cambio,
    max(v.tipo_cambio_fecha) as tipo_cambio_fecha,
    any_value(v.fuente_url) as fuente_url
from vigente v
left join {{ ref('int_service_familia') }} f using (marca, modelo_fuente)
group by all
