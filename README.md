# autos-ar

Cuánto vale, cuánto cuesta tener y qué conviene comprar: autos en Argentina con datos públicos.

**Estado: Fases 0 a 4 completas** (factibilidad, ingesta, catálogo canónico, marts, patente y service); **Fase 5 (repuestos) en curso**. Antes de diseñar cada pipeline se mide la fuente: si se puede acceder, cuánto pesa y si los modelos se pueden cruzar entre fuentes.

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

## Fase 4: patente y service

**Patente.** No hay un dataset: cada provincia fija el impuesto en su ley impositiva anual. Se cura a mano en dos tablas, con el artículo de ley de cada dato:

- `patente_reglas`: qué base usa, con qué coeficiente, qué modelos alcanza la escala y qué ajustes se aplican durante el año.
- `patente_escalas`: los tramos (cuota fija + alícuota sobre el excedente) por categoría (auto o pick-up), con mínimo anual y una valuación mínima opcional. Las escalas "por categoría" (alícuota sobre el valor total, como en Mendoza) se cargan con la misma fórmula, con cuota fija = base × alícuota. Un test verifica que en las escalas marginales cada cuota fija sea lo acumulado por los tramos anteriores (con tolerancia para los redondeos de la propia ley), así un error de tipeo al copiar una ley salta solo.

`mart_patente_estimada` calcula la patente anual por versión y año modelo. **Es una estimación, y lo dice en cada fila.** La base oficial casi nunca es la valuación de DNRPA:

| Provincia | Estado | Notas |
|---|---|---|
| Buenos Aires | cargada (Ley 15.558) | La base oficial son los valores de ACARA × 0,95; se aproxima con la valuación de DNRPA × 0,95. Las cuotas se ajustan por IPC. Los modelos 1990-2015 pagan al municipio |
| CABA | cargada (Ley 6927 art. 50, fe de erratas) | Siete tramos de 1,6% a 8%; las pick-ups pagan 2,3% fijo; tope del 6% de la valuación, mínimo de $13.300 y recargo del 10% para el Fondo Subte. En 2026 la base pasó a ACARA, y AGIP topeó el aumento en 31,8% sobre 2025: la patente real puede ser menor que la estimada |
| Córdoba | cargada (Ley 11.090 arts. 55-60) | **Usa la valuación de DNRPA como base oficial**: es la única de las tres donde la estimación no es una aproximación. Cuatro tramos de 0,85% a 2,10%. Modelos 2016 y anteriores exentos, salvo los 2009-2016 que valen $19,4 millones o más |
| Santa Fe | cargada (API, alícuotas 2026) | Sin tramos: alícuota única según el año del modelo (2,3%, 2,0%, 1,8%); pick-ups 2%. Tabla de valuación propia de API. Tope de aumento del 30% sobre 2025 para modelos 2022 y anteriores (no aplicado) |
| Mendoza | cargada (Ley 9680 art. 9) | Ocho categorías y **la alícuota se aplica sobre el valor completo**, no sobre el excedente: hay saltos entre categorías. Base ACARA |
| Tucumán | cargada (Ley 8467, Código Tributario arts. 300-307) | 2% plano los autos y 1,5% las pick-ups. Base ACARA. Autos de más de 15 años exentos si valen hasta $15,6 millones |
| Río Negro | cargada (Ley 5837 art. 24) | 3,5% plano. Tope de aumento del 25% sobre 2025 (no aplicado): la patente real puede ser menor. Exentos los modelos 2006 y anteriores |
| San Luis | cargada (Ley VIII-0254-2025 art. 40) | Nueve categorías de 2,5% a 5% **sobre el valor completo**, como Mendoza. Exentos los modelos 2010 y anteriores |
| Catamarca | cargada (Ley 5927 arts. 6-11) | **Base oficial DNRPA**. 2% plano; las cabina simple pagan 1,5%, pero DNRPA casi nunca dice la cabina. Exentos 20 años o más |
| La Rioja | cargada (Ley impositiva 2026 arts. 6-8) | **Base oficial DNRPA**. 2,5% plano. Pagan solo los modelos 2011 en adelante |
| La Pampa | cargada (Ley 3636 arts. 8-9, texto escaneado) | Escalas por categoría **sobre el valor completo**: autos 2% a 3%, pick-ups 2,1% a 3%. Valuaciones propias de la ley; los tramos están calibrados sobre ellas, así que con la valuación DNRPA la estimación puede quedar alta. Exentos los modelos 2013 y anteriores |
| Salta | **aproximación municipal**: ordenanza de la Ciudad de Salta (77% del parque) | 2% de la valuación. Más de 20 años: otra tasa (5 UT por mes). Transición que limita el impuesto al 40% del de 2024 (no aplicada) |
| Formosa | **aproximación municipal**: Código Tarifario de la Ciudad de Formosa (73%) | 2% del valor ACARA, sin exención por antigüedad |
| Chubut | **aproximación municipal**: ordenanza de Comodoro Rivadavia (42%) | Valuaciones provinciales (Res. 74/25) pero alícuota de cada municipio: Comodoro 2,7% con mínimo de ~$180.000 por año; Puerto Madryn 2,5% |
| Neuquén | **aproximación municipal**: Ordenanza 15065 de Neuquén capital (44%) | 2,5% con mínimo de $156.000; exentos los modelos 2005 y anteriores. Tabla de valuación propia |
| Corrientes | **aproximación municipal**: Ordenanza 7706 de Corrientes capital (34%) | 2,5% más 6% de recargo (Fondo de Mejora del Transporte); base DNRPA |
| Misiones | cargada (Ley XXII-25 art. 65): impuesto provincial que cobran los municipios | Autos 2%, **pick-ups 0,8%** (son "tipo 2", vehículos de carga). Hasta 16 años; los más viejos pagan montos fijos (no cargados) |
| Tierra del Fuego | **aproximación municipal**: Ordenanza 5069 de Ushuaia (47%; Río Grande no publica la suya) | Escala de 2% a 4% sobre el valor completo; desde $17,5 M paga 4%. La tabla municipal descontaría el IVA (la isla está exenta): la estimación puede quedar alta |
| Entre Ríos | **fuente secundaria**: tasa efectiva promedio del informe de Ineco-UADE (mayo 2026) | 3,33%. La ley combina cuota fija y alícuota progresiva, pero el decreto 2026 con los tramos no está publicado: una tasa plana sobreestima los autos baratos y subestima los caros |
| San Juan | **fuente secundaria**: Ineco-UADE | Alícuota única del 2%. La Ley 2803-I está en un sitio que rechaza los scripts |
| Jujuy | **fuente secundaria**: Ineco-UADE | Patente municipal; alícuota única del 2%. La ordenanza 2026 de San Salvador no está publicada |
| Sin cargar | Santiago del Estero, Santa Cruz y Chaco | Sin norma ni dato confiable publicado (las calculadoras se contradicen), y Resistencia (Chaco) cobra por peso, que DNRPA no publica. Ver [docs/patente_relevamiento.md](docs/patente_relevamiento.md) |

