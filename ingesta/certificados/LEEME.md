# Certificados intermedios

Intermedios publicos que algunos servidores no mandan bien. `ingesta/comun.py`
los suma a los certificados del sistema; la verificacion TLS sigue completa.

| Archivo | Para | Por que | Fuente |
|---|---|---|---|
| `sectigo_dv_r36.pem` | www.alperovichsa.com.ar (service VW) | el servidor manda otro intermedio de Sectigo; en Linux falla con CERTIFICATE_VERIFY_FAILED | http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt (la URL que figura en el propio certificado), vence en 2036 |
