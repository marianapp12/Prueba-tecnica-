import csv
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
import pandas as pd
import requests
from requests.exceptions import RequestException


with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

directorio_log = os.path.dirname(config['log_path'])
if directorio_log:
    os.makedirs(directorio_log, exist_ok=True)

logging.basicConfig(
    filename=config['log_path'],
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)

def registrar_log_cuenta(nivel, id_cuenta, intento, max_intentos, estado, causa):
    mensaje = (
        f"  -> Cuenta {id_cuenta} | Intento {intento}/{max_intentos} "
        f"-> {estado} ({causa})"
    )

    print(mensaje)

    logger = logging.getLogger()

    if nivel == "WARNING":
        logger.warning(mensaje)
    elif nivel == "ERROR":
        logger.error(mensaje)
    else:
        logger.info(mensaje)

def registrar_mensaje_proceso(nivel, texto):
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{hora} {nivel} {texto}")
    logger = logging.getLogger()
    if nivel == "WARNING":
        logger.warning(texto)
    elif nivel == "ERROR":
        logger.error(texto)
    else:
        logger.info(texto)

def inicializar_base_datos():
    directorio_db = os.path.dirname(config['db_path'])
    if directorio_db:
        os.makedirs(directorio_db, exist_ok=True)

    conn = sqlite3.connect(config['db_path'])
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cuentas (
            "ID Cuenta" TEXT PRIMARY KEY,
            "Estado" TEXT,
            "Causa" TEXT,
            "Detalle" TEXT,
            "Repeticiones" INTEGER,
            "Líneas CSV" TEXT,
            "Intentos" INTEGER,
            "UserID" INTEGER,
            "Título" TEXT,
            "Cuerpo" TEXT
        )
    ''')
    conn.commit()
    conn.close()

def obtener_ids_resueltos():
    conn = sqlite3.connect(config['db_path'])
    cur = conn.cursor()
    cur.execute('SELECT "ID Cuenta" FROM cuentas WHERE "Estado" != ?', ('error_tecnico',))
    filas = cur.fetchall()
    conn.close()
    return {str(f[0]) for f in filas}

def guardar_resultado_cuenta(reg):
    conn = sqlite3.connect(config['db_path'])
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO cuentas
        ("ID Cuenta", "Estado", "Causa", "Detalle", "Repeticiones", "Líneas CSV", "Intentos", "UserID", "Título", "Cuerpo")
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT("ID Cuenta") DO UPDATE SET
            "Estado" = excluded."Estado",
            "Causa" = excluded."Causa",
            "Detalle" = excluded."Detalle",
            "Repeticiones" = excluded."Repeticiones",
            "Líneas CSV" = excluded."Líneas CSV",
            "Intentos" = excluded."Intentos",
            "UserID" = excluded."UserID",
            "Título" = excluded."Título",
            "Cuerpo" = excluded."Cuerpo"
    ''', (
        str(reg['ID Cuenta']),
        reg['Estado'],
        reg['Causa'],
        reg.get('Detalle'),
        reg['Repeticiones'],
        reg['Líneas CSV'],
        reg['Intentos'],
        reg.get('UserID'),
        reg.get('Título'),
        reg.get('Cuerpo')
    ))
    conn.commit()
    conn.close()

def actualizar_repeticiones_y_lineas_csv(id_cuenta, repeticiones, lineas_csv):
    conn = sqlite3.connect(config['db_path'])
    cur = conn.cursor()
    cur.execute(
        'UPDATE cuentas SET "Repeticiones" = ?, "Líneas CSV" = ? WHERE "ID Cuenta" = ?',
        (repeticiones, lineas_csv, str(id_cuenta))
    )
    conn.commit()
    conn.close()

def exportar_resultados_a_excel():
    conn = sqlite3.connect(config['db_path'])
    df = pd.read_sql_query('SELECT * FROM cuentas', conn)
    conn.close()
    if not df.empty and config.get('output_path'):
        df.to_excel(config['output_path'], index=False)
    return len(df)


