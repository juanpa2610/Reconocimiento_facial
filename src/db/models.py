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
    tiempo_acceso_segundos: float = 0.0
    tipo_usuario: str = "estudiante"
    condicion_luz: str = "luz normal"


@dataclass
class Usuario:
    """
    Entidad de Usuario del Sistema con control de acceso basado en roles (RBAC).
    Permite diferenciar entre 'administrador' (acceso total) y 'operador' (solo vigilancia).
    """
    id: Optional[int]
    username: str
    password_hash: str
    nombre_completo: str
    rol: str  # 'administrador', 'operador'
    activo: bool = True
    created_at: Optional[str] = None

    def es_admin(self) -> bool:
        return self.rol.lower() == "administrador" and self.activo


@dataclass
class CamaraConfig:
    """
    Entidad de Configuración de Cámaras de Video / Sensores de Acceso.
    Permite registrar y switchear cámaras IP (RTSP) o locales dinámicamente sin tocar código.
    """
    id: Optional[int]
    nombre: str
    ip: str
    usuario: str
    password_enc: str  # Cifrada / protegida en reposo
    puerto: int = 554
    ruta_rtsp: str = "/stream2"
    activa: bool = False
    created_at: Optional[str] = None

    def get_password_plana(self) -> str:
        from src.utils.security import decrypt_camera_secret
        return decrypt_camera_secret(self.password_enc)

    def get_rtsp_url(self) -> str:
        from src.utils.security import build_rtsp_url
        return build_rtsp_url(self.ip, self.usuario, self.get_password_plana(), self.puerto, self.ruta_rtsp)

    def get_safe_url(self) -> str:
        from src.utils.security import build_safe_display_url
        return build_safe_display_url(self.ip, self.usuario, self.puerto, self.ruta_rtsp)


@dataclass
class RegistroAuditoria:
    """
    Entidad de Bitácora de Acciones Administrativas Sensibles.
    Garantiza trazabilidad de modificaciones y eliminaciones para la seguridad de la BD.
    """
    id: Optional[int]
    usuario: str
    operacion: str      # 'MODIFICAR_ESTUDIANTE', 'ELIMINAR_ESTUDIANTE', 'REGISTRAR_CAMARA', etc.
    entidad: str        # 'ESTUDIANTE', 'CAMARA', 'USUARIO', 'SISTEMA'
    detalles: str       # Registro de cambios sin almacenar contraseñas
    resultado: str      # 'EXITO', 'FALLIDO_AUTENTICACION', 'CANCELADO', 'ERROR'
    timestamp: Optional[str] = None

