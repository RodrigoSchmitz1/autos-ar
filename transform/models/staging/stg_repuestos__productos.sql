{#
  Repuestos de desgaste de dos tiendas, todas las fotos capturadas:
  Repuestos Express ('rex', ingesta/repuestos.py) y ARG Autopartes ('arg',
  ingesta/repuestos_arg.py). Ver fase0/06_repuestos.md.

  Grano: sku x fecha de captura (los SKU de ARG llevan el prefijo "ARG-").

  `tipo_pieza` sale del TITULO, no de la subcategoria del sitio: la
  subcategoria mezcla piezas ("Pastillas de Freno" trae pastillas de regular
  valvulas; en ARG, "Distribucion" trae lamparas) y conjuntos con su elemento
  (el filtro y su carcasa). Solo se clasifican las piezas que se cambian en el
  mantenimiento; soportes, carcasas, bulones, cables, bombas y tensores de
  accesorios quedan como 'otro'. Tambien van a 'otro' los combos que suman
  otra cosa: el filtro de aceite con el aceite, los discos con las pastillas,
  las campanas con las cintas, las pastillas de las 4 ruedas.

  En ARG la cantidad va al principio ("Kit X2 Amortiguadores", "Juego 4
  Bujias"): se quita para clasificar (`s`) y se usa para el precio por unidad.

  Precio por unidad (`precio`): discos, campanas, amortiguadores y bujias se
  venden sueltos o por juego. Se divide por la cantidad del titulo ("x2",
  "Kit 4", "X 2u", "(2)"); sin numero, "juego", "par" o el plural en ARG
  ("Discos De Freno Delanteros") cuentan como el par (4 en bujias), salvo que
  nombre un lado ("Amortiguadores Delantero Izquierdo" es uno solo). Las
  pastillas y los kits se cuentan por juego, como los intervalos de
  costo_repuestos_intervalos. El precio publicado queda en `precio_publicado`.

  Calidad: Repuestos Express la trae ('Original', 'Importado' o la marca). En
  ARG sale del titulo: "Original"/"Orig"/"Mopar" es original; si nombra una
  marca conocida, esa marca; si no, 'Alternativo'. La marca del auto, que ARG
  no publica aparte, es la primera marca nombrada en el titulo.

  `sku_base`: el SKU de Repuestos Express es codigo de la pieza + sufijo del
  proveedor ("-H" Mahle, "O" original, "-E"/"-M"/"-T" importadores). La base
  agrupa la misma pieza en distintas calidades: es la llave para comparar
  original contra alternativo. ARG no tiene ese codigo: su base es el SKU.
#}

with crudo as (
    select *, 'rex' as tienda
    from read_parquet('{{ var("raw") }}/repuestos/*.parquet', union_by_name = true)
    union all by name
    select *, 'arg' as tienda
    from read_parquet('{{ var("raw") }}/repuestos_arg/*.parquet', union_by_name = true)
),

fuente as (
    select *,
        lower(strip_accents(titulo)) as t,
        -- Titulo sin la cantidad del principio: "kit x2 amortiguadores ..." -> "amortiguadores ...".
        regexp_replace(lower(strip_accents(titulo)),
            '^((kits?|juego|jgo|par)( de)?( x)? ?(\(\d\)|\d+)? |x ?\d+ |\d+ )+', '') as s
    from crudo
),

nombrados as (
    select *,
        nullif(regexp_extract(t,
            '\b(bosch|skf|ina|litton|monroe|corven|mahle|fram|wega|valeo|luk|sachs|gates|dayco|ferodo|cofran|jurid|mann|lpr|cobreq|acdelco|wix|motrio|kyb|cofap|nakata|sadar|dolz|vmg|hutchinson|ngk|champion|beru|denso|trw|fremax|phc|kinetic|contitech|motorcraft|marelli|ans|wapsa|sigma)\b', 1), '') as marca_titulo,
        nullif(regexp_extract(t,
            '\b(volkswagen|volskwagen|vw|chevrolet|chev|gm|ford|fiat|renault|peugeot|citroen|toyota|nissan|honda|jeep|dodge|ram|hyundai|kia|suzuki|mitsubishi|audi|seat|mercedes|bmw)\b', 1), '') as auto_titulo
    from fuente
),

marcas as (
    select *,
        case when tienda = 'arg' then
            case
                when regexp_matches(t, '\b(original(es)?|orig|oem|mopar)\b') then 'Original'
                when regexp_matches(t, '\bfric ?rot\b') then 'Fric-Rot'
                when regexp_matches(t, '\bhipper\b') then 'Hipper Freios'
                when marca_titulo in ('skf', 'ina', 'lpr', 'vmg', 'phc', 'trw', 'ngk', 'kyb', 'ans', 'wix') then upper(marca_titulo)
                when marca_titulo is not null then upper(marca_titulo[1]) || marca_titulo[2:]
                else 'Alternativo'
            end
        else calidad end as calidad_final,
        case when tienda = 'arg' then
            case auto_titulo
                when 'volkswagen' then 'Volkswagen' when 'volskwagen' then 'Volkswagen' when 'vw' then 'Volkswagen'
                when 'chevrolet' then 'Chevrolet' when 'chev' then 'Chevrolet' when 'gm' then 'Chevrolet'
                when 'mercedes' then 'Mercedes Benz' when 'bmw' then 'BMW'
                else upper(auto_titulo[1]) || auto_titulo[2:]
            end
        else marca_auto end as marca_auto_final
    from nombrados
),

clasificados as (
    select *,
        case
            when regexp_matches(t, '\b(soporte|carcaza|carcasa|tapa|cano|conj|conjunto|base|bulon|tuerca|arandela|seguro|reparo|fijacion|baul|capot|porton|valija|parrilla|lampara|faro)\b') then 'otro'
            when regexp_matches(t, '^filtro.*\bcompleto\b') then 'otro'
            -- Combos con otra cosa (aceite, pastillas, cintas, 4 ruedas): no comparables.
            when regexp_matches(t, '\+ ?(\d+ ?l(ts?)? )?aceite|aceite (elf|total|shell|castrol|ypf|motul|ws)') then 'otro'
            when regexp_matches(t, 'discos? .*pastillas|pastillas .*discos?|cintas|zapatas|\b4 ruedas\b') then 'otro'
            when regexp_matches(t, '^kit lara aceite') then 'kit_service'
            when regexp_matches(t, '^(juego|kit|jgo)( lara)?( x)? ?\d* (de )?filtros?') then 'kit_filtros'
            when regexp_matches(t, '^filtro (de )?aire') then 'filtro_aire'
            when regexp_matches(t, '^filtro (de )?aceite') and not regexp_matches(t, '\bcaja\b') then 'filtro_aceite'
            when regexp_matches(t, '^filtro (de )?(habitaculo|polen|cabina)') then 'filtro_habitaculo'
            when regexp_matches(t, '^filtro (de )?(combustible|comb\b|nafta|gasoil|inyeccion)') then 'filtro_combustible'
            when regexp_matches(s, 'pastill?as? (de )?(freno|del|tras)|^(juego |jgo )?(de )?pastill?i?as')
                 and not regexp_matches(t, 'valvula|reg\.') then 'pastillas_freno'
            when regexp_matches(s, '^(juego |jgo )?(de )?discos? (de )?freno') then 'disco_freno'
            when regexp_matches(s, '^campanas?\b') then 'campana_freno'
            when regexp_matches(s, '^bujias? ') and regexp_matches(t, 'incandesc|incandec|precalent') then 'bujia_precalentamiento'
            when regexp_matches(s, '^bujias? ') then 'bujia_encendido'
            when regexp_matches(t, '^kit (de )?(correa )?distrib') and not regexp_matches(t, 'poly|poli') then 'kit_distribucion'
            when regexp_matches(t, '^correa (de )?distrib') then 'correa_distribucion'
            when subcategoria = 'Distribución' and regexp_matches(t, '^(tensor|ruleman tensor|polea tensor)') then 'tensor_distribucion'
            when regexp_matches(t, '^correa (de )?(\d*\s?-?pk|poly|poli|av|alternador|sk\b|v\b|accesorios)') then 'correa_accesorios'
            -- "Kit X4 Amortiguadores Delanteros Y Traseros": el juego completo.
            when regexp_matches(s, '^amortiguador') and regexp_matches(t, '\b(del|delant|delanteros?|adelante)\b')
                 and regexp_matches(t, '\b(tras|traseros?|tra)\b') then 'amortiguador'
            when regexp_matches(s, '^amortiguador') and regexp_matches(t, '\b(del|delant|delanteros?|adelante)\b') then 'amortiguador_delantero'
            when regexp_matches(s, '^amortiguador') and regexp_matches(t, '\b(tras|traseros?|tra)\b') then 'amortiguador_trasero'
            when regexp_matches(s, '^amortiguador') then 'amortiguador'
            when regexp_matches(t, '^kit (de )?(placa|embrague)|^embrague ') then 'kit_embrague'
            else 'otro'
        end as tipo_pieza,
        -- Cantidad del titulo: "x2", "x 4u", "kit 2", "juego 4", "(2)", "4 bujias".
        try_cast(coalesce(
            nullif(regexp_extract(t, '\bx ?(\d)u?\b', 1), ''),
            nullif(regexp_extract(t, '^(kit|juego|jgo)( de)? ?\(?(\d)\)? ', 3), ''),
            nullif(regexp_extract(t, '^(\d) ', 1), ''),
            nullif(regexp_extract(t, '\((\d)\)', 1), '')) as integer) as cantidad_titulo
    from marcas
),

con_unidades as (
    select *,
        case when tipo_pieza not in ('disco_freno', 'campana_freno', 'amortiguador_delantero', 'amortiguador_trasero',
                                     'amortiguador', 'bujia_encendido', 'bujia_precalentamiento') then 1
             when cantidad_titulo between 1 and 8 then cantidad_titulo
             -- "Amortiguadores Delantero Izquierdo": un lado solo, aunque diga plural.
             when regexp_matches(t, '\b(izquierdo|derecho|izq|der)\b') then 1
             when regexp_matches(t, '^(juego|jgo|par|kit)\b')
                  or (tienda = 'arg' and regexp_matches(s, '^(discos|campanas|amortiguadores|bujias)\b'))
                then case when tipo_pieza like 'bujia%' then 4 else 2 end
             else 1 end as unidades
    from clasificados
)

select
    sku,
    tienda,
    case when tienda = 'arg' then sku
         when sku like '%-%' then split_part(sku, '-', 1)
         when regexp_matches(sku, '[0-9][OHEMNKTPCA]$') then left(sku, length(sku) - 1)
         else sku end as sku_base,
    titulo,
    calidad_final as calidad,
    calidad_final = 'Original' as es_original,
    case when calidad_final not in ('Original', 'Importado', 'Alternativo') then calidad_final end as marca_repuesto,
    marca_auto_final as marca_auto,
    categoria,
    subcategoria,
    tipo_pieza,
    unidades,
    round(precio / unidades) as precio,
    precio as precio_publicado,
    precio_lista,
    url,
    capturado,
    capturado = max(capturado) over (partition by tienda) as es_vigente
from con_unidades
