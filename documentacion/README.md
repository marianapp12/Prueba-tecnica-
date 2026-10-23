# Proceso de consulta de cuentas

## Contenido

1. [Descripción](#descripción)
2. [Requisitos e instalación](#requisitos-e-instalación)
3. [Configuración](#configuración)
4. [Ejecución](#ejecución)
5. [Cómo se procesan los datos](#cómo-se-procesan-los-datos)
6. [Errores y reintentos](#errores-y-reintentos)
7. [Archivos generados y reejecución](#archivos-generados-y-reejecución)
8. [Runbook: falla a las 3:00 a. m.](#runbook-falla-a-las-300-a-m)

## Descripción

El programa lee un archivo CSV de cuentas, valida los identificadores, consulta una API REST y guarda los resultados en SQLite y Excel. También registra la ejecución en un archivo de log para facilitar el seguimiento y el diagnóstico.

Flujo general:

1. Lee `cuentas.csv`.
2. Normaliza y valida los valores de `id_cuenta`.
3. Agrupa los IDs repetidos para consultar cada ID una sola vez por lote.
4. Consulta la API para cada ID válido.
5. Guarda los resultados y produce un resumen.

## Requisitos e instalación

- Python 3.10 o superior
- `pandas`
- `requests`
- `openpyxl` (para generar el archivo Excel)

SQLite forma parte de Python y no requiere instalación aparte. Instala las dependencias desde una terminal:

```bash
pip install pandas requests openpyxl
```

## Configuración

El programa carga `config.json` desde la carpeta del proyecto. La configuración actual es:

```json
{
  "api_url": "https://jsonplaceholder.typicode.com/posts/",
  "csv_path": "cuentas.csv",
  "db_path": "data/estado_proceso.db",
  "output_path": "salida.xlsx",
  "log_path": "logs/proceso.log",
  "request_timeout": 10,
  "max_retries": 3,
  "backoff_factor": 2
}
```

| Parámetro | Uso |
| --- | --- |
| `api_url` | URL base; el programa añade el ID consultado al final. |
| `csv_path` | Ruta al CSV de entrada, que debe incluir la columna `id_cuenta`. |
| `db_path` | Ruta de la base SQLite que conserva los resultados. |
| `output_path` | Ruta del Excel consolidado. |
| `log_path` | Ruta del archivo de log. |
| `request_timeout` | Tiempo máximo, en segundos, que se espera por cada respuesta de la API. |
| `max_retries` | Reintentos adicionales ante fallos temporales. |
| `backoff_factor` | Base utilizada para calcular la espera creciente entre intentos. |

Las rutas se interpretan desde la carpeta donde se ejecuta `main.py`. El programa crea las carpetas necesarias cuando una ruta las especifica. Con esta configuración, la base se guarda en `data` y el log en `logs`.

## Ejecución

1. Coloca `cuentas.csv` en la ubicación indicada por `csv_path` y verifica que tenga el encabezado `id_cuenta`.
2. Confirma que `config.json` esté en la carpeta del proyecto.
3. Abre una terminal en esa carpeta y ejecuta:

```bash
python main.py
```

Al finalizar, revisa el resumen de consola y el archivo Excel indicado en `output_path`.

## Cómo se procesan los datos

- Se eliminan espacios y comillas exteriores de los valores antes de validarlos.
- También se quitan espacios del encabezado, así que el CSV funciona aunque llegue con espacios antes de `id_cuenta`.
- Las líneas en blanco que separan registros se ignoran; las líneas anotadas para cada ID corresponden a las líneas físicas del archivo.
- Los valores vacíos, no numéricos o menores o iguales a cero se registran como inválidos y no se consultan a la API.
- Los IDs repetidos se consultan una sola vez por lote. Se registra cuántas veces aparecen y en qué líneas del CSV.
- Cada resultado se guarda en SQLite usando el ID como clave primaria. Los IDs que ya aparecen en la base se omiten en ejecuciones posteriores.

La decisión de deduplicar reduce llamadas y tiempo de ejecución sin perder la trazabilidad de las filas originales.

## Errores y reintentos

Los números de esta tabla son **códigos HTTP**: la API los devuelve para explicar cómo terminó la consulta. Una forma sencilla de recordarlos es:

- **404 — No encontrado:** ese identificador no existe en la API.
- **408 — Se agotó el tiempo:** la API tardó demasiado en responder.
- **429 — Demasiadas solicitudes:** la API pide bajar el ritmo y esperar.
- **5xx — Problema del servidor:** la API tuvo un fallo temporal. `5xx` significa cualquier código entre 500 y 599.
- **4xx — Problema con la solicitud:** `4xx` significa cualquier código entre 400 y 499. En este programa, 404 y 408/429 tienen un tratamiento propio; los demás se registran como solicitud inválida.

| Situación | Resultado | ¿Se reintenta? | Criterio |
| --- | --- | --- | --- |
| Respuesta exitosa | Guarda los datos de la API. | No | La consulta terminó correctamente. |
| 404 — No encontrado | Registra `no_existe`. | No | Repetir la misma consulta no hará que la cuenta exista. |
| 408 — Se agotó el tiempo; 429 — Demasiadas solicitudes | Reintenta; agotados los intentos, registra `error_tecnico`. | Sí | Esperar antes de consultar otra vez puede ayudar. |
| Otro código 4xx — Problema con la solicitud | Registra `invalido`. | No | Repetir la solicitud sin cambiarla normalmente dará el mismo resultado. |
| Código 5xx — Problema del servidor | Reintenta; agotados los intentos, registra `error_tecnico`. | Sí | El servicio remoto podría recuperarse. |
| Error de conexión o tiempo de espera | Reintenta; agotados los intentos, registra `error_tecnico`. | Sí | El problema puede ser transitorio. |

La regla fácil de recordar es: **se reintenta cuando el problema podría desaparecer esperando; no se reintenta cuando repetir la misma solicitud daría el mismo resultado**. En `consultar_cuenta_en_api()` de `main.py`, esto significa reintentar errores de conexión, tiempos de espera y códigos 408, 429 y 5xx. El 404 y los demás códigos 4xx se registran sin reintentar. Los identificadores inválidos se detectan antes de consultar la API.

Con `max_retries = 3`, se hace un intento inicial y hasta tres reintentos. Con `backoff_factor = 2`, las esperas son 2, 4 y 8 segundos.

## Archivos generados y reejecución

Con la configuración actual:

- `logs/proceso.log`: eventos de las cuentas procesadas.
- `data/estado_proceso.db`: resultados persistentes y control de IDs ya registrados.
- `salida.xlsx`: exportación de los resultados guardados.

La base de datos conserva el progreso entre ejecuciones. Al volver a ejecutar el programa, se omiten los IDs con resultado definitivo y se vuelven a consultar los que quedaron en `error_tecnico`. Si el proceso se interrumpe, los resultados ya guardados no se duplican y los IDs pendientes o con error técnico pueden procesarse de nuevo.

## Runbook: falla a las 3:00 a. m.

Sigue estos pasos en orden:

1. **Identifica el síntoma.** Lee el mensaje final de la consola y las últimas entradas de `logs/proceso.log`. Anota el ID afectado y el estado o causa.
2. **Comprueba la entrada.** Verifica que `cuentas.csv` exista, que incluya `id_cuenta` y que se pueda abrir. Corrige el archivo fuente si falta o está mal formado.
3. **Comprueba la configuración y las rutas.** Confirma que `config.json` exista y que `api_url`, `csv_path`, `db_path`, `output_path` y `log_path` apunten a las ubicaciones correctas.
4. **Si el error es técnico, comprueba la API y la red.** Revisa la conectividad y la disponibilidad del servicio. Los errores 5xx, HTTP 408/429, los tiempos de espera y los problemas de conexión pueden ser transitorios; los 404 y otros 4xx definitivos no se solucionan repitiendo exactamente la misma consulta.
5. **Comprueba la salida.** Verifica que haya espacio y permisos de escritura, que Excel no tenga `salida.xlsx` abierto y que los archivos de base y log estén accesibles.
6. **Reejecuta y valida.** Después de resolver la causa, ejecuta `python main.py`. Los IDs con un resultado definitivo se omiten; los que quedaron como `error_tecnico` se intentan de nuevo. Revisa el resumen y confirma que `salida.xlsx` refleje los resultados esperados.

**No borres `data/estado_proceso.db` para “probar de nuevo” sin respaldarla y entender el impacto:** contiene el historial que el programa usa para decidir qué IDs omitir. Si el problema persiste, conserva la base y los logs para el diagnóstico.
