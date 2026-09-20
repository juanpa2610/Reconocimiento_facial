"""
Módulo de Extracción y Codificación Biométrica (Face Encoder).
Implementa la detección, alineación y extracción del vector matemático (embedding de 128-D)
utilizando redes neuronales convolucionales profundas basadas en ResNet (Dlib / face_recognition).

PRINCIPIO DE PRIVACIDAD:
Las matrices de imagen recibidas se procesan exclusivamente en memoria volátil y se descartan
tan pronto como se obtiene el vector numérico. No se efectúa escritura en disco de ninguna fotografía.
"""

import cv2
import face_recognition
import numpy as np
from typing import List, Tuple, Optional

import config


class FaceEncoder:
    def __init__(self, model: str = config.DETECTION_MODEL):
        """
        Inicializa el codificador facial.
        :param model: 'hog' (optimizado para CPU) o 'cnn' (requiere GPU/CUDA)
        """
        self.model = model

    def convert_to_rgb(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Convierte una imagen de BGR (OpenCV) a RGB (face_recognition / dlib)."""
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    def detect_face_locations(self, frame_rgb: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Localiza las coordenadas de los rostros en el fotograma.
        Retorna una lista de tuplas con formato (top, right, bottom, left).
        """
        return face_recognition.face_locations(frame_rgb, model=self.model)

    def extract_encodings(
        self,
        frame_rgb: np.ndarray,
        locations: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> List[np.ndarray]:
        """
        Calcula el vector de embedding de 128 dimensiones para cada rostro detectado.
        """
        if locations is None:
            locations = self.detect_face_locations(frame_rgb)
        
        if not locations:
            return []

        # Extraer vectores de 128 flotantes normalizados
        encodings = face_recognition.face_encodings(frame_rgb, known_face_locations=locations)
        return [np.array(enc, dtype=np.float64) for enc in encodings]

    def extract_single_face_encoding(self, frame_bgr: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[Tuple[int, int, int, int]], str]:
        """
        Procesa un fotograma para el proceso de REGISTRO.
        Asegura que exista exactamente UN solo rostro claramente enfocado.
        Retorna (embedding_128d, bounding_box, mensaje_estado).
        """
        rgb_frame = self.convert_to_rgb(frame_bgr)
        locations = self.detect_face_locations(rgb_frame)

        if len(locations) == 0:
            return None, None, "No se detectó ningún rostro en el encuadre."
        
        if len(locations) > 1:
            return None, None, "Se detectaron múltiples rostros. Por favor enfóquese solo una persona."

        # Exactamente 1 rostro detectado
        box = locations[0]
        encodings = face_recognition.face_encodings(rgb_frame, known_face_locations=[box])

        if not encodings or len(encodings) == 0:
            return None, None, "No fue posible generar el embedding biométrico del rostro."

        vector_128d = np.array(encodings[0], dtype=np.float64)

        # Validación formal del tamaño del template
        if vector_128d.shape != (128,):
            return None, None, f"Error en dimensión del vector: {vector_128d.shape}"

        return vector_128d, box, "Rostro capturado y vectorizado con éxito."
