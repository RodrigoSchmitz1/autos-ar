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

## Fase 1: ingesta y staging

```
ingesta/           Python: baja las fuentes y guarda un Parquet por mes en datos/raw/
  releases.py      publica y recupera datos/raw en GitHub Releases
  dnrpa.py         inscripciones, transferencias, prendas y robos (2018 en adelante)
  combustible.py   precios y volúmenes por estación (Res. 1104) + coordenadas (Res. 314)
transform/         dbt + DuckDB: staging con tests
.github/workflows/pipeline.yml   corre todos los días a las 07:23 (hora argentina)
```

Decisiones que importan:

- **Privacidad por lista blanca.** De DNRPA se guarda solo lo del trámite y el auto, y del titular únicamente si es persona física o jurídica. Una columna nueva que publique DNRPA queda afuera sola.
- **DNRPA revisa años cerrados** (el ZIP de 2025 cambió en agosto de 2026). La ingesta guarda la fecha de modificación de cada archivo y reprocesa el año entero si cambia. Rehacer un mes pisa su archivo: correr dos veces da lo mismo.
- **Combustible: Res. 1104, no Res. 314.** La 314 dejó de ser obligatoria en junio de 2025. En la 1104 el grano incluye si la venta es exenta de impuestos; sin eso aparecían 958 falsos duplicados.
- **Los datos viven en GitHub Releases** (`datos-2018` … `datos-2026` y `datos-general`), no en el repo ni en una PC. Cada corrida de Actions baja lo publicado, ingiere lo nuevo y sube solo los archivos cuya huella (SHA-256) cambió. Son públicos y se pueden bajar sin cuenta.
- **Tests de frescura contra la fecha de hoy**, no contra otra tabla: un pipeline que se mide contra sí mismo no ve su propio atraso.

Cómo correrlo:

```bash
python -m ingesta.releases bajar   # opcional: trae lo ya publicado en vez de rehacerlo
python -m ingesta.dnrpa
python -m ingesta.combustible
dbt build --project-dir transform --profiles-dir transform
```

## Fase 2: catálogo canónico de versiones

El centro del modelo es **`dim_version`**: una fila por versión de auto, identificada por el código de DNRPA (origen, marca, tipo, modelo). Cada fuente se cruza contra ese código, y cada cruce dice cómo se hizo.

| Fuente | Cómo cruza | 0 km livianos, último año |
|---|---|---|
| Valuación fiscal (DNRPA) | por código, exacto | 97,9% |
| Guía de precios CCA | por texto, a nivel modelo | 98,5% |
| Consumo (etiqueta, copia 2022) | por texto, a nivel modelo | 53,0% |

`cobertura_mapeos` publica estas cifras y un test frena el pipeline si caen.

Decisiones que importan:

- **El código es la llave, no el texto.** Los microdatos y la tabla de valuación usan los mismos códigos. Las descripciones no: el mismo código aparece escrito de varias formas en los usados.
- **~400 códigos nacionales se repiten entre fabricantes** (los microdatos no traen fabricante). Si los valores coinciden da igual cuál se tome. Si no (93 casos, como "Siena EX Fire" y "Duna CSD" con el mismo código), se elige por similitud con la descripción del trámite y queda registrado como `codigo_desempate_texto`.
- **Cruce por texto con método y alias.** La normalización viene de la Fase 0 y está cubierta por tests (`ingesta/test_texto.py`). Los nombres que la normalización no puede unir ("SW4" contra "HILUX SW4") se resuelven en una tabla de alias editable (`alias_modelos.csv`), no en el código. Los empates quedan marcados como `prefijo_ambiguo` con sus candidatos.
- **Livianos y pesados se miden por separado.** Las guías de precios no cubren camiones ni remolques; contarlos como "no cruza" bajaba la cobertura sin que fuera un problema del cruce.
- **La guía CCA se pisa cada mes en la misma URL**: se captura todos los días para no perder ningún mes.
- **Las tablas de valuación anteriores a 2023 tienen otro formato** y por ahora no se ingieren: la ingesta las rechaza con un error en vez de cargarlas mal.

