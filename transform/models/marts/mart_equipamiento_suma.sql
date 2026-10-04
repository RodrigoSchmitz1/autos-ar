{#
  Que suma cada version sobre la anterior de su familia: la "escalera" de
  equipamiento, de la version de entrada a la mas equipada.

  Grano: familia x version x item que cambia respecto de la version anterior.
  La version de entrada no tiene filas (no hay anterior).

  `cambio`:
    'agrega'  el item pasa de 'no' (u 'opcional') a 'si'
    'mejora'  el dato cambia de texto ("16''" -> "17''", "8''" -> "10,1''")
    'quita'   pasa de 'si' a 'no': pasa en fichas donde la version siguiente
              no es "la anterior + algo" (otro motor, otra carroceria)
  Las versiones se ordenan como en la ficha; algunas marcas no van de menor a
  mayor estrictamente, por eso existe 'quita'.
#}

with items as (
    select * from {{ ref('stg_equipamiento__items') }}
),

pares as (
    select
        a.marca, a.familia, a.seccion, a.item,
        a.version_fuente, a.orden_version,
        b.version_fuente as version_anterior,
        a.valor, b.valor as valor_anterior
    from items a
    join items b
      on b.marca = a.marca and b.familia = a.familia and b.item = a.item
     and b.orden_version = a.orden_version - 1
)

select
    marca, familia, version_fuente, orden_version, version_anterior, seccion, item,
    valor_anterior, valor,
    case when valor = 'si' and valor_anterior in ('no', 'opcional') then 'agrega'
         when valor in ('no', 'opcional') and valor_anterior = 'si' then 'quita'
         else 'mejora' end as cambio
from pares
where valor is distinct from valor_anterior
  and valor is not null and valor_anterior is not null
  -- Un dato que pasa a 'no' o de 'opcional' a 'no' no es algo que la version suma.
  and not (valor = 'no' and valor_anterior = 'opcional')