Las veintiuna cargadas reúnen el 96,5% de los trámites de autos livianos del último año. Donde la patente es municipal se usa la ordenanza de la ciudad con más parque: `precision = 'aproximacion_municipal'` y `ciudad_referencia` lo dicen en cada fila. Donde no hay norma 2026 accesible se usa la tasa del informe de Ineco-UADE (`precision = 'fuente_secundaria'`); sus valores coinciden con los de las leyes verificadas (Catamarca, Salta y Tucumán 2%; La Rioja y Corrientes 2,5%), lo que le da credibilidad. Para Tierra del Fuego el informe dice 2,5% y la ordenanza de Ushuaia da hasta 4%: probablemente el informe usó Río Grande.

Mismo auto, distinta provincia (estimación 2026, modelo 0 km):

| Provincia | Polo Track ($37,6 M) | Hilux SRX 4x4 ($84,3 M) |
|---|---|---|
| Córdoba | $518.254 (1,4%) | $1.500.666 (1,8%) |
| Catamarca | $751.350 (2,0%) | $1.686.980 (2,0%) |
| Mendoza | $751.350 (2,0%) | $2.108.725 (2,5%) |
| Tucumán | $751.350 (2,0%) | $1.265.235 (1,5%) |
| Buenos Aires | $838.565 (2,2%) | $2.747.420 (3,3%) |
| Santa Fe | $864.053 (2,3%) | $1.686.980 (2,0%) |
| La Rioja | $939.188 (2,5%) | $2.108.725 (2,5%) |
| Río Negro | $1.314.863 (3,5%) | $2.952.215 (3,5%) |
| San Luis | $1.314.863 (3,5%) | $4.217.450 (5,0%) |
| CABA | $1.697.451 (4,5%) | $2.134.030 (2,5%) |
| La Pampa | $1.127.025 (3,0%) | $2.530.470 (3,0%) |
| Salta (capital) | $751.350 (2,0%) | $1.686.980 (2,0%) |
| Neuquén (capital) | $939.188 (2,5%) | $2.108.725 (2,5%) |
| Corrientes (capital) | $995.539 (2,7%) | $2.235.249 (2,7%) |
| Misiones | $751.350 (2,0%) | $674.792 (0,8%) |
| Tierra del Fuego (Ushuaia) | $1.502.700 (4,0%) | $3.373.960 (4,0%) |
| Entre Ríos (tasa efectiva) | $1.250.998 (3,3%) | $2.808.822 (3,3%) |
| San Juan, Jujuy | $751.350 (2,0%) | $1.686.980 (2,0%) |
| Formosa (capital) | $751.350 (2,0%) | $1.686.980 (2,0%) |
| Chubut (Comodoro) | $1.014.323 (2,7%) | $2.277.423 (2,7%) |

