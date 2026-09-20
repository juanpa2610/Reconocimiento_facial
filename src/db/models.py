"""
Modelos de Datos para el Sistema Biométrico.
Representa las entidades del dominio de investigación y control de acceso.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import numpy as np


@dataclass
class Estudiante:
    """
    Entidad Estudiante.
    IMPORTANTE: No contiene ninguna fotografía ni ruta a archivo de imagen.
    Únicamente almacena el vector matemático de 128 dimensiones (embedding).
    """
    id: Optional[int]
    matricula: str
    nombre: str
    carrera: str
    embedding: np.ndarray  # Arreglo NumPy unidimensional de 128 floats
    activo: bool = True
    created_at: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.embedding, np.ndarray):
            self.embedding = np.array(self.embedding, dtype=np.float64)
        if self.embedding.ndim != 1 or self.embedding.shape[0] != 128:
            raise ValueError(
                f"El embedding debe tener exactamente 128 dimensiones, recibido: {self.embedding.shape}"
            )


@dataclass
class RegistroAcceso:
    """
    Entidad de Auditoría y Acceso.
    Registra los eventos de verificación en tiempo real con la métrica de distancia euclidiana.
    """
    id: Optional[int]
    matricula: Optional[str]
    nombre: Optional[str]
    distancia: float
    estado: str  # 'PERMITIDO', 'DENEGADO'
    timestamp: Optional[str] = None
    estudiante_id: Optional[int] = None
