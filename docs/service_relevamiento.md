# Service programado: relevamiento de fuentes (2026-10-01)

Qué publica cada marca, en qué formato y si un script lo puede leer. Medido antes de escribir recolectores, igual que en la Fase 0.

| Marca | Fuente oficial (o copia oficial en un concesionario) | Formato | ¿Lo lee un script? | Vigencia indicada | Granularidad |
|---|---|---|---|---|---|
| Fiat | `mantenimientomopar.com.ar/fiat/js/db.json` | JSON estático | Sí | No (archivo del 2-jul-2026); fiatstore dice "1 al 30/09/2026" | Modelo y motor, de 10.000 a 100.000 km |
| Jeep | `mantenimientomopar.com.ar/jeep/js/db.json` | JSON estático | Sí | No (2-jul-2026) | Modelo y motor, cada 12.000 km |
| Peugeot | `peugeotstore.com.ar/mantenimientos-programados` | Formulario con AJAX | Sí (necesita sesión y token CSRF) | No | Versión |
| Citroën | `citroenstore.com.ar/mantenimientos-programados` | Formulario con AJAX | Sí (mismo sistema que Peugeot) | No (el texto legal es de 2018) | Versión |
| Volkswagen | PDF de la lista nacional publicado por un concesionario (Alperovich) | PDF con texto | Sí | **"3º trimestre, julio a septiembre 2026"** | Grupo de modelos, cada 15.000 km hasta 105.000 |
| Toyota | toyota.com.ar (app que carga los precios por una API que robots.txt prohíbe); un concesionario publica la tabla en HTML | HTML | Solo el concesionario | No | Modelo, de 10.000 a 200.000 km |
| Ford | ford.com.ar, página por modelo y motor | HTML | Sí. En el relevamiento devolvió 403 a scripts; el 2026-10-02 respondió normal al User-Agent del proyecto, sin navegador. Si vuelve el bloqueo, no se esquiva | **Sí, mensual** (nota legal "Posventa mantenimiento") | Modelo y motor, con y sin IVA y precio prepago |
| Renault | Planilla "Precios Todo Incluido" del concesionario Pourtau (región A); hay otra versión de sep-2025 con adicionales "+ $" | PDF | Sí, con extracción de tablas | No (el PDF se regenera a diario) | Código de motor, precios por región |
| BYD | `byd.com/ar/service-guide` | HTML con JSON embebido | Sí | "1/05 al 30/06/2026": **vencida** | Modelo, cada 20.000 km (eléctricos) o 12.000 km (híbridos), **en dólares**: se convierte con el minorista del BCRA |
| Chevrolet | Sin fuente oficial: solo kits de repuestos | — | — | — | — |

## Lo que cambia el diseño

1. **Las marcas de Stellantis (Fiat, Jeep, Peugeot, Citroën) publican un único precio por modelo**, igual en todos los kilómetros (Cronos: $434.000 cada service). VW, Toyota, Ford y Renault, en cambio, tienen un precio distinto en cada intervalo. Para el costo por kilómetro sirven las dos, porque se suma el plan completo y se divide por los kilómetros, pero no se comparan service por service.
2. **La vigencia casi nunca está explícita.** Solo VW (trimestral) y los paquetes prepagos de Stellantis (mensuales) la indican. Los concesionarios actualizan sus páginas cuando quieren: la página de VW Mataderos todavía muestra el 2º trimestre ($448.960 el Polo a 15.000 km, contra $492.760 en la lista del 3º, un 9,8% más). Primero se anotó $444.970 por error: la página de Mataderos no tiene la columna del Up!, y al comparar se corrió una columna. El recolector tiene que guardar la fecha de captura y, cuando exista, la de vigencia.
3. **Mano de obra bonificada:** en VW, el 2º y el 3º service la tienen, solo si los anteriores se hicieron a tiempo. Es un precio distinto del de lista y hay que guardarlo marcado.
4. **Errores en las fuentes:** el JSON de Mopar tiene montos mal escritos ("$ 434.0000") y un valor sospechoso (RAM 2500 a 24.000 km = $5.084.000).
5. **Prepagos (Fiat Flexcare, Toyota Service Pack, Ford Protect)** son otro precio, más bajo y condicionado. Quedan afuera de la primera versión.

## Orden propuesto para los recolectores

1. **Fiat y Jeep:** un JSON por marca, el caso más simple, y Fiat está entre las marcas más vendidas.
2. **Peugeot y Citroën:** el mismo sistema de tienda para las dos.
3. **Volkswagen:** la única lista con vigencia explícita por intervalo.
4. **Toyota:** tabla HTML de un concesionario, sin fecha.
5. **Renault y BYD:** PDF regional sin fecha, y una lista en dólares que está vencida.
6. **Ford:** los mejores datos. Se pensó que necesitaba un navegador automatizado, pero al volver a probar el sitio respondió a pedidos simples. Usar un navegador para pasar un bloqueo anti-bots sería esquivarlo: si el 403 vuelve, Ford queda afuera.
7. **Chevrolet:** sin fuente oficial. Se deja afuera o se marca como dato secundario.