**Service programado.** Cada marca publica distinto: el relevamiento está en [docs/service_relevamiento.md](docs/service_relevamiento.md). `ingesta/service.py` guarda una foto de la lista de cada marca **solo cuando cambia** (fecha de captura), porque casi ninguna fuente dice desde cuándo rige el precio. Por ahora cubre Fiat y Jeep (la lista oficial de Mopar) Peugeot y Citroën (sus tiendas online de service) Volkswagen (la lista nacional trimestral) Toyota (la tabla que publica un concesionario) Renault (la planilla de un concesionario) BYD (su guía oficial, en dólares) y Ford (su página oficial, por versión).

`mart_service` calcula el **costo de service por kilómetro**: todo el plan publicado dividido por los kilómetros que cubre. Es la única forma de comparar marcas que cobran un precio parejo (Fiat: $434.000 cada service del Cronos) con marcas que cobran distinto en cada intervalo, y con intervalos distintos (Fiat cada 10.000 km, Jeep cada 12.000).

| Modelo | Service | Costo por km |
|---|---|---|
| Fiat Mobi | $420.000 cada 10.000 km | $42,0 |
| Fiat Cronos | $434.000 cada 10.000 km | $43,4 |
| Jeep Renegade | $575.000 cada 12.000 km | $47,9 |
| Fiat Toro Diesel | $730.000 cada 10.000 km | $73,0 |
| Jeep Grand Cherokee SRT | $1.050.000 cada 12.000 km (uno a $1.167.200) | $89,7 |

Dos detalles de la fuente: tiene precios con un cero de más ("$ 434.0000"), que se corrigen solo si coinciden con el precio habitual del modelo y quedan marcados; y los Jeep diésel tienen un service más caro a los 60.000 km.

Peugeot y Citroën publican el precio en un formulario (modelo, versión, service y concesionario) que se llena por pedidos AJAX: unos 180 pedidos por marca. Por eso se consultan **como máximo una vez cada 7 días** (las listas cambian una vez por mes) y con la pausa de cortesía de 2,5 s. El precio es el mismo en toda la red: cada corrida lo compara contra otros dos concesionarios y falla si difiere. La tienda tiene services cargados dos veces (el 208 1.6 N a 50.000 km): si tienen el mismo precio queda uno solo, y si difieren el pipeline falla. Como comparten plataforma, los utilitarios gemelos cuestan lo mismo en las dos marcas (Partner y Berlingo, Expert y Jumpy, Boxer y Jumper).

| Modelo | Service | Costo por km |
|---|---|---|
| Citroën C3 1.6 | $439.000 cada 10.000 km | $43,9 |
| Peugeot 208 1.6 | $460.000 cada 10.000 km | $46,0 |
| Peugeot 2008 T200 | $569.000 cada 10.000 km | $56,9 |
| Citroën C4 híbrido | $617.000 cada 10.000 km | $61,7 |

Volkswagen es la única marca que publica la **vigencia** ("Q3 - Julio a Septiembre 2026") y un precio distinto en cada service, cada 15.000 km. La lista nacional es un PDF por grupos de modelos ("Polo / Tera / Virtus / T-Cross / ..."), que un concesionario publica completa; se abre en una fila por modelo para cruzarla con el catálogo. El 2º y el 3º service tienen la mano de obra bonificada y entran al costo con ese precio, que es lo que se paga si se respetan los plazos. El concesionario puede tardar en subir la lista nueva: `lista_vencida` avisa cuando la última captura ya no está vigente. La lista es solo de nafta: la Amarok diésel queda afuera.

| Modelo VW | 1er service (15.000 km) | Costo por km |
|---|---|---|
| Up! | $354.910 | $19,2 |
| Polo, Virtus, T-Cross, Nivus, Tera | $492.760 | $26,9 |
| Vento | $627.650 | $38,8 |
| Touareg | $1.276.850 | $77,6 |

