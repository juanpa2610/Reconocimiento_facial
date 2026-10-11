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
    # --- ALUMNOS (Ingeniería en Sistemas Computacionales) ---
    {
        "numero_control": "208O0123",
        "nombre_completo": "Juan Pablo Pérez López",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "8vo Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "218O0456",
        "nombre_completo": "María Fernanda González Ruiz",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "228O0789",
        "nombre_completo": "Carlos Eduardo Morales Domínguez",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "4to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "238O1011",
        "nombre_completo": "Ana Sofía Hernández Martínez",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "2do Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "248O1234",
        "nombre_completo": "Diego Alejandro Ramírez Castillo",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "1er Semestre",
        "estatus": "ACTIVO"
    },

    # --- ALUMNOS (Ingeniería Mecatrónica) ---
    {
        "numero_control": "218O0211",
        "nombre_completo": "Luis Ángel Cruz Velázquez",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería Mecatrónica",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "228O0542",
        "nombre_completo": "Valeria Gómez Aguilar",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería Mecatrónica",
        "semestre": "4to Semestre",
        "estatus": "ACTIVO"
    },

    # --- ALUMNOS (Ingeniería Industrial) ---
    {
        "numero_control": "208O0333",
        "nombre_completo": "Rodrigo Flores Navarrete",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería Industrial",
        "semestre": "8vo Semestre",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "228O0890",
        "nombre_completo": "Camila Isabel Sánchez Ortiz",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería Industrial",
        "semestre": "4to Semestre",
        "estatus": "ACTIVO"
    },

    # --- ALUMNOS (Licenciatura en Gastronomía) ---
    {
        "numero_control": "218O0777",
        "nombre_completo": "Emiliano Rivas Salgado",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Licenciatura en Gastronomía",
        "semestre": "6to Semestre",
        "estatus": "ACTIVO"
    },

    # --- ALUMNOS (Ingeniería en Gestión Empresarial) ---
    {
        "numero_control": "238O0654",
        "nombre_completo": "Paola Jimena Mendoza Vargas",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería en Gestión Empresarial",
        "semestre": "2do Semestre",
        "estatus": "ACTIVO"
    },

    # --- ALUMNOS (Ingeniería Civil) ---
    {
        "numero_control": "228O0921",
        "nombre_completo": "Héctor Miguel Benítez Torres",
        "tipo_usuario": "Alumno",
        "carrera_o_departamento": "Ingeniería Civil",
        "semestre": "4to Semestre",
        "estatus": "ACTIVO"
    },

    # --- DOCENTES INSTITUCIONALES ---
    {
        "numero_control": "DOC-1025",
        "nombre_completo": "Dr. Fernando Javier Aguilar Solís",
        "tipo_usuario": "Docente",
        "carrera_o_departamento": "Ingeniería en Sistemas Computacionales",
        "semestre": "Profesor Investigador",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "DOC-2041",
        "nombre_completo": "Mtra. Claudia Patricia Romero Luna",
        "tipo_usuario": "Docente",
        "carrera_o_departamento": "Ciencias Básicas",
        "semestre": "Profesora de Asignatura",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "DOC-3088",
        "nombre_completo": "Ing. Roberto Carlos Méndez Vega",
        "tipo_usuario": "Docente",
        "carrera_o_departamento": "Ingeniería Mecatrónica",
        "semestre": "Profesor de Carrera",
        "estatus": "ACTIVO"
    },

    # --- PERSONAL ADMINISTRATIVO Y DIRECTIVO ---
    {
        "numero_control": "ADM-101",
        "nombre_completo": "Lic. Patricia Estrada Morales",
        "tipo_usuario": "Personal Administrativo",
        "carrera_o_departamento": "Servicios Escolares",
        "semestre": "Jefatura de Registro",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "ADM-205",
        "nombre_completo": "C.P. Jorge Alberto Silva Lozada",
        "tipo_usuario": "Personal Administrativo",
        "carrera_o_departamento": "Recursos Financieros",
        "semestre": "Coordinación de Pagos",
        "estatus": "ACTIVO"
    },
    {
        "numero_control": "PER-304",
        "nombre_completo": "Sr. Manuel Arturo Delgado Gómez",
        "tipo_usuario": "Personal Administrativo",
        "carrera_o_departamento": "Mantenimiento e Intendencia",
        "semestre": "Servicios Generales",
        "estatus": "ACTIVO"
    }
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

            cursor.execute("SELECT COUNT(*) FROM simulacion_escolar_itsx")
            count = cursor.fetchone()[0]

            if count == 0:
                for reg in REGISTROS_INICIALES:
                    try:
                        cursor.execute("""
                            INSERT INTO simulacion_escolar_itsx
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
