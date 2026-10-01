{#
  Consumo homologado (etiqueta de eficiencia vehicular), copia de junio 2022.

  Grano: un ensayo. Un mismo modelo puede tener varios (motor, transmision).
  Consumo en litros cada 100 km; CO2 en g/km. Son valores de LABORATORIO, no de
  uso real: sirven para comparar modelos entre si, no para predecir el gasto.
#}

select
    trim(vehiculo_marca) as marca,
    trim(vehiculo_modelo) as modelo,
    trim(vehiculo_tipo) as tipo,
    trim(vehiculo_id_motor) as motor,
    try_cast(vehiculo_cilindrada as integer) as cilindrada_cc,
    trim(vehiculo_tipo_transmision) as transmision,
    trim(vehiculo_tipo_combustible) as combustible,
    try_strptime(fecha_firma, '%d/%m/%Y')::date as fecha_firma,
    try_cast(replace(emision_CO2, ',', '.') as double) as co2_g_km,
    try_cast(replace(consumo_urbano, ',', '.') as double) as consumo_urbano,
    try_cast(replace(consumo_extraurbano, ',', '.') as double) as consumo_extraurbano,
    try_cast(replace(consumo_mixto, ',', '.') as double) as consumo_mixto
from read_parquet('{{ var("raw") }}/consumo/*.parquet')
