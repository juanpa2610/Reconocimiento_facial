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

