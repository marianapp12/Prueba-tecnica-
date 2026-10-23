import os
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime
import pandas as pd
import requests
from requests.exceptions import RequestException


with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

os.makedirs(os.path.dirname(config['log_path']), exist_ok=True)
os.makedirs(os.path.dirname(config['db_path']), exist_ok=True)

logging.basicConfig(
    filename=config['log_path'],
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)

def log_linea(nivel, id_cuenta, intento, max_intentos, estado, causa):
    mensaje = (
        f"Cuenta {id_cuenta} - "
        f"Intento {intento}/{max_intentos} - "
        f"{estado} ({causa})"
    )

    print(mensaje)

    logger = logging.getLogger()

    if nivel == "WARNING":
        logger.warning(mensaje)
    elif nivel == "ERROR":
        logger.error(mensaje)
    else:
        logger.info(mensaje)

def log_general(nivel, texto):
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{hora} {nivel} {texto}")

def init_db():
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

def obtener_resueltos():
    conn = sqlite3.connect(config['db_path'])
    cur = conn.cursor()
    cur.execute('SELECT "ID Cuenta" FROM cuentas')
    filas = cur.fetchall()
    conn.close()
    return {str(f[0]) for f in filas}

def guardar_registro(reg):
    conn = sqlite3.connect(config['db_path'])
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO cuentas 
        ("ID Cuenta", "Estado", "Causa", "Detalle", "Repeticiones", "Líneas CSV", "Intentos", "UserID", "Título", "Cuerpo")
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

def exportar_excel():
    conn = sqlite3.connect(config['db_path'])
    df = pd.read_sql_query('SELECT * FROM cuentas', conn)
    conn.close()
    if not df.empty and config.get('output_path'):
        try:
            df.to_excel(config['output_path'], index=False)
        except Exception as e:
            print(f"Aviso: No se pudo generar el Excel. Detalle: {e}")
    return len(df)


def validar_id(valor):
    if pd.isna(valor) or str(valor).strip() == "":
        return "", "vacia"
    
    val_clean = str(valor).strip().strip('"').strip("'")
    if val_clean == "":
        return "", "vacia"

    try:
        num = int(val_clean)
        if num <= 0:
            return val_clean, "no_positivo"
        return str(num), "ok"
    except ValueError:
        return val_clean, "no_numerico"

def consultar_api(id_cuenta):
    url = f"{config['api_url']}{id_cuenta}"
    max_retries = config['max_retries']
    max_intentos_totales = max_retries + 1
    backoff = config['backoff_factor']
    
    for intento in range(1, max_intentos_totales + 1):
        try:
            res = requests.get(url, timeout=10)
            
            if res.status_code == 404:
                return {
                    "Estado": "no_existe", 
                    "Causa": "no_existe", 
                    "Detalle": f"La cuenta con identificador {id_cuenta} no existe en el sistema externo (Código HTTP 404 Not Found).",
                    "UserID": None, "Título": None, "Cuerpo": None, 
                    "Intentos": intento, "max_intentos": max_intentos_totales
                }
            
            if 400 <= res.status_code < 500:
                return {
                    "Estado": "invalido", 
                    "Causa": f"http_{res.status_code}", 
                    "Detalle": f"Error del cliente HTTP al consultar el recurso (Código HTTP {res.status_code}).",
                    "UserID": None, "Título": None, "Cuerpo": None, 
                    "Intentos": intento, "max_intentos": max_intentos_totales
                }
                
            if res.status_code >= 500:
                raise RequestException(f"Error en el servidor remoto (Código HTTP {res.status_code})")
                
            res.raise_for_status()
            data = res.json()
            return {
                "Estado": "ok", 
                "Causa": "ok", 
                "Detalle": "Consulta exitosa a la API REST. Los datos de la cuenta fueron recuperados correctamente.",
                "UserID": data.get("userId"), "Título": data.get("title"), "Cuerpo": data.get("body"),
                "Intentos": intento, "max_intentos": max_intentos_totales
            }
            
        except RequestException as e:
            if intento == max_intentos_totales:
                return {
                    "Estado": "error_tecnico", 
                    "Causa": "error_tecnico", 
                    "Detalle": f"Falla técnica o de conectividad con la API tras agotar los intentos. Motivo: {e}",
                    "UserID": None, "Título": None, "Cuerpo": None, 
                    "Intentos": intento, "max_intentos": max_intentos_totales
                }
            time.sleep(backoff ** intento)


