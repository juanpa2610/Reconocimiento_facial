"""
Pruebas Automatizadas de Seguridad, Autenticación, RBAC, Integridad Criptográfica,
Prevención de Duplicados, Consentimientos LFPDPPP y Resiliencia Offline.
"""

import os
import json
import unittest
from unittest.mock import patch
import numpy as np

import config
from src.db.database import Database
from src.utils.crypto import encrypt_vector, decrypt_vector, derive_aes_key
from src.utils.security import hash_password, verify_password, encrypt_camera_secret, decrypt_camera_secret


class TestAuthAndSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database()
        cls.db.init_db()

    def setUp(self):
        # Limpieza previa de usuarios de prueba
        with self.db._get_sqlite_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM usuarios WHERE username LIKE 'test_%'")
            c.execute("DELETE FROM estudiantes WHERE matricula LIKE 'TEST_%'")
            c.execute("DELETE FROM consentimientos WHERE matricula LIKE 'TEST_%'")
            conn.commit()

    def tearDown(self):
        # Limpieza posterior
        with self.db._get_sqlite_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM usuarios WHERE username LIKE 'test_%'")
            c.execute("DELETE FROM estudiantes WHERE matricula LIKE 'TEST_%'")
            c.execute("DELETE FROM consentimientos WHERE matricula LIKE 'TEST_%'")
            conn.commit()

        # Limpiar archivo buffer de prueba si existiera
        if os.path.exists("test_offline_buffer.json"):
            try:
                os.remove("test_offline_buffer.json")
            except OSError:
                pass

    # -------------------------------------------------------------------------
    # 1. AUTENTICACIÓN Y HASHING SEGURO (PBKDF2)
    # -------------------------------------------------------------------------
    def test_pbkdf2_hashing_and_verification(self):
        """Verifica que el hashing PBKDF2 genere sales únicas y valide correctamente."""
        pass_plano = "ClaveUltraSegura#2026"
        hashed = hash_password(pass_plano)
        self.assertTrue(hashed.startswith("pbkdf2_sha256$100000$"))
        
        # Validar contraseña correcta
        self.assertTrue(verify_password(pass_plano, hashed))
        # Validar contraseña incorrecta
        self.assertFalse(verify_password("PasswordErroneo", hashed))
        # Verificar sal única (dos llamadas con misma clave producen hashes distintos)
        hashed2 = hash_password(pass_plano)
        self.assertNotEqual(hashed, hashed2)

    def test_verificar_credenciales_usuario(self):
        """Prueba el flujo de login de usuario en base de datos."""
        # Insertar usuario directamente para test
        hp = hash_password("OperadorPass123!")
        with self.db._get_sqlite_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) "
                "VALUES (?, ?, ?, ?, 1)",
                ("test_op", hp, "Operador de Pruebas", "operador")
            )
            conn.commit()

        # Login exitoso
        ok, usr, msg = self.db.verificar_credenciales("test_op", "OperadorPass123!")
        self.assertTrue(ok)
        self.assertIsNotNone(usr)
        self.assertEqual(usr.username, "test_op")
        self.assertEqual(usr.rol, "operador")

        # Login con contraseña errónea
        ok_bad, usr_bad, msg_bad = self.db.verificar_credenciales("test_op", "PasswordMal")
        self.assertFalse(ok_bad)
        self.assertIsNone(usr_bad)
        self.assertIn("incorrecta", msg_bad.lower())

        # Login con usuario inexistente
        ok_no, usr_no, msg_no = self.db.verificar_credenciales("test_no_existe", "PasswordMal")
        self.assertFalse(ok_no)
        self.assertIsNone(usr_no)

    # -------------------------------------------------------------------------
    # 2. CONTROL DE ACCESO BASADO EN ROLES (RBAC)
    # -------------------------------------------------------------------------
    def test_rbac_permisos_admin_vs_operador(self):
        """Verifica que verificar_credenciales_admin restrinja acceso a roles no administrativos."""
        hp_admin = hash_password("AdminPass2026!")
        hp_oper = hash_password("OperadorPass2026!")

        with self.db._get_sqlite_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) "
                "VALUES (?, ?, ?, ?, 1)",
                ("test_admin", hp_admin, "Super Administrador", "admin")
            )
            c.execute(
                "INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) "
                "VALUES (?, ?, ?, ?, 1)",
                ("test_oper", hp_oper, "Operador Simple", "operador")
            )
            conn.commit()

        # Administrador debe ser autorizado
        ok_adm, adm_obj, _ = self.db.verificar_credenciales_admin("test_admin", "AdminPass2026!")
        self.assertTrue(ok_adm)
        self.assertEqual(adm_obj.rol, "admin")

        # Operador debe ser RECHAZADO por no tener privilegios de Administrador
        ok_op, op_obj, msg_op = self.db.verificar_credenciales_admin("test_oper", "OperadorPass2026!")
        self.assertFalse(ok_op)
        self.assertIsNone(op_obj)
        self.assertIn("administrador", msg_op.lower())

    def test_rbac_crear_usuario_con_autorizacion(self):
        """Verifica que la creación de usuarios exija credenciales de administrador."""
        hp_admin = hash_password("RootAdmin77!")
        hp_oper = hash_password("OperSimple77!")

        with self.db._get_sqlite_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) "
                "VALUES (?, ?, ?, ?, 1)",
                ("test_admin_auth", hp_admin, "Admin Root", "admin")
            )
            c.execute(
                "INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) "
                "VALUES (?, ?, ?, ?, 1)",
                ("test_oper_auth", hp_oper, "Operador Normal", "operador")
            )
            conn.commit()

        # Intento de creación por operador -> Debe fallar
        ok_fail, msg_fail = self.db.crear_usuario(
            username="test_nuevo_01",
            password="NuevoPass123",
            nombre_completo="Nuevo Usuario",
            rol="operador",
            admin_user="test_oper_auth",
            admin_pass="OperSimple77!"
        )
        self.assertFalse(ok_fail)
        self.assertIn("administrador", msg_fail.lower())

        # Intento de creación por administrador -> Debe triunfar
        ok_ok, msg_ok = self.db.crear_usuario(
            username="test_nuevo_02",
            password="NuevoPass123!",
            nombre_completo="Usuario Aprobado",
            rol="operador",
            admin_user="test_admin_auth",
            admin_pass="RootAdmin77!"
        )
        self.assertTrue(ok_ok)
        self.assertIn("exitosamente", msg_ok.lower())

    # -------------------------------------------------------------------------
    # 3. PREVENCIÓN DE DUPLICADOS EN PADRÓN
    # -------------------------------------------------------------------------
    def test_prevencion_matricula_duplicada(self):
        """Verifica que save_estudiante impida registrar la misma matrícula dos veces."""
        v1 = np.random.rand(128).astype(np.float64)
        v1 = v1 / np.linalg.norm(v1)

        self.db.save_estudiante(
            matricula="TEST_MAT_01",
            nombre="Alumno Original",
            carrera="Sistemas",
            embedding=v1
        )

        v2 = np.random.rand(128).astype(np.float64)
        v2 = v2 / np.linalg.norm(v2)

        # Segundo registro con la misma matrícula debe disparar ValueError
        with self.assertRaises(ValueError) as ctx:
            self.db.save_estudiante(
                matricula="TEST_MAT_01",
                nombre="Alumno Impostor",
                carrera="Sistemas",
                embedding=v2
            )
        self.assertIn("ya está registrada", str(ctx.exception))

    def test_prevencion_rostro_duplicado(self):
        """Verifica que save_estudiante impida registrar un rostro biométricamente idéntico."""
        v1 = np.random.rand(128).astype(np.float64)
        v1 = v1 / np.linalg.norm(v1)

        self.db.save_estudiante(
            matricula="TEST_BIO_01",
            nombre="Alumno Primer Registro",
            carrera="Sistemas",
            embedding=v1
        )

        # Vector casi idéntico (distancia < 0.15 << umbral 0.6) con distinta matrícula
        v_similar = v1 + np.random.normal(0, 0.001, 128)
        v_similar = v_similar / np.linalg.norm(v_similar)

        with self.assertRaises(ValueError) as ctx:
            self.db.save_estudiante(
                matricula="TEST_BIO_02",
                nombre="Alumno Clon",
                carrera="Sistemas",
                embedding=v_similar
            )
        self.assertIn("similitud biométrica", str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # 4. CIFRADO AES-256-GCM Y DETECCIÓN DE ALTERACIONES
    # -------------------------------------------------------------------------
    def test_cifrado_aes_gcm_integridad_y_reversibilidad(self):
        """Verifica el ciclo de cifrado/descifrado de 128 flotantes con AES-256-GCM."""
        original = np.random.randn(128).astype(np.float64)
        original = original / np.linalg.norm(original)

        cifrado = encrypt_vector(original)
        self.assertTrue(cifrado.startswith(b"GCM2$"))
        # Header (5) + Nonce (12) + Ciphertext (1024) + Tag (16) = 1057 bytes
        self.assertEqual(len(cifrado), 1057)

        recuperado = decrypt_vector(cifrado)
        self.assertEqual(recuperado.shape, (128,))
        np.testing.assert_allclose(original, recuperado, rtol=1e-12, atol=1e-12)

    def test_deteccion_manipulacion_datos_aes_gcm(self):
        """Verifica que alterar 1 solo byte del ciphertext dispare error de integridad (InvalidTag)."""
        original = np.random.randn(128).astype(np.float64)
        cifrado = bytearray(encrypt_vector(original))

        # Modificar un solo byte en la zona del ciphertext
        cifrado[30] ^= 0xFF

        with self.assertRaises(ValueError) as ctx:
            decrypt_vector(bytes(cifrado))
        self.assertIn("alterado", str(ctx.exception).lower())

    def test_cifrado_contrasena_camara_rtsp(self):
        """Verifica el cifrado de credenciales de cámara RTSP con AES-256-GCM."""
        pwd_plano = "CameraAdminPass#99"
        enc = encrypt_camera_secret(pwd_plano)
        self.assertTrue(enc.startswith("gcm$"))

        dec = decrypt_camera_secret(enc)
        self.assertEqual(dec, pwd_plano)

    # -------------------------------------------------------------------------
    # 5. CONSENTIMIENTOS INFORMADOS LFPDPPP (PB-08)
    # -------------------------------------------------------------------------
    def test_registro_y_consulta_consentimiento_lfpdppp(self):
        """Verifica la generación de tokens criptográficos SHA-256 de consentimiento."""
        mat = "TEST_LFP_01"
        token = self.db.registrar_consentimiento(
            matricula=mat,
            tipo_usuario="Estudiante",
            otorgado=True,
            observaciones="Firma electrónica aceptada"
        )
        self.assertEqual(len(token), 64)  # SHA-256 hex string

        rec = self.db.consultar_consentimiento(mat)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["matricula"], mat)
        self.assertEqual(rec["consentimiento_otorgado"], 1)
        self.assertEqual(rec["token_consentimiento"], token)

    def test_registro_rechazo_explicito_lfpdppp(self):
        """Verifica que la negativa de consentimiento quede asentada formalmente."""
        mat = "TEST_LFP_REJ"
        token = self.db.registrar_consentimiento(
            matricula=mat,
            tipo_usuario="Invitado",
            otorgado=False,
            observaciones="Titular rechaza captura biométrica"
        )
        self.assertEqual(len(token), 64)

        rec = self.db.consultar_consentimiento(mat)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["consentimiento_otorgado"], 0)
        self.assertIn("rechaza", rec["observaciones"].lower())

    # -------------------------------------------------------------------------
    # 6. RESILIENCIA Y BUFFER OFFLINE (PB-06-03)
    # -------------------------------------------------------------------------
    def test_resiliencia_buffer_offline_y_flush(self):
        """Verifica que eventos de acceso fallidos se encolen localmente y se vacíen al reconectar."""
        # Configurar buffer de prueba
        buffer_file = "test_offline_buffer.json"
        self.db._offline_buffer_file = buffer_file
        self.db._offline_access_buffer.clear()

        # Simular fallo en la conexión a la base de datos durante log_acceso
        with patch.object(self.db, "_get_sqlite_connection", side_effect=Exception("Fallo inducido de red/disco")):
            reg = self.db.log_acceso(
                estudiante_id=None,
                matricula="TEST_OFFLINE_01",
                nombre="Persona en Modo Contingencia",
                distancia=0.25,
                estado="PERMITIDO",
                tiempo_acceso_segundos=0.12,
                tipo_usuario="estudiante",
                condicion_luz="Iluminación óptima (120 lux)"
            )
            # Debe retornar un RegistroAcceso con id=-1 para denotar modo contingencia
            self.assertEqual(reg.id, -1)

        # Verificar que el evento se resguardó en memoria y en disco
        self.assertEqual(len(self.db._offline_access_buffer), 1)
        self.assertTrue(os.path.exists(buffer_file))

        with open(buffer_file, "r", encoding="utf-8") as f:
            datos_guardados = json.load(f)
        self.assertEqual(len(datos_guardados), 1)
        self.assertEqual(datos_guardados[0]["matricula"], "TEST_OFFLINE_01")

        # Restaurar conectividad y ejecutar flush
        sincronizados = self.db.flush_offline_records()
        self.assertEqual(sincronizados, 1)
        self.assertEqual(len(self.db._offline_access_buffer), 0)

        # Verificar que el registro ahora reside en la base de datos
        recientes = self.db.get_recent_accesos(limit=10)
        encontrado = any(r.matricula == "TEST_OFFLINE_01" for r in recientes)
        self.assertTrue(encontrado)


if __name__ == "__main__":
    unittest.main()
