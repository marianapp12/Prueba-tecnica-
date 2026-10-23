# Bitácora

## 1. Qué herramienta de IA usaste y para qué partes

Utilicé ChatGPT y Gemini como apoyo durante el desarrollo del proyecto. Me sirvieron para resolver dudas conceptuales de Python, comparar alternativas de almacenamiento (elegí SQLite por ser ligero) y recibir orientación sobre librerías, conexión a la API y organización de los bucles de procesamiento.

## 2. Prompts que de verdad te sirvieron, copiados tal cual

* ¿Qué ventajas tiene SQLite frente a guardar los datos en un diccionario de Python y cómo puedo crear una tabla 
para almacenar los resultados del proceso?"
* ¿Cómo puedo implementar reintentos en Python cuando una consulta a una API falla por problemas de conexión, 
sin detener todo el proceso?
* "¿Cómo puedo identificar los valores repetidos y vacíos de un archivo CSV para evitar consultas innecesarias 
a la API y registrar los errores encontrados?

## 3. Algo que la IA te entregó mal o incompleto y cómo te diste cuenta

* **Manejo de errores HTTP en la API:** La IA trataba casi todos los errores de la API de la misma manera. Me di cuenta al hacer pruebas y ver que un código 404 (cuenta inexistente) no debía reintentarse como si fuera una caída de red. Tuve que ajustar `consultar_cuenta_en_api` para separar los 404 de las fallas del servidor y de conexión.
* **Manejo de duplicados en el CSV:** Las propuestas iniciales sugerían borrar los duplicados de golpe (por ejemplo, con `drop_duplicates()`), pero así se perdía cuántas veces aparecía un ID y en qué líneas. Lo resolví agrupando los IDs y guardando las líneas exactas.
* **Limpieza de datos del CSV:** La IA no contemplaba bien las celdas con espacios en blanco o comillas sueltas, lo que podía causar errores al convertir los valores a números. Lo detecté al probar el archivo y lo resolví con la función `validar_identificador`, que limpia los valores antes de validarlos.

## 4. Qué decidiste tú sin consultarle

* **Uso de SQLite con clave primaria:** Decidí usar el ID de la cuenta como `PRIMARY KEY` para conservar el progreso si el proceso se interrumpe y evitar volver a consultar las cuentas ya resueltas.
* **Criterio para procesar IDs duplicados:** Decidí consultar cada ID único una sola vez, en lugar de hacer una llamada a la API por cada fila repetida. Repetir la consulta agrega tiempo y carga sin aportar información; por eso conservo el número de apariciones y las líneas exactas del CSV.
* **Preprocesamiento y validación:** Creé una etapa de limpieza antes de llamar a la API para filtrar IDs negativos, vacíos o alfanuméricos.
* **Estrategia de reintentos con backoff:** Definí esperas crecientes entre intentos para que los fallos temporales de red no detengan el lote.
* **Formato de reportes y logs:** Diseñé los mensajes de la consola y la estructura del Excel para que la información fuera clara y fácil de auditar más adelante.