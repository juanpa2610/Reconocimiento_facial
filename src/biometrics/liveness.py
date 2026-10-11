"""
Módulo de Detección de Vitalidad y Anti-Suplantación (Liveness Detection).
Previene ataques de presentación (Presentation Attacks) con fotografías impresas
o pantallas digitales mediante el análisis del parpadeo ocular (Eye Aspect Ratio - EAR).

FUNDAMENTO MATEMÁTICO:
Basado en el modelo de Soukupová y Čech (2016), el Eye Aspect Ratio (EAR) para un ojo
definido por 6 puntos de referencia p1, p2, p3, p4, p5, p6 se calcula como:

           ||p2 - p6||_2 + ||p3 - p5||_2
    EAR = ─────────────────────────────────
                  2 * ||p1 - p4||_2

Donde p1 y p4 corresponden a las comisuras externas e internas del ojo, y los pares
(p2, p6) y (p3, p5) miden la apertura vertical del párpado.
- Ojo abierto: EAR típico entre 0.28 y 0.38
- Ojo cerrado (parpadeo): EAR desciende por debajo de 0.20 - 0.22
"""

import numpy as np
from typing import List, Tuple, Dict, Optional
import config


def eye_aspect_ratio(eye_points: List[Tuple[float, float]]) -> float:
    """
    Calcula el Eye Aspect Ratio (EAR) a partir de los 6 puntos fiduciales del ojo.
    :param eye_points: Lista de 6 tuplas o arrays (x, y) ordenados secuencialmente.
    :return: Escalar flotante con el ratio de apertura ocular.
    """
    if len(eye_points) != 6:
        return 0.0

    pts = np.array(eye_points, dtype=np.float64)

    # Distancias verticales euclidianas
    dist_v1 = np.linalg.norm(pts[1] - pts[5])
    dist_v2 = np.linalg.norm(pts[2] - pts[4])

    # Distancia horizontal
    dist_h = np.linalg.norm(pts[0] - pts[3])

    if dist_h <= 1e-6:
        return 0.0

    ear = (dist_v1 + dist_v2) / (2.0 * dist_h)
    return float(ear)


class BlinkLivenessDetector:
    """
    Detector de vitalidad activo basado en recuento de parpadeos en tiempo real.
    Permite validar que el sujeto frente al lente es un ser humano vivo y no una fotografía estática.
    """

    def __init__(
        self,
        ear_threshold: float = config.EAR_THRESHOLD,
        consec_frames: int = config.CONSECUTIVE_FRAMES_BLINK,
        required_blinks: int = config.REQUIRED_BLINKS
    ):
        self.ear_threshold = ear_threshold
        self.consec_frames = consec_frames
        self.required_blinks = required_blinks

        self.consecutive_closed_frames: int = 0
        self.total_blinks: int = 0
        self.last_ear: float = 0.30
        self.is_live: bool = False

    def reset(self) -> None:
        """Reinicia el estado del detector de parpadeos."""
        self.consecutive_closed_frames = 0
        self.total_blinks = 0
        self.last_ear = 0.30
        self.is_live = False

    def update(self, landmarks_dict: Optional[Dict]) -> Tuple[bool, float, int]:
        """
        Procesa el diccionario de landmarks faciales (Dlib / face_recognition).
        :param landmarks_dict: Diccionario que contiene las claves 'left_eye' y 'right_eye'.
        :return: Tupla (es_sujeto_vivo, ear_promedio, total_parpadeos_detectados).
        """
        if not landmarks_dict or "left_eye" not in landmarks_dict or "right_eye" not in landmarks_dict:
            return self.is_live, self.last_ear, self.total_blinks

        left_eye = landmarks_dict["left_eye"]
        right_eye = landmarks_dict["right_eye"]

        if len(left_eye) != 6 or len(right_eye) != 6:
            return self.is_live, self.last_ear, self.total_blinks

        left_ear = eye_aspect_ratio(left_eye)
        right_ear = eye_aspect_ratio(right_eye)
        avg_ear = (left_ear + right_ear) / 2.0
        self.last_ear = round(float(avg_ear), 3)

        # Evaluación de cierre de párpados
        if avg_ear < self.ear_threshold:
            self.consecutive_closed_frames += 1
        else:
            # Si los ojos estuvieron cerrados por el número mínimo de cuadros consecutivos y se abren
            if self.consecutive_closed_frames >= self.consec_frames:
                self.total_blinks += 1
                if self.total_blinks >= self.required_blinks:
                    self.is_live = True

            self.consecutive_closed_frames = 0

        return self.is_live, self.last_ear, self.total_blinks

    def get_status_text(self) -> str:
        """Genera mensaje legible para el HUD visual."""
        if self.is_live:
            return f"VITALIDAD OK (Parpadeos: {self.total_blinks})"
        return f"ESPERANDO PARPADEO ({self.total_blinks}/{self.required_blinks}) | EAR: {self.last_ear:.2f}"
