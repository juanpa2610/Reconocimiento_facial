"""
Módulo de Visualización y HUD para OpenCV.
Genera interfaces visuales profesionales, dinámicas y de alta legibilidad
para las fases de Registro con Malla Facial (MediaPipe) y Reconocimiento con Cooldown anti-parpadeo.
"""

import cv2
import numpy as np
import time
from typing import Tuple, Optional, Any

try:
    import mediapipe as mp
    if hasattr(mp, "solutions"):
        mp_face_mesh = mp.solutions.face_mesh
        mp_drawing = mp.solutions.drawing_utils
        mp_drawing_styles = mp.solutions.drawing_styles
        MEDIAPIPE_AVAILABLE = True
    else:
        MEDIAPIPE_AVAILABLE = False
except Exception:
    MEDIAPIPE_AVAILABLE = False


class Visualizer:
    # Paleta de colores BGR
    COLOR_SUCCESS = (113, 204, 46)     # Verde esmeralda vivo (46, 204, 113 en RGB)
    COLOR_DANGER = (52, 73, 235)       # Rojo carmesí
    COLOR_INFO = (243, 156, 18)        # Cyan / azul informativo
    COLOR_WARNING = (23, 192, 235)     # Amarillo ámbar
    COLOR_BG_DARK = (20, 20, 20)       # Fondo oscuro
    COLOR_WHITE = (255, 255, 255)
    COLOR_MESH_CYAN = (255, 215, 0)    # Cyan / dorado brillante para la malla
    COLOR_GOLD = (0, 215, 255)

    @staticmethod
    def draw_banner(
        frame: np.ndarray,
        text: str,
        color: Tuple[int, int, int] = COLOR_INFO,
        position: str = "top"
    ):
        """Dibuja una barra de estado informativa superior o inferior con transparencia."""
        h, w, _ = frame.shape
        if position == "top":
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 48), (15, 15, 15), -1)
            cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
            cv2.putText(
                frame, text, (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA
            )
        elif position == "bottom":
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, h - 45), (w, h), (15, 15, 15), -1)
            cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
            cv2.putText(
                frame, text, (20, h - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, Visualizer.COLOR_WHITE, 1, cv2.LINE_AA
            )

    @staticmethod
    def draw_face_mesh(frame: np.ndarray, face_landmarks: Any):
        """Renderiza los 468 puntos de la malla facial (MediaPipe Face Mesh)."""
        if not MEDIAPIPE_AVAILABLE or face_landmarks is None:
            return

        # Dibujar teselación de la superficie facial
        mp_drawing.draw_landmarks(
            image=frame,
            landmark_list=face_landmarks,
            connections=mp_face_mesh.FACEMESH_TESSELATION,
            landmark_drawing_spec=None,
            connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style()
        )
        # Dibujar contornos destacados (ojos, labios, cejas, óvalo facial)
        mp_drawing.draw_landmarks(
            image=frame,
            landmark_list=face_landmarks,
            connections=mp_face_mesh.FACEMESH_CONTOURS,
            landmark_drawing_spec=None,
            connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style()
        )

    @staticmethod
    def draw_facial_landmarks(frame: np.ndarray, landmarks_dict: dict):
        """
        Dibuja los hitos anatómicos faciales y la malla conectada en pantalla.
        Soporta los puntos de Dlib / face_recognition como malla estructural de alta definición.
        """
        if not landmarks_dict:
            return

        color_line = (235, 206, 135)   # Cyan suave
        color_point = (113, 204, 46)   # Verde esmeralda

        for feature, points in landmarks_dict.items():
            pts = np.array(points, np.int32)
            # Dibujar polilíneas conectando los puntos del rasgo facial
            is_closed = feature in ("left_eye", "right_eye", "top_lip", "bottom_lip")
            cv2.polylines(frame, [pts], isClosed=is_closed, color=color_line, thickness=1, lineType=cv2.LINE_AA)
            for (x, y) in points:
                cv2.circle(frame, (x, y), 2, color_point, -1, lineType=cv2.LINE_AA)

    @staticmethod
    def draw_registration_hud(
        frame: np.ndarray,
        mesh_detected: bool,
        status_msg: str,
        alerta_duplicado: Optional[str] = None
    ):
        """HUD para el registro interactivo con retroalimentación en vivo."""
        h, w, _ = frame.shape

        if alerta_duplicado:
            # Notificación de duplicado en rojo prominente
            overlay = frame.copy()
            cv2.rectangle(overlay, (w // 10, h // 2 - 50), (w * 9 // 10, h // 2 + 50), (20, 20, 160), -1)
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
            cv2.rectangle(frame, (w // 10, h // 2 - 50), (w * 9 // 10, h // 2 + 50), Visualizer.COLOR_DANGER, 2)
            cv2.putText(
                frame, "ALERTA: ROSTRO YA REGISTRADO", (w // 10 + 20, h // 2 - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA
            )
            cv2.putText(
                frame, alerta_duplicado[:55], (w // 10 + 20, h // 2 + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, Visualizer.COLOR_WARNING, 1, cv2.LINE_AA
            )
        else:
            # Color según estado
            color = Visualizer.COLOR_SUCCESS if mesh_detected else Visualizer.COLOR_WARNING

            # Banner superior
            Visualizer.draw_banner(
                frame,
                f"REGISTRO CON MALLA FACIAL: {status_msg}",
                color=color,
                position="top"
            )

            # Banner inferior con atajos
            footer = "[ESPACIO / ENTER]: Capturar Template 128-D  |  [Q]: Cancelar" if mesh_detected else "Enfoque su rostro al centro de la camara  |  [Q]: Salir"
            Visualizer.draw_banner(frame, footer, position="bottom")

    @staticmethod
    def draw_access_feedback_card(
        frame: np.ndarray,
        estado: str,
        nombre: str,
        matricula: Optional[str],
        distancia: float,
        confianza: float,
        tiempo_restante: float
    ):
        """
        Dibuja una tarjeta central tipo torniquete de control de acceso con persistencia visual.
        Permanece estable en pantalla evitando parpadeos bruscos.
        """
        h, w, _ = frame.shape
        es_autorizado = (estado == "PERMITIDO")

        card_w = min(560, w - 40)
        card_h = 100
        x1 = (w - card_w) // 2
        y1 = h - card_h - 60
        x2 = x1 + card_w
        y2 = y1 + card_h

        color_borde = Visualizer.COLOR_SUCCESS if es_autorizado else Visualizer.COLOR_DANGER
        bg_color = (20, 35, 20) if es_autorizado else (20, 20, 40)

        # Fondo con transparencia
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), bg_color, -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color_borde, 2)

        # Barra lateral indicadora
        cv2.rectangle(frame, (x1, y1), (x1 + 10, y2), color_borde, -1)

        if es_autorizado:
            titulo = "ACCESO AUTORIZADO"
            sub1 = f"Bienvenido(a): {nombre}"
            sub2 = f"Matricula: {matricula}  |  Distancia L2: {distancia:.2f}  |  Confianza: {confianza:.0f}%"
        else:
            titulo = "ACCESO DENEGADO"
            sub1 = "Sujeto no registrado en la base de datos"
            sub2 = f"Distancia minima obtenida: {distancia:.2f} > 0.55"

        cv2.putText(
            frame, titulo, (x1 + 25, y1 + 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.85, color_borde, 2, cv2.LINE_AA
        )
        cv2.putText(
            frame, sub1, (x1 + 25, y1 + 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, Visualizer.COLOR_WHITE, 2, cv2.LINE_AA
        )
        cv2.putText(
            frame, sub2, (x1 + 25, y1 + 86),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, cv2.LINE_AA
        )

    @staticmethod
    def draw_recognition_box(
        frame: np.ndarray,
        box: Tuple[int, int, int, int],
        nombre: str,
        matricula: Optional[str],
        distancia: float,
        confianza: float,
        es_autorizado: bool
    ):
        """Dibuja el recuadro y etiqueta para un rostro individual en tiempo real."""
        top, right, bottom, left = box
        color = Visualizer.COLOR_SUCCESS if es_autorizado else Visualizer.COLOR_DANGER

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        # Etiqueta sobre el rostro
        label = f"{nombre[:15]} ({distancia:.2f})" if es_autorizado else f"No registrado ({distancia:.2f})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

        y_label = max(top - 8, th + 8)
        cv2.rectangle(frame, (left, y_label - th - 6), (left + tw + 10, y_label + 4), color, -1)
        cv2.putText(
            frame, label, (left + 5, y_label - 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA
        )
