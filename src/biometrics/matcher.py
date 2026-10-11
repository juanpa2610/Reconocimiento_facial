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
        self._cached_students: List[Estudiante] = []
        self._cached_matrix: Optional[np.ndarray] = None

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
        Calcula un puntaje de similitud normalizado (0% a 100%).
        Calibrado heurísticamente contra el umbral de decisión L2 (tau = 0.55).
        """
        if distance > self.threshold:
            # Entre el umbral y el doble del umbral decrece linealmente
            score = max(0.0, 50.0 - ((distance - self.threshold) / self.threshold) * 50.0)
        else:
            # Desde distancia 0.0 (100%) hasta el umbral (75%)
            score = 75.0 + ((self.threshold - distance) / self.threshold) * 25.0
        return round(float(score), 2)

    def set_known_students(self, known_students: List[Estudiante]) -> None:
        """
        Precarga y almacena en caché la matriz (N, 128) de templates biométricos en memoria RAM.
        Elimina la sobrecarga de reconstruir arreglos NumPy en cada fotograma analizado.
        """
        self._cached_students = list(known_students) if known_students else []
        if self._cached_students:
            self._cached_matrix = np.array(
                [est.embedding for est in self._cached_students],
                dtype=np.float64
            )
        else:
            self._cached_matrix = np.empty((0, config.VECTOR_DIMENSION), dtype=np.float64)

    def match_candidate(self, candidate_embedding: np.ndarray) -> MatchResult:
        """
        Compara un embedding en vivo directamente contra la matriz persistida en caché.
        Alcanza latencias inferiores a 0.5 milisegundos para cientos de estudiantes.
        """
        if self._cached_matrix is None or len(self._cached_students) == 0:
            return MatchResult(
                reconocido=False,
                estudiante=None,
                distancia=1.0,
                umbral=self.threshold,
                confianza_pct=0.0
            )

        # Distancia euclidiana vectorizada: ||M - c||_2 fila por fila sin bucles Python
        diff = self._cached_matrix - candidate_embedding
        distances = np.linalg.norm(diff, axis=1)

        min_idx = int(np.argmin(distances))
        best_distance = float(distances[min_idx])
        best_student = self._cached_students[min_idx]

        reconocido = best_distance <= self.threshold
        confianza = self.calculate_confidence(best_distance)

        return MatchResult(
            reconocido=reconocido,
            estudiante=best_student if reconocido else None,
            distancia=round(best_distance, 4),
            umbral=self.threshold,
            confianza_pct=confianza
        )

    def match(
        self,
        candidate_embedding: np.ndarray,
        known_students: Optional[List[Estudiante]] = None
    ) -> MatchResult:
        """
        Compara un embedding contra la lista de estudiantes registrados.
        Si se suministra una lista nueva o no inicializada, actualiza la caché automáticamente.
        """
        if known_students is not None:
            # Si la lista provista es diferente en tamaño o no está cacheada, actualizar
            if (
                self._cached_matrix is None or
                len(known_students) != len(self._cached_students) or
                known_students is not self._cached_students
            ):
                self.set_known_students(known_students)

        return self.match_candidate(candidate_embedding)

    def match_with_timing(
        self,
        candidate_embedding: np.ndarray,
        known_students: Optional[List[Estudiante]] = None
    ) -> Tuple[MatchResult, float]:
        """
        Ejecuta el matching y retorna (MatchResult, tiempo_en_milisegundos).
        Útil para pruebas de benchmark, medición de hipótesis y auditoría de latencia.
        """
        import time
        t0 = time.perf_counter()
        result = self.match(candidate_embedding, known_students)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return result, round(elapsed_ms, 3)

