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

## Fase 1: ingesta y staging (en curso)

```
ingesta/           Python: baja las fuentes y guarda un Parquet por mes en datos/raw/
  dnrpa.py         inscripciones, transferencias, prendas y robos (2018 en adelante)
  combustible.py   precios y volúmenes por estación (Res. 1104) + coordenadas (Res. 314)
transform/         dbt + DuckDB: staging con tests
```

Decisiones que importan:

- **Privacidad por lista blanca.** De DNRPA se guarda solo lo del trámite y el auto, y del titular únicamente si es persona física o jurídica. Una columna nueva que publique DNRPA queda afuera sola.
- **DNRPA revisa años cerrados** (el ZIP de 2025 cambió en agosto de 2026). La ingesta guarda la fecha de modificación de cada archivo y reprocesa el año entero si cambia. Rehacer un mes pisa su archivo: correr dos veces da lo mismo.
- **Combustible: Res. 1104, no Res. 314.** La 314 dejó de ser obligatoria en junio de 2025. En la 1104 el grano incluye si la venta es exenta de impuestos; sin eso aparecían 958 falsos duplicados.
- **Tests de frescura contra la fecha de hoy**, no contra otra tabla: un pipeline que se mide contra sí mismo no ve su propio atraso.

Cómo correrlo:

```bash
python -m ingesta.dnrpa
python -m ingesta.combustible
dbt build --project-dir transform --profiles-dir transform
```
