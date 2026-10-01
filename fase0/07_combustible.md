# Fase 0.7 - Combustible

Script: [perfilar_combustible.py](perfilar_combustible.py). Archivos (en `datos/combustible/`, fuera de git):

- Precios vigentes en surtidor (Res. 314/2016): `precios-en-surtidor-resolucin-3142016.csv`, 9 MiB
- Precios históricos (Res. 314/2016): `precios-historicos.csv`, 741 MiB
- Precios y volúmenes EESS (Res. 1104/2004), desde diciembre 2024: `precios-eess-2025-.csv`, 122 MiB

Los tres se descubren con `package_show` en datos.energia.gob.ar (datasets `precios-en-surtidor` y `precios-eess-resolucion-1104-04`).

## El hallazgo: la fuente prevista dejó de ser obligatoria

La **Resolución 717 del 2 de junio de 2025 derogó la 314/2016**, que obligaba a cada estación a informar sus cambios de precio dentro de las 8 horas. Desde ese mes informar es voluntario, y los datos lo muestran:

| Mes (histórico 314) | Estaciones que informan | YPF |
|---|---|---|
| 2025-05 | 3.590 | 1.644 |
| 2025-06 | 3.458 | 1.550 |
| 2025-07 | 1.752 | **245** |
| 2025-11 | 1.220 | **44** |

Un juzgado federal de La Plata declaró inconstitucional la derogación, pero en los datos no se ve que las estaciones hayan vuelto a informar.

**"Vigentes" no quiere decir vigentes.** El archivo de precios vigentes tiene 4.611 estaciones:
- solo **758 (16%)** informaron en septiembre de 2026;
- el **70%** no actualiza desde antes de 2026;
- la más vieja tiene un precio de junio de 2016;
- de YPF informan **38 de 1.560 (2%)**.

Por eso aparecen mínimos como Gas Oil a $13,71 o GNC a $7. Con todas las estaciones, la mediana del Gas Oil Grado 2 da **$1.342**; con las que informaron en septiembre, **$2.421**. Los precios congelados la bajan un 45%.

## La fuente que sirve: Resolución 1104/2004

La 1104 no fue derogada. Cada estación declara **todos los meses** precio de surtidor, **volumen vendido** y el desglose de impuestos (combustibles, CO2, ingresos brutos, tasa vial, tasa municipal, IVA).

| Período | Estaciones | YPF | Mediana súper |
|---|---|---|---|
| 2025-06 | 4.743 | 1.637 | $1.299 |
| 2026-07 | 4.528 | 1.600 | $2.139 |
| 2026-08 | 4.368 | 1.564 | $2.143 |

- **Cobertura:** casi todas las estaciones, YPF incluida.
- **Atraso:** un mes. Agosto se publicó el 30 de septiembre.
- **El último mes está incompleto:** 4.368 estaciones en agosto, contra ~4.530 en julio. Son declaraciones que llegan tarde, la misma trampa que en SEPA: el último período no se compara con los anteriores sin ajustar.
- **Coordenadas:** el 91% de las estaciones de la 1104 (4.106 de 4.528) cruza con las de la 314 por número de estación. Para el resto hay un shapefile en el mismo dataset.
- **Pendiente:** la documentación no aclara si `precio_surtidor` es el promedio del mes o el precio al cierre. Hay que averiguarlo antes de compararlo con otras fuentes.

## Histórico 314 (2017-2025)
- 3.375.005 filas y 5.705 estaciones. Unas 4.400 informan por año hasta 2024.
- **Frecuencia real de cambio de precio:** mediana de **12 cambios por año** en la súper (p10: 9, p90: 18), o sea más o menos mensual. Que el precio se informe hasta 8 horas después pesa poco; un dato mensual alcanza para comparar.
- **Fechas imposibles:** 293 anteriores a 2016 (incluye `01/01/0001`) y 148 futuras (años 2044, 3201, 9920). Se descartan en la ingesta.
- **Espacio:** 741 MiB de CSV → **15 MiB de Parquet**.

## Coordenadas
4.609 de 4.611 estaciones tienen coordenadas dentro de Argentina. No hay ceros ni latitudes y longitudes invertidas.

## Impacto en el producto

| Cara del producto | Antes | Ahora |
|---|---|---|
| "La estación más barata cerca" en tiempo real | Res. 314 | **No es posible para todas las estaciones.** Solo el ~16% que todavía informa voluntariamente |
| Estación más barata **del mes**, comparación entre banderas, evolución | Res. 314 | **Res. 1104**, mensual, con YPF |
| Costo de combustible para el costo total por km | Res. 314 | **Res. 1104**: alcanza, porque el precio cambia ~1 vez por mes |
| Nuevo: cuánto del precio son impuestos | — | La 1104 trae el desglose |

También es una historia en sí misma, del estilo "decisiones que importan" de SEPA: **desde junio de 2025 no hay datos públicos de precios de combustible en tiempo real**, y se puede mostrar con los datos.
