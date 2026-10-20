{#
  Costo de mantenimiento por km de cada familia: service oficial y repuestos de
  desgaste. Lo usan el costo de los 0 km (mart_costo_componentes) y el de
  cualquier auto, nuevo o usado (mart_mantenimiento_version), para que los dos
  calculen igual.

    service    costo por km del plan oficial (mart_service); si la familia tiene
               varios motores, la mediana. Incluye filtros, aceite y bujias.
    repuestos  piezas de desgaste fuera del service (frenos, amortiguadores,
               distribucion, embrague) con los intervalos SUPUESTOS del seed
               costo_repuestos_intervalos y el precio mediano de la familia
               (mart_repuestos). Con repuesto alternativo (el que se usa en el
               total; si no hay, el original) y con original (si no hay, el
               alternativo). El embrague va aparte: solo cuenta en cajas manuales.
               Las piezas sin precio en la familia usan la mediana de esa pieza
               en todas; piezas_propias_* dice cuantas tienen precio propio.

  Grano: familia (cca_marca, familia) con service o repuestos. Las medianas
  generales para las familias sin dato se calculan en cada mart.
#}

with service as (
    select upper(marca) as marca, familia, median(costo_por_km) as service_por_km
    from {{ ref('mart_service') }}
    where familia is not null
    group by all
),

-- Precio de cada pieza de desgaste por familia; la que la familia no tiene usa la
-- mediana de esa pieza en todas (si no, el total quedaria corto: un modelo con
-- solo pastillas relevadas sumaria solo pastillas).
precios as (
    select upper(r.cca_marca) as marca, r.familia, r.tipo_pieza,
           coalesce(r.precio_mediano_alternativo, r.precio_mediano_original) as alternativo,
           coalesce(r.precio_mediano_original, r.precio_mediano_alternativo) as original
    from {{ ref('mart_repuestos') }} r
    join {{ ref('costo_repuestos_intervalos') }} i using (tipo_pieza)
),

mediana_pieza as (
    select tipo_pieza, median(alternativo) as alternativo, median(original) as original from precios group by all
),

familias_con_repuestos as (
    select distinct marca, familia from precios
),

repuestos as (
    select f.marca, f.familia,
           sum(coalesce(p.alternativo, m.alternativo) * i.unidades / i.intervalo_km) filter (where not i.solo_manual) as repuestos_sin_embrague,
           sum(coalesce(p.alternativo, m.alternativo) * i.unidades / i.intervalo_km) as repuestos_con_embrague,
           sum(coalesce(p.original, m.original) * i.unidades / i.intervalo_km) filter (where not i.solo_manual) as repuestos_original_sin_embrague,
           sum(coalesce(p.original, m.original) * i.unidades / i.intervalo_km) as repuestos_original_con_embrague,
           -- Cuantas piezas tienen precio propio de la familia (sin y con embrague).
           count(p.tipo_pieza) filter (where not i.solo_manual) as piezas_propias_sin_embrague,
           count(*) filter (where not i.solo_manual) as piezas_sin_embrague,
           count(p.tipo_pieza) as piezas_propias_con_embrague,
           count(*) as piezas_con_embrague
    from familias_con_repuestos f
    cross join {{ ref('costo_repuestos_intervalos') }} i
    join mediana_pieza m using (tipo_pieza)
    left join precios p on p.marca = f.marca and p.familia = f.familia and p.tipo_pieza = i.tipo_pieza
    group by all
)

select coalesce(s.marca, r.marca) as marca, coalesce(s.familia, r.familia) as familia,
       s.service_por_km,
       r.repuestos_sin_embrague, r.repuestos_con_embrague,
       r.repuestos_original_sin_embrague, r.repuestos_original_con_embrague,
       r.piezas_propias_sin_embrague, r.piezas_sin_embrague, r.piezas_propias_con_embrague, r.piezas_con_embrague
from service s
full join repuestos r on r.marca = s.marca and r.familia = s.familia
