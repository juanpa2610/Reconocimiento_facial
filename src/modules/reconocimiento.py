"""
Módulo B: Reconocimiento Facial en Tiempo Real para Control de Acceso.

MEJORAS INCORPORADAS:
1. Indicadores de Coincidencia Estables (HUD Visual sin parpadeo):
   - Tarjeta central informativa persistente (Verde: AUTORIZADO, Rojo: DESCONOCIDO/DENEGADO).
   - Temporizador de persistencia visual (Visual Cooldown de 3.0s) para garantizar que el mensaje
     se mantenga legible mientras el alumno está frente a la cámara.
2. Auditoría Inteligente: Cooldown de inserción en BD para evitar saturación de bitácora.
3. Descarte de Fotogramas: Cero almacenamiento de imágenes en disco ni BD (LFPDPPP).
"""

import cv2
import time
import numpy as np
from typing import Dict, Optional, Tuple
import gc

import config
from src.db.database import Database
from src.biometrics.encoder import FaceEncoder
from src.biometrics.matcher import FaceMatcher, MatchResult
from src.utils.visualizer import Visualizer


class AccessVisualState:
    """Maneja el estado visual persistente en pantalla para evitar parpadeos (Flicker Prevention)."""
    def __init__(self, persistence_seconds: float = config.VISUAL_STATUS_PERSISTENCE_SECONDS):
        self.persistence_seconds = persistence_seconds
        self.estado: Optional[str] = None  # 'PERMITIDO', 'DENEGADO'
        self.nombre: str = ""
        self.matricula: Optional[str] = None
        self.distancia: float = 0.0
        self.confianza: float = 0.0
        self.ultimo_cambio: float = 0.0

    def actualizar(self, estado: str, nombre: str, matricula: Optional[str], distancia: float, confianza: float):
        ahora = time.time()
        self.estado = estado
        self.nombre = nombre
        self.matricula = matricula
        self.distancia = distancia
        self.confianza = confianza
        self.ultimo_cambio = ahora

    def es_activo(self) -> bool:
        return (self.estado is not None) and (time.time() - self.ultimo_cambio <= self.persistence_seconds)

    def tiempo_restante(self) -> float:
        return max(0.0, self.persistence_seconds - (time.time() - self.ultimo_cambio))


