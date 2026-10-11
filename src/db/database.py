"""
Capa de Persistencia y Acceso a Datos (Database Adapter).
Soporta SQLite para desarrollo y evaluación local sin dependencias de servidor,
y PostgreSQL para despliegue formal/producción.

SEGURIDAD Y CONTROL DE ACCESO (RBAC):
- Almacenamiento seguro de usuarios y roles (administrador / operador) con PBKDF2-HMAC-SHA256.
- Control de cambios en base de datos: validación estricta de credenciales de administrador
  para operaciones de modificación y eliminación de registros biométricos o configuraciones.
- Bitácora de auditoría inmutable para trazabilidad de operaciones críticas.
- Gestión de cámaras IP y locales con contraseñas protegidas.
- Almacena estrictamente los vectores (embeddings de 128 flotantes) en formato binario (BLOB / BYTEA)
  garantizando que NUNCA se guarde ninguna imagen de rostro (LFPDPPP).
"""

import sqlite3
import numpy as np
from typing import List, Optional, Tuple, Dict
from datetime import datetime
import os

import config
from src.db.models import Estudiante, RegistroAcceso, Usuario, CamaraConfig, RegistroAuditoria
from src.utils.security import (
    hash_password,
    verify_password,
    encrypt_camera_secret,
    decrypt_camera_secret
)
from src.utils.crypto import encrypt_vector_bytes, decrypt_vector_bytes

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class Database:
    def __init__(self):
        self.engine = config.DB_ENGINE
        self.sqlite_path = config.SQLITE_DB_PATH

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_postgres_connection(self):
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 no está instalado en el entorno.")
        return psycopg2.connect(
            host=config.PG_HOST,
            port=config.PG_PORT,
            database=config.PG_DATABASE,
            user=config.PG_USER,
            password=config.PG_PASSWORD
        )

    def init_db(self):
        """Crea las tablas requeridas si aún no existen y siembra usuarios y cámaras por defecto."""
        if self.engine == "postgres":
            self._init_postgres()
        else:
            self._init_sqlite()

        self._seed_default_users()
        self._seed_default_cameras()

    def _init_sqlite(self):
        with self._get_sqlite_connection() as conn:
            cursor = conn.cursor()
            # 1. Tabla de Estudiantes (solo almacena template matemático en BLOB)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS estudiantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    carrera TEXT,
                    embedding_vector BLOB NOT NULL,
                    activo INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 2. Tabla de Registro de Accesos (Auditoría de Paso y Métricas de Investigación)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registro_accesos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    estudiante_id INTEGER,
                    matricula TEXT,
                    nombre TEXT,
                    distancia REAL,
                    estado TEXT NOT NULL,
                    tiempo_acceso_segundos REAL DEFAULT 0.0,
                    tipo_usuario TEXT DEFAULT 'estudiante',
                    condicion_luz TEXT DEFAULT 'luz normal',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id)
                )
            """)
            # Migraciones preventivas para columnas de métricas en bases de datos existentes
            for col_name, col_type in [
                ("tiempo_acceso_segundos", "REAL DEFAULT 0.0"),
                ("tipo_usuario", "TEXT DEFAULT 'estudiante'"),
                ("condicion_luz", "TEXT DEFAULT 'luz normal'")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE registro_accesos ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass
            # 3. Tabla de Usuarios y Roles (RBAC)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'operador',
                    activo INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 4. Tabla de Configuración de Cámaras
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuracion_camaras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    usuario TEXT DEFAULT '',
                    password_enc TEXT DEFAULT '',
                    puerto INTEGER DEFAULT 554,
                    ruta_rtsp TEXT DEFAULT '/stream2',
                    activa INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 5. Tabla de Bitácora de Acciones Administrativas Sensibles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bitacora_auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT NOT NULL,
                    operacion TEXT NOT NULL,
                    entidad TEXT NOT NULL,
                    detalles TEXT,
                    resultado TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _init_postgres(self):
        with self._get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS estudiantes (
                        id SERIAL PRIMARY KEY,
                        matricula VARCHAR(50) UNIQUE NOT NULL,
                        nombre VARCHAR(150) NOT NULL,
                        carrera VARCHAR(100),
                        embedding_vector BYTEA NOT NULL,
                        activo BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS registro_accesos (
                        id SERIAL PRIMARY KEY,
                        estudiante_id INTEGER REFERENCES estudiantes(id),
                        matricula VARCHAR(50),
                        nombre VARCHAR(150),
                        distancia REAL,
                        estado VARCHAR(30) NOT NULL,
                        tiempo_acceso_segundos REAL DEFAULT 0.0,
                        tipo_usuario VARCHAR(50) DEFAULT 'estudiante',
                        condicion_luz VARCHAR(50) DEFAULT 'luz normal',
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                for col_name, col_type in [
                    ("tiempo_acceso_segundos", "REAL DEFAULT 0.0"),
                    ("tipo_usuario", "VARCHAR(50) DEFAULT 'estudiante'"),
                    ("condicion_luz", "VARCHAR(50) DEFAULT 'luz normal'")
                ]:
                    try:
                        cursor.execute(f"ALTER TABLE registro_accesos ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                    except Exception:
                        pass
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(80) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        nombre_completo VARCHAR(150) NOT NULL,
                        rol VARCHAR(30) NOT NULL DEFAULT 'operador',
                        activo BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS configuracion_camaras (
                        id SERIAL PRIMARY KEY,
                        nombre VARCHAR(120) NOT NULL,
                        ip VARCHAR(80) NOT NULL,
                        usuario VARCHAR(80) DEFAULT '',
                        password_enc TEXT DEFAULT '',
                        puerto INTEGER DEFAULT 554,
                        ruta_rtsp VARCHAR(150) DEFAULT '/stream2',
                        activa BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bitacora_auditoria (
                        id SERIAL PRIMARY KEY,
                        usuario VARCHAR(80) NOT NULL,
                        operacion VARCHAR(80) NOT NULL,
                        entidad VARCHAR(80) NOT NULL,
                        detalles TEXT,
                        resultado VARCHAR(50) NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                conn.commit()

    # -------------------------------------------------------------------------
    # SIEMBRA DE DATOS INICIALES (ADMINISTRADOR Y CÁMARAS)
    # -------------------------------------------------------------------------
    def _seed_default_users(self):
        """
        Crea el usuario administrador y operador iniciales si no existen usuarios registrados.
        Las credenciales se leen desde el archivo .env (ADMIN_USER / ADMIN_PASS).
        Si no están definidas en .env se usan los valores predeterminados de primera instalación.
        """
        admin_user = os.getenv("ADMIN_USER", "admin#ITSX26")
        admin_pass = os.getenv("ADMIN_PASS", "Admin#2026ITSX")
        admin_name = os.getenv("ADMIN_NAME", "Administrador Principal ITSX")

        operador_user = os.getenv("OPERADOR_USER", "operador#ITSX26")
        operador_pass = os.getenv("OPERADOR_PASS", "Operador#2026ITSX")
        operador_name = os.getenv("OPERADOR_NAME", "Operador de Guardia ITSX")

        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM usuarios;")
                    count = cursor.fetchone()[0]
                    if count == 0:
                        h_admin = hash_password(admin_pass)
                        h_oper = hash_password(operador_pass)
                        cursor.execute("""
                            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                            VALUES (%s, %s, %s, 'administrador', TRUE),
                                   (%s, %s, %s, 'operador', TRUE);
                        """, (admin_user, h_admin, admin_name, operador_user, h_oper, operador_name))
                        conn.commit()
                        self.log_auditoria("SISTEMA", "CREAR_USUARIO", "USUARIO", f"Usuario administrador inicial '{admin_user}' creado desde configuración", "EXITO")
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM usuarios")
                count = cursor.fetchone()[0]
                if count == 0:
                    h_admin = hash_password(admin_pass)
                    h_oper = hash_password(operador_pass)
                    cursor.execute("""
                        INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                        VALUES (?, ?, ?, 'administrador', 1),
                               (?, ?, ?, 'operador', 1)
                    """, (admin_user, h_admin, admin_name, operador_user, h_oper, operador_name))
                    conn.commit()
                    self.log_auditoria("SISTEMA", "CREAR_USUARIO", "USUARIO", f"Usuario administrador inicial '{admin_user}' creado desde configuración", "EXITO")

    def _seed_default_cameras(self):
        """Siembra la cámara Tapo C310 inicial o dispositivo local si no hay cámaras configuradas."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM configuracion_camaras;")
                    if cursor.fetchone()[0] == 0:
                        cursor.execute("""
                            INSERT INTO configuracion_camaras (nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa)
                            VALUES ('Cámara Tapo C310 - Caseta 1', '192.168.1.101', 'admin', '', 554, '/stream2', TRUE),
                                   ('Webcam Local / Integrada', '0', '', '', 0, '', FALSE);
                        """)
                        conn.commit()
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM configuracion_camaras")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO configuracion_camaras (nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa)
                        VALUES ('Cámara Tapo C310 - Caseta 1', '192.168.1.101', 'admin', '', 554, '/stream2', 1),
                               ('Webcam Local / Integrada', '0', '', '', 0, '', 0)
                    """)
                    conn.commit()

    # -------------------------------------------------------------------------
    # AUTENTICACIÓN Y ROLES (RBAC)
    # -------------------------------------------------------------------------
    def autenticar_usuario(self, username: str, password: str) -> Optional[Usuario]:
        """
        Valida las credenciales de un usuario contra la base de datos usando PBKDF2-HMAC-SHA256 con sal.
        Retorna el objeto Usuario si es válido y está activo, o None si falla.
        """
        user_clean = username.strip()
        if not user_clean or not password:
            return None

        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(
                        "SELECT id, username, password_hash, nombre_completo, rol, activo, created_at FROM usuarios WHERE username = %s AND activo = TRUE",
                        (user_clean,)
                    )
                    row = cursor.fetchone()
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, username, password_hash, nombre_completo, rol, activo, created_at FROM usuarios WHERE username = ? AND activo = 1",
                    (user_clean,)
                )
                row = cursor.fetchone()

        if not row:
            return None

        if verify_password(password, row["password_hash"]):
            return Usuario(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                nombre_completo=row["nombre_completo"],
                rol=row["rol"],
                activo=bool(row["activo"]),
                created_at=str(row["created_at"])
            )
        return None

    def verificar_credenciales_admin(self, username: Optional[str], password: Optional[str]) -> Tuple[bool, Optional[Usuario], str]:
        """
        Verifica si las credenciales provistas corresponden a un usuario con rol 'administrador' activo.
        """
        if not username or not password:
            return False, None, "Debe proporcionar usuario y contraseña de administrador."

        user = self.autenticar_usuario(username, password)
        if not user:
            return False, None, "Credenciales de administrador incorrectas."

        if not user.es_admin():
            return False, user, "Acceso denegado: El usuario no cuenta con rol de Administrador."

        return True, user, "Credenciales de administrador válidas."

    def crear_usuario(
        self,
        username: str,
        password: str,
        nombre_completo: str,
        rol: str,
        admin_user: str,
        admin_pass: str
    ) -> Tuple[bool, str]:
        """Crea un nuevo usuario en el sistema. Requiere autorización de administrador."""
        ok_admin, admin_obj, msg = self.verificar_credenciales_admin(admin_user, admin_pass)
        if not ok_admin:
            self.log_auditoria(admin_user or "DESCONOCIDO", "CREAR_USUARIO", "USUARIO", f"Intento no autorizado de creación de '{username}': {msg}", "FALLIDO_AUTENTICACION")
            return False, msg

        u_clean = username.strip()
        p_clean = password.strip()
        n_clean = nombre_completo.strip()
        r_clean = rol.strip().lower()

        if not u_clean or not p_clean or not n_clean:
            return False, "Todos los campos de usuario son obligatorios."

        if r_clean not in ("administrador", "operador"):
            return False, "El rol debe ser 'administrador' o 'operador'."

        p_hash = hash_password(p_clean)

        try:
            if self.engine == "postgres":
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                            VALUES (%s, %s, %s, %s, TRUE);
                        """, (u_clean, p_hash, n_clean, r_clean))
                        conn.commit()
            else:
                with self._get_sqlite_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                        VALUES (?, ?, ?, ?, 1)
                    """, (u_clean, p_hash, n_clean, r_clean))
                    conn.commit()

            self.log_auditoria(admin_obj.username, "CREAR_USUARIO", "USUARIO", f"Usuario '{u_clean}' ({r_clean}) creado por {admin_obj.username}", "EXITO")
            return True, f"Usuario '{u_clean}' creado exitosamente."
        except Exception as e:
            err = f"Error al crear usuario (posible nombre duplicado): {e}"
            self.log_auditoria(admin_obj.username, "CREAR_USUARIO", "USUARIO", err, "ERROR")
            return False, err

    def obtener_usuarios(self) -> List[Usuario]:
        """Retorna la lista de usuarios del sistema."""
        usuarios = []
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT id, username, password_hash, nombre_completo, rol, activo, created_at FROM usuarios ORDER BY id ASC")
                    for row in cursor.fetchall():
                        usuarios.append(Usuario(
                            id=row["id"], username=row["username"], password_hash=row["password_hash"],
                            nombre_completo=row["nombre_completo"], rol=row["rol"],
                            activo=bool(row["activo"]), created_at=str(row["created_at"])
                        ))
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, password_hash, nombre_completo, rol, activo, created_at FROM usuarios ORDER BY id ASC")
                for row in cursor.fetchall():
                    usuarios.append(Usuario(
                        id=row["id"], username=row["username"], password_hash=row["password_hash"],
                        nombre_completo=row["nombre_completo"], rol=row["rol"],
                        activo=bool(row["activo"]), created_at=str(row["created_at"])
                    ))
        return usuarios

    # -------------------------------------------------------------------------
    # GESTIÓN Y PERSISTENCIA DE CÁMARAS
    # -------------------------------------------------------------------------
    def guardar_camara(
        self,
        nombre: str,
        ip: str,
        usuario: str,
        password_plana: str,
        puerto: int = 554,
        ruta_rtsp: str = "/stream2",
        activa: bool = False,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None
    ) -> Tuple[int, str]:
        """
        Registra una nueva cámara. La contraseña se cifra con AES/derivación
        antes de guardarse en la base de datos (nunca texto claro).
        Requiere validación de administrador si se especifican credenciales.
        """
        operador = "SISTEMA"
        if admin_username is not None:
            ok_admin, admin_obj, msg = self.verificar_credenciales_admin(admin_username, admin_password)
            if not ok_admin:
                self.log_auditoria(admin_username or "DESCONOCIDO", "REGISTRAR_CAMARA", "CAMARA", f"Intento no autorizado de registrar cámara '{nombre}': {msg}", "FALLIDO_AUTENTICACION")
                return 0, msg
            operador = admin_obj.username

        nom_clean = nombre.strip()
        ip_clean = ip.strip()
        usr_clean = usuario.strip()
        ruta_clean = ruta_rtsp.strip() or "/stream2"
        p_enc = encrypt_camera_secret(password_plana) if password_plana else ""
        puerto_val = int(puerto) if puerto else 554

        if not nom_clean or not ip_clean:
            return 0, "El nombre y la IP de la cámara son obligatorios."

        try:
            if self.engine == "postgres":
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        if activa:
                            cursor.execute("UPDATE configuracion_camaras SET activa = FALSE;")
                        cursor.execute("""
                            INSERT INTO configuracion_camaras (nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            RETURNING id;
                        """, (nom_clean, ip_clean, usr_clean, p_enc, puerto_val, ruta_clean, activa))
                        new_id = cursor.fetchone()[0]
                        conn.commit()
            else:
                with self._get_sqlite_connection() as conn:
                    cursor = conn.cursor()
                    if activa:
                        cursor.execute("UPDATE configuracion_camaras SET activa = 0")
                    cursor.execute("""
                        INSERT INTO configuracion_camaras (nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (nom_clean, ip_clean, usr_clean, p_enc, puerto_val, ruta_clean, 1 if activa else 0))
                    conn.commit()
                    new_id = cursor.lastrowid

            self.log_auditoria(operador, "REGISTRAR_CAMARA", "CAMARA", f"Cámara '{nom_clean}' (IP: {ip_clean}:{puerto_val}) registrada", "EXITO")
            return new_id, f"Cámara '{nom_clean}' registrada correctamente."
        except Exception as e:
            err = f"Error al guardar cámara: {e}"
            self.log_auditoria(operador, "REGISTRAR_CAMARA", "CAMARA", err, "ERROR")
            return 0, err

    def actualizar_camara(
        self,
        camara_id: int,
        nombre: str,
        ip: str,
        usuario: str,
        password_plana: Optional[str] = None,
        puerto: int = 554,
        ruta_rtsp: str = "/stream2",
        activa: Optional[bool] = None,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Actualiza los datos de una cámara registrada.
        Valida credenciales de administrador en la capa de datos.
        """
        operador = "SISTEMA"
        if admin_username is not None:
            ok_admin, admin_obj, msg = self.verificar_credenciales_admin(admin_username, admin_password)
            if not ok_admin:
                self.log_auditoria(admin_username or "DESCONOCIDO", "MODIFICAR_CAMARA", "CAMARA", f"Intento no autorizado de modificar cámara ID {camara_id}: {msg}", "FALLIDO_AUTENTICACION")
                return False, msg
            operador = admin_obj.username

        nom_clean = nombre.strip()
        ip_clean = ip.strip()
        usr_clean = usuario.strip()
        ruta_clean = ruta_rtsp.strip() or "/stream2"
        puerto_val = int(puerto) if puerto else 554

        cam_actual = self.obtener_camara_por_id(camara_id)
        if not cam_actual:
            return False, "La cámara especificada no existe."

        p_enc = encrypt_camera_secret(password_plana) if (password_plana is not None and password_plana != "") else cam_actual.password_enc
        activa_val = activa if activa is not None else cam_actual.activa

        try:
            if self.engine == "postgres":
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        if activa_val:
                            cursor.execute("UPDATE configuracion_camaras SET activa = FALSE;")
                        cursor.execute("""
                            UPDATE configuracion_camaras
                            SET nombre = %s, ip = %s, usuario = %s, password_enc = %s,
                                puerto = %s, ruta_rtsp = %s, activa = %s
                            WHERE id = %s;
                        """, (nom_clean, ip_clean, usr_clean, p_enc, puerto_val, ruta_clean, activa_val, camara_id))
                        conn.commit()
            else:
                with self._get_sqlite_connection() as conn:
                    cursor = conn.cursor()
                    if activa_val:
                        cursor.execute("UPDATE configuracion_camaras SET activa = 0")
                    cursor.execute("""
                        UPDATE configuracion_camaras
                        SET nombre = ?, ip = ?, usuario = ?, password_enc = ?,
                            puerto = ?, ruta_rtsp = ?, activa = ?
                        WHERE id = ?
                    """, (nom_clean, ip_clean, usr_clean, p_enc, puerto_val, ruta_clean, 1 if activa_val else 0, camara_id))
                    conn.commit()

            self.log_auditoria(operador, "MODIFICAR_CAMARA", "CAMARA", f"Cámara ID {camara_id} ('{nom_clean}', IP: {ip_clean}) modificada", "EXITO")
            return True, f"Cámara '{nom_clean}' actualizada correctamente."
        except Exception as e:
            err = f"Error al actualizar cámara: {e}"
            self.log_auditoria(operador, "MODIFICAR_CAMARA", "CAMARA", err, "ERROR")
            return False, err

    def obtener_camaras(self) -> List[CamaraConfig]:
        """Retorna todas las cámaras configuradas en la BD."""
        camaras = []
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT id, nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa, created_at FROM configuracion_camaras ORDER BY id ASC;")
                    for row in cursor.fetchall():
                        camaras.append(CamaraConfig(
                            id=row["id"], nombre=row["nombre"], ip=row["ip"], usuario=row["usuario"] or "",
                            password_enc=row["password_enc"] or "", puerto=row["puerto"] or 554,
                            ruta_rtsp=row["ruta_rtsp"] or "/stream2", activa=bool(row["activa"]),
                            created_at=str(row["created_at"])
                        ))
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa, created_at FROM configuracion_camaras ORDER BY id ASC")
                for row in cursor.fetchall():
                    camaras.append(CamaraConfig(
                        id=row["id"], nombre=row["nombre"], ip=row["ip"], usuario=row["usuario"] or "",
                        password_enc=row["password_enc"] or "", puerto=row["puerto"] or 554,
                        ruta_rtsp=row["ruta_rtsp"] or "/stream2", activa=bool(row["activa"]),
                        created_at=str(row["created_at"])
                    ))
        return camaras

    def obtener_camara_por_id(self, camara_id: int) -> Optional[CamaraConfig]:
        """Obtiene una cámara específica por su ID primario."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT id, nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa, created_at FROM configuracion_camaras WHERE id = %s;", (camara_id,))
                    row = cursor.fetchone()
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, nombre, ip, usuario, password_enc, puerto, ruta_rtsp, activa, created_at FROM configuracion_camaras WHERE id = ?", (camara_id,))
                row = cursor.fetchone()

        if not row:
            return None
        return CamaraConfig(
            id=row["id"], nombre=row["nombre"], ip=row["ip"], usuario=row["usuario"] or "",
            password_enc=row["password_enc"] or "", puerto=row["puerto"] or 554,
            ruta_rtsp=row["ruta_rtsp"] or "/stream2", activa=bool(row["activa"]),
            created_at=str(row["created_at"])
        )

    def obtener_camara_activa(self) -> Optional[CamaraConfig]:
        """Retorna la cámara marcada como activa actualmente, o la primera registrada."""
        camaras = self.obtener_camaras()
        for c in camaras:
            if c.activa:
                return c
        return camaras[0] if camaras else None

    def activar_camara(self, camara_id: int) -> bool:
        """Marca una cámara como la activa para el streaming de video."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE configuracion_camaras SET activa = FALSE;")
                    cursor.execute("UPDATE configuracion_camaras SET activa = TRUE WHERE id = %s;", (camara_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE configuracion_camaras SET activa = 0")
                cursor.execute("UPDATE configuracion_camaras SET activa = 1 WHERE id = ?", (camara_id,))
                conn.commit()
                return cursor.rowcount > 0

    def eliminar_camara(
        self,
        camara_id: int,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Elimina una cámara tras validar credenciales de administrador."""
        ok_admin, admin_obj, msg = self.verificar_credenciales_admin(admin_username, admin_password)
        if not ok_admin:
            self.log_auditoria(admin_username or "DESCONOCIDO", "ELIMINAR_CAMARA", "CAMARA", f"Intento no autorizado de eliminar cámara ID {camara_id}: {msg}", "FALLIDO_AUTENTICACION")
            return False, msg

        cam = self.obtener_camara_por_id(camara_id)
        if not cam:
            return False, "La cámara especificada no existe."

        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM configuracion_camaras WHERE id = %s;", (camara_id,))
                    conn.commit()
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM configuracion_camaras WHERE id = ?", (camara_id,))
                conn.commit()

        self.log_auditoria(admin_obj.username, "ELIMINAR_CAMARA", "CAMARA", f"Cámara '{cam.nombre}' (IP: {cam.ip}) eliminada por {admin_obj.username}", "EXITO")
        return True, f"Cámara '{cam.nombre}' eliminada correctamente."

    # -------------------------------------------------------------------------
    # BITÁCORA DE AUDITORÍA DE SEGURIDAD
    # -------------------------------------------------------------------------
    def log_auditoria(
        self,
        usuario: str,
        operacion: str,
        entidad: str,
        detalles: str,
        resultado: str
    ):
        """Registra una acción administrativa o intento de acceso en la bitácora de seguridad."""
        u_clean = usuario or "ANONIMO"
        op_clean = operacion
        ent_clean = entidad
        det_clean = detalles
        res_clean = resultado

        try:
            if self.engine == "postgres":
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO bitacora_auditoria (usuario, operacion, entidad, detalles, resultado)
                            VALUES (%s, %s, %s, %s, %s);
                        """, (u_clean, op_clean, ent_clean, det_clean, res_clean))
                        conn.commit()
            else:
                with self._get_sqlite_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO bitacora_auditoria (usuario, operacion, entidad, detalles, resultado)
                        VALUES (?, ?, ?, ?, ?)
                    """, (u_clean, op_clean, ent_clean, det_clean, res_clean))
                    conn.commit()
        except Exception as e:
            print(f"[-] Error al guardar log de auditoría: {e}")

    def obtener_bitacora_auditoria(self, limit: int = 100) -> List[RegistroAuditoria]:
        """Recupera los eventos más recientes de la bitácora de seguridad."""
        logs = []
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, usuario, operacion, entidad, detalles, resultado, timestamp
                        FROM bitacora_auditoria
                        ORDER BY id DESC LIMIT %s;
                    """, (limit,))
                    for row in cursor.fetchall():
                        logs.append(RegistroAuditoria(
                            id=row["id"], usuario=row["usuario"], operacion=row["operacion"],
                            entidad=row["entidad"], detalles=row["detalles"], resultado=row["resultado"],
                            timestamp=str(row["timestamp"])
                        ))
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, usuario, operacion, entidad, detalles, resultado, timestamp
                    FROM bitacora_auditoria
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
                for row in cursor.fetchall():
                    logs.append(RegistroAuditoria(
                        id=row["id"], usuario=row["usuario"], operacion=row["operacion"],
                        entidad=row["entidad"], detalles=row["detalles"], resultado=row["resultado"],
                        timestamp=str(row["timestamp"])
                    ))
        return logs

    # -------------------------------------------------------------------------
    # OPERACIONES PROTEGIDAS SOBRE REGISTROS BIOMÉTRICOS (ESTUDIANTES)
    # -------------------------------------------------------------------------
    @staticmethod
    def serialize_vector(vector: np.ndarray) -> bytes:
        """Convierte el arreglo NumPy de 128 flotantes en bytes exactos (1024 bytes)."""
        vec = np.asarray(vector, dtype=np.float64)
        if vec.shape != (128,):
            raise ValueError(f"Vector debe ser 128-D, forma actual: {vec.shape}")
        return vec.tobytes()

    @staticmethod
    def deserialize_vector(data: bytes) -> np.ndarray:
        """Reconstruye el arreglo NumPy de 128 flotantes desde su representación binaria (descifra si está cifrado)."""
        if isinstance(data, memoryview):
            data = data.tobytes()
        if data.startswith(b"ENC1$"):
            data = decrypt_vector_bytes(data)
        vec = np.frombuffer(data, dtype=np.float64)
        if vec.shape != (128,):
            raise ValueError(f"Formato inválido al deserializar vector: esperado (128,), obtenido {vec.shape}")
        return vec

    def save_estudiante(self, matricula: str, nombre: str, carrera: str, embedding: np.ndarray) -> Estudiante:
        """
        Guarda un estudiante junto a su template biométrico (cifrado en reposo según LFPDPPP).
        Si la matrícula ya existe lanza ValueError (no sobreescribe datos silenciosamente).
        """
        raw_bytes = self.serialize_vector(embedding)
        vector_bytes = encrypt_vector_bytes(raw_bytes) if getattr(config, "ENCRYPT_BIOMETRICS", True) else raw_bytes

        # Verificar duplicado antes de insertar
        existente = self.get_estudiante_by_matricula(matricula)
        if existente:
            raise ValueError(f"La matrícula '{matricula}' ya está registrada en el padrón. Use 'Editar' para modificar datos.")

        try:
            if self.engine == "postgres":
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO estudiantes (matricula, nombre, carrera, embedding_vector, activo)
                            VALUES (%s, %s, %s, %s, TRUE)
                            RETURNING id, created_at;
                        """, (matricula, nombre, carrera, psycopg2.Binary(vector_bytes)))
                        res = cursor.fetchone()
                        conn.commit()
                        return Estudiante(
                            id=res[0],
                            matricula=matricula,
                            nombre=nombre,
                            carrera=carrera,
                            embedding=embedding,
                            activo=True,
                            created_at=str(res[1])
                        )
            else:
                with self._get_sqlite_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO estudiantes (matricula, nombre, carrera, embedding_vector, activo)
                        VALUES (?, ?, ?, ?, 1)
                    """, (matricula, nombre, carrera, vector_bytes))
                    conn.commit()
                    return self.get_estudiante_by_matricula(matricula)
        except sqlite3.IntegrityError:
            raise ValueError(f"La matrícula '{matricula}' ya está registrada. Operación cancelada.")

    def update_estudiante(
        self,
        matricula_actual: Optional[str] = None,
        nuevo_nombre: str = "",
        nueva_carrera: str = "",
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None,
        nueva_matricula: Optional[str] = None,
        nuevo_embedding: Optional[np.ndarray] = None,
        matricula: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Modifica los datos o biometría de un estudiante registrado.
        Requiere validación obligatoria de credenciales de Administrador en la capa de datos.
        Acepta tanto 'matricula_actual' como 'matricula'.
        """
        mat_origen = matricula_actual or matricula
        if not mat_origen:
            return False, "Debe especificar la matrícula del estudiante a modificar."

        ok_admin, admin_obj, msg = self.verificar_credenciales_admin(admin_username, admin_password)
        if not ok_admin:
            self.log_auditoria(
                admin_username or "ANONIMO",
                "MODIFICAR_ESTUDIANTE",
                "ESTUDIANTE",
                f"Intento no autorizado de modificar matrícula {mat_origen}: {msg}",
                "FALLIDO_AUTENTICACION"
            )
            return False, msg

        est = self.get_estudiante_by_matricula(mat_origen)
        if not est:
            return False, f"No se encontró ningún estudiante con matrícula {mat_origen}."

        mat_final = nueva_matricula.strip() if nueva_matricula else mat_origen
        nom_final = nuevo_nombre.strip() if nuevo_nombre else est.nombre
        car_final = nueva_carrera.strip() if nueva_carrera else est.carrera

        vector_bytes = self.serialize_vector(nuevo_embedding) if nuevo_embedding is not None else None

        try:
            if self.engine == "postgres":
                with self._get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        if vector_bytes is not None:
                            cursor.execute("""
                                UPDATE estudiantes
                                SET matricula = %s, nombre = %s, carrera = %s, embedding_vector = %s
                                WHERE matricula = %s;
                            """, (mat_final, nom_final, car_final, psycopg2.Binary(vector_bytes), matricula_actual))
                        else:
                            cursor.execute("""
                                UPDATE estudiantes
                                SET matricula = %s, nombre = %s, carrera = %s
                                WHERE matricula = %s;
                            """, (mat_final, nom_final, car_final, matricula_actual))
                        conn.commit()
            else:
                with self._get_sqlite_connection() as conn:
                    cursor = conn.cursor()
                    if vector_bytes is not None:
                        cursor.execute("""
                            UPDATE estudiantes
                            SET matricula = ?, nombre = ?, carrera = ?, embedding_vector = ?
                            WHERE matricula = ?
                        """, (mat_final, nom_final, car_final, vector_bytes, matricula_actual))
                    else:
                        cursor.execute("""
                            UPDATE estudiantes
                            SET matricula = ?, nombre = ?, carrera = ?
                            WHERE matricula = ?
                        """, (mat_final, nom_final, car_final, matricula_actual))
                    conn.commit()

            detalles_cambio = f"Matrícula: {matricula_actual} -> {mat_final}, Nombre: {nom_final}, Carrera: {car_final}"
            if vector_bytes is not None:
                detalles_cambio += " [Vector Biométrico Actualizado]"

            self.log_auditoria(admin_obj.username, "MODIFICAR_ESTUDIANTE", "ESTUDIANTE", detalles_cambio, "EXITO")
            return True, f"Estudiante {mat_final} actualizado correctamente."
        except Exception as e:
            err = f"Error al modificar estudiante {matricula_actual}: {e}"
            self.log_auditoria(admin_obj.username, "MODIFICAR_ESTUDIANTE", "ESTUDIANTE", err, "ERROR")
            return False, err

    def delete_estudiante(
        self,
        matricula: str,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None
    ) -> bool:
        """
        Elimina un estudiante de la base de datos de forma segura.
        Valida rigurosamente las credenciales de administrador antes de ejecutar la eliminación.
        Preserva la bitácora histórica de accesos desvinculando la clave foránea.
        """
        ok_admin, admin_obj, msg = self.verificar_credenciales_admin(admin_username, admin_password)
        if not ok_admin:
            self.log_auditoria(
                admin_username or "ANONIMO",
                "ELIMINAR_ESTUDIANTE",
                "ESTUDIANTE",
                f"Intento no autorizado de eliminar matrícula {matricula}: {msg}",
                "FALLIDO_AUTENTICACION"
            )
            return False
        operador_nombre = admin_obj.username

        est = self.get_estudiante_by_matricula(matricula)
        if not est:
            return False

        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    # Anonimizar bitácora histórica para no romper FK ni perder auditoría
                    cursor.execute("UPDATE registro_accesos SET estudiante_id = NULL WHERE matricula = %s;", (matricula,))
                    cursor.execute("DELETE FROM estudiantes WHERE matricula = %s;", (matricula,))
                    conn.commit()
                    eliminado = cursor.rowcount > 0
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE registro_accesos SET estudiante_id = NULL WHERE matricula = ?", (matricula,))
                cursor.execute("DELETE FROM estudiantes WHERE matricula = ?", (matricula,))
                conn.commit()
                eliminado = cursor.rowcount > 0

        if eliminado:
            self.log_auditoria(
                operador_nombre,
                "ELIMINAR_ESTUDIANTE",
                "ESTUDIANTE",
                f"Estudiante '{est.nombre}' ({matricula}) eliminado por {operador_nombre}",
                "EXITO"
            )
        return eliminado

    def get_estudiante_by_matricula(self, matricula: str) -> Optional[Estudiante]:
        """Recupera un estudiante por su matrícula."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(
                        "SELECT id, matricula, nombre, carrera, embedding_vector, activo, created_at FROM estudiantes WHERE matricula = %s",
                        (matricula,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        return None
                    return Estudiante(
                        id=row["id"],
                        matricula=row["matricula"],
                        nombre=row["nombre"],
                        carrera=row["carrera"],
                        embedding=self.deserialize_vector(bytes(row["embedding_vector"])),
                        activo=bool(row["activo"]),
                        created_at=str(row["created_at"])
                    )
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, matricula, nombre, carrera, embedding_vector, activo, created_at FROM estudiantes WHERE matricula = ?",
                    (matricula,)
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return Estudiante(
                    id=row["id"],
                    matricula=row["matricula"],
                    nombre=row["nombre"],
                    carrera=row["carrera"],
                    embedding=self.deserialize_vector(row["embedding_vector"]),
                    activo=bool(row["activo"]),
                    created_at=str(row["created_at"])
                )

    def get_all_active_estudiantes(self) -> List[Estudiante]:
        """Obtiene la lista de todos los estudiantes activos y sus templates."""
        estudiantes = []
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(
                        "SELECT id, matricula, nombre, carrera, embedding_vector, activo, created_at FROM estudiantes WHERE activo = TRUE"
                    )
                    for row in cursor.fetchall():
                        estudiantes.append(
                            Estudiante(
                                id=row["id"],
                                matricula=row["matricula"],
                                nombre=row["nombre"],
                                carrera=row["carrera"],
                                embedding=self.deserialize_vector(bytes(row["embedding_vector"])),
                                activo=True,
                                created_at=str(row["created_at"])
                            )
                        )
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, matricula, nombre, carrera, embedding_vector, activo, created_at FROM estudiantes WHERE activo = 1"
                )
                for row in cursor.fetchall():
                    estudiantes.append(
                        Estudiante(
                            id=row["id"],
                            matricula=row["matricula"],
                            nombre=row["nombre"],
                            carrera=row["carrera"],
                            embedding=self.deserialize_vector(row["embedding_vector"]),
                            activo=True,
                            created_at=str(row["created_at"])
                        )
                    )
        return estudiantes

    def log_acceso(
        self,
        estudiante_id: Optional[int] = None,
        matricula: Optional[str] = None,
        nombre: Optional[str] = None,
        distancia: float = 0.0,
        estado: str = "PERMITIDO",
        tiempo_acceso_segundos: float = 0.0,
        tipo_usuario: str = "estudiante",
        condicion_luz: str = "luz normal"
    ) -> RegistroAcceso:
        """Registra un evento de acceso en la bitácora de auditoría con métricas científicas."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO registro_accesos (
                            estudiante_id, matricula, nombre, distancia, estado,
                            tiempo_acceso_segundos, tipo_usuario, condicion_luz
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, timestamp;
                    """, (
                        estudiante_id, matricula, nombre, float(distancia), estado,
                        float(tiempo_acceso_segundos), tipo_usuario, condicion_luz
                    ))
                    res = cursor.fetchone()
                    conn.commit()
                    return RegistroAcceso(
                        id=res[0],
                        estudiante_id=estudiante_id,
                        matricula=matricula,
                        nombre=nombre,
                        distancia=distancia,
                        estado=estado,
                        timestamp=str(res[1]),
                        tiempo_acceso_segundos=float(tiempo_acceso_segundos),
                        tipo_usuario=tipo_usuario,
                        condicion_luz=condicion_luz
                    )
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO registro_accesos (
                        estudiante_id, matricula, nombre, distancia, estado,
                        tiempo_acceso_segundos, tipo_usuario, condicion_luz
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    estudiante_id, matricula, nombre, float(distancia), estado,
                    float(tiempo_acceso_segundos), tipo_usuario, condicion_luz
                ))
                conn.commit()
                last_id = cursor.lastrowid
                return RegistroAcceso(
                    id=last_id,
                    estudiante_id=estudiante_id,
                    matricula=matricula,
                    nombre=nombre,
                    distancia=distancia,
                    estado=estado,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tiempo_acceso_segundos=float(tiempo_acceso_segundos),
                    tipo_usuario=tipo_usuario,
                    condicion_luz=condicion_luz
                )

    def get_recent_accesos(self, limit: int = 50) -> List[RegistroAcceso]:
        """Obtiene los últimos accesos registrados con métricas completas."""
        logs = []
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, estudiante_id, matricula, nombre, distancia, estado, timestamp,
                               tiempo_acceso_segundos, tipo_usuario, condicion_luz
                        FROM registro_accesos 
                        ORDER BY id DESC LIMIT %s
                    """, (limit,))
                    for row in cursor.fetchall():
                        logs.append(
                            RegistroAcceso(
                                id=row["id"],
                                estudiante_id=row["estudiante_id"],
                                matricula=row["matricula"],
                                nombre=row["nombre"],
                                distancia=float(row["distancia"]),
                                estado=row["estado"],
                                timestamp=str(row["timestamp"]),
                                tiempo_acceso_segundos=float(row.get("tiempo_acceso_segundos") or 0.0),
                                tipo_usuario=row.get("tipo_usuario") or "estudiante",
                                condicion_luz=row.get("condicion_luz") or "luz normal"
                            )
                        )
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, estudiante_id, matricula, nombre, distancia, estado, timestamp,
                           tiempo_acceso_segundos, tipo_usuario, condicion_luz
                    FROM registro_accesos 
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
                for row in cursor.fetchall():
                    logs.append(
                        RegistroAcceso(
                            id=row["id"],
                            estudiante_id=row["estudiante_id"],
                            matricula=row["matricula"],
                            nombre=row["nombre"],
                            distancia=float(row["distancia"]),
                            estado=row["estado"],
                            timestamp=str(row["timestamp"]),
                            tiempo_acceso_segundos=float(row["tiempo_acceso_segundos"] or 0.0),
                            tipo_usuario=row["tipo_usuario"] or "estudiante",
                            condicion_luz=row["condicion_luz"] or "luz normal"
                        )
                    )
        return logs
