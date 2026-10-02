{#
  Tipo de cambio minorista del BCRA (promedio vendedor de los bancos), pesos
  por dolar, un valor por dia habil. Ver ingesta/cambio.py.

  Grano: fecha.
#}

select
    fecha,
    valor as pesos_por_dolar
from read_parquet('{{ var("raw") }}/cambio/usd_minorista.parquet')