def main():
    log_general("INFO", "============================================================")
    log_general("INFO", "PROCESO DE CONSULTA DE CUENTAS :)")
    log_general("INFO", "============================================================")

    if not os.path.exists(config['csv_path']):
        log_general("ERROR", f"No se encontró el archivo CSV: {config['csv_path']}")
        return

    init_db()
    resueltos = obtener_resueltos()
    
    log_general("INFO", f"Estado: {len(resueltos)} identificadores ya fueron procesados :)")
   
    df_csv = pd.read_csv(config['csv_path'], keep_default_na=False)
    total_filas = len(df_csv)

    log_general("INFO", f"CSV leido: {total_filas} identificadores encontrados :)")

    veces_repetido= {}
    num_lineas= {}
    ids_por_procesar = []

    for posicion_fila, fila in df_csv.iterrows():
        num_linea = posicion_fila + 2
        val_original = fila.get('id_cuenta', list(fila)[0])
        val_raw = val_original.strip()
        val_limpio, tipo_mensaje = validar_id(val_raw)

        clave = val_limpio if val_limpio != "" else f"Vacio no tiene tiene id: {num_linea}"

        if clave not in veces_repetido:
            veces_repetido[clave] = 0
            num_lineas[clave] = []
            ids_por_procesar.append((clave, val_raw, tipo_mensaje, num_linea))

        veces_repetido[clave] += 1
        num_lineas[clave].append(str(num_linea))

    cant_unicos = len(ids_por_procesar)
    repetidos = total_filas - cant_unicos
    log_general("INFO", f"Repetidos: {total_filas} identificadores -> {cant_unicos} unicos ({repetidos} aparecian repetidos).")

    max_intentos_defecto = config['max_retries'] + 1

    try:
        for clave, val_raw, tipo_mensaje, num_linea in ids_por_procesar:
            frec_veces = veces_repetido[clave]
            lineas_str = ", ".join(num_lineas[clave])

            if clave in resueltos:
                log_linea("INFO", clave, 0, max_intentos_defecto, "salta", "ya_resuelto")
                continue

            # CASO VACÍO
            if tipo_mensaje == "vacia":
                log_linea("WARNING", clave, 0, max_intentos_defecto, "invalido", "esta vacio")
                reg = {
                    "ID Cuenta": clave, "Estado": "invalido", "Causa": "identificador_invalido",
                    "Detalle": f"La línea {num_linea} del archivo CSV se encuentra vacía.",
                    "Repeticiones": frec_veces, "Líneas CSV": str(num_linea), "Intentos": 0,
                    "UserID": None, "Título": None, "Cuerpo": None
                }
                guardar_registro(reg)
                resueltos.add(clave)
                continue

            # CASO INVÁLIDO
            if tipo_mensaje in ["no_numerico", "no_positivo"]:
                log_linea("WARNING", val_raw, 0, max_intentos_defecto, "invalido", f"identificador_invalido: {tipo_mensaje}")
                detalle_msg = f"El valor '{val_raw}' no es un número válido."
                reg = {
                    "ID Cuenta": str(val_raw), "Estado": "invalido", "Causa": "identificador_invalido",
                    "Detalle": detalle_msg, "Repeticiones": frec_veces, "Líneas CSV": lineas_str, "Intentos": 0,
                    "UserID": None, "Título": None, "Cuerpo": None
                }
                guardar_registro(reg)
                resueltos.add(str(val_raw))
                continue

            # CASO NORMAL: CONSULTA API
            res_api = consultar_api(clave)
            
            nivel_log = "WARNING" if res_api["Estado"] != "ok" else "INFO"
            log_linea(nivel_log, clave, res_api["Intentos"], res_api["max_intentos"], res_api["Estado"], res_api["Causa"])

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
            guardar_registro(reg)
            resueltos.add(clave)

    except KeyboardInterrupt:
        print("\n")
        log_general("WARNING", "Proceso detenido manualmente por el usuario.")
        try:
            exportar_excel()
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        log_general("ERROR", f"Proceso detenido por error inesperado: {e}")
        try:
            exportar_excel()
        except Exception:
            pass
        sys.exit(1)

    filas_excel = exportar_excel()
    log_general("INFO", f"Excel generado: {config['output_path']} ({filas_excel} filas)")

    conn = sqlite3.connect(config['db_path'])
    df_db = pd.read_sql_query('SELECT * FROM cuentas', conn)
    conn.close()

    total_proc = len(df_db)
    resueltos_ok = len(df_db[df_db['Estado'] == 'ok'])
    no_existe_cnt = len(df_db[df_db['Estado'] == 'no_existe'])
    error_tec_cnt = len(df_db[df_db['Estado'] == 'error_tecnico'])
    invalidos_cnt = len(df_db[df_db['Estado'] == 'invalido'])
    fallidos_tot = no_existe_cnt + error_tec_cnt + invalidos_cnt

    log_general("INFO", "Resumen")
    print("============================================================")
    print("RESUMEN")
    print("============================================================")
    print(f"  Total de identificadores procesados: {total_proc}")
    print(f"  Resueltos (OK):            {resueltos_ok}")
    print(f"  Fallidos:                  {fallidos_tot}")
    print(f"    - No existe (404):       {no_existe_cnt}")
    print(f"    - Error tecnico:         {error_tec_cnt}")
    print(f"    - Identificador invalido:{invalidos_cnt}")
    print("============================================================")

if __name__ == '__main__':
    main()