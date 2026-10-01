{#
  Precio de mercado de la guia de la CCA, por marca, modelo, version y anio.

  Grano: periodo x marca x modelo x version x anio.
  El precio viene en miles de pesos (los usados de marcas de lujo, en millones:
  la ingesta ya los llevo a miles y `unidad_original` lo registra); aca se pasa a pesos.
  anio = 0 es el 0 km.
  Sin codigos: el cruce con DNRPA es por texto, a nivel modelo (int_versiones_cca).
#}

select
    periodo,
    trim(marca) as marca,
    trim(modelo) as modelo,
    trim(version) as version,
    anio,
    precio_miles * 1000 as precio,
    unidad_original
from read_parquet('{{ var("raw") }}/cca/*.parquet')
