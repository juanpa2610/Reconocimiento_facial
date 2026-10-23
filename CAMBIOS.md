# Cambios para eliminar el delay con la Tapo C310 (RTSP)

Copia estos archivos encima de los de tu proyecto (respetando las rutas):

| Archivo | Qué cambia |
|---|---|
| `src/utils/video_stream.py` | **NUEVO.** `ThreadedCamera`: hilo que lee la cámara sin parar y guarda solo el último cuadro; reduce el cuadro a `CAMERA_MAX_WIDTH`; reconecta si el stream se cae. |
| `src/utils/__init__.py` | Exporta `ThreadedCamera`. |
| `config.py` | Opciones FFmpeg de baja latencia para RTSP + variables `CAMERA_MAX_WIDTH`, `DETECTION_WIDTH`, `PROCESS_EVERY_N_FRAMES`, `CAMERA_RECONNECT_SECONDS`. |
| `src/biometrics/encoder.py` | Nuevo método `detect_face_locations_scaled()` (detecta en copia reducida y devuelve cajas en coordenadas originales). |
| `src/gui/app.py` | Usa `ThreadedCamera`, lectura no bloqueante, procesa 1 de cada N cuadros con caché y dibuja las cajas en todos los cuadros. Pestaña de registro también optimizada. |
| `src/modules/reconocimiento.py` | Igual que la GUI, para el modo consola. |
| `src/modules/registro.py` | `ThreadedCamera` + detección reducida. |
| `main.py` | La prueba de cámara (opción 9) usa `ThreadedCamera` y muestra resolución y FPS reales. |
| `.env.example` | Variables nuevas y ejemplo de URL RTSP. |

## Resumen de Mejoras del Sprint 2 (Integración Completa por Integrante)

| Integrante | Rol | Módulos Modificados | Funcionalidad Implementada |
|---|---|---|---|
| **Martínez Vera Josué Aldair** | Hardware & RTSP | `src/utils/video_stream.py`, `src/gui/app.py` | Eliminación definitiva del delay de 2 minutos vía `ThreadedCamera`, reconexión automática en micro-cortes, pestaña de configuración de cámaras IP/RTSP y prueba de conexión asíncrona. |
| **Bello Franco Samantha** | Base de Datos | `src/db/database.py`, `src/db/models.py` | Prevención de duplicados con rechazo de sobrescritura (`IntegrityError`), eliminación segura desvinculando FK para preservar auditoría histórica, y registro de variables científicas (`tiempo_acceso_segundos`, `tipo_usuario`, `condicion_luz`). |
| **Morales Hernández Guadalupe Aleida** | QA & Tester | `tests/test_performance.py`, `tests/test_biometrics.py` | Suite de benchmarks automatizados por etapa (adquisición, detección, extracción 128-D y matching), validación del SLA total <= 1.5s, fijación de semillas deterministas (`seed=42`) y pruebas de concurrencia. |
| **Solís Contreras Darian Giselle** | Jira Lead & UI | `src/gui/app.py`, `src/gui/dialogs.py` | Casilla obligatoria de consentimiento informado en la GUI para enrolamiento, trazabilidad de backlog en Jira y optimización de experiencia de usuario en control de acceso. |
| **Trujillo Trujillo Juan Pablo** | Scrum Master & Core | `src/biometrics/matcher.py`, `src/gui/app.py`, `config.py` | Desacoplamiento del procesamiento pesado en cola en segundo plano (`queue.Queue`), matching matricial vectorizado sub-milisegundo (< 1 ms) y validación de dimensiones finitas. |
| **Velázquez López Guadalupe** | Compliance & Privacidad | `src/utils/crypto.py`, `src/gui/dialogs.py`, `src/modules/admin.py` | Cifrado simétrico de templates biométricos en reposo (LFPDPPP), modal institucional con texto oficial de Aviso de Privacidad y exportación completa a CSV con métricas de investigación. |


## Sprint 3 (U3P3) - Integración y Calibración Final (Equipo 12)

### 1. Tabla de Responsabilidades por Integrante

