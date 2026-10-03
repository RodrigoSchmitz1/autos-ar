"""
Costo total de tener un auto, para un perfil de uso.

Es el mismo calculo que mart_costo_total (dbt), pero con los datos del
usuario en vez del perfil fijo: lo usan el comparador y, mas adelante, el
sitio y el asistente ("la IA interpreta el texto, el codigo cuenta").
test_calculo.py verifica que, con el perfil por defecto, de exactamente lo
mismo que el mart: si las dos versiones divergen, el test falla.

  costo anual = km_anio x (combustible + service + repuestos por km)
              + patente anual
              + depreciacion anual = valor 0 km x (1 - proporcion conservada) / anios
              + seguro (12 x el mensual que carga el usuario)

La curva de depreciacion tiene tres puntos (1, 5 y 10 anios); entre ellos se
interpola en linea recta y mas alla de 10 anios se usa el de 10. La patente es
la del 0 km todos los anios: cota alta, la valuacion baja con la edad.
"""

from dataclasses import dataclass, field

COMPONENTES = ("combustible_por_km", "service_por_km", "repuestos_por_km", "patente_anual",
               "proporcion_conservada_1", "proporcion_conservada_5", "proporcion_conservada_10", "valor_0km")


@dataclass
class Perfil:
    km_anio: float = 15000
    anios: float = 5
    seguro_mensual: float = 0
    repuestos_originales: bool = False

    def __post_init__(self):
        if self.km_anio <= 0:
            raise ValueError("km_anio tiene que ser positivo")
        if self.anios <= 0:
            raise ValueError("anios tiene que ser positivo")
        if self.seguro_mensual < 0:
            raise ValueError("seguro_mensual no puede ser negativo")


@dataclass
class Costo:
    combustible_anual: float
    service_anual: float
    repuestos_anual: float
    patente_anual: float
    depreciacion_anual: float
    seguro_anual: float
    faltantes: list = field(default_factory=list)

    @property
    def completo(self):
        return not self.faltantes

    @property
    def anual(self):
        return (self.combustible_anual + self.service_anual + self.repuestos_anual
                + self.patente_anual + self.depreciacion_anual + self.seguro_anual)

    def mensual(self):
        return self.anual / 12

    def por_km(self, km_anio):
        return self.anual / km_anio


def proporcion_conservada(c, anios):
    """Proporcion del valor 0 km que conserva el auto a los `anios` anios."""
    puntos = [(1, c.get("proporcion_conservada_1")), (5, c.get("proporcion_conservada_5")),
              (10, c.get("proporcion_conservada_10"))]
    puntos = [(a, p) for a, p in puntos if p is not None]
    if not puntos:
        return None
    if anios <= puntos[0][0]:
        # Antes del primer punto: recta desde (0, 1), el 0 km vale el 100%.
        a, p = puntos[0]
        return 1 - (1 - p) * anios / a
    for (a0, p0), (a1, p1) in zip(puntos, puntos[1:]):
        if anios <= a1:
            return p0 + (p1 - p0) * (anios - a0) / (a1 - a0)
    return puntos[-1][1]


def calcular(c, perfil):
    """`c`: componentes de una version (una fila de mart_costo_componentes, como dict)."""
    faltantes = []

    def por_km(nombre):
        v = c.get(nombre)
        if v is None:
            faltantes.append(nombre.replace("_por_km", ""))
            return 0.0
        return v * perfil.km_anio

    combustible = por_km("combustible_por_km")
    service = por_km("service_por_km")
    nombre_rep = "repuestos_por_km_original" if perfil.repuestos_originales and c.get("repuestos_por_km_original") is not None else "repuestos_por_km"
    repuestos = c.get(nombre_rep)
    if repuestos is None:
        faltantes.append("repuestos")
        repuestos = 0.0
    else:
        repuestos *= perfil.km_anio
    patente = c.get("patente_anual")
    if patente is None:
        faltantes.append("patente")
        patente = 0.0
    prop = proporcion_conservada(c, perfil.anios)
    if prop is None or c.get("valor_0km") is None:
        faltantes.append("depreciacion")
        depreciacion = 0.0
    else:
        depreciacion = c["valor_0km"] * (1 - prop) / perfil.anios
    return Costo(combustible, service, repuestos, patente, depreciacion, perfil.seguro_mensual * 12, faltantes)
