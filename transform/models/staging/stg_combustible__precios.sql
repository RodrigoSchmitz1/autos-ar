{#
  Precios y volumenes por estacion, producto, canal y mes (Res. 1104/2004).

  Por que la 1104 y no la 314 ("precios en surtidor"): la Res. 717/2025 derogo
  la obligacion de informar en tiempo real y desde julio de 2025 informa ~16% de
  las estaciones (YPF, el 2%). La 1104 la declaran ~4.500 estaciones por mes.
  Ver fase0/07_combustible.md.

  Grano: estacion x producto x canal x EXENTO x mes. Una estacion declara por
  separado lo que vende con impuestos y exento (la 1195 en enero 2018: Gas Oil a
  $26,77 y a $22,30). Sin `exentos` en la llave aparecian 958 "duplicados".

  Se descartan los renglones vacios (producto "N/D" y sin movimientos): son
  estaciones que declararon no haber vendido ese mes, y no aportan precio.

  Quedan unos pocos duplicados reales (misma llave, dos precios distintos, sin
  forma de saber cual vale). Se conservan marcados con `declaracion_duplicada`
  para que las comparaciones de precio los excluyan, en vez de borrarlos sin
  dejar rastro.

  El ultimo mes publicado llega INCOMPLETO (declaraciones tardias): se marca con
  `periodo_completo` para que nadie lo compare de igual a igual con los anteriores.
#}

with fuente as (
    select * from read_parquet('{{ var("raw") }}/combustible/precios_1104/*.parquet')
    where not (trim(producto) = 'N/D' and no_movimientos = 'SI')
),

ultimo as (
    select max(periodo) as periodo from fuente
)

select
    strptime(f.periodo, '%Y%m')::date as periodo,
    f.nro_inscripcion,
    trim(f.operador) as operador,
    trim(f.bandera) as bandera,
    trim(f.tipo_negocio) as tipo_negocio,
    trim(f.direccion) as direccion,
    trim(f.localidad) as localidad,
    {{ provincia_id('f.provincia') }} as provincia_id,
    trim(f.producto) as producto,
    trim(f.canal_de_comercializacion) as canal,
    f.precio_surtidor,
    f.precio_sin_impuestos,
    f.precio_con_impuestos,
    f.volumen,
    f.no_movimientos = 'SI' as sin_movimientos,
    f.exentos,
    f.impuesto_combustible_liquidos,
    f.impuesto_dioxido_carbono,
    f.tasa_vial,
    f.tasa_municipal,
    f.ingresos_brutos,
    f.iva,
    f.fondo_fiduciario_GNC as fondo_fiduciario_gnc,
    f.fecha_de_baja is not null and trim(f.fecha_de_baja) <> '' as dada_de_baja,
    f.periodo <> (select periodo from ultimo) as periodo_completo,
    count(*) over (
        partition by f.periodo, f.nro_inscripcion, f.producto, f.canal_de_comercializacion, f.exentos
    ) > 1 as declaracion_duplicada
from fuente f
