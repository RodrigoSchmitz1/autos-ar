-- Falla si el ultimo mes de DNRPA tiene mas de 3 meses. DNRPA publica cada mes
-- con ~40 dias de atraso (agosto 2026 salio el 11 de septiembre), asi que el 1
-- de octubre lo esperable es tener agosto. Se compara contra CURRENT_DATE y no
-- contra otra tabla: un pipeline que se mide contra si mismo no ve su atraso.
select max(periodo) as ultimo_periodo
from {{ ref('stg_dnrpa__tramites') }}
having max(periodo) < date_trunc('month', current_date) - interval 3 month
