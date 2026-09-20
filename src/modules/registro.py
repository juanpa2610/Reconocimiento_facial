"""
Módulo A: Registro Biométrico "Biometría Primero" con Malla Facial en Vivo (MediaPipe).

FLUJO OPERATIVO OPTIMIZADO:
1. "ROSTRO PRIMERO": El alumno se posiciona frente a la cámara antes de escribir nada.
2. Escaneo y Extracción de Embedding 128-D (Dlib / face_recognition) con Malla Facial en Vivo.
3. Validación Biométrica Preventiva Inmediata:
   - Si el rostro YA EXISTE en la base de datos (distancia euclidiana L2 <= 0.55),
     el sistema bloquea el registro e informa de inmediato los datos del alumno existente.
     EL GUARDIA NO PIERDE TIEMPO ESCRIBIENDO DATOS.
   - Si el rostro NO EXISTE (es nuevo), se solicitan los datos: Matrícula, Nombre y Carrera.
4. Validación de Matrícula (Nivel Datos): Verifica que la matrícula ingresada no esté duplicada.
5. Almacenamiento Vectorial Exclusivo: Solo se guarda el buffer binario (1024 bytes) en la BD.
   LA IMAGEN SE DESTRUYE DE LA MEMORIA RAM INMEDIATAMENTE (Cumplimiento LFPDPPP).
"""

import cv2
import numpy as np
import time
import gc
from typing import Optional, Tuple

import config
from src.db.database import Database
from src.db.models import Estudiante
from src.biometrics.encoder import FaceEncoder
from src.biometrics.matcher import FaceMatcher
from src.utils.visualizer import Visualizer

try:
    import mediapipe as mp
    if hasattr(mp, "solutions"):
        mp_face_mesh = mp.solutions.face_mesh
        MEDIAPIPE_AVAILABLE = True
    else:
        MEDIAPIPE_AVAILABLE = False
except Exception:
    MEDIAPIPE_AVAILABLE = False
import face_recognition


def verificar_rostro_previo(
    embedding: np.ndarray,
    db: Optional[Database] = None,
    threshold: float = config.FACE_DISTANCE_THRESHOLD
) -> Tuple[bool, Optional[Estudiante], float]:
    """
    Función modular para verificar si un rostro ya está registrado en la base de datos.
    Retorna (ya_registrado: bool, estudiante_encontrado: Optional[Estudiante], distancia: float).
    """
    if db is None:
        db = Database()
        db.init_db()

    matcher = FaceMatcher(threshold=threshold)
    alumnos_registrados = db.get_all_active_estudiantes()
    match_result = matcher.match(embedding, alumnos_registrados)

    if match_result.reconocido and match_result.estudiante:
        return True, match_result.estudiante, match_result.distancia
    return False, None, match_result.distancia


