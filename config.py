"""
Módulo de Configuración Central del Sistema Biométrico.
Carga variables de entorno y define constantes de operación para garantizar
modularidad, portabilidad y reproducibilidad en la investigación.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe antes de configurar opciones de FFmpeg
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)

# Configurar directorio temporal de caché para matplotlib y mediapipe
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_cache")

# Opciones de FFmpeg para streams RTSP (cámaras IP como la Tapo C310) con la menor latencia posible.
# IMPORTANTE: deben estar definidas ANTES de la primera llamada a cv2.VideoCapture.
#   - rtsp_transport;udp  -> sin bloqueos de retransmisión por micro-cortes Wi-Fi
#   - fflags;nobuffer     -> FFmpeg no acumula cuadros en su búfer interno de entrada
#   - flags;low_delay     -> decodificación de baja latencia
_RTSP_TRANSPORT = os.getenv("RTSP_TRANSPORT", "udp").lower()
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    f"rtsp_transport;{_RTSP_TRANSPORT}|fflags;nobuffer|flags;low_delay|threads;4|max_delay;0"
)


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
# Un valor de 0.50 es el estándar estricto de alta seguridad para evitar falsos positivos y falsas asociaciones.
FACE_DISTANCE_THRESHOLD = float(os.getenv("FACE_DISTANCE_THRESHOLD", "0.50"))

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

# -----------------------------------------------------------------------------
# Rendimiento / baja latencia
# -----------------------------------------------------------------------------
# Ancho máximo (px) al que se reduce cada cuadro DENTRO del hilo lector de la cámara.
# La Tapo C310 en 'stream1' envía ~2304x1296; procesarlo completo en CPU es inviable.
# 0 = no redimensionar. Recomendado: 960.
CAMERA_MAX_WIDTH = int(os.getenv("CAMERA_MAX_WIDTH", "1280"))

# Ancho (px) de la imagen que se le entrega al detector HOG. Menor = más rápido,
# pero detecta peor rostros lejanos. Recomendado: 400-640.
DETECTION_WIDTH = int(os.getenv("DETECTION_WIDTH", "480"))

# Se ejecuta detección + encoding solo 1 de cada N cuadros (los demás reutilizan el resultado).
PROCESS_EVERY_N_FRAMES = max(1, int(os.getenv("PROCESS_EVERY_N_FRAMES", "3")))

# Segundos sin recibir cuadros tras los cuales se reconecta automáticamente (cámaras IP/Wi-Fi).
# Valores muy bajos (3 s) provocan reconexiones constantes por micro-cortes del Wi-Fi.
CAMERA_RECONNECT_SECONDS = float(os.getenv("CAMERA_RECONNECT_SECONDS", "10.0"))

# -----------------------------------------------------------------------------
# Anti-suplantación / Liveness (Detección de parpadeo con Eye Aspect Ratio - EAR)
# -----------------------------------------------------------------------------
# Habilita o deshabilita la verificación activa de parpadeo humano para prevenir fotos estáticas
ENABLE_LIVENESS_CHECK = os.getenv("ENABLE_LIVENESS_CHECK", "false").lower() in ("true", "1", "yes")

# Umbral del Eye Aspect Ratio (EAR): por debajo de este valor se considera ojo cerrado
EAR_THRESHOLD = float(os.getenv("EAR_THRESHOLD", "0.22"))

# Fotogramas consecutivos requeridos con ojo cerrado para registrar un parpadeo
CONSECUTIVE_FRAMES_BLINK = int(os.getenv("CONSECUTIVE_FRAMES_BLINK", "2"))

# Cantidad mínima de parpadeos requeridos para validar sujeto vivo
REQUIRED_BLINKS = int(os.getenv("REQUIRED_BLINKS", "1"))

# -----------------------------------------------------------------------------
# Criptografía y Protección en Reposo (LFPDPPP)
# -----------------------------------------------------------------------------
_env_secret = os.getenv("SECRET_KEY")
if not _env_secret:
    # Si no existe SECRET_KEY en .env, generar una clave criptográfica de 256 bits
    import secrets
    _env_secret = secrets.token_hex(32)
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        if os.path.exists(env_file):
            with open(env_file, "a", encoding="utf-8") as _f:
                _f.write(f"\nSECRET_KEY={_env_secret}\n")
        else:
            with open(env_file, "w", encoding="utf-8") as _f:
                _f.write(f"SECRET_KEY={_env_secret}\n")
    except Exception as _err:
        pass

SECRET_KEY = _env_secret
ENCRYPT_BIOMETRICS = os.getenv("ENCRYPT_BIOMETRICS", "true").lower() in ("true", "1", "yes")

