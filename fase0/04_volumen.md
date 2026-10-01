# Fase 0.4 - Volumen y perfil de DNRPA

Muestra: agosto 2026, el último mes publicado (subido el 11-09-2026). Scripts: [bajar_muestra.py](bajar_muestra.py) y [perfilar_muestra.py](perfilar_muestra.py). Los CSV quedan en `datos/`, fuera de git, porque traen datos del titular.

## Filas por mes

| Dataset | Filas | CSV | Parquet sin titular |
|---|---|---|---|
| Inscripciones iniciales (0 km) | 45.229 | 10,4 MiB | 0,32 MiB |
| Transferencias (usados) | 155.246 | 34,2 MiB | 1,78 MiB |
| Prendas | 35.129 | 7,7 MiB | 0,34 MiB |
| Robos y recuperos | 2.451 | 0,6 MiB | 0,05 MiB |

Los cuatro datasets tienen **el mismo esquema de 25 columnas**: alcanza con una sola ingesta parametrizada.

**Espacio:** ~2,5 MiB de Parquet por mes. Para 2018-2026 (~104 meses) son unos **260 MiB**, contra los ~5,5 GiB de CSV estimados en el paso 1. Parquet sin las columnas del titular comprime entre 11 y 32 veces.

## Decisiones que cambia este perfil

### 1. Una fila es un auto: se cuentan filas
- El campo `titular_porcentaje_titularidad` sugería que un auto con dos dueños aparecía en dos filas. **No es así.** De los grupos con 50% de titularidad, 2.857 tienen una sola fila y apenas 50 tienen dos. El porcentaje es la parte del **primer titular**, y el segundo no figura.
- La estadística oficial de DNRPA cuenta filas: 45.230 contra 45.229.
- Contra ACARA (agosto 2026: 44.415 vehículos en total, 2.616 Hilux, 7.247 Toyota), contar filas da diferencias de entre 0,5% y 4,7% por marca. Son del orden de las diferencias de fecha y de criterio entre fuentes.
- Sumar porcentajes habría **subestimado los patentamientos un 3,4%**.

### 2. La provincia del titular no es el domicilio real
`titular_domicilio_provincia` coincide con la provincia del registro en el **100%** de las filas. Las diferencias son solo de escritura ("C.AUTONOMA DE BS.AS" contra "Ciudad Autónoma de Buenos Aires"). Si fuera el domicilio real habría diferencias, por ejemplo gente del conurbano que patenta en Capital. El campo no aporta información propia: se usa la provincia del registro y la trampa del contexto ("registro vs domicilio") no aplica.

### 3. Privacidad: qué se descarta en la ingesta
Las columnas del titular no traen nombre ni documento, pero localidad, género, año y país de nacimiento, combinados con registro y fecha, pueden identificar a alguien en un lugar chico.
- **Se descartan:** localidad, género, año de nacimiento, país de nacimiento (y su id) y porcentaje de titularidad.
- **Se conservan:** tipo de persona (física o jurídica, útil para distinguir flotas) y provincia.

### 4. Matching: los 0 km vienen limpios, los usados no
- **Inscripciones:** 1.621 pares marca-modelo con 1.644 descripciones, casi uno a uno. La descripción es a nivel versión ("TERRITORY TREND 1.5L HIBRIDA AT"), así que el ranking por descripción parte un modelo en varias filas.
- **Transferencias:** 8.157 pares de códigos con 14.122 descripciones, y 1,3% sin código. Un mismo modelo aparece escrito de varias formas: "GOL TREND 1.6 2011", "GOL TREND 1.6/2009", "GOL TREND 1,6". Ahí está el trabajo grueso de resolución de entidades, y el paso 5 lo mide.
- El código de modelo **no es único solo**: la llave es marca + modelo.

### 5. Nombres de provincia
Cada fuente escribe las provincias distinto: CABA aparece de tres formas entre microdatos, domicilio y estadística. Para cruzar fuentes hay que normalizar por id de provincia, no por nombre.

## Calidad
- Nulos o vacíos: menos del 2,2% en todas las columnas del auto. La excepción es `titular_pais_nacimiento_id` (6% a 20%), que igual se descarta.
- Fechas: todos los trámites caen dentro del mes (del 01-08 al 31-08).
