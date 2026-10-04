"""
Tests de permitido_por_robots (ingesta/comun.py), con los robots.txt reales
que motivaron escribirlo. Uso: python -m ingesta.test_robots
"""

from ingesta.comun import permitido_por_robots as ok

CHEVROLET = """User-agent: *
Disallow: */fr/CA/
Disallow: /content/*
Disallow: /*?*
"""
GOOGLE_EJEMPLO = """User-agent: *
Disallow: /fotos/
Allow: /fotos/publicas/
Disallow: /*.pdf$

User-agent: autos-ar
Disallow: /privado/
"""
casos = [
    # El caso que urllib.robotparser resolvia mal: el comodin del medio.
    (CHEVROLET, "https://www.chevrolet.com.ar/content/dam/ficha.pdf", False),
    (CHEVROLET, "https://www.chevrolet.com.ar/suvs/tracker", True),
    (CHEVROLET, "https://www.chevrolet.com.ar/suvs/tracker?color=rojo", False),
    # Un grupo propio para el agente reemplaza al de "*".
    (GOOGLE_EJEMPLO, "https://x.com/fotos/a.jpg", True),
    (GOOGLE_EJEMPLO, "https://x.com/privado/a", False),
    ("User-agent: *\nDisallow: /fotos/\nAllow: /fotos/publicas/\n", "https://x.com/fotos/publicas/a.jpg", True),
    ("User-agent: *\nDisallow: /fotos/\nAllow: /fotos/publicas/\n", "https://x.com/fotos/b.jpg", False),
    # "$" ancla el final.
    ("User-agent: *\nDisallow: /*.pdf$\n", "https://x.com/a.pdf", False),
    ("User-agent: *\nDisallow: /*.pdf$\n", "https://x.com/a.pdf.html", True),
    # Sin reglas que coincidan, o Disallow vacio: permitido.
    ("User-agent: *\nDisallow:\n", "https://x.com/lo-que-sea", True),
    ("", "https://x.com/a", True),
]
errores = [(u, esperado) for robots, u, esperado in casos if ok(u, robots) != esperado]
for u, esperado in errores:
    print(f"MAL: {u} deberia dar {esperado}")
if errores:
    raise SystemExit(1)
print(f"OK: {len(casos)} casos de robots.txt")
