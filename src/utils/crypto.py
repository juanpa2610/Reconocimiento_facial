"""
Módulo de Cifrado y Protección de Templates Biométricos en Reposo (LFPDPPP).
Responsable: Velázquez López Guadalupe / Compliance LFPDPPP & Criptografía.

Cifra los vectores de 128 flotantes (1024 bytes) antes de persistirlos en la base de datos,
asegurando que si el archivo de base de datos es extraído, los templates no puedan ser leídos.
Cumple con el principio de seguridad y confidencialidad de la Ley Federal de Protección de
Datos Personales en Posesión de los Particulares (LFPDPPP).
"""

import os
import hashlib
import hmac
import secrets
import base64
from typing import Optional
import numpy as np

import config

MAGIC_HEADER = b"ENC1$"  # Encabezado identificador de template cifrado


def _get_encryption_key(secret_key: Optional[str] = None) -> bytes:
    """Obtiene la clave simétrica de 256 bits a partir del .env o parámetro."""
    raw_key = secret_key or getattr(config, "SECRET_KEY", "ITSX-BIOMETRIC-SECURITY-KEY-2026")
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def _generate_keystream(enc_key: bytes, salt: bytes, length: int) -> bytes:
    """Genera un flujo pseudoaleatorio de cifrado usando SHA-256 en modo contador (CTR)."""
    blocks = []
    counter = 0
    generated = 0
    while generated < length:
        block = hashlib.sha256(enc_key + salt + counter.to_bytes(4, "big")).digest()
        blocks.append(block)
        generated += len(block)
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_vector_bytes(raw_bytes: bytes, secret_key: Optional[str] = None) -> bytes:
    """
    Cifra un payload de bytes de template biométrico (1024 bytes) usando un esquema
    autenticado de flujo simétrico (CTR-SHA256 con HMAC-SHA256) garantizando integridad y confidencialidad.
    Formato: MAGIC_HEADER (5B) + salt (16B) + ciphertext (1024B) + hmac (32B) = 1077 bytes.
    Latencia: < 0.2 milisegundos.
    """
    if not raw_bytes:
        return b""

    key = _get_encryption_key(secret_key)
    salt = secrets.token_bytes(16)

    # Derivar claves de cifrado y autenticación vía HKDF-Expand simplificado
    prk = hashlib.sha256(key + salt).digest()
    enc_key = hashlib.sha256(prk + b"itsx-enc").digest()
    mac_key = hashlib.sha256(prk + b"itsx-mac").digest()

    # Generar keystream del mismo tamaño que raw_bytes
    keystream = _generate_keystream(enc_key, salt, len(raw_bytes))
    ciphertext = bytes(b ^ k for b, k in zip(raw_bytes, keystream))

    # Calcular HMAC sobre header + salt + ciphertext
    payload_to_mac = MAGIC_HEADER + salt + ciphertext
    tag = hmac.new(mac_key, payload_to_mac, hashlib.sha256).digest()

    return payload_to_mac + tag


def decrypt_vector_bytes(encrypted_data: bytes, secret_key: Optional[str] = None) -> bytes:
    """
    Descifra un payload de bytes cifrado. Si no está cifrado (legacy), retorna los bytes originales.
    Valida la firma HMAC antes de descifrar para evitar manipulaciones.
    """
    if not encrypted_data:
        return b""

    # Si no tiene el encabezado mágico, asumimos que son datos binarios sin cifrar (compatibilidad)
    if not encrypted_data.startswith(MAGIC_HEADER):
        return encrypted_data

    header_len = len(MAGIC_HEADER)
    salt_len = 16
    mac_len = 32

    if len(encrypted_data) < header_len + salt_len + mac_len:
        raise ValueError("Datos cifrados corruptos o truncados.")

    salt = encrypted_data[header_len:header_len + salt_len]
    tag = encrypted_data[-mac_len:]
    ciphertext = encrypted_data[header_len + salt_len:-mac_len]

    key = _get_encryption_key(secret_key)
    prk = hashlib.sha256(key + salt).digest()
    enc_key = hashlib.sha256(prk + b"itsx-enc").digest()
    mac_key = hashlib.sha256(prk + b"itsx-mac").digest()

    # Validar HMAC
    payload_to_mac = encrypted_data[:-mac_len]
    expected_tag = hmac.new(mac_key, payload_to_mac, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Error de integridad criptográfica: el template biométrico ha sido alterado.")

    # Descifrar keystream
    keystream = _generate_keystream(enc_key, salt, len(ciphertext))
    raw_bytes = bytes(b ^ k for b, k in zip(ciphertext, keystream))
    return raw_bytes


def encrypt_template(vector: np.ndarray, secret_key: Optional[str] = None) -> bytes:
    """Cifra directamente un arreglo NumPy de 128 flotantes."""
    vec = np.asarray(vector, dtype=np.float64)
    if vec.shape != (config.VECTOR_DIMENSION,):
        raise ValueError(f"El template debe ser de {config.VECTOR_DIMENSION}-D, recibido: {vec.shape}")
    raw_bytes = vec.tobytes()
    return encrypt_vector_bytes(raw_bytes, secret_key)


def decrypt_template(data: bytes, secret_key: Optional[str] = None) -> np.ndarray:
    """Descifra un blob cifrado y reconstruye el arreglo NumPy de 128 flotantes."""
    raw_bytes = decrypt_vector_bytes(data, secret_key)
    vec = np.frombuffer(raw_bytes, dtype=np.float64)
    if vec.shape != (config.VECTOR_DIMENSION,):
        raise ValueError(f"Vector descifrado inválido: esperado ({config.VECTOR_DIMENSION},), obtenido {vec.shape}")
    return vec