def registrar_estudiante_en_vivo(
    video_source=config.VIDEO_SOURCE,
    db: Optional[Database] = None
) -> bool:
    """
    Asistente interactivo de consola con filosofía "Biometría Primero":
    Enciende la cámara primero -> Escanea el rostro -> Si ya existe bloquea -> Si es nuevo pide datos.
    """
    if db is None:
        db = Database()
        db.init_db()

    print("\n" + "=" * 70)
    print("      MÓDULO DE REGISTRO BIOMÉTRICO (FLUJO: BIOMETRÍA PRIMERO)         ")
    print("    [Paso 1: Identificar Rostro  ->  Paso 2: Capturar Datos si es Nuevo] ")
    print("=" * 70)

    encoder = FaceEncoder(model=config.DETECTION_MODEL)
    matcher = FaceMatcher(threshold=config.FACE_DISTANCE_THRESHOLD)

    print(f"\n[*] Conectando con la cámara ({video_source}) ...")
    cap = cv2.VideoCapture(video_source)

    if not cap.isOpened():
        print(f"[-] Error: No se pudo abrir la cámara en '{video_source}'.")
        return False

    window_name = "Registro Biometrico (Biometria Primero) - Taller de Investigacion II"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    captured_vector = None
    alerta_biometrica = None
    rostro_ya_existente = False
    estudiante_coincidente = None

    print("[+] Cámara iniciada correctamente.")
    print("[*] PASO 1: Pida al alumno que se coloque frente a la cámara.")
    print("    - Cuando la malla facial o recuadro esté VERDE, presione [ESPACIO] para escanear.")
    print("    - Para salir presione [Q].\n")

    face_mesh = None
    if MEDIAPIPE_AVAILABLE and config.ENABLE_FACE_MESH:
        face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("[-] Error al leer de la cámara.")
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            mesh_detected = False
            face_landmarks = None

            if face_mesh:
                mesh_results = face_mesh.process(rgb_frame)
                if mesh_results.multi_face_landmarks:
                    mesh_detected = True
                    face_landmarks = mesh_results.multi_face_landmarks[0]
                    Visualizer.draw_face_mesh(frame, face_landmarks)
            else:
                landmarks_list = face_recognition.face_landmarks(rgb_frame)
                if len(landmarks_list) == 1:
                    mesh_detected = True
                    Visualizer.draw_facial_landmarks(frame, landmarks_list[0])
                else:
                    mesh_detected = False

            if alerta_biometrica:
                status_msg = "ALERTA: ESTE ROSTRO YA ESTA REGISTRADO"
            elif mesh_detected:
                status_msg = "Rostro Enfocado - Presione [ESPACIO] para verificar"
            else:
                status_msg = "Buscando rostro... Enfoquese al centro"

            Visualizer.draw_registration_hud(
                frame=frame,
                mesh_detected=mesh_detected,
                status_msg=status_msg,
                alerta_duplicado=alerta_biometrica
            )

            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == 27:
                print("[*] Operación cancelada por el usuario.")
                break

            if (key == 32 or key == 13) and mesh_detected:
                print("\n[*] Extrayendo vector biométrico del rostro...")
                boxes = encoder.detect_face_locations(rgb_frame)

                if len(boxes) != 1:
                    print("[-] Error: Debe haber exactamente un solo rostro en el encuadre.")
                    continue

                encodings = encoder.extract_encodings(rgb_frame, boxes)
                if not encodings or len(encodings) == 0:
                    print("[-] Error al generar vector biométrico.")
                    continue

                candidato_vector = encodings[0]

                # VALIDACIÓN BIOMÉTRICA INMEDIATA EN LA BASE DE DATOS
                print("[*] Comprobando en base de datos si este rostro ya fue registrado...")
                ya_registrado, est_existente, dist = verificar_rostro_previo(candidato_vector, db)

                if ya_registrado and est_existente:
                    rostro_ya_existente = True
                    estudiante_coincidente = est_existente
                    alerta_biometrica = f"Ya pertenece a: {est_existente.nombre} (Matr: {est_existente.matricula})"

                    print(f"\n{'!' * 70}")
                    print("[-] ATENCIÓN: ESTE ROSTRO YA ESTÁ REGISTRADO EN EL SISTEMA")
                    print(f"    - Alumno:          {est_existente.nombre}")
                    print(f"    - Matrícula:       {est_existente.matricula}")
                    print(f"    - Carrera:          {est_existente.carrera or 'N/A'}")
                    print(f"    - Distancia L2:    {dist:.4f} <= {matcher.threshold:.2f}")
                    print("    NO ES NECESARIO INGRESAR INFORMACIÓN. REGISTRO BLOQUEADO.")
                    print(f"{'!' * 70}\n")

                    Visualizer.draw_registration_hud(
                        frame=frame,
                        mesh_detected=True,
                        status_msg="ROSTRO YA REGISTRADO",
                        alerta_duplicado=alerta_biometrica
                    )
                    cv2.imshow(window_name, frame)
                    cv2.waitKey(3000)
                    break

                # Rostro NUEVO y legítimo
                captured_vector = candidato_vector
                print("\n[✓] VERIFICACIÓN BIOMÉTRICA SUPERADA: Rostro NUEVO (No registrado previamente).")
                break

    finally:
        if face_mesh:
            face_mesh.close()
        cap.release()
        cv2.destroyAllWindows()
        del frame
        del rgb_frame
        gc.collect()

    if rostro_ya_existente:
        print(f"[*] El estudiante ya cuenta con acceso bajo la matrícula {estudiante_coincidente.matricula}.")
        return False

    if captured_vector is None:
        return False

    # -------------------------------------------------------------------------
    # PASO 2: SOLICITAR DATOS ÚNICAMENTE DESPUÉS DE VALIDAR QUE ES NUEVO
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("PASO 2: INGRESO DE DATOS DEL ALUMNO")
    print("El rostro ya fue validado y digitalizado en memoria. Ingrese los datos:")
    print("-" * 70)

    while True:
        matricula = input("Matrícula del estudiante: ").strip()
        if not matricula:
            print("[-] La matrícula no puede estar vacía.")
            continue
        # Comprobar que la matrícula no choque con otro alumno
        alumno_mat = db.get_estudiante_by_matricula(matricula)
        if alumno_mat:
            print(f"[-] ERROR: La matrícula '{matricula}' ya está asignada a '{alumno_mat.nombre}'. Ingrese una matrícula distinta.")
            continue
        break

    while True:
        nombre = input("Nombre completo del estudiante: ").strip()
        if nombre:
            break
        print("[-] El nombre no puede estar vacío.")

    carrera = input("Carrera / Programa académico: ").strip()

    # Guardar en Base de Datos (solo el vector binario de 1024 bytes)
    print("\n[*] Guardando template biométrico en base de datos...")
    estudiante = db.save_estudiante(
        matricula=matricula,
        nombre=nombre,
        carrera=carrera,
        embedding=captured_vector
    )

    vector_bytes = Database.serialize_vector(captured_vector)

    print("-" * 70)
    print(f"[✓] REGISTRO BIOMÉTRICO EXITOSO:")
    print(f"    - Matrícula:        {estudiante.matricula}")
    print(f"    - Nombre:           {estudiante.nombre}")
    print(f"    - Carrera:          {estudiante.carrera}")
    print(f"    - Vector 128-D:     {len(vector_bytes)} bytes guardados en la BD.")
    print(f"    - Privacidad:       FOTOGRAMA DESTRUIDO DE RAM. CERO IMÁGENES GUARDADAS.")
    print("-" * 70)

    return True


