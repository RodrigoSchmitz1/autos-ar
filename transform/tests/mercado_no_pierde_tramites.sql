-- El mart de mercado tiene que contar TODOS los tramites de staging. Con un
-- JOIN comun contra el catalogo se perdian en silencio los que no tienen codigo
-- de modelo (2,4%; en agosto 2026, 49 inscripciones).
select
    (select count(*) from {{ ref('stg_dnrpa__tramites') }}) as en_staging,
    (select sum(unidades) from {{ ref('mart_mercado_mensual') }}) as en_mart
where (select count(*) from {{ ref('stg_dnrpa__tramites') }})
   <> (select sum(unidades) from {{ ref('mart_mercado_mensual') }})
