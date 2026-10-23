# BITACORA.md

### 1. Qué herramienta de IA usaste y para qué partes
Utilicé ChatGPT y Gemini como apoyo durante el desarrollo del proyecto. Me sirvió para consultar dudas conceptuales de Python, 
comparar alternativas de almacenamiento (donde elegí SQLite por ser ligero) y recibir orientación sobre librerías, 
la estructura básica para la conexión a la API y la organización inicial de los bucles de procesamiento.

### 2. Dos o tres prompts que de verdad te sirvieron, copiados tal cual
* ¿Qué ventajas tiene SQLite frente a guardar los datos en un diccionario de Python y cómo puedo crear una tabla 
para almacenar los resultados del proceso?"
* ¿Cómo puedo implementar reintentos en Python cuando una consulta a una API falla por problemas de conexión, 
sin detener todo el proceso?
* "¿Cómo puedo identificar los valores repetidos y vacíos de un archivo CSV para evitar consultas innecesarias 
a la API y registrar los errores encontrados?

### 3. Algo que la IA te entregó mal o incompleto, y cómo te diste cuenta
* **Manejo de errores HTTP en la API:** La IA trataba cualquier error de la API casi por igual. Me di cuenta 
al hacer pruebas y ver que un código 404 (cuenta inexistente) no debía reintentarse como si fuera una caída de red.
Tuve que ajustar `consultar_api` para separar los 404 de las fallas de servidor/conexión.
* **Manejo de duplicados en el CSV:** Las propuestas iniciales sugerían borrar duplicados de golpe (como `drop_duplicates()`), pero me di cuenta de que se perdía la información de cuántas veces aparecía un ID y en qué líneas estaba. Lo solucioné usando diccionarios para agrupar y guardar las líneas exactas.
* **Limpieza de datos (CSV sucio):** La IA no contemplaba bien celdas con espacios en blanco o comillas sueltas, provocando errores al intentar convertir a número. Me di cuenta probando el archivo y lo resolví creando la función `validar_id` 
con `.strip()`.

### 4. Qué decidiste tú sin consultarle
* **Uso de SQLite con clave primaria:** Decidí usar el ID de la cuenta como `PRIMARY KEY` para que, si el proceso 
se llega a interrumpir, no se pierda lo avanzado ni se vuelvan a consultar cuentas resueltas.
* **Trazabilidad de duplicados:** Diseñé la lógica de guardar las repeticiones y las líneas exactas del CSV en lugar de simplemente descartar las filas repetidas.
* **Preprocesamiento y validación:** Creé una etapa previa de limpieza antes de llamar a la API para filtrar IDs negativos, vacíos o alfanuméricos.
* **Estrategia de reintentos con backoff:** Definí los tiempos de espera entre intentos e independicé el flujo para que los fallos temporales de red no detuvieran la ejecución del lote.
* **Formato de reportes y logs:** Diseñé los mensajes de la consola y la estructura del Excel final para que la información fuera clara y fácil de auditar si mas adelante fuera necesario.