| Integrante | Rol | Módulo Modificado | Problema Anterior | Corrección Implementada | Cómo Probarla |
|---|---|---|---|---|---|
| **Martínez Vera Josué Aldair** | Reconocimiento Biométrico | `config.py`, `.env.example`, `src/biometrics/matcher.py`, `src/gui/app.py`, `src/modules/reconocimiento.py`, `src/modules/cambios.py`, `src/utils/visualizer.py` | `.env.example` en 0.55 sobrescribía la calibración; inconsistencia entre etiquetas "Desconocido" y "No Registrado"; pruebas débiles en FaceMatcher. | Calibración estricta de `FACE_DISTANCE_THRESHOLD=0.50` en `.env.example` y `config.py`. Unificación a constante `NOMBRE_NO_REGISTRADO = "No Registrado"`. Verificación de que rostros no registrados nunca asocien alumno/ID y se muestren con recuadro rojo. | Ejecutar `python3 -m unittest tests/test_sprint3_validation.py -k test_facematcher`. Probar cámara con un sujeto no registrado para ver recuadro rojo y "No registrado". |
| **Bello Franco Samantha** | Filtros de Fecha, Hora y Nombre | `src/utils/text_filters.py`, `src/utils/__init__.py`, `src/gui/app.py` | Validación de fecha/hora por regex permitía fechas imposibles (2026-13-45) y horas imposibles (25:99); rangos invertidos comparados como texto; rangos parciales fallaban en silencio; búsqueda sensible a acentos. | Creación de módulo `text_filters.py` con `validar_fecha`, `validar_hora`, `validar_rango_fechas`, `validar_rango_horas` usando objetos `datetime.date`/`time`. Bloqueo de rangos incompletos con alerta en `lbl_aviso_filtro_accesos`. Normalización Unicode (`NFKD`) en `coincide_nombre` insensible a acentos, orden y mayúsculas. | Ejecutar `python3 -m unittest tests/test_sprint3_validation.py -k test_validacion_fechas`. En la GUI, ingresar `2026-13-45` o buscar `velazquez guadalupe` sin tilde para verificar coincidencia. |
| **Morales Hernández Guadalupe Aleida** | Usuarios, Seguridad y Consultas | `src/db/database.py`, `src/gui/app.py`, `src/gui/dialogs.py`, `ver_bd.py` | Consultas sin resultado quedaban en silencio; bloques `except Exception: pass` ocultaban fallos en rotación y base de datos; verificar que no haya contraseñas en texto claro. | Retroalimentación visible mediante `lbl_aviso_*` y modales cuando no hay coincidencias o hay sintaxis inválida. Reemplazo de fallos silenciosos por avisos y logging en auditoría (`db.log_auditoria`). Confirmación de hash PBKDF2 sin fugas de texto claro en terminal ni BD. | Ejecutar `python3 -m unittest tests/test_sprint3_validation.py -k test_cambio_password`. Buscar un nombre inexistente en la bitácora o padrón para ver la alerta visible. |
| **Velázquez López Guadalupe** | Reportes y Mantenimiento de Registros | `src/modules/admin.py`, `src/db/database.py`, `src/gui/app.py`, `config.py` | Reporte diario solo se generaba manualmente; typo en nombre de carpeta (`Archivos exel`); rotación de auditoría no purgaba por días y no garantizaba respaldo previo. | Automatización del reporte diario `itsx_accesos_YYYY-MM-DD.xlsx` de forma asíncrona al arrancar la app (`root.after(1000)`) y al cerrar. Configuración de `REPORTS_DIR` (por defecto `reportes/` con retrocompatibilidad con `Archivos exel`). Purgado de `registro_accesos` y `bitacora_auditoria` por días y tope máximo, asegurando respaldo antes de purga. | Ejecutar `python3 -m unittest tests/test_sprint3_validation.py -k test_reporte_diario`. Verificar generación del archivo en la carpeta de reportes y verificar el registro de auditoría `ROTACION_MANTENIMIENTO`. |
| **Solís Contreras Darian Giselle** | Validación de Matrículas ITSX | `src/utils/validators.py`, `src/gui/app.py`, `src/modules/registro.py`, `src/db/school_db_sim.py` | Validación previa aceptaba cualquier longitud o generaciones futuras; no conectada a todas las barras de búsqueda. | Regla estricta de matrícula escolar ITSX `AA7O#####` (9 caracteres exactos, año `AA` entre generación 07 y actual 26, clave 7, O tolerando 0, 5 dígitos numéricos). Rechazo de caracteres especiales (`23#...`, `$`, `?`), generaciones futuras (`277O...`) y longitudes erróneas. Conexión a buscador de accesos, padrón y registro escolar antes de consultar la BD. | Ejecutar `python3 -m unittest tests/test_sprint3_validation.py -k test_validacion_matricula`. En la GUI, escribir `23#00123` o `277O00123` en los buscadores y validar advertencia inmediata. |
| **Trujillo Trujillo Juan Pablo** | Coordinación, Login y Suite QA | `src/gui/app.py`, `src/gui/dialogs.py`, `tests/test_sprint3_validation.py` | La ventana principal del sistema se mostraba de fondo antes del login o el diálogo modal se bloqueaba en Linux X11/Wayland. | Desacoplamiento del flujo de inicio de sesión: la ventana de Login se lanza de forma exclusiva en primer plano; la ventana principal de vigilancia se inicializa y renderiza únicamente tras superar la autenticación. Cobertura de suite de pruebas unitarias integrales. | Ejecutar `python3 main.py` y verificar que solo aparece la ventana de Login. Ejecutar `.venv/bin/python3 -m unittest discover tests` para validar 43 pruebas exitosas. |