def iniciar_control_acceso(video_source=config.VIDEO_SOURCE):
    """
    Inicia el bucle de reconocimiento facial en tiempo real para control de acceso con HUD persistente.
    """
    db = Database()
    db.init_db()

    encoder = FaceEncoder(model=config.DETECTION_MODEL)
    matcher = FaceMatcher(threshold=config.FACE_DISTANCE_THRESHOLD)

    print("\n" + "=" * 70)
    print("   MÓDULO DE CONTROL DE ACCESO EN TIEMPO REAL (ARQUITECTURA TEMPLATES)  ")
    print("=" * 70)
    print("[*] Cargando plantillas biométricas desde la base de datos...")

    estudiantes = db.get_all_active_estudiantes()
    print(f"[+] Plantillas cargadas en memoria: {len(estudiantes)} estudiante(s) activo(s).")
    print(f"[*] Umbral de decisión euclidiana (L2): <= {matcher.threshold:.2f}")

    if len(estudiantes) == 0:
        print("[!] Advertencia: No hay estudiantes registrados en la base de datos.")
        print("    Cualquier rostro detectado será clasificado como NO REGISTRADO.")
        print("    Registre alumnos usando el Módulo de Registro (Opción 1).")

    print(f"\n[*] Abriendo flujo de video: {video_source} ...")
    cap = cv2.VideoCapture(video_source)

    if not cap.isOpened():
        print(f"[-] Error: No se pudo abrir la fuente de video ({video_source}).")
        return

    # Rastreador de cooldown para la base de datos (evita escribir registros continuos cada 30 ms)
    db_cooldown_tracker: Dict[str, float] = {}

    # Estado visual persistente para la interfaz de pantalla (evita parpadeo)
    visual_state = AccessVisualState(persistence_seconds=config.VISUAL_STATUS_PERSISTENCE_SECONDS)

    window_name = "Control de Acceso Biometrico - Reconocimiento en Vivo"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    frame_count = 0
    process_every_n_frames = 2
    cached_face_locations = []
    cached_match_results = []

    fps_start_time = time.time()
    fps_counter = 0
    current_fps = 0.0

    print("[+] Sistema de control de acceso activo.")
    print("    - [Q / ESC]: Salir")
    print("    - [R]: Recargar base de datos en caliente\n")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("[-] Fin o interrupción de la transmisión de video.")
                break

            # Medición de FPS
            fps_counter += 1
            if time.time() - fps_start_time >= 1.0:
                current_fps = fps_counter / (time.time() - fps_start_time)
                fps_counter = 0
                fps_start_time = time.time()

            h, w, _ = frame.shape

            # Procesar detección facial cada N cuadros para mantener alta tasa de FPS en CPU
            if frame_count % process_every_n_frames == 0:
                small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                small_locations = encoder.detect_face_locations(rgb_small_frame)
                encodings = encoder.extract_encodings(rgb_small_frame, small_locations)

                cached_face_locations = []
                cached_match_results = []
                ahora = time.time()

                for small_box, encoding in zip(small_locations, encodings):
                    # Reescalar coordenadas a tamaño nativo (x2)
                    top, right, bottom, left = small_box
                    box = (top * 2, right * 2, bottom * 2, left * 2)
                    cached_face_locations.append(box)

                    # Búsqueda vectorial ultrarrápida en memoria RAM
                    match_result = matcher.match(encoding, estudiantes)
                    cached_match_results.append(match_result)

                    if match_result.reconocido and match_result.estudiante:
                        est = match_result.estudiante
                        # Actualizar tarjeta visual persistente (Verde)
                        visual_state.actualizar(
                            estado="PERMITIDO",
                            nombre=est.nombre,
                            matricula=est.matricula,
                            distancia=match_result.distancia,
                            confianza=match_result.confianza_pct
                        )

                        # Auditoría en BD con cooldown
                        last_logged = db_cooldown_tracker.get(est.matricula, 0.0)
                        if ahora - last_logged >= config.ACCESS_LOG_COOLDOWN_SECONDS:
                            db_cooldown_tracker[est.matricula] = ahora
                            db.log_acceso(
                                estudiante_id=est.id,
                                matricula=est.matricula,
                                nombre=est.nombre,
                                distancia=match_result.distancia,
                                estado="PERMITIDO"
                            )
                            print(f"[✓ AUTORIZADO] {est.nombre} (Matr: {est.matricula}) | d={match_result.distancia:.3f} | {match_result.confianza_pct}%")

                    else:
                        # Actualizar tarjeta visual persistente si no había un autorizado reciente
                        if not (visual_state.es_activo() and visual_state.estado == "PERMITIDO"):
                            visual_state.actualizar(
                                estado="DENEGADO",
                                nombre="Desconocido",
                                matricula=None,
                                distancia=match_result.distancia,
                                confianza=match_result.confianza_pct
                            )

                        # Auditoría en BD de sujetos desconocidos
                        last_logged = db_cooldown_tracker.get("UNKNOWN", 0.0)
                        if ahora - last_logged >= config.ACCESS_LOG_COOLDOWN_SECONDS:
                            db_cooldown_tracker["UNKNOWN"] = ahora
                            db.log_acceso(
                                estudiante_id=None,
                                matricula=None,
                                nombre="Desconocido",
                                distancia=match_result.distancia,
                                estado="DENEGADO"
                            )
                            print(f"[✗ DENEGADO] Sujeto no identificado | Distancia mínima: {match_result.distancia:.3f} > {matcher.threshold}")

            frame_count += 1

            # Renderizar cajas sobre los rostros presentes
            for box, match_result in zip(cached_face_locations, cached_match_results):
                es_autorizado = (match_result.reconocido and match_result.estudiante is not None)
                nombre_display = match_result.estudiante.nombre if es_autorizado else "No Registrado"
                mat_display = match_result.estudiante.matricula if es_autorizado else None

                Visualizer.draw_recognition_box(
                    frame=frame,
                    box=box,
                    nombre=nombre_display,
                    matricula=mat_display,
                    distancia=match_result.distancia,
                    confianza=match_result.confianza_pct,
                    es_autorizado=es_autorizado
                )

            # Renderizar tarjeta informativa persistente (con cooldown visual para evitar parpadeo)
            if visual_state.es_activo():
                Visualizer.draw_access_feedback_card(
                    frame=frame,
                    estado=visual_state.estado or "DENEGADO",
                    nombre=visual_state.nombre,
                    matricula=visual_state.matricula,
                    distancia=visual_state.distancia,
                    confianza=visual_state.confianza,
                    tiempo_restante=visual_state.tiempo_restante()
                )

            # Barra de estado superior con métricas
            header_text = f"CONTROL DE ACCESO | Templates: {len(estudiantes)} | Umbral L2: {matcher.threshold:.2f} | FPS: {current_fps:.1f}"
            Visualizer.draw_banner(frame, header_text, color=Visualizer.COLOR_INFO, position="top")

            # Barra inferior
            footer_text = "[Q / ESC]: Salir  |  [R]: Recargar Alumnos de BD"
            Visualizer.draw_banner(frame, footer_text, position="bottom")

            cv2.imshow(window_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
            elif key == ord('r') or key == ord('R'):
                print("\n[*] Recargando plantillas desde la base de datos...")
                estudiantes = db.get_all_active_estudiantes()
                print(f"[+] Plantillas actualizadas: {len(estudiantes)} estudiante(s) activo(s).\n")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        gc.collect()
        print("\n[*] Módulo de control de acceso finalizado.")
