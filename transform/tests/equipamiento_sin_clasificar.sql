{{ config(severity = 'warn') }}
{#
  Items de las fichas de equipamiento que no estan en la clasificacion
  (seeds/equipamiento_clasificacion.csv): aparecen cuando una marca cambia su
  ficha. No frena nada (esos items no se comparan hasta clasificarlos); avisa
  que hay que correr python -m equipamiento.clasificar.
#}
select distinct i.marca, i.item
from {{ ref('stg_equipamiento__items') }} i
left join {{ ref('equipamiento_clasificacion') }} c on c.marca = i.marca and c.item = i.item
where c.item is null
