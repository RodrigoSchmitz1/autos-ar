# Fase 0.1 - BigQuery: ¿se comparte el free tier con SEPA?

Medido el 2026-10-01 con `INFORMATION_SCHEMA.JOBS_BY_PROJECT` (región US) y `__TABLES__` sobre `proyecto-precios-504221`. Costo de la medición: <100 MiB.

## Respuesta: sí, se comparte

- La página de precios de BigQuery indica los tramos gratuitos "per 1 month / account": se cuentan por **cuenta de facturación**, no por proyecto. El free tier de la Storage Read API lo dice explícito ("300 TiB per month for each billing account").
- SEPA es el único proyecto en su cuenta de facturación.
- Un proyecto nuevo en esa misma cuenta comparte con SEPA 1 TiB de consultas y 10 GiB de almacenamiento.

## Consumo real de SEPA

Consultas (GiB facturados, mes según horario de Los Ángeles, sin contar dos veces los scripts):

| Mes | Jobs | GiB |
|---|---|---|
| 2026-08 | 910 | 219,1 |
| 2026-09 | 5.857 | **896,2** de 1.024 |

- Régimen (25 al 30 de septiembre, sin backfills): ~14 GiB/día, o sea ~430 GiB/mes.
- Días de desarrollo o backfill: 19 a 34 GiB/día.
- El documento de contexto decía ~340 GiB/mes. El número real es más alto.

Almacenamiento (lógico, al 2026-10-01): **15,3 GiB** de 10 gratis.

- `sepa.productos`: 11,0 GiB, 8 particiones.
- `dbt_precios.stg_productos`: 3,6 GiB, 5 particiones.
- La expiración de particiones de las dos tablas está en 8 días, no en 3. No es un error: `ingesta_backfill.py` abre la retención mientras haya fechas que todavía no llegaron a los históricos (el 26, el 27 y el 30 de septiembre, cargadas el 01-10 después de que corriera dbt) y la vuelve a 3 sola cuando dbt las captura.
- El almacenamiento se cobra prorrateado por MiB y por segundo. Lo que importa es el promedio del mes contra 10 GiB, no el pico de un día.

## Conclusión

Compartir con SEPA no es viable: en septiembre quedaron ~128 GiB de margen en consultas, y el almacenamiento ya está por encima del límite gratis.

## Volumen publicado por las fuentes (medido 2026-10-01)

Tamaño de cada archivo, sin descargarlo (pedido de 1 byte con Range):

| Dataset | Publicado | Estimado sin comprimir |
|---|---|---|
| Transferencias 2018-2026 | 497 MiB en ZIP | ~3,4 GiB de CSV (un mes = 34 MiB) |
| Inscripciones iniciales | 97 MiB en ZIP | ~0,7 GiB |
| Prendas | 76 MiB en ZIP | ~0,5 GiB |
| Robos y recuperos | 13 MiB en ZIP | ~0,1 GiB |
| Combustible histórico | 741 MiB de CSV | 0,7 GiB |
| **Total** | **1,4 GiB** | **~5,5 GiB de CSV** |

La relación de compresión (~7x) sale de comparar el ZIP 2026 (8 meses, 38 MiB) con el CSV de un mes (34 MiB). Se confirma en la Fase 0.4 contando filas reales. En Parquet, sin las columnas de titulares, el total debería quedar por debajo de 1 GiB.

### Repuestos (scraping), medido 2026-10-01

- **Repuestos Express:** 37.441 productos según su sitemap, 48 por página de listado, con el precio en el HTML. Un relevamiento completo son ~780 páginas, ~33 min a 1 pedido cada 2,5 s. Solo una parte del catálogo es de autos: tiene categorías como "Peces" o "Muebles para el Hogar". Tiene también una categoría "Servicio Programado", a revisar para la Fase 4.
- **Original Repuestos:** 6.484 URLs en el sitemap. **Casa de Repuesto:** ~2.800.
- **Toyodaih y Chevcar:** sin robots.txt ni sitemap en el dominio probado. Sin medir.

Universo estimado con margen: ~80 mil productos entre todas las tiendas.

| Escenario | Filas por año | Parquet por año (estimado) |
|---|---|---|
| Foto semanal de todo | ~4 M | ~0,1-0,2 GiB |
| Foto diaria de todo (peor caso) | ~29 M | ~0,5-1,5 GiB |
| Solo cambios de precio (diseño probable) | mucho menos | decenas de MiB |

Aun en el peor caso, todo el proyecto queda en pocos GiB por año, un volumen que DuckDB maneja sin problema en una notebook. Lo que hay que resolver es dónde vive el histórico crudo, si hace falta publicarlo: el sitio solo necesita los agregados.

Alternativas:

1. **Segunda cuenta de facturación**: free tier propio y el mismo stack que SEPA.
2. **BigQuery Sandbox** (sin cuenta de facturación): las tablas vencen a los 60 días y no admite DML. No sirve para series históricas.
3. **DuckDB + Parquet** (local o en GitHub, MotherDuck como opción): sin cuotas ni tarjeta. Viable si el volumen es chico.
