# Proceso de consulta de cuentas médicas
## 1. Requisitos

Para ejecutar el proyecto se necesita:

- Python 3.10 o superior.
- pandas
- requests
- openpyxl

SQLite viene incluido con Python, por lo que no es necesario instalarlo por separado.

## 2. Configuración
Crea el archivo `config.json` con los siguientes parámetros:

{
    "csv_path": "cuentas.csv",
    "log_path": "salida/proceso.log",
    "db_path": "salida/cuentas.db",
    "output_path": "salida/resultado.xlsx",
    "api_url": "https://jsonplaceholder.typicode.com/posts/",
    "max_retries": 3,
    "backoff_factor": 2
}

Las rutas se pueden modificar según la ubicación de los archivos. El programa crea las carpetas necesarias para la base de datos y el log.
## 3. Preparación y ejecución

Guarda el archivo recibido como `cuentas.csv`, conservando el encabezado `id_cuenta` y los datos originales. No es necesario corregir manualmente los espacios, las comillas, los valores vacíos ni los identificadores repetidos.
Para ejecutar el proceso, abre una terminal en la carpeta del proyecto y escribe:
```bash
python main.py
```
El programa lee el CSV, valida los identificadores, consulta la API, guarda los resultados y genera el Excel consolidado.

## 4. Manejo de errores y reintentos
El programa distingue los errores según el resultado de cada consulta:

| Situación | Tratamiento | 
| ------- | ------- |
| Consulta exitosa (HTTP 200) | Guarda los datos obtenidos. | 
| Identificador inexistente (HTTP 404) | Registra el resultado como `no_existe`. |
| Otro error HTTP 4xx | Registra el resultado como `invalido`. |
| Error del servidor HTTP 5xx | Reintenta la consulta. |
| Problemas de conexión o tiempo de espera | Reintenta la consulta. | 
| Identificador vacío | Lo registra como inválido sin consultar la API. |
| Identificador no numérico o menor o igual a cero | Lo registra como inválido sin consultar la API. |

Los reintentos se aplican a los errores técnicos que podrían ser temporales, como los problemas de conexión y los errores HTTP 5xx. No se reintentan los errores HTTP 404 ni los demás errores HTTP 4xx, porque repetir la consulta normalmente no cambia la respuesta.

Con `max_retries = 3`, se realiza un intento inicial y hasta tres reintentos. El parámetro `backoff_factor = 2` establece esperas crecientes de 2, 4 y 8 segundos entre intentos.



## 5. Decisión sobre los identificadores repetidos

Cuando un identificador aparece varias veces en el CSV, se consulta una sola vez durante el procesamiento del archivo. En el Excel se registra la cantidad de apariciones y los números de línea donde se encontró, mediante las columnas `Repeticiones` y `Líneas CSV`.

Esta decisión evita consultas innecesarias y permite identificar dónde aparecía cada cuenta en el archivo original.
Los identificadores vacíos se registran por separado, utilizando el número de línea para distinguirlos.
## 6. Persistencia y reejecución
El programa utiliza SQLite para conservar los resultados entre ejecuciones. La tabla `cuentas` tiene el identificador como clave primaria y utiliza `INSERT OR IGNORE` para evitar registros duplicados.

Antes de consultar la API, el programa verifica qué identificadores ya están registrados y omite los que encuentra en la base de datos.

Si el proceso se interrumpe, los registros guardados permanecen en SQLite. Al ejecutarlo nuevamente, se omiten esos registros y se continúa con los identificadores que todavía no están guardados.

## 7. Resumen de ejecución

Al finalizar, el programa muestra un resumen con el total de registros guardados, las consultas exitosas y los resultados fallidos, agrupados por causa:

- Consultas exitosas.
- Identificadores inexistentes.
- Errores técnicos.
- Identificadores inválidos.

El resumen se calcula a partir de los registros almacenados en SQLite, por lo que corresponde al acumulado de la base de datos y no únicamente a la ejecución actual.

## 8. Runbook: ¿qué hacer si falla a las 3:00 a. m.?

Si el proceso falla durante la madrugada, sigue estos pasos:

1. **Revisar el log:** consultar los últimos mensajes para identificar el problema.
2. **Verificar el CSV:** comprobar que `cuentas.csv` exista y tenga el encabezado `id_cuenta`.
3. **Revisar la configuración:** confirmar que `config.json` contenga las rutas y la URL de la API correctas.
4. **Comprobar la conexión:** verificar el acceso a internet y la disponibilidad del servicio externo si aparecen errores técnicos.
5. **Revisar los archivos de salida:** comprobar que exista la carpeta correspondiente y que el Excel no esté bloqueado por otro proceso.
6. **Ejecutar nuevamente:** después de corregir el problema, ejecutar `python main.py`.
7. **Validar el resultado:** revisar el Excel y el resumen final para identificar las cuentas que requieren revisión.

Si el problema continúa, conservar el log y la base de datos para facilitar el diagnóstico. No eliminar la base de datos, ya que contiene los resultados utilizados para controlar las consultas repetidas.# Prueba-tecnica-
