"""
Resume las tasas de interés que cobraron los bancos, financieras y cooperativas a las personas en
las últimas semanas, según la Superintendencia Financiera de Colombia (datos abiertos, formato 414),
en un archivo pequeño que lee la app Mis Finanzas para proponer la tasa de cada deuda.

Uso: python tasas/tasas.py tasas.json

Solo usa la biblioteca estándar de Python. Lo corre cada semana .github/workflows/tasas.yml.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

# Tasas de interés activas por tipo de crédito, últimos dos meses (una fila por cada combinación de
# entidad, producto, plazo, municipio…: unos 14 millones). Por eso se consulta entidad por entidad.
TASAS = "https://www.datos.gov.co/resource/qzsc-9esp.json"
# Tasa de interés bancario corriente de cada mes. La usura (lo máximo legal) es 1,5 veces esa tasa.
CORRIENTE = "https://www.datos.gov.co/resource/pare-7x5i.json"

# Bancos, compañías de financiamiento, cooperativas financieras e instituciones oficiales (el FNA).
TIPOS_DE_ENTIDAD = [1, 4, 32, 22]
# Cuántas semanas se promedian: con una sola, una entidad pequeña puede no tener créditos de algo.
SEMANAS = 4
# Con menos créditos que estos en esas semanas, el promedio no dice mucho y no se publica.
MINIMO_DE_CREDITOS = 10

NOMBRES = {"Banagrario": "Banco Agrario"}


def consultar(url, **parametros):
    """Una consulta SoQL; reintenta unas veces, porque el servidor a veces se demora o falla."""
    direccion = url + "?" + urllib.parse.urlencode({"$" + k: v for k, v in parametros.items()})
    for intento in range(4):
        try:
            with urllib.request.urlopen(direccion, timeout=180) as respuesta:
                return json.load(respuesta)
        except Exception as e:
            if intento == 3:
                raise
            print(f"  reintento ({e})", file=sys.stderr)
            time.sleep(15 * (intento + 1))


def producto(tipo, nombre):
    """La clave del tipo de crédito en la app; None si no es algo que use una persona."""
    n = nombre.lower()
    if n.startswith("tarjeta de crédito para ingresos"):
        return "tarjeta"
    if n == "libre inversión":
        return "libre_inversion"
    if n.startswith("libranza"):
        return "libranza"
    if n == "vehículo":
        return "vehiculo"
    # Los de UVR suman la inflación aparte: su tasa no se compara con las demás.
    if tipo == "Vivienda" and "colocación en pesos" in n:
        return "vivienda"
    if n == "crédito rotativo":
        return "rotativo"
    if n == "créditos de consumo de bajo monto":
        return "bajo_monto"
    if n.startswith("créditos educativos"):
        return "educativo"
    if tipo == "Crédito productivo" and "mayor monto" not in n:
        return "microcredito"
    return None


def nombre_corto(nombre):
    """«Banco Falabella S.A.» → «Banco Falabella»; «Nu Colombia C.F.» → «Nu Colombia»."""
    corto = re.sub(r"\s*(S\.A\.|C\.F\.|Compa[ñn][ií]a [Dd]e [Ff]inanciamiento)", "", nombre).strip()
    return NOMBRES.get(corto, corto)


def entre(desde, hasta):
    return f"fecha_corte between '{desde.isoformat()}T00:00:00' and '{hasta.isoformat()}T00:00:00'"


def usura(hoy):
    """La usura vigente hoy para consumo y para consumo de bajo monto, E.A. en %."""
    filas = consultar(
        CORRIENTE,
        where=f"vigencia_desde <= '{hoy.isoformat()}T00:00:00' and vigencia_hasta >= '{hoy.isoformat()}T00:00:00'",
    )
    resultado = {}
    for fila in filas:
        corriente = float(fila["interes_bancario_corriente"].strip().rstrip("%").replace(",", "."))
        modalidad = fila["modalidad"].upper()
        clave = {"CONSUMO Y ORDINARIO": "consumo", "CONSUMO BAJO MONTO": "bajo_monto"}.get(modalidad)
        if clave:
            resultado[clave] = round(corriente * 1.5, 2)
            resultado["desde"] = fila["vigencia_desde"][:10]
            resultado["hasta"] = fila["vigencia_hasta"][:10]
    return resultado


def main(salida):
    hasta = date.fromisoformat(consultar(TASAS, select="max(fecha_corte) as ultima")[0]["ultima"][:10])
    desde = hasta - timedelta(weeks=SEMANAS - 1)
    print(f"Semanas del {desde} al {hasta}", file=sys.stderr)
    entidades = []
    for tipo in TIPOS_DE_ENTIDAD:
        lista = consultar(
            TASAS,
            select="codigo_entidad,nombre_entidad,sum(montos_desembolsados) as monto",
            where=f"{entre(desde, hasta)} and tipo_entidad={tipo} and tipo_de_persona='Natural'",
            group="codigo_entidad,nombre_entidad",
            limit=500,
        )
        for e in lista:
            print(f"  {e['nombre_entidad']}", file=sys.stderr)
            filas = consultar(
                TASAS,
                select="tipo_de_cr_dito,producto_de_cr_dito,"
                "sum(tasa_efectiva_promedio*montos_desembolsados) as ponderada,"
                "sum(montos_desembolsados) as monto,sum(numero_de_creditos) as creditos",
                # Las compras con tarjeta a un mes casi nunca cobran intereses: bajarían el promedio
                # de la tarjeta muy por debajo de lo que se paga al diferir.
                where=f"{entre(desde, hasta)} and tipo_entidad={tipo} and codigo_entidad={e['codigo_entidad']} "
                "and tipo_de_persona='Natural' and tasa_efectiva_promedio > 0 "
                "and plazo_de_cr_dito != 'Consumos a un mes' "
                "and tipo_de_cr_dito in ('Consumo', 'Vivienda', 'Crédito productivo')",
                group="tipo_de_cr_dito,producto_de_cr_dito",
                limit=500,
            )
            # Promedio ponderado por lo prestado: un crédito grande pesa más que uno pequeño.
            suma = {}
            for f in filas:
                clave = producto(f["tipo_de_cr_dito"], f["producto_de_cr_dito"])
                if clave is None:
                    continue
                ponderada, monto, creditos = suma.get(clave, (0.0, 0.0, 0))
                suma[clave] = (
                    ponderada + float(f["ponderada"]),
                    monto + float(f["monto"]),
                    creditos + int(float(f["creditos"])),
                )
            tasas = {
                clave: round(ponderada / monto, 2)
                for clave, (ponderada, monto, creditos) in sorted(suma.items())
                if monto > 0 and creditos >= MINIMO_DE_CREDITOS
            }
            if tasas:
                entidades.append({
                    "id": f"{tipo}-{e['codigo_entidad']}",
                    "nombre": nombre_corto(e["nombre_entidad"]),
                    "tasas": tasas,
                    "_monto": float(e["monto"]),
                })
    # De la que más le presta a las personas a la que menos: las más conocidas quedan primero.
    entidades.sort(key=lambda e: -e["_monto"])
    for e in entidades:
        del e["_monto"]
    resultado = {
        "fuente": "Superintendencia Financiera de Colombia: tasas de interés activas por tipo de crédito "
        "(formato 414), en datos.gov.co. Promedio ponderado por monto, personas naturales, E.A. en %.",
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "usura": usura(date.today()),
        "entidades": entidades,
    }
    with open(salida, "w", encoding="utf-8", newline="\n") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=1)
        archivo.write("\n")
    print(f"{len(entidades)} entidades en {salida}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tasas.json")
