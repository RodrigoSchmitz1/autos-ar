# Fase 0.2 - Acceso a las fuentes

Script: [probar_acceso.py](probar_acceso.py). Pide solo los primeros 4 KB de cada archivo, con una pausa de 2,5 s por host y un User-Agent identificable. Resultados crudos: `resultados_acceso_<origen>.csv`.

## Desde la PC (2026-10-01)

| Fuente | Resultado | Nota |
|---|---|---|
| DNRPA: inscripciones, transferencias, prendas, robos, registros seccionales, estadística | OK (12 de 12 descargas, los 2 recursos más nuevos de cada dataset) | Agosto 2026 publicado el 11-09: un mes y medio de atraso |
| Combustible (vigentes e históricos) | OK | Vigentes actualizado hoy |
| BCRA API de transparencia (prendarios) | OK | Devuelve JSON con tasas por banco |
| Guía CCA (PDF) | OK | |
| ACARA (acaramotos y acara) | OK | Falta ver si la guía es descargable o requiere suscripción |
| Repuestos Express (robots, sitemap, búsqueda, producto) | OK | |
| Service VW Mataderos | OK | |
| **Etiqueta vehicular (consumo)** | **No disponible** | Ver abajo |

## Consumo por modelo: el dataset oficial desapareció

- La página "Datos abiertos" de la etiqueta vehicular da error en un navegador normal. El link sale del propio sitio oficial, así que está roto en origen. A un script le responde 403 (Cloudflare).
- El dataset de datos.gob.ar da 404, tanto la página como la API del catálogo.
- El archivo real vivía en **datos.ambiente.gob.ar**, que fue dado de baja: hoy redirige a una URL rota de datos.gob.ar.
- **En el Internet Archive hay copia** del CSV de junio de 2022 (`ensayos_co2_consumos_09062022.csv`): 811 ensayos, 55 marcas, 489 modelos, firmados entre 2015 y 2022. Trae consumo urbano, extraurbano y mixto, CO2, motor, cilindrada, transmisión y combustible. Pierde los modelos lanzados después de mediados de 2022.

Opciones, de más a menos rápida:

1. Usar la copia de 2022 como base, documentando la fecha de corte.
2. Pedido de acceso a la información pública (Ley 27.275) por la base actualizada. Por ley responden en 15 días hábiles, prorrogables.
3. Fichas técnicas de las marcas para los modelos posteriores a 2022.

## Detalles técnicos para la ingesta

- **Python 3.13+ valida certificados en modo estricto** y rechaza algunas cadenas viejas (por ejemplo, la de GoDaddy G2 que usa el Internet Archive). Lo verifiqué: no hay nada en la PC que intercepte las conexiones.
- **BCRA:** algún servidor de www.bcra.gob.ar manda la cadena SSL incompleta. La API (api.bcra.gob.ar) no tuvo el problema. La ingesta tiene que reintentar.
- Las URLs de descarga de DNRPA cambian con cada publicación: hay que descubrirlas con la API del catálogo (`package_show`), no escribirlas a mano.

## Desde GitHub Actions (2026-10-01, run #1)

Se repitió la prueba con el workflow `.github/workflows/fase0_acceso.yml` desde una IP de datacenter. Resultados: `resultados_acceso_actions.csv`.

**Ningún portal del Estado bloquea a Actions**: DNRPA, Energía, BCRA y datos.gob.ar responden igual que desde la PC. A diferencia de SEPA, la ingesta puede correr entera en la nube, sin depender de la PC.

Diferencias (2 de 39):

| Fuente | PC | Actions | Lectura |
|---|---|---|---|
| acaramotos.org.ar | 200 | timeout (30 s) | Puede ser un bloqueo a IPs de nube o algo pasajero; con una prueba no alcanza. El sitio de autos (acara.org.ar) respondió en los dos lados. Reprobar antes de diseñar su ingesta |
| CSV de la etiqueta (Wayback) | error SSL | 200 | Confirma que el error era de Python en Windows con la cadena de certificados, no de la red |

La página de la etiqueta vehicular da 403 en los dos lados: Cloudflare frena a los scripts sin importar desde dónde vengan.