## Fase 3: marts

| Mart | Grano | Para qué |
|---|---|---|
| `mart_mercado_mensual` | mes × provincia × trámite × marca × modelo | qué se patenta, transfiere, prenda y roba, y con qué antigüedad |
| `mart_depreciacion` | marca × modelo × antigüedad (1-14 años) | cuánto del 0 km conserva un auto, según el fisco y según el mercado |
| `mart_combustible_mensual` | mes × provincia × producto × bandera | precio mediano, precio ponderado por volumen e impuestos |
| `mart_combustible_estaciones` | estación × producto (último mes completo) | el mapa de estaciones más baratas |

**Primer hallazgo: la valuación fiscal deprecia menos que el mercado.** Mediana de los modelos con respaldo (al menos 3 versiones de cada lado):

| Antigüedad | Valuación fiscal | Mercado (guía CCA) |
|---|---|---|
| 1 año | 84% del 0 km | 68% |
| 5 años | 63% | 53% |
| 10 años | 48% | 40% |

Es decir, el fisco considera que un auto usado vale más de lo que vale en el mercado. La patente y los aranceles de transferencia se calculan sobre esa base. La excepción es la Hilux: fiscal y mercado van casi juntos durante cinco años.

Decisiones que importan:

- **Depreciación por índice encadenado.** La CCA le pone el año al nombre de la versión ("TITANIUM 2025"), así que casi ninguna tiene a la vez precio 0 km y de varios años atrás. Se encadenan los saltos de un año (mediana de precio(N) / precio(N-1) de la misma versión): las curvas con respaldo pasaron de 74 a 285 puntos. Se usa el mismo método del lado fiscal para que las curvas sean comparables.
- **Proporciones, no precios.** El ratio entre el precio de la CCA y el valor fiscal sale bimodal (1,00 en unos modelos, ~0,70 en otros), porque las fuentes miden en fechas y niveles distintos. La proporción dentro de cada fuente elimina ese problema.
- **La CCA cambia de unidad en el mismo renglón.** En las marcas de lujo, los años usados vienen en millones y el 0 km en miles: un Cayman 2017 figuraba a $87 mil. Menos de 1.000 = millones. Son 740 precios, sin ninguno en la zona ambigua (1.000 a 3.000), y la ingesta falla si aparece alguno.
- **El mart de mercado no pierde trámites.** Los que no tienen código de modelo (2,4%) entran como `sin_codigo`. Un test verifica que el total coincida con staging.
- **Combustible: mediana, sin exentos ni valores atípicos** (menos de la mitad o más del doble de la mediana provincial: 0,4% de las filas).

## Fase 4: patente y service (en curso)

**Patente.** No hay un dataset: cada provincia fija el impuesto en su ley impositiva anual. Se cura a mano en dos tablas, con el artículo de ley de cada dato:

- `patente_reglas`: qué base usa, con qué coeficiente, qué modelos alcanza la escala y qué ajustes se aplican durante el año.
- `patente_escalas`: los tramos (cuota fija + alícuota sobre el excedente). Un test verifica que cada cuota fija sea lo acumulado por los tramos anteriores, así un error de tipeo al copiar una ley salta solo.

`mart_patente_estimada` calcula la patente anual por versión y año modelo. **Es una estimación, y lo dice en cada fila.** La base oficial casi nunca es la valuación de DNRPA:

| Provincia | Estado | Notas |
|---|---|---|
| Buenos Aires | cargada (Ley 15.558) | La base oficial son los valores de ACARA × 0,95; se aproxima con la valuación de DNRPA × 0,95. Las cuotas se ajustan por IPC. Los modelos 1990-2015 pagan al municipio |
| CABA | pendiente | En 2026 pasó a base ACARA, y AGIP topeó el aumento en 31,8% sobre lo pagado en 2025: la patente real depende del año anterior. El texto oficial de la ley no se puede bajar del Boletín Oficial porteño |
| Resto | pendiente | |
