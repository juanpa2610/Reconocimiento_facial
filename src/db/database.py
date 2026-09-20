"""
Capa de Persistencia y Acceso a Datos (Database Adapter).
Soporta SQLite para desarrollo y evaluación local sin dependencias de servidor,
y PostgreSQL para despliegue formal/producción.

Almacena estrictamente los vectores (embeddings de 128 flotantes) en formato binario (BLOB / BYTEA)
o tipos vectoriales, garantizando que NUNCA se guarde ninguna imagen de rostro.
"""

import sqlite3
import numpy as np
from typing import List, Optional, Tuple
from datetime import datetime
import os

import config
from src.db.models import Estudiante, RegistroAcceso

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
        """Crea las tablas requeridas si aún no existen."""
        if self.engine == "postgres":
            self._init_postgres()
        else:
            self._init_sqlite()

    def _init_sqlite(self):
        with self._get_sqlite_connection() as conn:
            cursor = conn.cursor()
            # Tabla de Estudiantes (solo almacena template matemático en BLOB)
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
            # Tabla de Registro de Accesos (Auditoría)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS registro_accesos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    estudiante_id INTEGER,
                    matricula TEXT,
                    nombre TEXT,
                    distancia REAL,
                    estado TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id)
                )
            """)
            conn.commit()

    def _init_postgres(self):
        with self._get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                # Verificar si existe extensión pgvector (opcional)
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    conn.commit()
                    vector_type = "vector(128)"
                except Exception:
                    conn.rollback()
                    vector_type = "BYTEA"

                cursor.execute(f"""
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
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                conn.commit()

    @staticmethod
    def serialize_vector(vector: np.ndarray) -> bytes:
        """Convierte el arreglo NumPy de 128 flotantes en bytes exactos (1024 bytes)."""
        vec = np.asarray(vector, dtype=np.float64)
        if vec.shape != (128,):
            raise ValueError(f"Vector debe ser 128-D, forma actual: {vec.shape}")
        return vec.tobytes()

    @staticmethod
    def deserialize_vector(data: bytes) -> np.ndarray:
        """Reconstruye el arreglo NumPy de 128 flotantes desde su representación binaria."""
        if isinstance(data, memoryview):
            data = data.tobytes()
        vec = np.frombuffer(data, dtype=np.float64)
        if vec.shape != (128,):
            raise ValueError(f"Formato inválido al deserializar vector: esperado (128,), obtenido {vec.shape}")
        return vec

    def save_estudiante(self, matricula: str, nombre: str, carrera: str, embedding: np.ndarray) -> Estudiante:
        """Guarda o actualiza un estudiante junto a su template biométrico (sin imagen)."""
        vector_bytes = self.serialize_vector(embedding)
        
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO estudiantes (matricula, nombre, carrera, embedding_vector, activo)
                        VALUES (%s, %s, %s, %s, TRUE)
                        ON CONFLICT (matricula) DO UPDATE 
                        SET nombre = EXCLUDED.nombre,
                            carrera = EXCLUDED.carrera,
                            embedding_vector = EXCLUDED.embedding_vector,
                            activo = TRUE
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
                    ON CONFLICT(matricula) DO UPDATE 
                    SET nombre = excluded.nombre,
                        carrera = excluded.carrera,
                        embedding_vector = excluded.embedding_vector,
                        activo = 1;
                """, (matricula, nombre, carrera, vector_bytes))
                conn.commit()
                return self.get_estudiante_by_matricula(matricula)

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
        estado: str = "PERMITIDO"
    ) -> RegistroAcceso:
        """Registra un evento de acceso en la bitácora de auditoría."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO registro_accesos (estudiante_id, matricula, nombre, distancia, estado)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, timestamp;
                    """, (estudiante_id, matricula, nombre, float(distancia), estado))
                    res = cursor.fetchone()
                    conn.commit()
                    return RegistroAcceso(
                        id=res[0],
                        estudiante_id=estudiante_id,
                        matricula=matricula,
                        nombre=nombre,
                        distancia=distancia,
                        estado=estado,
                        timestamp=str(res[1])
                    )
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO registro_accesos (estudiante_id, matricula, nombre, distancia, estado)
                    VALUES (?, ?, ?, ?, ?);
                """, (estudiante_id, matricula, nombre, float(distancia), estado))
                conn.commit()
                last_id = cursor.lastrowid
                return RegistroAcceso(
                    id=last_id,
                    estudiante_id=estudiante_id,
                    matricula=matricula,
                    nombre=nombre,
                    distancia=distancia,
                    estado=estado,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )

    def get_recent_accesos(self, limit: int = 50) -> List[RegistroAcceso]:
        """Obtiene los últimos accesos registrados."""
        logs = []
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, estudiante_id, matricula, nombre, distancia, estado, timestamp 
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
                                timestamp=str(row["timestamp"])
                            )
                        )
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, estudiante_id, matricula, nombre, distancia, estado, timestamp 
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
                            timestamp=str(row["timestamp"])
                        )
                    )
        return logs

    def delete_estudiante(self, matricula: str) -> bool:
        """Elimina un estudiante de la base de datos."""
        if self.engine == "postgres":
            with self._get_postgres_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM estudiantes WHERE matricula = %s", (matricula,))
                    conn.commit()
                    return cursor.rowcount > 0
        else:
            with self._get_sqlite_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM estudiantes WHERE matricula = ?", (matricula,))
                conn.commit()
                return cursor.rowcount > 0
