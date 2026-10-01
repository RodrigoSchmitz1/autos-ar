-- Piso de cobertura de cada cruce, sobre los 0 km LIVIANOS del ultimo anio.
-- Si una fuente cambia como escribe las marcas o el formato del PDF, el cruce
-- cae sin que nada mas falle: este test lo frena. Pisos ~10 puntos debajo de
-- lo medido al construir el catalogo (valuacion 97,9%, CCA 98,5%).
select fuente, pct_inscripciones_12m
from {{ ref('cobertura_mapeos') }}
where (fuente = 'valuacion' and pct_inscripciones_12m < 88)
   or (fuente = 'cca' and pct_inscripciones_12m < 88)