def registrar_desde_imagen(
    ruta_imagen: str,
    matricula: str,
    nombre: str,
    carrera: str
) -> bool:
    """Enrolamiento desde imagen para pruebas o migraciones."""
    db = Database()
    db.init_db()

    encoder = FaceEncoder(model=config.DETECTION_MODEL)
    img = cv2.imread(ruta_imagen)
    if img is None:
        print(f"[-] No se pudo cargar la imagen: {ruta_imagen}")
        return False

    vector, box, msg = encoder.extract_single_face_encoding(img)
    del img
    gc.collect()

    if vector is None:
        print(f"[-] Fallo en extracción: {msg}")
        return False

    # 1. Verificar rostro previo
    ya_reg, est_dup, dist = verificar_rostro_previo(vector, db)
    if ya_reg and est_dup:
        print(f"[-] ERROR BIOMÉTRICO: Rostro ya pertenece al alumno '{est_dup.nombre}' ({est_dup.matricula}).")
        return False

    # 2. Verificar matrícula
    existente = db.get_estudiante_by_matricula(matricula)
    if existente:
        print(f"[-] Error: Matrícula '{matricula}' ya registrada a nombre de '{existente.nombre}'.")
        return False

    db.save_estudiante(matricula=matricula, nombre=nombre, carrera=carrera, embedding=vector)
    print(f"[✓] Estudiante {nombre} ({matricula}) registrado con éxito vía template.")
    return True
