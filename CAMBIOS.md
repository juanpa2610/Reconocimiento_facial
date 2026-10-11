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

## Pasos en tu máquina
1. Reemplaza los archivos.
2. En tu `.env` real (no el .example) pon la URL del **stream2**:
   `VIDEO_SOURCE=rtsp://USUARIO:CLAVE@IP_DE_LA_CAMARA:554/stream2`
   (USUARIO/CLAVE son los de la "Cuenta de cámara" creada en la app Tapo.)
3. Opcional, para afinar: `DETECTION_WIDTH` (320-640) y `PROCESS_EVERY_N_FRAMES` (2-5).
4. Prueba primero con la opción 9 del menú (`python3 main.py --cli`): debe verse fluido y mostrar los fps.

Nota: el encoding facial ahora se calcula sobre el cuadro completo (hasta 960 px) y no sobre una copia a la mitad;
es el mismo tamaño de imagen que usa el registro, así que la comparación de vectores queda más consistente.
