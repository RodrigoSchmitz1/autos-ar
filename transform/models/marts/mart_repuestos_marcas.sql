{#
  Cuanto cuesta cada marca de repuesto contra el precio tipico de la misma
  pieza para el mismo modelo.

  Comparar precios de una marca a secas mezcla modelos: una marca que vende
  sobre todo para camionetas pareceria cara. Por eso cada producto se compara
  con la mediana de los alternativos de SU familia y tipo de pieza en SU
  tienda (indice 1 = el precio tipico), y la marca resume la mediana de esos
  cocientes. En la misma tienda, porque Repuestos Express es mas cara que ARG:
  una marca que solo vende ahi (Sachs, casi) pareceria cara por la tienda. Los
  productos sin marca (Importado en Repuestos Express, Alternativo en ARG) van
  juntos como 'Sin marca'; los originales, como referencia.

  Solo modelos y piezas con 3 alternativos (en la tienda) o mas (con uno o dos, el producto se
  compara casi contra si mismo), y marcas con 15 productos y 10 modelos o mas.

  Grano: tipo de pieza x marca.
#}

with p as (
    select distinct r.sku, r.tienda, r.tipo_pieza, r.precio, m.cca_marca, m.familia,
        case when r.calidad in ('Importado', 'Alternativo') then 'Sin marca' else r.calidad end as marca
    from {{ ref('stg_repuestos__productos') }} r
    join {{ ref('int_repuesto_modelos') }} m using (sku)
    where r.es_vigente and r.tipo_pieza <> 'otro'
),

tipico as (
    select tienda, cca_marca, familia, tipo_pieza, median(precio) filter (where marca <> 'Original') as precio_tipico
    from p
    group by all
    -- Con uno o dos productos, el producto se compara casi contra si mismo.
    having count(*) filter (where marca <> 'Original') >= 3
)

select
    p.tipo_pieza,
    p.marca,
    count(distinct p.sku) as productos,
    count(distinct p.cca_marca || p.familia) as familias,
    round(median(p.precio / t.precio_tipico), 2) as indice
from p
join tipico t using (tienda, cca_marca, familia, tipo_pieza)
where t.precio_tipico > 0
group by all
having count(distinct p.sku) >= 15 and count(distinct p.cca_marca || p.familia) >= 10