def validar_identificador(valor):
    val_clean = str(valor).strip().strip('"').strip("'").strip()
    if val_clean == "":
        return "", "vacia"

    try:
        num = int(val_clean)
        if num <= 0:
            return val_clean, "no_positivo"
        return str(num), "ok"
    except ValueError:
        return val_clean, "no_numerico"

def consultar_cuenta_en_api(id_cuenta):
    url = f"{config['api_url']}{id_cuenta}"
    max_retries = config['max_retries']
    max_intentos_totales = max_retries + 1
    backoff = config['backoff_factor']

    def resultado_tecnico(causa, detalle, intento):
        return {
            "Estado": "error_tecnico",
            "Causa": causa,
            "Detalle": detalle,
            "UserID": None,
            "Título": None,
            "Cuerpo": None,
            "Intentos": intento,
            "max_intentos": max_intentos_totales
        }

    for intento in range(1, max_intentos_totales + 1):
        try:
            res = requests.get(url, timeout=config['request_timeout'])

            if res.status_code == 404:
                return {
                    "Estado": "no_existe",
                    "Causa": "no_existe",
                    "Detalle": f"La cuenta con identificador {id_cuenta} no existe en el sistema externo (Código HTTP 404 Not Found).",
                    "UserID": None, "Título": None, "Cuerpo": None,
                    "Intentos": intento, "max_intentos": max_intentos_totales
                }

            if res.status_code in (408, 429) or res.status_code >= 500:
                causa = f"http_{res.status_code}"
                if intento == max_intentos_totales:
                    return resultado_tecnico(
                        causa,
                        f"Error HTTP {res.status_code} tras agotar los intentos.",
                        intento
                    )
                time.sleep(backoff ** intento)
                continue

            if 400 <= res.status_code < 500:
                return {
                    "Estado": "invalido",
                    "Causa": f"http_{res.status_code}",
                    "Detalle": f"Error del cliente HTTP al consultar el recurso (Código HTTP {res.status_code}).",
                    "UserID": None, "Título": None, "Cuerpo": None,
                    "Intentos": intento, "max_intentos": max_intentos_totales
                }

            try:
                data = res.json()
            except ValueError as e:
                return resultado_tecnico(
                    "respuesta_invalida",
                    f"La API devolvió una respuesta JSON inválida: {e}",
                    intento
                )
            if not isinstance(data, dict):
                return resultado_tecnico(
                    "respuesta_invalida",
                    "La API devolvió un JSON con formato inesperado.",
                    intento
                )
            if any(isinstance(data.get(campo), (dict, list)) for campo in ("userId", "title", "body")):
                return resultado_tecnico(
                    "respuesta_invalida",
                    "La API devolvió campos con un formato no compatible.",
                    intento
                )
            return {
                "Estado": "ok",
                "Causa": "ok",
                "Detalle": "Consulta exitosa a la API REST. Los datos de la cuenta fueron recuperados correctamente.",
                "UserID": data.get("userId"), "Título": data.get("title"), "Cuerpo": data.get("body"),
                "Intentos": intento, "max_intentos": max_intentos_totales
            }

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            causa = "timeout" if isinstance(e, requests.exceptions.Timeout) else "conexion"
            if intento == max_intentos_totales:
                return resultado_tecnico(
                    causa,
                    f"La consulta agotó los intentos disponibles. Motivo: {e}",
                    intento
                )
            time.sleep(backoff ** intento)

        except RequestException as e:
            return resultado_tecnico(
                "error_solicitud",
                f"No se pudo completar la solicitud a la API. Motivo: {e}",
                intento
            )

    return resultado_tecnico(
        "error_tecnico",
        "La consulta terminó sin una respuesta válida.",
        max_intentos_totales
    )


