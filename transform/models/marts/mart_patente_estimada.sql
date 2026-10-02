{#
  Patente anual ESTIMADA por provincia, version y anio modelo.

  Es una estimacion y se publica como tal. Cada provincia fija su impuesto en su
  ley impositiva anual y esos datos se curan a mano en dos seeds, con el
  articulo de ley de cada uno:
    patente_reglas   base oficial, coeficiente, tope, recargo, ajustes
    patente_escalas  tramos por categoria (auto / pick-up): cuota fija +
                     alicuota sobre el excedente, minimo anual, y una
                     valuacion minima opcional (Cordoba: los modelos 2009-2016
                     solo pagan si valen $19,4 M o mas)

  Por que estimada: la base oficial casi nunca es la valuacion de DNRPA (Buenos
  Aires y CABA usan ACARA, que no es publica). Se usa la valuacion fiscal de
  DNRPA, que se arma con precios de ACARA y CCA, como aproximacion;
  `base_usada` lo dice en cada fila. Tampoco incluye los ajustes durante el anio
  (IPC en Buenos Aires) ni topes sobre lo pagado el anio anterior (CABA): estan
  descriptos en `patente_reglas.ajustes`.

  Categoria: las pick-ups tienen escala propia en algunas jurisdicciones (CABA:
  2,3% fijo). Se toma de la carroceria de DNRPA.

  Orden del calculo: escala -> tope de tasa efectiva -> minimo -> recargo.

  Provincias donde la patente es municipal (Salta, Formosa, Chubut...): se usa
  la ordenanza de la ciudad con mas parque como aproximacion para toda la
  provincia; `precision` = 'aproximacion_municipal' y `ciudad_referencia` dice
  cual y cuanto pesa. Ver docs/patente_relevamiento.md.

  Provincias sin norma 2026 accesible (Entre Rios, San Juan, Jujuy): tasa de un
  estudio publicado (Ineco-UADE), con `precision` = 'fuente_secundaria'. En Entre
  Rios es una tasa efectiva promedio, no la escala de la ley.

  Grano: provincia x version x anio modelo. Solo livianos, solo provincias con
  reglas cargadas y solo los modelos que alcanza cada escala.
#}

with valuacion as (
    -- anio 0 de la tabla es el 0 km: el modelo del anio de la vigencia
    select v.*,
           case when v.anio = 0 then year(v.vigencia) else v.anio end as anio_modelo,
           case when d.tipo like 'PICK-UP%' then 'pickup' else 'auto' end as categoria
    from {{ ref('int_valuacion_version') }} v
    join {{ ref('dim_version') }} d using (origen_codigo, marca_codigo, tipo_codigo, modelo_codigo)
    where d.segmento = 'liviano'
),

escala as (
    select r.provincia_id, r.anio_fiscal, r.precision, r.ciudad_referencia, r.base_usada,
           r.tope_tasa_efectiva_pct, e.minimo_anual, coalesce(r.recargo_pct, 0) as recargo_pct,
           v.origen_codigo, v.marca_codigo, v.tipo_codigo, v.modelo_codigo, v.anio_modelo, v.categoria,
           v.valor_fiscal,
           v.valor_fiscal * r.coeficiente_base as base_imponible,
           e.cuota_fija + (v.valor_fiscal * r.coeficiente_base - e.base_desde) * e.alicuota_pct / 100 as segun_escala,
           e.alicuota_pct,
           e.fuente
    from valuacion v
    join {{ ref('patente_reglas') }} r on true
    join {{ ref('patente_escalas') }} e
      on e.provincia_id = r.provincia_id and e.anio_fiscal = r.anio_fiscal and e.categoria = v.categoria
     and v.anio_modelo between e.modelo_desde and e.modelo_hasta
     and (e.valuacion_minima is null or v.valor_fiscal >= e.valuacion_minima)
     and v.valor_fiscal * r.coeficiente_base > e.base_desde
     and (e.base_hasta is null or v.valor_fiscal * r.coeficiente_base <= e.base_hasta)
),

con_topes as (
    select *,
        greatest(
            case when tope_tasa_efectiva_pct is not null
                 then least(segun_escala, valor_fiscal * tope_tasa_efectiva_pct / 100)
                 else segun_escala end,
            coalesce(minimo_anual, 0)
        ) as antes_de_recargo
    from escala
)

select
    provincia_id, anio_fiscal,
    origen_codigo, marca_codigo, tipo_codigo, modelo_codigo, anio_modelo, categoria,
    valor_fiscal,
    round(base_imponible) as base_imponible,
    round(antes_de_recargo * (1 + recargo_pct / 100)) as patente_anual,
    alicuota_pct as alicuota_marginal_pct,
    round(segun_escala) <> round(antes_de_recargo) as aplico_tope_o_minimo,
    precision,
    ciudad_referencia,
    base_usada,
    fuente
from con_topes
