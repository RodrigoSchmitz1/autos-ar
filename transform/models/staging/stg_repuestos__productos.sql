{#
  Repuestos de desgaste de Repuestos Express, todas las fotos capturadas.
  Ver ingesta/repuestos.py y fase0/06_repuestos.md.

  Grano: sku x fecha de captura.

  `tipo_pieza` sale del TITULO, no de la subcategoria del sitio: la
  subcategoria mezcla piezas ("Pastillas de Freno" trae pastillas de regular
  valvulas) y conjuntos con su elemento (el filtro y su carcasa). Solo se
  clasifican las piezas que se cambian en el mantenimiento; soportes,
  carcasas, bulones, cables, bombas y tensores de accesorios quedan como
  'otro'. Los conjuntos ("Conj Filtro Aire", "Filtro Aceite Completo") van a
  'otro' porque cuestan 10 a 50 veces el elemento que se cambia.

  `sku_base`: el SKU es codigo de la pieza + sufijo del proveedor ("-H" Mahle,
  "O" original, "-E"/"-M"/"-T" importadores). La base agrupa la misma pieza en
  distintas calidades: es la llave para comparar original contra alternativo.
#}

with fuente as (
    select *, lower(strip_accents(titulo)) as t
    from read_parquet('{{ var("raw") }}/repuestos/*.parquet', union_by_name = true)
)

select
    sku,
    case when sku like '%-%' then split_part(sku, '-', 1)
         when regexp_matches(sku, '[0-9][OHEMNKTPCA]$') then left(sku, length(sku) - 1)
         else sku end as sku_base,
    titulo,
    calidad,
    calidad = 'Original' as es_original,
    case when calidad not in ('Original', 'Importado') then calidad end as marca_repuesto,
    marca_auto,
    categoria,
    subcategoria,
    case
        when regexp_matches(t, '\b(soporte|carcaza|carcasa|tapa|cano|conj|conjunto|completo|base|bulon|tuerca|arandela|seguro|reparo|fijacion)\b') then 'otro'
        when regexp_matches(t, '^kit lara aceite') then 'kit_service'
        when regexp_matches(t, '^(juego|kit|jgo)( lara)? (de )?filtros?') then 'kit_filtros'
        when regexp_matches(t, '^filtro (de )?aire') then 'filtro_aire'
        when regexp_matches(t, '^filtro (de )?aceite') and not regexp_matches(t, '\bcaja\b') then 'filtro_aceite'
        when regexp_matches(t, '^filtro (de )?(habitaculo|polen|cabina)') then 'filtro_habitaculo'
        when regexp_matches(t, '^filtro (de )?(combustible|comb\b|nafta|gasoil|inyeccion)') then 'filtro_combustible'
        when regexp_matches(t, 'pastill?as? (de )?(freno|del|tras)|^(juego|jgo) (de )?pastill?i?as')
             and not regexp_matches(t, 'valvula|reg\.') then 'pastillas_freno'
        when regexp_matches(t, '^(juego |jgo )?(de )?discos? (de )?freno') then 'disco_freno'
        when regexp_matches(t, '^campana') then 'campana_freno'
        when regexp_matches(t, '^bujias? ') and regexp_matches(t, 'incandesc|incandec|precalent') then 'bujia_precalentamiento'
        when regexp_matches(t, '^bujias? ') then 'bujia_encendido'
        when regexp_matches(t, '^kit (de )?distrib') then 'kit_distribucion'
        when regexp_matches(t, '^correa (de )?distrib') then 'correa_distribucion'
        when subcategoria = 'Distribución' and regexp_matches(t, '^(tensor|ruleman tensor|polea tensor)') then 'tensor_distribucion'
        when regexp_matches(t, '^correa (de )?(\d*\s?-?pk|poly|poli|av|alternador|sk\b|v\b|accesorios)') then 'correa_accesorios'
        when regexp_matches(t, '^amortiguador') and regexp_matches(t, '\b(del|delant|delantero)\b') then 'amortiguador_delantero'
        when regexp_matches(t, '^amortiguador') and regexp_matches(t, '\b(tras|trasero|tra)\b') then 'amortiguador_trasero'
        when regexp_matches(t, '^amortiguador') then 'amortiguador'
        when regexp_matches(t, '^kit (de )?(placa|embrague)') then 'kit_embrague'
        else 'otro'
    end as tipo_pieza,
    precio,
    precio_lista,
    capturado,
    capturado = max(capturado) over () as es_vigente
from fuente
