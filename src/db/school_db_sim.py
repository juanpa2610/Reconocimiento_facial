"""
Módulo de Simulación de la Base de Datos Institucional del ITSX.
Instituto Tecnológico Superior de Xalapa - Control Escolar y Recursos Humanos.

Este módulo simula el sistema integral de información escolar (SII / Control Escolar)
y nómina institucional, permitiendo validar números de control de alumnos,
docentes y personal administrativo antes del enrolamiento biométrico.
"""

import sqlite3
from typing import Optional, Dict, List
import config


# Directorio institucional predefinido con registros representativos del ITSX
REGISTROS_INICIALES = [
    # --- ALUMNOS (Ingeniería en Sistemas Computacionales - Solicitados) ---
    {
        "numero_control": "237O00526",
        "nombre_completo": "DIEGO CAPISTRAN ORTIZ",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O01367",
        "nombre_completo": "DANAE VILLA HERNÁNDEZ",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00470",
        "nombre_completo": "ARIADNA SARAI SANTIAGO ORTEGA",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O02104",
        "nombre_completo": "AXEL MAURITZIO RODRIGUEZ FLORES",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00868",
        "nombre_completo": "ISMAEL BAIZABAL ACOSTA",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00327",
        "nombre_completo": "RICARDO HERNANDEZ RODRÍGUEZ",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },

    # --- ALUMNOS (Ingeniería en Sistemas Computacionales - Integrantes del Equipo) ---
    {
        "numero_control": "237O00728",
        "nombre_completo": "Trujillo Trujillo Juan Pablo",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00386",
        "nombre_completo": "Bello Franco Samantha",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00955",
        "nombre_completo": "Martínez Vera Josué Aldair",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O03473",
        "nombre_completo": "Morales Hernández Guadalupe Aleida",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00598",
        "nombre_completo": "Solís Contreras Darian Giselle",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "237O00483",
        "nombre_completo": "Velázquez López Guadalupe",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
]



class SchoolDatabaseSim:
    """Manejador de la base de datos escolar simulada del ITSX."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or getattr(config, "SQLITE_DB_PATH", "biometric_templates.db")
        self._init_table()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_table(self):
        """Crea la tabla de simulación escolar y la puebla con datos iniciales si está vacía."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulacion_escolar_itsx (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_control TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    tipo_usuario TEXT NOT NULL,
                    carrera_o_departamento TEXT NOT NULL,
                    semestre TEXT DEFAULT 'Activo',
                    estatus TEXT DEFAULT 'ACTIVO',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for reg in REGISTROS_INICIALES:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO simulacion_escolar_itsx
                        (numero_control, nombre_completo, tipo_usuario, carrera_o_departamento, semestre, estatus)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        reg["numero_control"].upper().strip(),
                        reg["nombre_completo"].strip(),
                        reg["tipo_usuario"],
                        reg["carrera_o_departamento"],
                        reg.get("semestre", "Activo"),
                        reg.get("estatus", "ACTIVO")
                    ))
                except sqlite3.IntegrityError:
                    pass
            conn.commit()

    def buscar_por_control(self, numero_control: str) -> Optional[Dict]:
        """
        Busca un estudiante, docente o personal administrativo por su número de control o clave.
        Normaliza quitando espacios y convirtiendo a mayúsculas.
        """
        if not numero_control:
            return None

        clave_normalizada = numero_control.strip().upper()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT numero_control, nombre_completo, tipo_usuario, carrera_o_departamento, semestre, estatus
                FROM simulacion_escolar_itsx
                WHERE UPPER(TRIM(numero_control)) = ?
            """, (clave_normalizada,))
            row = cursor.fetchone()

            if row:
                return {
                    "numero_control": row["numero_control"],
                    "nombre_completo": row["nombre_completo"],
                    "tipo_usuario": row["tipo_usuario"],
                    "carrera_o_departamento": row["carrera_o_departamento"],
                    "semestre": row["semestre"],
                    "estatus": row["estatus"]
                }

        # Fallback en memoria si la BD no arrojó resultados
        for reg in REGISTROS_INICIALES:
            if reg["numero_control"].upper().strip() == clave_normalizada:
                return dict(reg)

        return None

    def agregar_registro(
        self,
        numero_control: str,
        nombre_completo: str,
        tipo_usuario: str = "Alumno",
        carrera_o_departamento: str = "Ingeniería en Sistemas Computacionales",
        semestre: str = "1er Semestre",
        estatus: str = "ACTIVO"
    ) -> bool:
        """Permite agregar un nuevo registro a la base de datos escolar simulada."""
        clave = numero_control.strip().upper()
        nombre = nombre_completo.strip()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO simulacion_escolar_itsx
                    (numero_control, nombre_completo, tipo_usuario, carrera_o_departamento, semestre, estatus)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clave, nombre, tipo_usuario, carrera_o_departamento, semestre, estatus))
                conn.commit()
            return True
        except Exception:
            return False

    def obtener_todos(self) -> List[Dict]:
        """Devuelve la lista completa de personas dadas de alta en la simulación escolar."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT numero_control, nombre_completo, tipo_usuario, carrera_o_departamento, semestre, estatus
                FROM simulacion_escolar_itsx
                ORDER BY tipo_usuario, nombre_completo
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]


# Instancia singleton para uso rápido
_instancia_sim = None

def get_school_db() -> SchoolDatabaseSim:
    global _instancia_sim
    if _instancia_sim is None:
        _instancia_sim = SchoolDatabaseSim()
    return _instancia_sim

def buscar_en_base_escolar(numero_control: str) -> Optional[Dict]:
    """Helper directo para consultar si un número de control existe en la base escolar."""
    return get_school_db().buscar_por_control(numero_control)
