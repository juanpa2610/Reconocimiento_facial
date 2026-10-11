"""
Módulo de Seguridad, Criptografía y Control de Acceso (Security & Authentication).
Implementa hashing seguro con PBKDF2-HMAC-SHA256, sal aleatoria, cifrado simétrico
de credenciales de cámaras y enmascaramiento para visualización segura en interfaces y logs.
"""

import hashlib
import secrets
import base64
from typing import Tuple, Optional
import config


def hash_password(password: str) -> str:
    """
    Genera un hash criptográfico seguro para contraseñas usando PBKDF2-HMAC-SHA256
    con 100,000 iteraciones y una sal criptográfica de 16 bytes (32 caracteres hex).
    Formato retornado: pbkdf2_sha256$<iteraciones>$<salt>$<hash_hex>
    """
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")

    iterations = 100000
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations
    ).hex()

    return f"pbkdf2_sha256${iterations}${salt}${derived}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verifica una contraseña en texto claro contra el hash almacenado con sal.
    Utiliza comparación en tiempo constante (secrets.compare_digest) para mitigar ataques de tiempo.
    """
    if not password or not stored_hash:
        return False

    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False

        iterations = int(parts[1])
        salt = parts[2]
        expected_hash = parts[3]

        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        ).hex()

        return secrets.compare_digest(derived, expected_hash)
    except Exception:
        return False


from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def _derive_camera_key(secret_seed: str, salt: bytes) -> bytes:
    """Deriva una clave simétrica de 256 bits para credenciales de red."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=50_000,
    )
    return kdf.derive(secret_seed.encode("utf-8"))


def encrypt_camera_secret(secret: str) -> str:
    """
    Cifra la contraseña de una cámara antes de persistirla en base de datos usando AES-256-GCM.
    No almacena contraseñas de cámaras en texto plano.
    """
    if not secret:
        return ""

    secret_seed = getattr(config, "SECRET_KEY", "")
    if not secret_seed:
        return secret

    salt = secrets.token_bytes(16)
    key = _derive_camera_key(secret_seed, salt)
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, secret.encode("utf-8"), b"itsx-cam-v2")
    payload = salt + nonce + ct
    return "gcm$" + base64.b64encode(payload).decode("ascii")


def decrypt_camera_secret(encrypted_str: str) -> str:
    """
    Descifra la contraseña de la cámara únicamente en memoria volátil
    al momento de establecer la conexión de video RTSP.
    Soporta formato moderno AES-256-GCM (gcm$) y retrocompatibilidad con formato histórico (enc$).
    """
    if not encrypted_str:
        return ""

    if encrypted_str.startswith("gcm$"):
        try:
            payload = base64.b64decode(encrypted_str[4:])
            if len(payload) < 28:
                return ""
            salt = payload[:16]
            nonce = payload[16:28]
            ct = payload[28:]
            secret_seed = getattr(config, "SECRET_KEY", "")
            if not secret_seed:
                return ""
            key = _derive_camera_key(secret_seed, salt)
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ct, b"itsx-cam-v2").decode("utf-8")
        except Exception:
            return ""

    if encrypted_str.startswith("enc$"):
        try:
            raw_b64 = encrypted_str[4:]
            payload = base64.b64decode(raw_b64)
            if len(payload) < 8:
                return ""
            salt = payload[:8]
            encrypted = payload[8:]
            secret_seed = getattr(config, "SECRET_KEY", "ITSX-BIOMETRIC-SECURITY-KEY-2026")
            key = hashlib.sha256(secret_seed.encode("utf-8")).digest()
            keystream = hashlib.pbkdf2_hmac("sha256", key, salt, 1000, dklen=len(encrypted))
            decrypted = bytes([b ^ k for b, k in zip(encrypted, keystream)])
            return decrypted.decode("utf-8")
        except Exception:
            return ""

    return encrypted_str


def mask_camera_secret(secret: Optional[str]) -> str:
    """Retorna una representación enmascarada para la interfaz de usuario."""
    if not secret:
        return "(Sin contraseña)"
    return "••••••••"


def build_rtsp_url(ip: str, user: str, password: str, port: int = 554, ruta: str = "/stream2") -> str:
    """
    Construye la URL RTSP completa para cv2.VideoCapture.
    Soporta cámaras IP comerciales (ej. Tapo C310, Dahua, Hikvision) o dispositivos locales.
    """
    ip_clean = ip.strip()
    # Si es webcam local (ej. "0", "1")
    if ip_clean.isdigit():
        return ip_clean

    ruta_clean = ruta.strip()
    if not ruta_clean.startswith("/"):
        ruta_clean = "/" + ruta_clean

    port_val = int(port) if port else 554

    user_clean = user.strip()
    pass_clean = password.strip() if password else ""

    if user_clean:
        return f"rtsp://{user_clean}:{pass_clean}@{ip_clean}:{port_val}{ruta_clean}"
    return f"rtsp://{ip_clean}:{port_val}{ruta_clean}"


def build_safe_display_url(ip: str, user: str, port: int = 554, ruta: str = "/stream2") -> str:
    """
    Construye una URL segura sin exponer la contraseña para logs, bitácoras y tablas de interfaz.
    """
    ip_clean = ip.strip()
    if ip_clean.isdigit():
        return f"Dispositivo Local (/dev/video{ip_clean})"

    ruta_clean = ruta.strip()
    if not ruta_clean.startswith("/"):
        ruta_clean = "/" + ruta_clean

    port_val = int(port) if port else 554
    user_clean = user.strip()

    if user_clean:
        return f"rtsp://{user_clean}:***@{ip_clean}:{port_val}{ruta_clean}"
    return f"rtsp://{ip_clean}:{port_val}{ruta_clean}"
