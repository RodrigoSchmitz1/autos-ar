{#
  Lleva el nombre de una provincia, como venga escrito, a su codigo INDEC.

  Cada fuente (y la misma fuente en distintos anios) escribe distinto:
  "Ciudad Autónoma de Bs.As.", "C.AUTONOMA DE BS.AS", "Ciudad Autónoma de
  Buenos Aires". Se normaliza (minusculas, sin tildes, sin espacios ni
  puntuacion) y se busca primero en las variantes conocidas y despues en el
  nombre oficial. Si no aparece queda nulo, y el test de staging lo detecta.

  Cuidado: es una subconsulta correlacionada. Si la columna de afuera se llamara
  igual que una de las tablas de provincias, SQL la resolveria contra la tabla
  de adentro y la condicion seria siempre verdadera. Paso con `provincia` en el
  modelo de estaciones: por eso las columnas de los seeds tienen nombres que no
  usa ninguna fuente (provincia_nombre, variante_clave) y conviene calificar
  la columna al llamar la macro.
#}
{% macro clave_texto(columna) -%}
    regexp_replace(lower(strip_accents({{ columna }})), '[^a-z]', '', 'g')
{%- endmacro %}

{% macro provincia_id(columna) -%}
    coalesce(
        (select _v.provincia_id from {{ ref('provincias_variantes') }} _v
         where _v.variante_clave = {{ clave_texto(columna) }}),
        (select _p.provincia_id from {{ ref('provincias') }} _p
         where {{ clave_texto('_p.provincia_nombre') }} = {{ clave_texto(columna) }})
    )
{%- endmacro %}
