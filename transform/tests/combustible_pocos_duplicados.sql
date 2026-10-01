-- Los duplicados reales (misma estacion, producto, canal, exento y mes con dos
-- precios distintos) se conservan marcados. Eran 22 filas al armar el modelo;
-- si pasan de 500, algo cambio en como se declara y hay que mirarlo.
select count(*) as filas_duplicadas
from {{ ref('stg_combustible__precios') }}
where declaracion_duplicada
having count(*) > 500
