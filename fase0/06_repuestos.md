# Fase 0.6 - Repuestos

Relevamiento de una categoría completa de Repuestos Express (**Filtros**, 2026-10-01). Scripts: [scrapear_repuestos.py](scrapear_repuestos.py) y [medir_repuestos.py](medir_repuestos.py).

## Cómo se relevó
- Solo `/buscar`, que robots.txt permite. Un pedido cada 2,5 s, User-Agent identificable y caché en disco.
- Se usa el listado (48 productos por página) y no la ficha de cada producto: **52 pedidos en vez de 1.243**, con los mismos datos.
- Control de cambios de HTML: si una página trae 0 productos, el script falla.
- Resultado: **1.243 productos**, exactamente los que el sitio dice tener, sin precios ni títulos vacíos.

## Qué trae cada producto
- SKU, título, precio y precio de lista.
- Calidad: "Original", "Importado" o la marca del repuesto (Mahle, Bosch, ACDelco, Denso).
- Marca del auto: la trae el 81% de los productos.

## Pregunta 1: ¿se puede sacar el modelo del título?

Catálogo de modelos por marca = nombres de DNRPA (0 km y usados del mes) + modelos de la CCA. Se busca cada palabra del título en el catálogo de la marca del auto.

| Medida | % de productos |
|---|---|
| Menciona al menos un modelo reconocible | **88,1%** |
| Con marca y modelo | 76,7% |
| Compatible con varios modelos ("Polo/golf/caddy/passat") | 36,6% |
| Indica motor (1.6, 2.0) | 38,1% |
| Indica rango de años ("16/18", "13/") | 10,5% |

**Precisión:** en una muestra de 40 detecciones, las 40 tienen al menos un modelo correcto. Los errores son tokens sueltos, fáciles de filtrar ("II" de "Clio Ii", "VW").

**Lo que un diccionario no resuelve** (trabajo para la IA, como estaba previsto):
- Palabras pegadas: "1.4fiesta", "Vwpolo".
- Truncadas o abreviadas: "Hil" (Hilux), "meg" (Mégane), "sce" (Scénic).
- Genéricos: "Motor Audi", "Vw Varios".
- La lista completa de compatibilidades: detectar un modelo es fácil, detectar todos no.

**El año casi nunca está (10,5%).** La compatibilidad por año habrá que inferirla del motor y la generación ("Golf IV", "Clio II"), no leerla del título.

## Pregunta 2: ¿el SKU sirve para comparar original contra alternativo?

El SKU es **código base + sufijo del proveedor**: `O` = original, `H` = Mahle, `E`/`M`/`N`/`T` = importadores. A veces va con guion (`030115561K-H`) y a veces pegado (`1109Z10O`).

| Medida | % de productos |
|---|---|
| Comparte la base con otra calidad en la misma tienda | **27,0%** |
| ...y una de esas calidades es la original | **16,7%** |
| SKU con código propio del fabricante del repuesto (Bosch `0986…`), no del auto | ~12% |

Los grupos son la misma pieza. Ejemplos:

| Pieza | Original | Alternativo | Diferencia |
|---|---|---|---|
| Filtro de aire Polo 2015 | $151.550 | $15.370 (importado) | 9,9x |
| Filtro de aceite caja automática VW | $198.790 | $23.040 (importado) | 8,6x |
| Filtro de aceite Golf IV / Bora TDI | $107.440 | $12.090 (importado) | 8,9x |
| Filtro de aceite Scirocco / Polo 15-17 | $79.670 | $43.760 (Mahle) | 1,8x |

**Cuidado:** en algunos códigos la última letra es parte del código de fábrica (la "K" de `030115561K`). Cuando no hay guion, quitar una letra final puede unir dos piezas distintas. En esta muestra los grupos revisados eran correctos, pero en la Fase 5 conviene validarlo contra otra tienda.

## Trampas encontradas
- **La categoría mezcla el filtro con lo que lo sostiene.** La mediana es $27.100, pero 16 productos superan los $500.000 (el máximo es $1.860.980). No son errores de carga: son conjuntos, soportes y carcasas ("Conj Filtro Aire Orig Hil", "Filtro Aceite **Completo**", "**Soporte** Filtro", "**Tapa** Carcaza"). Para el costo de mantenimiento cuenta el elemento filtrante, que es lo que se cambia en el service. Hay que clasificar el tipo de pieza (elemento, conjunto o soporte) antes de comparar precios: es la trampa de "kits contra unidad" del plan.
- **El catálogo no es solo de autos:** el sitio tiene categorías como "Peces" o "Muebles para el Hogar" (ver [01_bigquery.md](01_bigquery.md)). Se filtra por categoría desde la ingesta.
- **Las imágenes vienen de Mercado Libre** (`http2.mlstatic.com`): la tienda probablemente publica el mismo catálogo allá. Puede servir para cruzar precios en el futuro.

## Veredicto
Con un diccionario alcanza para ubicar el modelo en ~88% de los productos, y el SKU da una llave de comparación directa en ~27%. La IA queda para lo que estaba previsto en el plan: extraer la compatibilidad completa del texto libre, validada contra el catálogo de modelos.