---

### 2. Problemas Técnicos Encontrados y Soluciones Aplicadas (Retrospectiva)

1. **Gestión de Ventanas en Linux (Tkinter X11):**
   - *Problema:* El uso de `root.withdraw()` mientras se instanciaba un `tk.Toplevel` como modal provocaba que el gestor de ventanas del sistema operativo congelara o no mapeara el diálogo de login, mostrando la consola colgada sin abrir la interfaz gráfica.
   - *Solución:* Se desacopló la secuencia en `iniciar_gui()`: primero se crea una ventana ligera y exclusiva para `LoginDialog` en la ventana raíz; al validar credenciales exitosamente, se destruye dicha ventana y se inicializa limpiamente `GuardApp(root, current_user)` en una nueva ventana principal con sus dimensiones completas (`1260x820`).
2. **Validaciones de Fechas y Horas Permisivas con Regex:**
   - *Problema:* Una expresión regular como `\d{4}-\d{2}-\d{2}` permitía fechas como `2026-13-45` o `2026-02-30`, y las comparaciones lexicográficas de cadenas (`"2026-10-25" > "2026-10-10"`) fallaban ante formatos no estandarizados o rangos de horas sobre días distintos.
   - *Solución:* Se implementó `src/utils/text_filters.py` utilizando `datetime.strptime()` para parsear objetos reales `datetime.date` y `datetime.time`. Se crearon validadores estrictos que devuelven mensajes claros y bloquean rangos invertidos o incompletos.
3. **Búsqueda Insensible a Acentos y Diacríticos:**
   - *Problema:* La búsqueda por tokens separaba palabras pero fallaba si el usuario escribía "Velazquez" sin acento y en la base de datos estaba "Velázquez".
   - *Solución:* Se incorporó la normalización Unicode mediante `unicodedata.normalize('NFKD')`, descomponiendo tildes y diacríticos antes de comparar tokens.
4. **Respaldo de Evidencia Previo a Purga de Base de Datos:**
   - *Problema:* Si la rotación de registros se ejecutaba automáticamente por superar los 30 días, existía el riesgo de perder trazabilidad si no se había exportado el reporte del día correspondiente.
   - *Solución:* Se conectó la rutina `rotar_registros_antiguos()` para que verifique e invoque `generar_reporte_diario_excel()` antes de ejecutar cualquier sentencia `DELETE`, registrando el resultado en la bitácora de auditoría.
5. **Restricción Estricta de Generaciones de Alumnos (267O):**
   - *Problema:* No había un control del año de generación ni de la estructura oficial del ITSX, permitiendo números de control ficticios o del futuro (`277O...`, `997O...`).
   - *Solución:* Se implementó el rango paramétrico `ANIO_INICIO_ITSX = 7` y `ANIO_ACTUAL_ITSX = 26`, validando exactamente los 9 caracteres bajo la sintaxis `AA7O#####` con tolerancia para digitación del número 0 en lugar de la letra O.

---

### 3. Resultado de la Suite de Pruebas

Toda la suite de pruebas unitarias (`.venv/bin/python3 -m unittest discover tests`) pasa al 100%:
```text
Ran 43 tests in 9.472s

OK
```


