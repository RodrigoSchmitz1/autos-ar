{#
  Estaciones de servicio con coordenadas, tomadas de la Res. 314 (vigentes e
  historico): la 1104 no trae ubicacion, pero el numero de estacion es el mismo.

  Grano: una fila por estacion (la ubicacion mas reciente que informo).
  La ingesta ya descarto coordenadas fuera de Argentina y fechas futuras.
#}

select
    nro_inscripcion,
    trim(empresa) as empresa,
    trim(bandera) as bandera,
    trim(direccion) as direccion,
    trim(localidad) as localidad,
    {{ provincia_id('e.provincia') }} as provincia_id,
    latitud,
    longitud,
    ultima_informacion
from read_parquet('{{ var("raw") }}/combustible/estaciones.parquet') e
