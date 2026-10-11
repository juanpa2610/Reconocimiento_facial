"""
Lector de video en HILO APARTE con baja latencia (ThreadedCamera).

PROBLEMA QUE RESUELVE
---------------------
Con cv2.VideoCapture normal, cap.read() devuelve el cuadro MÁS VIEJO que está en el búfer.
Si el procesamiento (detección + encoding facial) tarda más que el intervalo entre cuadros de la
cámara (típico con RTSP / cámaras IP como la Tapo C310), el búfer se llena y lo que se ve en
pantalla es de hace varios segundos (delay acumulativo).

SOLUCIÓN
--------
Un hilo dedicado lee la cámara SIN PARAR y conserva únicamente el último cuadro recibido.
El resto de la aplicación siempre obtiene el cuadro más reciente; los intermedios se descartan.
Además reduce el cuadro a CAMERA_MAX_WIDTH dentro del hilo lector y reconecta si el stream se cae.

API compatible con cv2.VideoCapture (isOpened / read / release).
"""

import threading
import time
from typing import Optional, Tuple, Union

import cv2
import numpy as np

import config


class ThreadedCamera:
    def __init__(
        self,
        source: Union[int, str] = config.VIDEO_SOURCE,
        max_width: int = config.CAMERA_MAX_WIDTH,
        reconnect_seconds: float = config.CAMERA_RECONNECT_SECONDS,
    ):
        self.source = source
        self.max_width = max_width
        self.reconnect_seconds = reconnect_seconds

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self._cond = threading.Condition()
        self._frame: Optional[np.ndarray] = None
        self._frame_id = 0          # contador de cuadros recibidos
        self._delivered_id = 0      # último cuadro entregado al consumidor

        self.fps = 0.0              # FPS reales de recepción de la cámara

        # Solo se reconecta si la fuente es "en vivo" (webcam o stream de red), no un archivo
        self._is_live = isinstance(source, int) or str(source).lower().startswith(
            ("rtsp://", "rtsps://", "http://", "https://", "rtmp://", "udp://", "tcp://")
        )

    # ------------------------------------------------------------------ apertura
    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        if isinstance(self.source, str):
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            cap.release()
            return None
        # Búfer mínimo (funciona en webcams V4L2/DirectShow; FFmpeg/RTSP lo ignora y usa nobuffer)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def start(self) -> bool:
        """Abre la fuente y lanza el hilo lector. Devuelve False si no se pudo abrir."""
        self._cap = self._open_capture()
        if self._cap is None:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, name="ThreadedCamera", daemon=True)
        self._thread.start()
        return True

    # ------------------------------------------------------------------ hilo lector
    def _publish(self, frame: np.ndarray):
        if self.max_width and frame.shape[1] > self.max_width:
            scale = self.max_width / frame.shape[1]
            frame = cv2.resize(
                frame, (self.max_width, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA
            )
        with self._cond:
            self._frame = frame
            self._frame_id += 1
            self._cond.notify_all()

    def _reader_loop(self):
        fps_t0 = time.time()
        fps_n = 0
        last_ok = time.time()

        while self._running:
            cap = self._cap
            ok, frame = (False, None)
            if cap is not None:
                ok, frame = cap.read()

            if ok and frame is not None:
                last_ok = time.time()
                self._publish(frame)
                fps_n += 1
                dt = time.time() - fps_t0
                if dt >= 1.0:
                    self.fps = fps_n / dt
                    fps_n, fps_t0 = 0, time.time()
                continue

            # --- lectura fallida ---
            if not self._is_live:
                break  # fin de archivo de video
            if time.time() - last_ok >= self.reconnect_seconds:
                print(f"[!] Sin cuadros de la cámara por {self.reconnect_seconds:.0f}s. Reconectando...")
                if cap is not None:
                    cap.release()
                self._cap = self._open_capture()
                last_ok = time.time()
            else:
                time.sleep(0.05)

        self._running = False
        with self._cond:
            self._cond.notify_all()

    # ------------------------------------------------------------------ API pública
    @property
    def frame_id(self) -> int:
        return self._frame_id

    def isOpened(self) -> bool:
        return self._running

    def read(self, timeout: float = 2.0) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Devuelve (True, copia_del_ultimo_cuadro) SOLO si llegó un cuadro nuevo desde la última lectura.
          - timeout > 0 : espera hasta ese tiempo por un cuadro nuevo (bucles de OpenCV/consola).
          - timeout = 0 : no bloquea; devuelve (False, None) si no hay cuadro nuevo (bucle de Tkinter).
        """
        with self._cond:
            if self._frame_id == self._delivered_id and timeout > 0:
                self._cond.wait_for(
                    lambda: self._frame_id != self._delivered_id or not self._running,
                    timeout=timeout,
                )
            if self._frame is None or self._frame_id == self._delivered_id:
                return False, None
            self._delivered_id = self._frame_id
            return True, self._frame.copy()

    def release(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
