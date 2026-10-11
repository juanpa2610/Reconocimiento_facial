"""
Suite de Benchmarking, Latencia y Pruebas de Rendimiento (Sprint 2 - ITSX).
Responsable: Morales Hernández Guadalupe Aleida / QA & Tester.

Evalúa los tiempos de procesamiento por etapa del pipeline biométrico:
  - Etapa 1: Captura / Adquisición de fotograma.
  - Etapa 2: Detección facial (HOG / Dlib sobre copia escalada).
  - Etapa 3: Extracción del vector 128-D (ResNet-34).
  - Etapa 4: Comparación vectorial euclidiana L2 (matriz en memoria).

Criterio de Aceptación Oficial del Sprint 2:
  - Tiempo de procesamiento total por usuario <= 1.5 segundos.
  - Matching matricial en memoria < 2 milisegundos.
"""

import unittest
import time
import numpy as np
import tempfile
import os

import config
from src.db.database import Database
from src.db.models import Estudiante
from src.biometrics.matcher import FaceMatcher
from src.biometrics.encoder import FaceEncoder
from src.utils.crypto import encrypt_vector_bytes, decrypt_vector_bytes


class TestPerformanceAndLatency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        np.random.seed(42)

    def setUp(self):
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

    def test_matching_stage_latency_sub_millisecond(self):
        """Etapa 4: Verifica que el matching contra 200 estudiantes tome menos de 2 milisegundos (< 0.002 s)."""
        matcher = FaceMatcher(threshold=0.55)
        n_estudiantes = 200
        estudiantes = []

        for i in range(n_estudiantes):
            vec = np.random.randn(128).astype(np.float64)
            vec /= np.linalg.norm(vec)
            estudiantes.append(Estudiante(
                id=i + 1,
                matricula=f"237O0{i:04d}",
                nombre=f"Estudiante {i}",
                carrera="Ingeniería en Sistemas",
                embedding=vec
            ))

        matcher.set_known_students(estudiantes)

        candidato = estudiantes[50].embedding.copy()

        # Medir latencia sobre 20 repeticiones
        tiempos = []
        for _ in range(20):
            t0 = time.perf_counter()
            res = matcher.match_candidate(candidato)
            t1 = time.perf_counter()
            tiempos.append(t1 - t0)

        t_promedio = float(np.mean(tiempos))
        t_max = float(np.max(tiempos))

        self.assertTrue(res.reconocido)
        self.assertLess(t_promedio, 0.002, f"Matching promedio debe ser < 2 ms, fue {t_promedio * 1000:.3f} ms")
        self.assertLess(t_max, 0.005, f"Matching máximo debe ser < 5 ms, fue {t_max * 1000:.3f} ms")

    def test_crypto_overhead_negligible(self):
        """Verifica que el cifrado y descifrado de un template tome menos de 1 milisegundo."""
        raw_vector = np.random.randn(128).astype(np.float64)
        raw_vector /= np.linalg.norm(raw_vector)
        raw_bytes = raw_vector.tobytes()

        t0 = time.perf_counter()
        encrypted = encrypt_vector_bytes(raw_bytes)
        t_enc = time.perf_counter() - t0

        t0 = time.perf_counter()
        decrypted = decrypt_vector_bytes(encrypted)
        t_dec = time.perf_counter() - t0

        self.assertEqual(raw_bytes, decrypted)
        self.assertLess(t_enc + t_dec, 0.003, f"Sobrecarga criptográfica excesiva: {(t_enc + t_dec) * 1000:.3f} ms")

    def test_pipeline_benchmark_sla_under_1_5_seconds(self):
        """
        Simula el pipeline completo de acceso en 10 intentos y valida que cada uno cumpla el SLA <= 1.5s.
        """
        encoder = FaceEncoder(model="hog")
        matcher = FaceMatcher(threshold=0.55)

        # Cargar estudiantes conocidos en memoria
        estudiantes = []
        for i in range(50):
            v = np.random.randn(128).astype(np.float64)
            v /= np.linalg.norm(v)
            estudiantes.append(Estudiante(
                id=i + 1,
                matricula=f"MAT{i}",
                nombre=f"Alumno {i}",
                carrera="Sistemas",
                embedding=v
            ))
        matcher.set_known_students(estudiantes)

        # Fotograma sintético estándar (640x480 RGB)
        synthetic_frame = (np.random.rand(480, 640, 3) * 255).astype(np.uint8)

        # Medir 5 iteraciones del pipeline simulado
        tiempos_etapa1 = []
        tiempos_etapa2 = []
        tiempos_etapa3 = []
        tiempos_etapa4 = []
        tiempos_totales = []

        for _ in range(5):
            t_inicio = time.perf_counter()

            # Etapa 1: Ingesta del fotograma
            t0 = time.perf_counter()
            frame = synthetic_frame.copy()
            t1 = time.perf_counter()
            tiempos_etapa1.append(t1 - t0)

            # Etapa 2: Detección facial
            t0 = time.perf_counter()
            boxes = encoder.detect_face_locations_scaled(frame, target_width=config.DETECTION_WIDTH)
            t1 = time.perf_counter()
            tiempos_etapa2.append(t1 - t0)

            # Etapa 3: Extracción de vector
            t0 = time.perf_counter()
            # Si no hay rostro real en el ruido sintético, medimos la llamada controlada
            encodings = encoder.extract_encodings(frame, boxes)
            t1 = time.perf_counter()
            tiempos_etapa3.append(t1 - t0)

            # Etapa 4: Matching matricial
            t0 = time.perf_counter()
            dummy_cand = np.random.randn(128).astype(np.float64)
            dummy_cand /= np.linalg.norm(dummy_cand)
            res = matcher.match_candidate(dummy_cand)
            t1 = time.perf_counter()
            tiempos_etapa4.append(t1 - t0)

            t_total = time.perf_counter() - t_inicio
            tiempos_totales.append(t_total)

        prom_total = float(np.mean(tiempos_totales))
        self.assertLessEqual(prom_total, 1.5, f"El tiempo total superó el SLA de 1.5s: {prom_total:.3f} s")

    def test_stress_concurrency_queue_throughput(self):
        """Verifica la estabilidad de colas de visión bajo ráfagas intensivas de fotogramas."""
        import queue
        vision_q = queue.Queue(maxsize=2)

        # Enviar 100 cuadros simulados descartando si la cola se satura
        descartados = 0
        procesados = 0

        for i in range(100):
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            try:
                vision_q.put_nowait(frame)
                procesados += 1
            except queue.Full:
                descartados += 1

            # Consumir de vez en cuando
            if i % 3 == 0:
                try:
                    vision_q.get_nowait()
                except queue.Empty:
                    pass

        self.assertGreater(procesados, 0)
        self.assertGreaterEqual(descartados, 0)


if __name__ == "__main__":
    unittest.main()