Integrar VW destapó dos problemas del catálogo: la normalización borraba "UP" (lo trataba como parte de "PICK - UP") y el Up! no cruzaba con ninguna fuente; y DNRPA antepone la versión al nombre ("TAKE UP! 1.0"). Con el arreglo y siete alias, la cobertura de la guía CCA sobre las unidades subió de 91,5% a 91,8%. También apareció que el catálogo no era reproducible: `mode()` elige cualquiera de dos descripciones empatadas, y ~160 códigos cambiaban de modelo entre corridas. Ahora se desempata por orden alfabético, y dos corridas seguidas dan el mismo resultado fila por fila.

Toyota publica el plan más largo: 20 services, de 10.000 a 200.000 km, con precios que se repiten en ciclos (el Etios cuesta $260.900 en los services impares y entre $324.500 y $515.500 en los pares). El sitio oficial carga los precios desde una API que su `robots.txt` prohíbe, así que la fuente es la tabla HTML del concesionario Toyota Federico, cuyo `robots.txt` permite todo. Antes de usarla se verificó que no fueran precios propios: otro concesionario (Panamericana) publica exactamente los mismos montos. La huella se calcula sobre los precios extraídos y no sobre la página, que también muestra los precios de los 0 km y cambia seguido.

Costo de service por km, mediana de los modelos de cada marca:

| Marca | Modelos | Mediana por km | Plan publicado |
|---|---|---|---|
| Volkswagen | 25 | $26,9 | cada 15.000 km hasta 105.000, dos con mano de obra bonificada |
| Ford | 41 | $37,6 | cada 10.000, 15.000, 16.000 o 20.000 km según el modelo |
| BYD | 5 | $37,9 | cada 20.000 km (eléctricos) o 12.000 km (híbridos), en dólares |
| Toyota | 13 | $49,2 | cada 10.000 km hasta 200.000 |
| Jeep | 10 | $49,7 | cada 12.000 km |
| Citroën | 15 | $50,1 | cada 10.000 km (utilitarios, cada 20.000) |
| Fiat | 15 | $51,3 | cada 10.000 km |
| Peugeot | 15 | $52,9 | cada 10.000 km (utilitarios, cada 20.000) |
| Renault | 41 | $55,2 | cada 10.000 km hasta 120.000 |

Renault no publica una lista por service sino un precio base que depende del aceite del motor, más "packs" a los 20.000/100.000, 40.000, 60.000, 80.000 y 120.000 km. La fuente es la planilla "Precios Todo Incluido" del concesionario Pourtau (región A de precios Renault, AMBA), un PDF que se regenera todos los días: la huella es de los precios extraídos. Que las columnas de packs son el precio total y no un adicional se confirmó con la versión anterior del mismo archivo, que los publicaba como "+ $". Los precios salen del texto de cada renglón y los nombres de la grilla, porque la grilla junta celdas y perdía un precio (Boreal). No se encontró otro concesionario con la misma planilla para compararla, y un dato es sospechoso: el Grand Koleos nafta cuesta menos a los 120.000 km que a los 60.000, al revés que todos los demás motores. Los eléctricos son los más baratos de todo el relevamiento: Kwid E-TECH $19,8 por km, contra $38,8 del Kwid nafta.

BYD publica en **dólares con IVA** ("USD 92 (IVA Incluido)"). La ingesta guarda el monto tal como se publica (`moneda` = 'USD') y dbt lo pasa a pesos con el **tipo de cambio minorista del BCRA** (promedio vendedor de los bancos, `ingesta/cambio.py`): la lista vigente, con el último dólar publicado, porque eso es lo que cuesta hoy; las fotos viejas, con el del día en que se capturaron. Un *asof join* toma el último día hábil con dato. Su lista además está vencida (mayo-junio de 2026) y queda marcada con `lista_vencida`. Los eléctricos de BYD tienen el service más barato por km de todo el relevamiento: Dolphin Mini $12,0 y Yuan Pro $13,0, contra $37,9 y $39,0 de los híbridos enchufables (Atto 2 y Song Pro), que sí cambian aceite.

