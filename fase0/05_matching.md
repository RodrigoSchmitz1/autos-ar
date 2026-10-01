# Fase 0.5 - Matching entre fuentes

El riesgo número 1 del proyecto: el mismo auto se llama distinto en cada fuente. Criterio para seguir: **al menos ~70% de cruce con métodos razonables** en los modelos más patentados.

Scripts: [parsear_valuacion.py](parsear_valuacion.py), [parsear_cca.py](parsear_cca.py), [medir_matching.py](medir_matching.py). Cruces del top 50 para revisar a mano: `matching_top50_0km.csv` y `matching_top50_usados.csv`.

## Fuentes

| Fuente | Qué trae | Cómo se cruza con DNRPA |
|---|---|---|
| Valuación fiscal DNRPA (Disp. 160/2026, vigencia 01-10-2026) | 18.163 vehículos, valor de 0 km a 2002 | **Por código** (marca, tipo, modelo): los mismos códigos que los microdatos |
| Guía CCA (octubre 2026) | 69 marcas, 671 modelos, 6.048 versiones, precio de 0 km a 2012 | Por texto: no tiene códigos |
| Consumo (etiqueta, copia de jun-2022) | 489 modelos | Por texto |
| Guía ACARA | — | **Descartada:** requiere registro de socio |

## Resultados (agosto 2026, ponderado por unidades)

| Cruce | Método | 0 km top 50 | 0 km total | Usados top 50 | Usados total |
|---|---|---|---|---|---|
| Valuación | código + año | **97%** | **88%** | **87%** | **81%** |
| CCA, modelo | texto, prefijo normalizado | **100%** | **89%** | **92%** | **82%** |
| CCA, modelo con precio para ese año | texto + año | 98% | 87% | 47% | 53% |
| CCA, versión | — | no resuelto | | | |
| Consumo 2022, modelo | texto | 53% | 47% | 56% | 41% |

**Techo por año en usados.** La CCA publica precios desde 2012 y la valuación desde 2002. El 61% de las transferencias son de 2012 en adelante y el 85% de 2002 en adelante. Dentro de su rango, la CCA cruza el ~87% y la valuación el ~96%. Lo que falta en usados es **cobertura de las fuentes**, no matching.

**Precisión:**
- **Valuación:** en los cruces por código, marca y modelo coinciden en el 100% de las unidades 0 km y en el 96% de los usados. El 4% restante son diferencias de escritura ("F-100" contra "F100"), no autos distintos.
- **CCA a nivel modelo:** revisé a mano los 100 cruces del top 50. El único error encontrado (el Ka viejo cruzaba con el "Ka+", que es otro auto) se corrigió.

## Veredicto

| Cruce | ¿Pasa el 70%? | Comentario |
|---|---|---|
| DNRPA ↔ valuación | **Sí** | Exacto por código, sin necesidad de IA |
| DNRPA ↔ CCA, modelo | **Sí** | Alcanza para depreciación por modelo y para el comparador |
| DNRPA ↔ CCA, versión | **No** | Es trabajo de la Fase 2: reglas + IA + revisión manual |
| DNRPA ↔ consumo | **No** | El límite es la fuente (de 2022, sin los modelos nuevos), no el método |

**Conclusión: el proyecto puede seguir.** La valuación fiscal da precio por versión con cruce exacto, y la CCA da el mercado por modelo. El precio de mercado por versión y el consumo actualizado quedan como trabajo identificado, no como bloqueo.

## Lo que se aprendió en el camino

1. **Los PDF mienten si se leen como texto.** En la valuación, los valores de más de 100 millones salían pegados ("270270000243100000…" son nueve años en un solo número). En la CCA conviven tres formatos de precio: "24259", "111,660" y "36270,0". Los dos parsers asignan cada número a su columna de año **por posición horizontal**, no por orden.
2. **Los códigos nacionales tienen fabricante.** Las columnas de la valuación son "Fab Marca Tipo Mod". Los nacionales traen fabricante (3) + marca (2) + tipo + modelo, y los importados no tienen fabricante. Con eso, la llave contra los microdatos es (marca, tipo, modelo) en los dos casos. Control: el código completo es la suma de sus partes en el 99,9% de los casos.
3. **En la CCA, las marcas se reconocen por el espacio vertical**, no por el texto. Una versión discontinuada sin precios se ve igual que una marca (negrita, sin números). Lo que las separa es el salto antes de cada marca nueva, y en el primer renglón de página, que el nombre no tenga dígitos.
4. **La valuación fiscal no es un múltiplo fijo del precio de mercado.** La idea de elegir la versión de la CCA por proporción con el valor fiscal falló: el ratio CCA/fiscal tiene dos grupos. En unos es 1,00 exacto (Honda WR-V: 42.490.000 en las dos fuentes) y en otros ~0,70 (BYD Seal U: 72 millones fiscal contra 48 de la CCA). Probablemente la DNRPA toma ACARA para unos y CCA para otros, o en fechas distintas. Queda para investigar: es una historia en sí misma ("¿la valuación fiscal sigue al mercado?").
5. **Normalizar tiene efectos colaterales.** Una regla para "HB 20" → "HB20" pegaba también "GOL 1,6" → "GOL1,6" y hacía perder al Gol entero. Los casos quedaron como test: [test_norm.py](test_norm.py).
