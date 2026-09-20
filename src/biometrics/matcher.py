"""
Módulo de Comparación y Métrica Biométrica (Face Matcher).
Implementa la distancia euclidiana L2 y la similitud de coseno sobre arreglos vectoriales de 128 flotantes.

FUNDAMENTO MATEMÁTICO:
La distancia euclidiana entre dos vectores u, v en R^128 se define como:
    d(u, v) = ||u - v||_2 = sqrt( sum_{i=1}^{128} (u_i - v_i)^2 )

Si d(u, v) <= THRESHOLD (usualmente <= 0.55 o 0.60), se confirma que ambos vectores
pertenecen a la misma identidad biométrica.
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass

import config
from src.db.models import Estudiante


@dataclass
class MatchResult:
    reconocido: bool
    estudiante: Optional[Estudiante]
    distancia: float
    umbral: float
    confianza_pct: float  # Estimación porcentual de certidumbre biométrica


class FaceMatcher:
    def __init__(self, threshold: float = config.FACE_DISTANCE_THRESHOLD):
        self.threshold = threshold

    @staticmethod
    def euclidean_distance(u: np.ndarray, v: np.ndarray) -> float:
        """Calcula la distancia euclidiana L2 entre dos vectores 128-D."""
        return float(np.linalg.norm(u - v))

    @staticmethod
    def cosine_distance(u: np.ndarray, v: np.ndarray) -> float:
        """Calcula la distancia de coseno: 1 - (u . v) / (||u|| * ||v||)."""
        dot = np.dot(u, v)
        norm_u = np.linalg.norm(u)
        norm_v = np.linalg.norm(v)
        if norm_u == 0 or norm_v == 0:
            return 1.0
        similarity = dot / (norm_u * norm_v)
        # Asegurar rango numérico [-1.0, 1.0] por errores de precisión flotante
        similarity = np.clip(similarity, -1.0, 1.0)
        return float(1.0 - similarity)

    def calculate_confidence(self, distance: float) -> float:
        """
        Calcula una métrica de confianza porcentual normalizada (0% a 100%).
        Basada en la distancia relativa al umbral de corte.
        """
        if distance > self.threshold:
            # Entre el umbral y el doble del umbral decrece linealmente
            score = max(0.0, 50.0 - ((distance - self.threshold) / self.threshold) * 50.0)
        else:
            # Desde distancia 0.0 (100%) hasta el umbral (75%)
            score = 75.0 + ((self.threshold - distance) / self.threshold) * 25.0
        return round(float(score), 2)

    def match(
        self,
        candidate_embedding: np.ndarray,
        known_students: List[Estudiante]
    ) -> MatchResult:
        """
        Compara un embedding capturado en vivo contra la lista de estudiantes registrados.
        Utiliza álgebra lineal vectorizada de NumPy para máxima velocidad de ejecución.
        """
        if not known_students:
            return MatchResult(
                reconocido=False,
                estudiante=None,
                distancia=1.0,
                umbral=self.threshold,
                confianza_pct=0.0
            )

        # Crear matriz (N, 128) con todos los vectores registrados
        known_matrix = np.array([est.embedding for est in known_students], dtype=np.float64)

        # Distancia euclidiana vectorizada: ||M - c||_2 sobre cada fila
        # Equivalente a face_recognition.face_distance
        diff = known_matrix - candidate_embedding
        distances = np.linalg.norm(diff, axis=1)

        min_idx = int(np.argmin(distances))
        best_distance = float(distances[min_idx])
        best_student = known_students[min_idx]

        reconocido = best_distance <= self.threshold
        confianza = self.calculate_confidence(best_distance)

        return MatchResult(
            reconocido=reconocido,
            estudiante=best_student if reconocido else None,
            distancia=round(best_distance, 4),
            umbral=self.threshold,
            confianza_pct=confianza
        )
