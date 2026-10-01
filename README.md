# autos-ar

Cuánto vale, cuánto cuesta tener y qué conviene comprar: autos en Argentina con datos públicos.

**Estado: Fase 0 (factibilidad) completa.** Antes de diseñar pipelines se mide cada fuente: si se puede acceder, cuánto pesa y si los modelos se pueden cruzar entre fuentes.

| Paso | Resultado |
|---|---|
| [Almacenamiento y costo](fase0/01_bigquery.md) | DuckDB + Parquet: todo el proyecto ocupa pocos GiB por año y no requiere tarjeta |
| [Acceso a las fuentes](fase0/02_acceso.md) | Todas responden igual desde una conexión domiciliaria y desde GitHub Actions. El dataset oficial de consumo por modelo fue dado de baja; se rescató una copia de 2022 |
| [Volumen y perfil de DNRPA](fase0/04_volumen.md) | ~2,5 MiB de Parquet por mes. Una fila es un auto. Los 0 km vienen con descripciones limpias; los usados, en texto libre |
| [Matching entre fuentes](fase0/05_matching.md) | Pasa el criterio: valuación fiscal por código exacto (88% de los 0 km) y guía CCA por modelo (89%). La versión exacta y el consumo actualizado quedan como trabajo identificado |
| [Repuestos](fase0/06_repuestos.md) | El 88% de los títulos menciona un modelo reconocible. El SKU permite comparar original contra alternativo en el 27% (filtro de aire Polo: $151.550 original, $15.370 importado) |
| [Combustible](fase0/07_combustible.md) | La Res. 717/2025 derogó la obligación de informar precios en tiempo real: desde julio de 2025 informa el ~16% de las estaciones (YPF, el 2%). Se usa la Res. 1104 (mensual, con YPF y con volúmenes) |

Fuentes: DNRPA (inscripciones, transferencias, prendas, robos), Secretaría de Energía (precios en surtidor), BCRA (tasas prendarias), guías de precios ACARA y CCA, y tiendas de repuestos.
