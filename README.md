# autos-ar

Cuánto vale, cuánto cuesta tener y qué conviene comprar: autos en Argentina con datos públicos.

**Estado: Fase 0 (factibilidad).** Antes de diseñar pipelines se mide cada fuente: si se puede acceder, cuánto pesa y si los modelos se pueden cruzar entre fuentes.

| Paso | Resultado |
|---|---|
| [Almacenamiento y costo](fase0/01_bigquery.md) | DuckDB + Parquet: todo el proyecto ocupa pocos GiB por año y no requiere tarjeta |
| [Acceso a las fuentes](fase0/02_acceso.md) | Todas responden igual desde una conexión domiciliaria y desde GitHub Actions. El dataset oficial de consumo por modelo fue dado de baja; se rescató una copia de 2022 |
| [Volumen y perfil de DNRPA](fase0/04_volumen.md) | ~2,5 MiB de Parquet por mes. Una fila es un auto. Los 0 km vienen con descripciones limpias; los usados, en texto libre |

Fuentes: DNRPA (inscripciones, transferencias, prendas, robos), Secretaría de Energía (precios en surtidor), BCRA (tasas prendarias), guías de precios ACARA y CCA, y tiendas de repuestos.
