"""
Módulo de Configuración Central del Sistema Biométrico.
Carga variables de entorno y define constantes de operación para garantizar
modularidad, portabilidad y reproducibilidad en la investigación.
"""

import os
from pathlib import Path

# Configurar directorio temporal de caché para matplotlib y mediapipe
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_cache")

from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Configuración de Base de Datos
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "biometric_templates.db"))

# Parámetros PostgreSQL
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "biometria_db")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# Parámetros de Biometría y Visión Computacional
# Vector flotante de 128 dimensiones estándar (Dlib / face_recognition ResNet)
VECTOR_DIMENSION = 128

# Umbral de distancia euclidiana L2:
# Distancia <= FACE_DISTANCE_THRESHOLD indica una coincidencia de identidad positiva.
# Un valor de 0.50 a 0.55 es el estándar de alta seguridad para evitar falsos positivos.
FACE_DISTANCE_THRESHOLD = float(os.getenv("FACE_DISTANCE_THRESHOLD", "0.55"))

# Fuente de video: int si es cámara local (ej. 0), string si es URL RTSP / archivo
_raw_source = os.getenv("VIDEO_SOURCE", "0")
VIDEO_SOURCE = int(_raw_source) if _raw_source.isdigit() else _raw_source

# Cooldown en segundos entre registros de auditoría sucesivos en BD para un mismo alumno
ACCESS_LOG_COOLDOWN_SECONDS = float(os.getenv("ACCESS_LOG_COOLDOWN_SECONDS", "10.0"))

# Tiempo en segundos de persistencia visual del mensaje de acceso (evita parpadeo en pantalla)
VISUAL_STATUS_PERSISTENCE_SECONDS = float(os.getenv("VISUAL_STATUS_PERSISTENCE_SECONDS", "3.0"))

# Configuración del detector facial: 'hog' (más rápido en CPU) o 'cnn' (más preciso con GPU)
DETECTION_MODEL = os.getenv("DETECTION_MODEL", "hog")

# Habilitar Malla Facial (MediaPipe 468 landmarks) en tiempo real
ENABLE_FACE_MESH = os.getenv("ENABLE_FACE_MESH", "true").lower() in ("true", "1", "yes")
