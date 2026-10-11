"""
Módulo de Diagnóstico y Prueba de Conexión de Cámaras (Camera Tester).
Verifica en segundo plano la disponibilidad de cámaras IP (RTSP) y cámaras locales
sin congelar la interfaz de usuario, entregando diagnósticos claros de conectividad.
"""

import time
import socket
import threading
from typing import Tuple, Optional
import cv2

from src.utils.security import build_rtsp_url, build_safe_display_url


def test_camera_connection(
    ip: str,
    user: str = "",
    password: str = "",
    port: int = 554,
    ruta: str = "/stream2",
    timeout_sec: float = 4.0
) -> Tuple[bool, str, Optional[Tuple[int, int]], float]:
    """
    Prueba la conexión a una cámara IP o dispositivo local.
    :return: (exito: bool, mensaje: str, resolucion: Optional[(ancho, alto)], fps: float)
    """
    ip_clean = ip.strip()
    if not ip_clean:
        return False, "La dirección IP o índice de cámara no puede estar vacío.", None, 0.0

    # 1. Si es dispositivo local (webcam USB / índice numérico)
    if ip_clean.isdigit():
        idx = int(ip_clean)
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            return False, f"No se pudo abrir el dispositivo local /dev/video{idx}.", None, 0.0
        
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            h, w = frame.shape[:2]
            return True, f"Cámara local detectada correctamente ({w}x{h} px).", (w, h), 30.0
        return False, f"El dispositivo /dev/video{idx} respondió pero no entregó fotogramas válidos.", None, 0.0

    # 2. Si es cámara de red (RTSP / IP)
    port_val = int(port) if port else 554

    # Verificación preliminar de socket TCP (IP y puerto alcanzables)
    sock_ok = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(timeout_sec, 2.5))
        res = sock.connect_ex((ip_clean, port_val))
        sock.close()
        sock_ok = (res == 0)
    except Exception as e:
        return False, f"Error al resolver dirección de red '{ip_clean}': {e}", None, 0.0

    if not sock_ok:
        return False, f"No se pudo conectar a {ip_clean}:{port_val}. Verifique que la cámara esté encendida y en la misma red LAN.", None, 0.0

    # Construir URL RTSP completa
    rtsp_url = build_rtsp_url(ip_clean, user, password, port_val, ruta)
    safe_url = build_safe_display_url(ip_clean, user, port_val, ruta)

    # Abrir con OpenCV y opciones de baja latencia
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        return False, f"Puerto {port_val} abierto, pero el flujo RTSP fue rechazado. Verifique usuario, contraseña o la ruta ({ruta}).", None, 0.0

    t_start = time.time()
    read_ok = False
    test_frame = None

    while (time.time() - t_start) < timeout_sec:
        ok, frame = cap.read()
        if ok and frame is not None:
            read_ok = True
            test_frame = frame
            break
        time.sleep(0.05)

    fps_val = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.release()

    if read_ok and test_frame is not None:
        h, w = test_frame.shape[:2]
        return True, f"Conexión exitosa a {safe_url}\nResolución: {w}x{h} px | FPS: ~{fps_val:.0f}", (w, h), float(fps_val)

    return False, f"Tiempo de espera agotado ({timeout_sec:.1f}s) al recibir stream de video en {safe_url}.", None, 0.0


def test_camera_connection_async(
    ip: str,
    user: str,
    password: str,
    port: int,
    ruta: str,
    callback,
    timeout_sec: float = 4.0
):
    """Ejecuta la prueba de conexión en un hilo secundario y llama al callback con el resultado."""
    def worker():
        resultado = test_camera_connection(ip, user, password, port, ruta, timeout_sec)
        callback(resultado)

    t = threading.Thread(target=worker, name="CameraTestThread", daemon=True)
    t.start()