Ford publica la mejor fuente: una página por versión (41, incluidas las de años anteriores) con el precio de cada service, con y sin IVA, y una nota legal con la **vigencia mensual** ("precios sugeridos al público vigentes desde el 01/10/2026 al 31/10/2026") y aclarando que es el precio que Ford sugiere a toda la red. Se toma ese precio; el "Ford Protect" es prepago y queda afuera. El recolector recorre los enlaces desde la página de mantenimientos (~65 páginas, como máximo una vez por semana) y saca el nombre de la versión de la URL, porque los títulos de las páginas están mal (las E-Transit dicen "Bronco sport"). En el relevamiento el sitio había devuelto 403 a los scripts; al volver a probar respondió normal al User-Agent del proyecto. Si el bloqueo vuelve, Ford queda afuera: usar un navegador automatizado para pasarlo sería esquivarlo. Un control evitó guardar un precio mal leído: algunas solapas tienen el id en mayúscula ("60K") y su contenido quedaba pegado a la anterior; ahora la cantidad de solapas leídas tiene que coincidir con las de la página.

La tabla de alias ahora también puede **impedir** un cruce (`(sin familia)`): el prefijo unía el Mustang Mach-E, un SUV eléctrico que la CCA no tiene, con el Mustang V8. Aplica a los service y a los patentamientos.

## Fase 5: repuestos (en curso)

**Fuente.** Repuestos Express, la tienda relevada en la Fase 0. `ingesta/repuestos.py` baja solo las piezas que se cambian en el mantenimiento (filtros, pastillas, discos y campanas de freno, bujías, distribución, correas, amortiguadores y embragues): **5.368 productos**, exactamente los que el sitio dice tener en esas categorías. Scraping responsable: solo `/buscar`, que `robots.txt` permite; el listado trae 24 productos por página con los mismos datos que la ficha (~230 pedidos en vez de 5.368); un pedido cada 2,5 s; como máximo una consulta por semana, y falla si una página trae 0 productos (cambió el HTML).

**Tipo de pieza.** La subcategoría del sitio no alcanza: "Pastillas de Freno" trae pastillas para regular válvulas, y "Filtros" mezcla el elemento con su carcasa y soporte, que cuestan 10 a 50 veces más. `stg_repuestos__productos` clasifica por el **título** en 18 tipos de pieza de mantenimiento (filtro de aceite, kit de distribución, amortiguador delantero...); conjuntos, soportes, bulones, cables y bombas quedan como `otro`. Clasifica el 71% de los productos, con 39 aciertos en una muestra de 40.

**Cruce con los modelos.** `int_repuesto_modelos` busca en el título los nombres de modelo de cada marca. Un repuesto puede ser compatible con varios ("Hilux/Corolla/Yaris"): una fila por familia. El catálogo de nombres tiene tres orígenes: las familias de la guía CCA (las mismas con las que cruzan patentamientos y service); las raíces de modelo de DNRPA con 1.000 trámites o más, para los autos que la guía ya no lista o lista solo "con apellido" (Corsa, Duna, Escort; "Megane" a secas, porque la CCA solo tiene "MEGANE III"); y una tabla de abreviaturas ("Hil" = Hilux, "Xsa" = Xsara, "R19" = 19), cargadas por frecuencia en los títulos que no cruzaban. Cruza el **76%** de los repuestos de mantenimiento y el **91%** de los que traen la marca del auto, sin errores en las muestras revisadas, **sin IA y sin costo**. Ajustes que salieron de mirar los casos fallidos: en los títulos la barra y el guion separan modelos ("Vento/passat/tiguan" era una sola palabra); sin marca del auto no se aceptan nombres tipo código ("D-20" cruzaba con BAIC D20, "juego X2" con BMW X2); y si con la marca no aparece nada se prueba sin ella, porque hay productos con la marca mal cargada ("Corolla" etiquetado como Peugeot). Lo que queda afuera son abreviaturas menos frecuentes; si hace falta, el siguiente paso es el free tier de Gemini, como en SEPA.

**Original contra alternativo.** El SKU es código de la pieza + sufijo del proveedor; la base agrupa la misma pieza en distintas calidades (`mart_repuestos_comparables`). En 108 piezas comparables, **la original cuesta en mediana 2,3 veces** la alternativa más barata; los extremos: filtro de combustible de la Hilux 11,3x, filtro de aire del Polo 9,9x. Otras 16 quedan marcadas con `revisar`: la original sale más barata, casi seguro porque el código base une dos piezas distintas (un kit de distribución con bomba de agua contra uno sin).

`mart_repuestos` resume por familia y tipo de pieza el precio mediano original y alternativo (1.345 combinaciones de 195 familias). Ejemplo, pastillas de freno: Peugeot 208 $287.525 original contra $57.125 alternativa; Toyota Corolla $531.540 contra $75.905.

