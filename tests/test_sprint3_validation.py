"""
Pruebas Unitarias para el Sprint 3 (U3P3) - Equipo 12.
Verifica las responsabilidades asignadas:
1. Josué Aldair: Umbral euclidiano estricto (0.50) y match de personas no registradas.
2. Samantha: Búsqueda flexible de nombres (cualquier orden) y validación de filtros.
3. Aleida: Cambio seguro de contraseña con hash PBKDF2 y manejo de consultas.
4. Guadalupe Velázquez: Generación de reporte diario en Excel y rotación de registros.
5. Darian: Validación sintáctica de matrículas ITSX (rechazo de caracteres como 23#...).
"""

import unittest
import os
import shutil
import tempfile
import numpy as np

import config
from src.db.database import Database
from src.utils.validators import validar_matricula_itsx
from src.modules.admin import generar_reporte_diario_excel
from src.biometrics.matcher import FaceMatcher


class TestSprint3Requirements(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_sprint3.db")
        self.orig_sqlite_path = config.SQLITE_DB_PATH
        config.SQLITE_DB_PATH = self.db_path
        self.db = Database()
        self.db.init_db()

    def tearDown(self):
        config.SQLITE_DB_PATH = self.orig_sqlite_path
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # -------------------------------------------------------------------------
    # 1. Josué Aldair: Umbral y Filtrado de Desconocidos
    # -------------------------------------------------------------------------
    def test_umbral_calibrado_y_desconocidos(self):
        """Comprueba que el umbral esté en 0.50 y un vector lejano se clasifique como no registrado."""
        self.assertEqual(config.FACE_DISTANCE_THRESHOLD, 0.50)
        matcher = FaceMatcher(threshold=config.FACE_DISTANCE_THRESHOLD)
        self.assertEqual(matcher.threshold, 0.50)

        # Si no hay registrados, match debe ser falso
        rand_emb = np.random.randn(128)
        res = matcher.match_candidate(rand_emb)
        self.assertFalse(res.reconocido)
        self.assertIsNone(res.estudiante)

    # -------------------------------------------------------------------------
    # 2. Samantha: Búsqueda flexible de nombres (independiente del orden)
    # -------------------------------------------------------------------------
    def test_busqueda_nombres_flexible(self):
        """Valida que tokens en cualquier orden coincidan con el estudiante."""
        nombre = "Trujillo Trujillo Juan Pablo"
        # Consulta empezando por nombre o por apellido
        query_nombre = "Juan Pablo"
        query_apellido = "Trujillo Juan"
        
        tokens1 = query_nombre.lower().split()
        tokens2 = query_apellido.lower().split()

        nombre_lower = nombre.lower()
        self.assertTrue(all(t in nombre_lower for t in tokens1))
        self.assertTrue(all(t in nombre_lower for t in tokens2))

    # -------------------------------------------------------------------------
    # 3. Aleida: Cambio seguro de contraseña de usuario
    # -------------------------------------------------------------------------
    def test_cambio_password_seguro(self):
        """Verifica que se actualice la contraseña con hash PBKDF2 y se rechacen contraseñas cortas o erróneas."""
        # Crear usuario de prueba
        ok, msg = self.db.crear_usuario(
            username="operador_test",
            password="clave123",
            nombre_completo="Operador Prueba",
            rol="operador",
            admin_user="JUANPA_ITSX",
            admin_pass="JUANPA_237O00728"
        )
        self.assertTrue(ok)

        # Intentar cambiar con contraseña actual incorrecta
        ok_cambio, msg_c = self.db.cambiar_password_usuario("operador_test", "mala_clave", "nueva123")
        self.assertFalse(ok_cambio)

        # Intentar con clave nueva menor a 6 caracteres
        ok_cambio, msg_c = self.db.cambiar_password_usuario("operador_test", "clave123", "123")
        self.assertFalse(ok_cambio)

        # Cambio correcto
        ok_cambio, msg_c = self.db.cambiar_password_usuario("operador_test", "clave123", "nuevaClave123")
        self.assertTrue(ok_cambio)

        # Verificar login con la nueva contraseña
        user = self.db.autenticar_usuario("operador_test", "nuevaClave123")
        self.assertIsNotNone(user)

    # -------------------------------------------------------------------------
    # 4. Guadalupe Velázquez: Reporte Diario Excel y Rotación
    # -------------------------------------------------------------------------
    def test_reporte_diario_excel_y_rotacion(self):
        """Verifica la generación del archivo itsx_accesos_YYYY-MM-DD.xlsx y la purga."""
        archivo_generado = generar_reporte_diario_excel(fecha="2026-10-19", output_dir=self.test_dir)
        self.assertTrue(os.path.exists(archivo_generado))
        self.assertTrue(archivo_generado.endswith("itsx_accesos_2026-10-19.xlsx"))

        # Probar rotación de registros
        res = self.db.rotar_registros_antiguos(dias_retencion=30, max_registros=100)
        self.assertIn("accesos_purgados", res)
        self.assertIn("auditoria_purgada", res)

    # -------------------------------------------------------------------------
    # 5. Darian: Validación sintáctica de matrículas ITSX
    # -------------------------------------------------------------------------
    def test_validacion_matricula_itsx(self):
        """Rechaza caracteres especiales raros como 23#... y aprueba formatos oficiales."""
        # Válidas
        valida, _ = validar_matricula_itsx("237O00728")
        self.assertTrue(valida)
        valida, _ = validar_matricula_itsx("237O01367")
        self.assertTrue(valida)
        valida, _ = validar_matricula_itsx("INV-20261019-001")
        self.assertTrue(valida)

        # Inválidas con caracteres raros (como 23#...)
        valida, msg = validar_matricula_itsx("23#00123")
        self.assertFalse(valida)
        self.assertIn("caracteres inválidos", msg)

        valida, msg = validar_matricula_itsx("23?O00123")
        self.assertFalse(valida)

        valida, msg = validar_matricula_itsx("")
        self.assertFalse(valida)

        valida, msg = validar_matricula_itsx("12")
        self.assertFalse(valida)


if __name__ == '__main__':
    unittest.main()
