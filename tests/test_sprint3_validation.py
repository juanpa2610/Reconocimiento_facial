"""
Pruebas Unitarias para el Sprint 3 (U3P3) - Equipo 12.
Verifica las responsabilidades asignadas:
1. Josué Aldair: Umbral euclidiano estricto (0.50), matches con FaceMatcher (< 0.50, > 0.50, borde 0.50, NaN/dimensión) y filtrado de desconocidos.
2. Samantha: Normalización de texto/acentos, búsqueda flexible de nombres, validación real de fechas y horas, y bloqueo de rangos invertidos o incompletos.
3. Aleida: Cambio seguro de contraseña con hash PBKDF2 y alertas visibles en consultas sin resultados.
4. Guadalupe Velázquez: Generación de reporte diario en Excel, retención de bitácoras por fecha/tope y conservación de evidencia.
5. Darian: Validación sintáctica de matrículas ITSX (generación 07 a 267O, formato AA7O#####, rechazo de 277O, caracteres raros, etc.).
"""

import unittest
import os
import shutil
import tempfile
from datetime import datetime, date, time
import numpy as np

import config
from src.db.database import Database
from src.db.models import Estudiante
from src.utils.validators import validar_matricula_itsx, ANIO_INICIO_ITSX, ANIO_ACTUAL_ITSX
from src.utils.text_filters import (
    normalizar_texto,
    coincide_nombre,
    validar_fecha,
    validar_hora,
    validar_rango_fechas,
    validar_rango_horas
)
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
    # 1. Josué Aldair: Umbral y Filtrado de Desconocidos (FaceMatcher)
    # -------------------------------------------------------------------------
    def test_umbral_calibrado_y_desconocidos(self):
        """Comprueba que el umbral esté en 0.50 y un vector lejano se clasifique como no registrado."""
        self.assertEqual(config.FACE_DISTANCE_THRESHOLD, 0.50)
        matcher = FaceMatcher(threshold=config.FACE_DISTANCE_THRESHOLD)
        self.assertEqual(matcher.threshold, 0.50)

        # Si no hay registrados, match debe ser falso y estudiante None
        rand_emb = np.random.randn(128)
        res = matcher.match_candidate(rand_emb)
        self.assertFalse(res.reconocido)
        self.assertIsNone(res.estudiante)

    def test_facematcher_distancia_menor_umbral(self):
        """Vector a distancia < 0.50 de un alumno registrado -> reconocido=True con su estudiante."""
        matcher = FaceMatcher(threshold=0.50)
        base_vec = np.zeros(128, dtype=np.float64)
        base_vec[0] = 1.0

        estudiante = Estudiante(id=1, matricula="237O00728", nombre="Juan Pablo", carrera="Sistemas", embedding=base_vec)
        matcher.set_known_students([estudiante])

        # Crear candidato a distancia 0.30 (< 0.50)
        candidato = base_vec.copy()
        candidato[1] = 0.30
        res = matcher.match_candidate(candidato)

        self.assertTrue(res.reconocido)
        self.assertIsNotNone(res.estudiante)
        self.assertEqual(res.estudiante.matricula, "237O00728")
        self.assertLess(res.distancia, 0.50)

    def test_facematcher_distancia_mayor_umbral(self):
        """Vector a distancia > 0.50 de un alumno registrado -> reconocido=False, estudiante is None."""
        matcher = FaceMatcher(threshold=0.50)
        base_vec = np.zeros(128, dtype=np.float64)
        base_vec[0] = 1.0

        estudiante = Estudiante(id=1, matricula="237O00728", nombre="Juan Pablo", carrera="Sistemas", embedding=base_vec)
        matcher.set_known_students([estudiante])

        # Crear candidato a distancia 0.70 (> 0.50)
        candidato = base_vec.copy()
        candidato[1] = 0.70
        res = matcher.match_candidate(candidato)

        self.assertFalse(res.reconocido)
        self.assertIsNone(res.estudiante)
        self.assertGreater(res.distancia, 0.50)

    def test_facematcher_borde_exacto_050(self):
        """Vector a distancia exactamente en el borde (0.50) -> reconocido=True (menor o igual)."""
        matcher = FaceMatcher(threshold=0.50)
        base_vec = np.zeros(128, dtype=np.float64)
        estudiante = Estudiante(id=2, matricula="237O00386", nombre="Samantha", carrera="Sistemas", embedding=base_vec)
        matcher.set_known_students([estudiante])

        candidato = base_vec.copy()
        candidato[0] = 0.50  # Distancia euclidiana exactamente 0.50
        res = matcher.match_candidate(candidato)

        self.assertTrue(res.reconocido)
        self.assertIsNotNone(res.estudiante)
        self.assertAlmostEqual(res.distancia, 0.50, places=4)

    def test_facematcher_nan_e_invalido(self):
        """Vectores con NaN, Inf o dimensión incorrecta no deben lanzar excepciones y retornar reconocido=False."""
        matcher = FaceMatcher(threshold=0.50)
        base_vec = np.ones(128, dtype=np.float64)
        matcher.set_known_students([Estudiante(id=3, matricula="237O00955", nombre="Josué", carrera="Sistemas", embedding=base_vec)])

        # Vector con NaN
        nan_vec = np.ones(128, dtype=np.float64)
        nan_vec[5] = np.nan
        res_nan = matcher.match_candidate(nan_vec)
        self.assertFalse(res_nan.reconocido)
        self.assertIsNone(res_nan.estudiante)

        # Vector con Inf
        inf_vec = np.ones(128, dtype=np.float64)
        inf_vec[10] = np.inf
        res_inf = matcher.match_candidate(inf_vec)
        self.assertFalse(res_inf.reconocido)

        # Dimensión errónea (64 en vez de 128)
        dim_err = np.ones(64, dtype=np.float64)
        res_dim = matcher.match_candidate(dim_err)
        self.assertFalse(res_dim.reconocido)

    # -------------------------------------------------------------------------
    # 2. Samantha: Filtros de Fecha, Hora y Coincidencia de Nombres
    # -------------------------------------------------------------------------
    def test_normalizacion_y_coincidencia_nombres(self):
        """Verifica coincidencia independiente de acentos, mayúsculas y orden de palabras."""
        nombre_oficial = "Velázquez López Guadalupe"
        
        # Consultas en diferente orden y con/sin acento
        self.assertTrue(coincide_nombre("velazquez guadalupe", nombre_oficial))
        self.assertTrue(coincide_nombre("guadalupe velazquez", nombre_oficial))
        self.assertTrue(coincide_nombre("lopez guadalupe velazquez", nombre_oficial))
        self.assertTrue(coincide_nombre("VELÁZQUEZ", nombre_oficial))
        self.assertFalse(coincide_nombre("Roberto Carlos", nombre_oficial))

    def test_validacion_fechas_reales_e_imposibles(self):
        """Rechaza fechas inexistentes como 2026-13-45 o 2026-02-30 y acepta válidas."""
        ok, d_val, _ = validar_fecha("2026-10-19")
        self.assertTrue(ok)
        self.assertEqual(d_val, date(2026, 10, 19))

        # Fechas imposibles
        ok_imp1, _, msg1 = validar_fecha("2026-13-45")
        self.assertFalse(ok_imp1)
        self.assertIn("inexistente", msg1)

        ok_imp2, _, msg2 = validar_fecha("2026-02-30")
        self.assertFalse(ok_imp2)

    def test_validacion_horas_reales_e_imposibles(self):
        """Rechaza horas imposibles como 25:99 o 12:75 y acepta válidas."""
        ok, t_val, _ = validar_hora("14:30")
        self.assertTrue(ok)
        self.assertEqual(t_val, time(14, 30))

        ok_imp1, _, msg1 = validar_hora("25:99")
        self.assertFalse(ok_imp1)
        self.assertIn("inexistente", msg1)

        ok_imp2, _, _ = validar_hora("12:80")
        self.assertFalse(ok_imp2)

    def test_validacion_rangos_invertidos_e_incompletos(self):
        """Bloquea rangos invertidos comparando objetos reales de fecha y hora."""
        # Fechas invertidas
        ok_r, msg_r = validar_rango_fechas("2026-10-25", "2026-10-10")
        self.assertFalse(ok_r)
        self.assertIn("Rango invertido", msg_r)

        # Horas invertidas
        ok_h, msg_h = validar_rango_horas("18:30", "09:00")
        self.assertFalse(ok_h)
        self.assertIn("Rango invertido", msg_h)

        # Rango correcto
        ok_h_corr, _ = validar_rango_horas("08:00", "14:00")
        self.assertTrue(ok_h_corr)

    # -------------------------------------------------------------------------
    # 3. Aleida: Cambio seguro de contraseña de usuario
    # -------------------------------------------------------------------------
    def test_cambio_password_seguro(self):
        """Verifica que se actualice la contraseña con hash PBKDF2 y se rechacen contraseñas cortas o erróneas."""
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
        ok_cambio, _ = self.db.cambiar_password_usuario("operador_test", "mala_clave", "nueva123")
        self.assertFalse(ok_cambio)

        # Intentar con clave nueva menor a 6 caracteres
        ok_cambio, _ = self.db.cambiar_password_usuario("operador_test", "clave123", "123")
        self.assertFalse(ok_cambio)

        # Cambio correcto
        ok_cambio, _ = self.db.cambiar_password_usuario("operador_test", "clave123", "nuevaClave123")
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

    def test_exportacion_verificada_borra_solo_fecha_elegible(self):
        from datetime import date, timedelta
        day = (date.today() - timedelta(days=max(config.LOG_KEEP_DAYS + 2, 9))).isoformat()
        protected = (date.today() - timedelta(days=2)).isoformat()
        for i, fecha in enumerate((day, day, protected, date.today().isoformat())):
            log = self.db.log_acceso(nombre=f"Persona {i}", estado="DENEGADO")
            with self.db._get_sqlite_connection() as conn:
                conn.execute("UPDATE registro_accesos SET timestamp=? WHERE id=?", (f"{fecha} 12:00:00", log.id))
        path = generar_reporte_diario_excel(fecha=day, output_dir=self.test_dir)
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True)
        verified = book.active.max_row - 1
        book.close()
        self.assertEqual(verified, 2)
        self.assertEqual(self.db.eliminar_accesos_dia_exportado(day, verified), 2)
        logs = self.db.get_recent_accesos(limit=20)
        timestamps = [str(log.timestamp)[:10] for log in logs]
        self.assertNotIn(day, timestamps)
        self.assertIn(protected, timestamps)
        self.assertIn(date.today().isoformat(), timestamps)

    def test_excel_incompleto_no_borra_accesos(self):
        from datetime import date, timedelta
        day = (date.today() - timedelta(days=max(config.LOG_KEEP_DAYS + 2, 9))).isoformat()
        log = self.db.log_acceso(nombre="Debe conservarse", estado="DENEGADO")
        with self.db._get_sqlite_connection() as conn:
            conn.execute("UPDATE registro_accesos SET timestamp=? WHERE id=?", (f"{day} 12:00:00", log.id))
        with self.assertRaises(ValueError):
            self.db.eliminar_accesos_dia_exportado(day, 0)
        self.assertEqual(len(self.db.get_recent_accesos(limit=10)), 1)

    def test_invitado_expira_a_las_24_horas(self):
        from datetime import datetime, timedelta
        guest = self.db.save_estudiante("INV-TEST-24H", "Invitado Temporal", "Invitado: visita", np.ones(128))
        self.db.registrar_consentimiento("INV-TEST-24H", "Invitado", True)
        access = self.db.log_acceso(estudiante_id=guest.id, matricula=guest.matricula,
                                    nombre=guest.nombre, estado="PERMITIDO", tipo_usuario="invitado")
        expired = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db._get_sqlite_connection() as conn:
            conn.execute("UPDATE estudiantes SET created_at=? WHERE matricula=?", (expired, guest.matricula))
        self.assertEqual(self.db.purgar_invitados_expirados(), 1)
        self.assertIsNone(self.db.get_estudiante_by_matricula(guest.matricula))
        self.assertIsNone(self.db.consultar_consentimiento(guest.matricula))
        self.assertNotIn(access.id, [log.id for log in self.db.get_recent_accesos(limit=20)])

    def test_siembra_no_elimina_usuarios_personalizados(self):
        with self.db._get_sqlite_connection() as conn:
            conn.execute("INSERT INTO usuarios (username,password_hash,nombre_completo,rol,activo) VALUES (?,?,?,?,1)",
                         ("cuenta_personalizada", "hash_de_prueba", "Cuenta Prueba", "operador"))
        self.db.init_db()
        with self.db._get_sqlite_connection() as conn:
            row = conn.execute("SELECT username FROM usuarios WHERE username=?", ("cuenta_personalizada",)).fetchone()
        self.assertIsNotNone(row)

    # -------------------------------------------------------------------------
    # 5. Darian: Validación sintáctica de matrículas ITSX (Regla 267O)
    # -------------------------------------------------------------------------
    def test_validacion_matricula_itsx(self):
        """Valida que solo se acepten matrículas de generación 07 a 267O y formatos válidos."""
        # 1. Matrículas válidas de alumnos
        valida, _ = validar_matricula_itsx("237O00728")
        self.assertTrue(valida)
        valida, _ = validar_matricula_itsx("267O00123")  # Generación actual 267O
        self.assertTrue(valida)
        valida, _ = validar_matricula_itsx("237000728")  # Tolerancia 0 en lugar de O
        self.assertTrue(valida)
        valida, _ = validar_matricula_itsx("077O00001")  # Generación 07 (primera admitida)
        self.assertTrue(valida)

        # 2. Claves institucionales válidas (no alumnos)
        valida, _ = validar_matricula_itsx("INV-20261019-001")
        self.assertTrue(valida)
        valida, _ = validar_matricula_itsx("DOC-12345")
        self.assertTrue(valida)

        # 3. Inválidas por generación futura o inexistente
        valida, msg = validar_matricula_itsx("277O00123")  # Generación futura 277O
        self.assertFalse(valida)
        self.assertIn("inválida", msg)

        valida, msg = validar_matricula_itsx("067O00123")  # Previa a generación 07
        self.assertFalse(valida)

        # 4. Inválidas por caracteres especiales o longitud incorrecta
        valida, msg = validar_matricula_itsx("23#00123")
        self.assertFalse(valida)
        self.assertIn("caracteres inválidos", msg)

        valida, _ = validar_matricula_itsx("237O0072")    # Longitud 8 (debe ser 9)
        self.assertFalse(valida)

        valida, _ = validar_matricula_itsx("237O007288")  # Longitud 10
        self.assertFalse(valida)

        valida, _ = validar_matricula_itsx("23XO00728")   # No tiene '7' en posición 3
        self.assertFalse(valida)

        valida, _ = validar_matricula_itsx("")            # Vacía
        self.assertFalse(valida)


if __name__ == '__main__':
    unittest.main()
