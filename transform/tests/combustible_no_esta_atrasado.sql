-- Igual que con DNRPA: la Res. 1104 publica cada mes con ~30 dias de atraso.
select max(periodo) as ultimo_periodo
from {{ ref('stg_combustible__precios') }}
having max(periodo) < date_trunc('month', current_date) - interval 3 month
