"""
Suite de Pruebas Automatizadas para el Sistema Biométrico.
Verifica la consistencia matemática, serialización de templates, operaciones en base de datos
y las validaciones preventivas de duplicados (por matrícula y por vector biométrico).
"""

import unittest
import numpy as np
import os
import tempfile

from src.db.database import Database
from src.db.models import Estudiante
from src.biometrics.matcher import FaceMatcher
from src.biometrics.liveness import BlinkLivenessDetector, eye_aspect_ratio


class TestBiometricSystem(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)  # Semilla fija para reproducibilidad y estabilidad estadística
        # Base de datos temporal para pruebas unitarias aisladas
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.db = Database()
        self.db.engine = "sqlite"
        self.db.sqlite_path = self.db_path
        self.db.init_db()


    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_vector_serialization_dimensions(self):
        """Verifica que el template serializado sea exactamente de 1024 bytes (128 floats de 64 bits)."""
        original_vector = np.random.randn(128).astype(np.float64)
        original_vector /= np.linalg.norm(original_vector)

        serialized = Database.serialize_vector(original_vector)
        self.assertEqual(len(serialized), 1024, "El vector de 128 floats de 64 bits debe pesar exactamente 1024 bytes")

        recovered_vector = Database.deserialize_vector(serialized)
        self.assertEqual(recovered_vector.shape, (128,))
        np.testing.assert_allclose(original_vector, recovered_vector, rtol=1e-12, atol=1e-12)

    def test_invalid_vector_dimensions_raise_error(self):
        """Verifica que vectores con dimensiones distintas de 128 sean rechazados."""
        bad_vector = np.zeros(64, dtype=np.float64)
        with self.assertRaises(ValueError):
            Database.serialize_vector(bad_vector)

    def test_database_persistence_without_images(self):
        """Verifica que el estudiante se guarde y recupere exclusivamente mediante su vector en la BD."""
        dummy_vector = np.random.randn(128).astype(np.float64)
        dummy_vector /= np.linalg.norm(dummy_vector)

        matricula = "237000728"
        nombre = "Juan Pablo Perez"
        carrera = "Ingeniería en Sistemas"

        estudiante = self.db.save_estudiante(matricula, nombre, carrera, dummy_vector)
        self.assertIsNotNone(estudiante)
        self.assertEqual(estudiante.matricula, matricula)

        recuperado = self.db.get_estudiante_by_matricula(matricula)
        self.assertIsNotNone(recuperado)
        self.assertEqual(recuperado.nombre, nombre)
        self.assertEqual(recuperado.carrera, carrera)
        self.assertEqual(recuperado.embedding.shape, (128,))
        np.testing.assert_allclose(recuperado.embedding, dummy_vector)

    def test_euclidean_distance_and_matching(self):
        """Verifica que la distancia euclidiana L2 confirme o rechace identidades según el umbral."""
        matcher = FaceMatcher(threshold=0.55)

        base_vector = np.random.randn(128).astype(np.float64)
        base_vector /= np.linalg.norm(base_vector)

        student = Estudiante(
            id=1,
            matricula="1001",
            nombre="Estudiante Prueba",
            carrera="Computación",
            embedding=base_vector
        )

        # 1. Distancia idéntica (d = 0.0) -> Debe reconocer
        result_same = matcher.match(base_vector, [student])
        self.assertTrue(result_same.reconocido)
        self.assertAlmostEqual(result_same.distancia, 0.0, places=4)
        self.assertGreaterEqual(result_same.confianza_pct, 99.0)

        # 2. Vector con ligera perturbación (dentro de umbral, d ~ 0.20) -> Debe reconocer
        slight_noise = np.random.randn(128) * 0.02
        close_vector = base_vector + slight_noise
        close_vector /= np.linalg.norm(close_vector)

        result_close = matcher.match(close_vector, [student])
        self.assertTrue(result_close.reconocido)
        self.assertLessEqual(result_close.distancia, 0.55)

        # 3. Vector totalmente distinto (d > 0.8) -> Debe rechazar
        different_vector = np.random.randn(128).astype(np.float64)
        different_vector /= np.linalg.norm(different_vector)

        result_diff = matcher.match(different_vector, [student])
        self.assertFalse(result_diff.reconocido)
        self.assertGreater(result_diff.distancia, 0.55)

    def test_duplicate_matricula_detection(self):
        """Verifica la validación previa por matrícula (Nivel Datos)."""
        vec = np.random.randn(128).astype(np.float64)
        vec /= np.linalg.norm(vec)

        self.db.save_estudiante("MAT-999", "Alumno A", "Sistemas", vec)
        alumno = self.db.get_estudiante_by_matricula("MAT-999")
        self.assertIsNotNone(alumno)
        self.assertEqual(alumno.nombre, "Alumno A")

    def test_preventive_biometric_duplicate_detection(self):
        """Verifica la validación biométrica preventiva contra rostros duplicados (Nivel Rostro)."""
        matcher = FaceMatcher(threshold=0.55)

        # Alumno 1 ya registrado en BD
        vec_alumno1 = np.random.randn(128).astype(np.float64)
        vec_alumno1 /= np.linalg.norm(vec_alumno1)
        self.db.save_estudiante("MAT-001", "Carlos Mendoza", "Mecatrónica", vec_alumno1)

        registrados = self.db.get_all_active_estudiantes()

        # Intento de enrolar con nueva matrícula 'MAT-002', pero con el mismo rostro (o ligera variación d <= 0.55)
        vec_intento = vec_alumno1 + (np.random.randn(128) * 0.01)
        vec_intento /= np.linalg.norm(vec_intento)

        match_dup = matcher.match(vec_intento, registrados)
        self.assertTrue(match_dup.reconocido, "Debe detectar que el rostro ya existe")
        self.assertEqual(match_dup.estudiante.matricula, "MAT-001")
        self.assertEqual(match_dup.estudiante.nombre, "Carlos Mendoza")
        self.assertLessEqual(match_dup.distancia, 0.55)

    def test_access_audit_log(self):
        """Verifica que los eventos de acceso queden registrados con su métrica de distancia."""
        log = self.db.log_acceso(
            estudiante_id=1,
            matricula="237000728",
            nombre="Juan Pablo",
            distancia=0.3421,
            estado="PERMITIDO"
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.estado, "PERMITIDO")

        logs = self.db.get_recent_accesos(limit=10)
        self.assertEqual(len(logs), 1)
    def test_verificar_rostro_previo_function(self):
        """Prueba la función modular de verificación biométrica previa (Biometría Primero)."""
        from src.modules.registro import verificar_rostro_previo

        vec_base = np.random.randn(128).astype(np.float64)
        vec_base /= np.linalg.norm(vec_base)
        self.db.save_estudiante("MAT-PREV", "Alumno Previo", "Computación", vec_base)

        # 1. Rostro idéntico -> Debe retornar ya_registrado=True y el estudiante
        ya_reg, est, dist = verificar_rostro_previo(vec_base, db=self.db, threshold=0.55)
        self.assertTrue(ya_reg)
        self.assertIsNotNone(est)
        self.assertEqual(est.matricula, "MAT-PREV")
        self.assertAlmostEqual(dist, 0.0, places=4)

        # 2. Rostro nuevo totalmente distinto -> Debe retornar ya_registrado=False
        vec_nuevo = np.random.randn(128).astype(np.float64)
        vec_nuevo /= np.linalg.norm(vec_nuevo)
        ya_reg_nuevo, est_nuevo, dist_nuevo = verificar_rostro_previo(vec_nuevo, db=self.db, threshold=0.55)
        self.assertFalse(ya_reg_nuevo)
        self.assertIsNone(est_nuevo)
        self.assertGreater(dist_nuevo, 0.55)

    def test_cached_matrix_matcher(self):
        """Verifica la optimización de caché de la matriz (N, 128) y medición de tiempo en sub-milisegundo."""
        matcher = FaceMatcher(threshold=0.55)

        # Generar 20 estudiantes sintéticos con vectores unitarios
        alumnos = []
        for i in range(20):
            v = np.random.randn(128).astype(np.float64)
            v /= np.linalg.norm(v)
            alumnos.append(Estudiante(id=i+1, matricula=f"MAT-{i:03d}", nombre=f"Alumno {i}", carrera="ISC", embedding=v))

        # Precargar matriz en caché
        matcher.set_known_students(alumnos)
        self.assertEqual(matcher._cached_matrix.shape, (20, 128))

        # Candidato idéntico al alumno #7
        candidato = alumnos[7].embedding
        res, t_ms = matcher.match_with_timing(candidato)

        self.assertTrue(res.reconocido)
        self.assertEqual(res.estudiante.matricula, "MAT-007")
        self.assertAlmostEqual(res.distancia, 0.0, places=4)
        # La comparación vectorizada contra 20 identidades debe tomar menos de 5 milisegundos
        self.assertLess(t_ms, 5.0, f"El tiempo de matching fue {t_ms} ms, debería ser < 5 ms")

    def test_liveness_ear_and_blink(self):
        """Verifica el cálculo del Eye Aspect Ratio (EAR) y la detección de parpadeo humano."""
        # Definir 6 puntos de un ojo abierto: [p1, p2, p3, p4, p5, p6]
        # p1=(0,0), p4=(10,0) -> ancho horizontal = 10
        # p2=(3,3), p6=(3,-3) -> altura vertical 1 = 6
        # p3=(7,3), p5=(7,-3) -> altura vertical 2 = 6
        # EAR = (6 + 6) / (2 * 10) = 12 / 20 = 0.60
        open_eye = [(0.0, 0.0), (3.0, 3.0), (7.0, 3.0), (10.0, 0.0), (7.0, -3.0), (3.0, -3.0)]
        ear_open = eye_aspect_ratio(open_eye)
        self.assertGreater(ear_open, 0.25, "Ojo abierto debe tener EAR alto")

        # Ojo cerrado (altura vertical reducida a 1):
        # p2=(3, 0.5), p6=(3, -0.5) -> altura = 1.0
        # p3=(7, 0.5), p5=(7, -0.5) -> altura = 1.0
        # EAR = (1 + 1) / (2 * 10) = 0.10
        closed_eye = [(0.0, 0.0), (3.0, 0.5), (7.0, 0.5), (10.0, 0.0), (7.0, -0.5), (3.0, -0.5)]
        ear_closed = eye_aspect_ratio(closed_eye)
        self.assertLess(ear_closed, 0.15, "Ojo cerrado debe tener EAR bajo (< 0.15)")

        # Probar detector de parpadeo
        detector = BlinkLivenessDetector(ear_threshold=0.22, consec_frames=2, required_blinks=1)

        landmarks_abierto = {"left_eye": open_eye, "right_eye": open_eye}
        landmarks_cerrado = {"left_eye": closed_eye, "right_eye": closed_eye}

        # Estado inicial
        self.assertFalse(detector.is_live)

        # 3 cuadros de ojos abiertos -> sigue sin confirmar parpadeo
        for _ in range(3):
            detector.update(landmarks_abierto)
        self.assertFalse(detector.is_live)

        # 2 cuadros de ojos cerrados -> parpadeo en curso
        detector.update(landmarks_cerrado)
        detector.update(landmarks_cerrado)

        # Se vuelve a abrir el ojo -> parpadeo completado, vitalidad confirmada
        is_live, _, blinks = detector.update(landmarks_abierto)
        self.assertTrue(is_live, "Debe confirmar que el sujeto está vivo tras completar el parpadeo")
        self.assertEqual(blinks, 1)

        detector.reset()
        for _ in range(8):
            live, _, _ = detector.update(landmarks_abierto)
        self.assertFalse(live, "Una secuencia sin parpadeo no debe validar vitalidad")
        detector.update(landmarks_cerrado)
        detector.update(landmarks_cerrado)
        detector.reset()  # cambio de persona/rostro
        self.assertFalse(detector.update(landmarks_abierto)[0])


if __name__ == "__main__":
    unittest.main()