def ejecutar_proceso():
    registrar_mensaje_proceso("INFO", "------------------------------------------------------------")
    registrar_mensaje_proceso("INFO", "INICIO DEL PROCESO DE CONSULTA DE CUENTAS")
    registrar_mensaje_proceso("INFO", "------------------------------------------------------------")

    if not os.path.exists(config['csv_path']):
        registrar_mensaje_proceso("ERROR", f"No se encontró el archivo CSV: {config['csv_path']}")
        return

    total_filas = 0

    veces_repetido= {}
    num_lineas= {}
    ids_por_procesar = []

    with open(config['csv_path'], 'r', encoding='utf-8-sig', newline='') as archivo_csv:
        lector_csv = csv.reader(archivo_csv)
        encabezados = next(lector_csv, [])
        encabezados = [str(columna).strip() for columna in encabezados]
        if 'id_cuenta' not in encabezados:
            registrar_mensaje_proceso("ERROR", "El CSV no contiene la columna obligatoria 'id_cuenta'.")
            sys.exit(1)
        indice_id = encabezados.index('id_cuenta')

        for fila_csv in lector_csv:
            num_linea = lector_csv.line_num
            if not fila_csv or (
                all(valor.strip() == "" for valor in fila_csv)
                and any(valor != "" for valor in fila_csv)
            ):
                continue

            total_filas += 1
            val_raw = fila_csv[indice_id].strip() if indice_id < len(fila_csv) else ""
            val_limpio, tipo_mensaje = validar_identificador(val_raw)

            clave = val_limpio if val_limpio != "" else f"Vacio no tiene tiene id: {num_linea}"

            if clave not in veces_repetido:
                veces_repetido[clave] = 0
                num_lineas[clave] = []
                ids_por_procesar.append((clave, val_raw, tipo_mensaje, num_linea))

            veces_repetido[clave] += 1
            num_lineas[clave].append(str(num_linea))

    registrar_mensaje_proceso("INFO", f"CSV leído: {total_filas} identificadores encontrados.")

    inicializar_base_datos()
    resueltos = obtener_ids_resueltos()
    registrar_mensaje_proceso("INFO", f"IDs con resultado definitivo: {len(resueltos)}.")

    cant_unicos = len(ids_por_procesar)
    repetidos = total_filas - cant_unicos
    registrar_mensaje_proceso(
        "INFO",
        f"IDs leídos: {total_filas}; IDs únicos: {cant_unicos}; "
        f"apariciones repetidas: {repetidos}."
    )

    max_intentos_defecto = config['max_retries'] + 1

    omitidos_ya_resueltos = 0
    try:
        for clave, val_raw, tipo_mensaje, num_linea in ids_por_procesar:
            frec_veces = veces_repetido[clave]
            lineas_str = ", ".join(num_lineas[clave])

            if clave in resueltos:
                actualizar_repeticiones_y_lineas_csv(clave, frec_veces, lineas_str)
                registrar_log_cuenta("INFO", clave, 0, max_intentos_defecto, "omitida", "ya_resuelta")
                omitidos_ya_resueltos += 1
                continue

            # CASO VACÍO
            if tipo_mensaje == "vacia":
                registrar_log_cuenta("WARNING", clave, 0, max_intentos_defecto, "inválida", "identificador_vacío")
                reg = {
                    "ID Cuenta": clave, "Estado": "invalido", "Causa": "identificador_invalido",
                    "Detalle": f"La línea {num_linea} del archivo CSV se encuentra vacía.",
                    "Repeticiones": frec_veces, "Líneas CSV": str(num_linea), "Intentos": 0,
                    "UserID": None, "Título": None, "Cuerpo": None
                }
                guardar_resultado_cuenta(reg)
                continue

            # CASO INVÁLIDO
            if tipo_mensaje in ["no_numerico", "no_positivo"]:
                registrar_log_cuenta("WARNING", val_raw, 0, max_intentos_defecto, "inválido", f"identificador_inválido: {tipo_mensaje}")
                detalle_msg = f"El valor '{val_raw}' no es un número válido."
                reg = {
                    "ID Cuenta": clave, "Estado": "invalido", "Causa": "identificador_invalido",
                    "Detalle": detalle_msg, "Repeticiones": frec_veces, "Líneas CSV": lineas_str, "Intentos": 0,
                    "UserID": None, "Título": None, "Cuerpo": None
                }
                guardar_resultado_cuenta(reg)
                continue

            # CASO NORMAL: CONSULTA API
            try:
                res_api = consultar_cuenta_en_api(clave)
            except Exception as e:
                logging.exception("Error inesperado al procesar la cuenta %s", clave)
                res_api = {
                    "Estado": "error_tecnico",
                    "Causa": "error_procesamiento",
                    "Detalle": f"Error inesperado durante la consulta: {e}",
                    "UserID": None,
                    "Título": None,
                    "Cuerpo": None,
                    "Intentos": 0,
                    "max_intentos": max_intentos_defecto
                }

            nivel_log = "WARNING" if res_api["Estado"] != "ok" else "INFO"
            registrar_log_cuenta(nivel_log, clave, res_api["Intentos"], res_api["max_intentos"], res_api["Estado"], res_api["Causa"])

            reg = {
                "ID Cuenta": clave,
                "Estado": res_api["Estado"],
                "Causa": res_api["Causa"],
                "Detalle": res_api["Detalle"],
                "Repeticiones": frec_veces,
                "Líneas CSV": lineas_str,
                "Intentos": res_api["Intentos"],
                "UserID": res_api["UserID"],
                "Título": res_api["Título"],
                "Cuerpo": res_api["Cuerpo"]
            }
            guardar_resultado_cuenta(reg)

    except KeyboardInterrupt:
        print("\n")
        registrar_mensaje_proceso("WARNING", "Proceso detenido manualmente por el usuario.")
        try:
            exportar_resultados_a_excel()
        except Exception:
            logging.exception("No se pudo exportar el Excel al detener el proceso.")
        sys.exit(0)
    except Exception as e:
        registrar_mensaje_proceso("ERROR", f"Proceso detenido por un error inesperado: {e}")
        try:
            exportar_resultados_a_excel()
        except Exception:
            logging.exception("No se pudo exportar el Excel después del error.")
        sys.exit(1)

    filas_excel = exportar_resultados_a_excel()
    registrar_mensaje_proceso("INFO", f"Excel generado: {config['output_path']} ({filas_excel} filas).")

    conn = sqlite3.connect(config['db_path'])
    df_db = pd.read_sql_query('SELECT * FROM cuentas', conn)
    conn.close()

    claves_lote = {item[0] for item in ids_por_procesar}
    df_lote = df_db[df_db["ID Cuenta"].astype(str).isin(claves_lote)]
    resueltos_ok = len(df_lote[df_lote["Estado"] == "ok"])
    fallidos_tot = len(df_lote[df_lote["Estado"].isin(["no_existe", "error_tecnico", "invalido"])])
    fallidos_por_causa = (
        df_lote[df_lote["Estado"].isin(["no_existe", "error_tecnico", "invalido"])]
        .groupby("Causa")
        .size()
        .sort_values(ascending=False)
    )

    registrar_mensaje_proceso("INFO", "Resumen de esta ejecución")
    print()
    print("+---------------------- RESUMEN ----------------------+")
    print(f"  -> IDs únicos del CSV:       {len(claves_lote)}")
    print(f"  -> Ya resueltos (omitidos):  {omitidos_ya_resueltos}")
    print(f"  -> Consultas exitosas:       {resueltos_ok}")
    print(f"  -> Resultados fallidos:      {fallidos_tot}")
    for causa, cantidad in fallidos_por_causa.items():
        print(f"     |-> {causa}: {cantidad}")
    print("+-----------------------------------------------------+")

if __name__ == '__main__':
    ejecutar_proceso()