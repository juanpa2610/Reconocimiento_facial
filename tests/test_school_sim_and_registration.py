"""
Pruebas unitarias para la Simulación Escolar del ITSX y Flujo de Registro (Escolar e Invitados).
"""

import unittest
import numpy as np
import os

from src.db.school_db_sim import SchoolDatabaseSim, buscar_en_base_escolar
from src.db.database import Database
import config


class TestSchoolSimAndRegistration(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.db.init_db()

    def test_busqueda_alumno_existente(self):
        """Verifica que un alumno existente en la base escolar simulada sea encontrado."""
        res = buscar_en_base_escolar("208O0123")
        self.assertIsNotNone(res)
        self.assertEqual(res["nombre_completo"], "Juan Pablo Pérez López")
        self.assertEqual(res["tipo_usuario"], "Alumno")
        self.assertIn("Sistemas", res["carrera_o_departamento"])

    def test_busqueda_docente_existente(self):
        """Verifica que un docente sea encontrado sin importar mayúsculas o espacios."""
        res = buscar_en_base_escolar("  doc-1025  ")
        self.assertIsNotNone(res)
        self.assertIn("Aguilar", res["nombre_completo"])
        self.assertEqual(res["tipo_usuario"], "Docente")

    def test_busqueda_personal_existente(self):
        """Verifica que personal administrativo sea encontrado."""
        res = buscar_en_base_escolar("ADM-101")
        self.assertIsNotNone(res)
        self.assertEqual(res["tipo_usuario"], "Personal Administrativo")

    def test_busqueda_persona_inexistente(self):
        """Verifica que un número de control no registrado retorne None."""
        res = buscar_en_base_escolar("NO_EXISTE_9999")
        self.assertIsNone(res)

    def test_registro_invitado_en_padrón(self):
        """Verifica que un invitado pueda guardarse en el padrón con su asunto."""
        matricula_inv = "INV-TEST-001"
        # Eliminar si existía previamente
        try:
            with self.db._get_sqlite_connection() as conn:
                conn.cursor().execute("DELETE FROM estudiantes WHERE matricula = ?", (matricula_inv,))
                conn.commit()
        except Exception:
            pass

        vector = np.random.rand(128).astype(np.float64)
        # Normalizar vector L2
        vector = vector / np.linalg.norm(vector)

        est = self.db.save_estudiante(
            matricula=matricula_inv,
            nombre="Proveedor Bimbo",
            carrera="Invitado: Venta de productos cafetería",
            embedding=vector
        )
        self.assertIsNotNone(est)
        self.assertEqual(est.matricula, matricula_inv)
        self.assertIn("Invitado", est.carrera)

        # Limpieza
        with self.db._get_sqlite_connection() as conn:
            conn.cursor().execute("DELETE FROM estudiantes WHERE matricula = ?", (matricula_inv,))
            conn.commit()


if __name__ == "__main__":
    unittest.main()
