{#
  Valor fiscal por version (codigo DNRPA) y anio, de cada tabla de valuacion.

  Grano: vigencia x origen x marca x tipo x modelo x anio.
  anio = 0 es el 0 km (asi viene la columna "0Km" del PDF).

  La llave (origen, marca, tipo, modelo) es la MISMA de los microdatos de DNRPA:
  el cruce es exacto, sin texto ni IA (ver fase0/05_matching.md).
#}

select
    vigencia,
    origen as origen_codigo,
    marca as marca_codigo,
    tipo as tipo_codigo,
    modelo as modelo_codigo,
    fab as fabricante_codigo,
    trim(descripcion) as descripcion,
    anio,
    valor
from read_parquet('{{ var("raw") }}/valuacion/*.parquet')
