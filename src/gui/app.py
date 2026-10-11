"""
Interfaz Gráfica de Usuario (GUI) Institucional para el ITSX.
Instituto Tecnológico Superior de Xalapa - Taller de Investigación II.

DISEÑO EJECUTIVO Y PROFESIONAL:
1. Logotipo oficial del ITSX integrado en alta resolución.
2. Identidad institucional con paleta de colores corporativa (Azul pizarra, Oro ITSX, Esmeralda y Rubí).
3. Reloj digital en vivo con fecha institucional.
4. Módulo de Vigilancia en Tiempo Real con tarjeta de decisión gigante para guardias.
5. Flujo de Enrolamiento "Biometría Primero" (escanea y valida duplicados antes de solicitar datos).
6. Combobox pre-cargado con la oferta académica oficial de ingenierías del ITSX.
7. Bitácora institucional con filtros por estado y exportación directa a formato CSV/Excel.
8. Cumplimiento con la LFPDPPP: Cero imágenes en disco, almacenamiento exclusivo de 1024 bytes.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import cv2
from PIL import Image, ImageTk
import numpy as np
import time
from datetime import datetime
import os
import gc
from typing import Optional, Dict, List, Tuple

import config
from src.db.database import Database
from src.db.models import Estudiante, Usuario, CamaraConfig, RegistroAuditoria
from src.biometrics.encoder import FaceEncoder
from src.biometrics.matcher import FaceMatcher, MatchResult
from src.modules.registro import verificar_rostro_previo
from src.utils.visualizer import Visualizer
from src.utils.video_stream import ThreadedCamera
from src.utils.security import mask_camera_secret, build_rtsp_url, build_safe_display_url
from src.utils.camera_tester import test_camera_connection_async
from src.gui.dialogs import (
    LoginDialog,
    ConfirmAdminDialog,
    EditEstudianteDialog,
    CrearUsuarioDialog
)

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

# Catálogo de carreras oficiales del Instituto Tecnológico Superior de Xalapa (ITSX)
CARRERAS_ITSX = [
    "Ingeniería en Sistemas Computacionales",
    "Ingeniería Industrial",
    "Ingeniería Mecatrónica",
    "Ingeniería Electrónica",
    "Ingeniería en Gestión Empresarial",
    "Ingeniería Bioquímica",
    "Ingeniería Civil",
    "Ingeniería Electromecánica",
    "Licenciatura en Gastronomía",
    "Posgrado / Maestría",
    "Personal Docente / Administrativo"
]


class GuardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ITSX - Sistema Biométrico de Control de Acceso Institucional")
        self.root.geometry("1260x820")
        self.root.minsize(1050, 720)

        # Paleta Institucional ITSX / Executive Dark Theme
        self.COLOR_BG = "#0B1120"          # Azul marino muy oscuro / Midnight
        self.COLOR_PANEL = "#151F32"       # Slate navy institucional
        self.COLOR_CARD = "#1E293B"        # Card background (Slate 800)
        self.COLOR_CARD_BORDER = "#334155" # Borde sutil (Slate 700)
        self.COLOR_TEXT = "#F8FAFC"        # Texto blanco puro
        self.COLOR_TEXT_MUTED = "#94A3B8"  # Texto secundario (Slate 400)
        self.COLOR_GOLD_ITSX = "#E5A823"   # Oro institucional ITSX
        self.COLOR_GREEN = "#10B981"       # Verde esmeralda vivo
        self.COLOR_RED = "#EF4444"         # Rojo rubí
        self.COLOR_ACCENT = "#38BDF8"      # Cyan tecnológico

        self.root.configure(bg=self.COLOR_BG)

        # Base de datos y autenticación
        self.db = Database()
        self.db.init_db()
        self.current_user: Optional[Usuario] = None

        # Motor biométrico
        self.encoder = FaceEncoder(model=config.DETECTION_MODEL)
        self.matcher = FaceMatcher(threshold=config.FACE_DISTANCE_THRESHOLD)
        self.estudiantes: List[Estudiante] = self.db.get_all_active_estudiantes()
        self.matcher.set_known_students(self.estudiantes)

        # Dispositivo / Flujo de video inicial (resuelto dinámicamente desde la BD)
        cam_activa = self.db.obtener_camara_activa()
        if cam_activa:
            if cam_activa.ip in ("0", "", "localhost_cam"):
                try:
                    self.video_source = int(cam_activa.ip)
                except ValueError:
                    self.video_source = 0
            else:
                self.video_source = cam_activa.get_rtsp_url()
            self.nombre_camara_activa = cam_activa.nombre
        else:
            self.video_source = config.VIDEO_SOURCE
            self.nombre_camara_activa = "Cámara Predeterminada"

        self.cap: Optional[ThreadedCamera] = None
        self.is_camera_running = False
        self._camera_started = False

        # Caché de resultados para procesar solo 1 de cada N cuadros (baja latencia)
        self._frame_counter = 0
        self._cache_acceso = []          # lista de dicts con caja + datos de coincidencia
        self._cache_landmarks = []       # landmarks del rostro en la pestaña de registro
        self._cache_n_rostros_reg = 0

        # Auditoría y contadores del día
        self.db_cooldown: Dict[str, float] = {}
        self.conteo_autorizados = 0
        self.conteo_denegados = 0

        # Estado visual persistente de la tarjeta de guardia
        self.access_card_state = {
            "status": "STANDBY",
            "name": "",
            "matricula": "",
            "carrera": "",
            "distancia": 0.0,
            "confianza": 0.0,
            "timer": 0.0
        }

        # Estado del flujo "Biometría Primero"
        self.nuevo_vector_candidato: Optional[np.ndarray] = None

        # Cargar recursos gráficos (Logo ITSX)
        self._cargar_recursos()

        # Construir Interfaz de Usuario
        self._setup_styles()
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        # Iniciar reloj institucional
        self._actualizar_reloj()

        # Programar pantalla de Login obligatoria al iniciar
        self.root.after(100, self._mostrar_login)

        # Evento de cierre
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _cargar_recursos(self):
        """Carga y procesa el logo oficial del ITSX."""
        self.logo_header_img = None
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        ruta_logo = os.path.join(base_dir, "assets", "itsx_logo_header.png")
        if not os.path.exists(ruta_logo):
            ruta_logo = os.path.join(base_dir, "assets", "itsx_logo_cropped.png")

        if os.path.exists(ruta_logo):
            try:
                pil_img = Image.open(ruta_logo)
                # Escalar con alta calidad (LANCZOS)
                h_target = 54
                w_target = int(pil_img.width * (h_target / pil_img.height))
                pil_resized = pil_img.resize((w_target, h_target), Image.Resampling.LANCZOS)
                self.logo_header_img = ImageTk.PhotoImage(pil_resized)
            except Exception as e:
                print(f"[-] Aviso: No se pudo cargar el logo: {e}")

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Pestañas principales con acento Oro ITSX
        style.configure("TNotebook", background=self.COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT_MUTED,
                        padding=[22, 10],
                        font=("Helvetica", 11, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", self.COLOR_CARD)],
                  foreground=[("selected", self.COLOR_GOLD_ITSX)])

        # Tablas modernas
        style.configure("Treeview",
                        background=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT,
                        fieldbackground=self.COLOR_PANEL,
                        rowheight=30,
                        font=("Helvetica", 10))
        style.configure("Treeview.Heading",
                        background=self.COLOR_CARD,
                        foreground="#ffffff",
                        padding=[10, 6],
                        font=("Helvetica", 10, "bold"))
        style.map("Treeview", background=[("selected", "#0284C7")])

        # Combobox
        style.configure("TCombobox", fieldbackground=self.COLOR_CARD, background=self.COLOR_CARD, foreground="#000000")

    def _build_header(self):
        header = tk.Frame(self.root, bg=self.COLOR_PANEL, height=80, padx=20, pady=10)
        header.pack(side=tk.TOP, fill=tk.X)

        # Lado izquierdo: Contenedor con Logo ITSX y Títulos Oficiales
        left_box = tk.Frame(header, bg=self.COLOR_PANEL)
        left_box.pack(side=tk.LEFT, fill=tk.Y)

        # Tarjeta blanca para renderizar el logo institucional con máximo contraste
        if self.logo_header_img:
            logo_frame = tk.Frame(left_box, bg="#ffffff", padx=8, pady=4, bd=1, relief=tk.SOLID)
            logo_frame.pack(side=tk.LEFT, padx=(0, 16))
            lbl_logo = tk.Label(logo_frame, image=self.logo_header_img, bg="#ffffff")
            lbl_logo.pack()

        # Textos Institucionales
        text_frame = tk.Frame(left_box, bg=self.COLOR_PANEL)
        text_frame.pack(side=tk.LEFT, fill=tk.Y)

        lbl_inst = tk.Label(
            text_frame,
            text="INSTITUTO TECNOLÓGICO SUPERIOR DE XALAPA",
            font=("Helvetica", 13, "bold"),
            fg=self.COLOR_GOLD_ITSX,
            bg=self.COLOR_PANEL
        )
        lbl_inst.pack(anchor=tk.W)

        lbl_sys = tk.Label(
            text_frame,
            text="SISTEMA BIOMÉTRICO INSTITUCIONAL | CONTROL DE ACCESO",
            font=("Helvetica", 12, "bold"),
            fg="#FFFFFF",
            bg=self.COLOR_PANEL
        )
        lbl_sys.pack(anchor=tk.W)

        lbl_sub = tk.Label(
            text_frame,
            text="Taller de Investigación II • Privacidad por Diseño (LFPDPPP) • Red ResNet-34",
            font=("Helvetica", 9),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_PANEL
        )
        lbl_sub.pack(anchor=tk.W)

        # Lado derecho: Sesión de usuario, Reloj en vivo y Status Badge
        right_box = tk.Frame(header, bg=self.COLOR_PANEL)
        right_box.pack(side=tk.RIGHT, fill=tk.Y)

        top_right_row = tk.Frame(right_box, bg=self.COLOR_PANEL)
        top_right_row.pack(anchor=tk.E, pady=(0, 4))

        self.lbl_clock = tk.Label(
            top_right_row,
            text="--:--:--  |  --/--/----",
            font=("Helvetica", 11, "bold"),
            fg=self.COLOR_ACCENT,
            bg=self.COLOR_PANEL
        )
        self.lbl_clock.pack(side=tk.LEFT, padx=(0, 12))

        self.btn_logout = tk.Button(
            top_right_row,
            text="🚪 Cerrar Sesión",
            font=("Helvetica", 9, "bold"),
            bg="#334155",
            fg="#ffffff",
            activebackground="#475569",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._cerrar_sesion
        )
        self.btn_logout.pack(side=tk.RIGHT)

        # Badge de usuario y estado de base de datos
        badge = tk.Frame(right_box, bg=self.COLOR_CARD, padx=12, pady=4, bd=1, relief=tk.GROOVE)
        badge.pack(anchor=tk.E)

        self.lbl_user_badge = tk.Label(
            badge,
            text="👤 Sesión: Requerida",
            font=("Helvetica", 9, "bold"),
            fg=self.COLOR_GOLD_ITSX,
            bg=self.COLOR_CARD
        )
        self.lbl_user_badge.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_db_badge = tk.Label(
            badge,
            text=f"🟢 EN LÍNEA | MOTOR: {config.DB_ENGINE.upper()} | PADRÓN: {len(self.estudiantes)} ALUMNOS",
            font=("Helvetica", 9, "bold"),
            fg=self.COLOR_GREEN,
            bg=self.COLOR_CARD
        )
        self.lbl_db_badge.pack(side=tk.RIGHT)

    def _actualizar_reloj(self):
        """Actualiza el reloj institucional cada segundo."""
        ahora = datetime.now().strftime("%H:%M:%S  |  %d/%m/%Y")
        self.lbl_clock.config(text=ahora)
        self.root.after(1000, self._actualizar_reloj)

    def _mostrar_login(self):
        """Despliega la pantalla modal de inicio de sesión."""
        LoginDialog(
            parent=self.root,
            db=self.db,
            on_success=self._on_login_exitoso,
            on_cancel=self._on_login_cancelado
        )

    def _on_login_exitoso(self, usuario: Usuario):
        """Callback invocado cuando el usuario se autentica correctamente."""
        self.current_user = usuario
        self._aplicar_permisos_usuario()

        # Iniciar cámara solo una vez después del login
        if not self._camera_started:
            self._iniciar_camara()
            self._camera_started = True

    def _on_login_cancelado(self):
        """Si el usuario cancela o cierra la ventana de login sin autenticarse, salir."""
        if not self.current_user:
            self._on_close()

    def _cerrar_sesion(self):
        """Cierra la sesión actual y solicita re-autenticación."""
        if messagebox.askyesno("Cerrar Sesión", "¿Está seguro de que desea cerrar la sesión actual?"):
            if self.current_user:
                self.db.log_auditoria(
                    self.current_user.username,
                    "CIERRE_SESION",
                    "SISTEMA",
                    f"Sesión cerrada por el usuario '{self.current_user.username}'",
                    "EXITO"
                )
            self.current_user = None
            self.lbl_user_badge.config(text="👤 Sesión: Requerida", fg=self.COLOR_RED)
            try:
                self.notebook.select(self.tab_acceso)
            except Exception:
                pass
            self._mostrar_login()

    def _aplicar_permisos_usuario(self):
        """Aplica el Control de Acceso Basado en Roles (RBAC) en la interfaz gráfica."""
        if not self.current_user:
            return

        tabs_existentes = [self.notebook.tab(i, "text").strip() for i in range(self.notebook.index("end"))]

        if self.current_user.es_admin():
            self.lbl_user_badge.config(
                text=f"👑 Administrador: {self.current_user.username}",
                fg=self.COLOR_GOLD_ITSX
            )
            # Asegurar pestañas de administrador
            if not any("Configuración" in t for t in tabs_existentes):
                self.notebook.add(self.tab_configuracion, text="   ⚙️  Configuración   ")
            if not any("Seguridad" in t for t in tabs_existentes):
                self.notebook.add(self.tab_seguridad, text="   🔒  Seguridad y Auditoría   ")
        else:
            self.lbl_user_badge.config(
                text=f"👤 Operador: {self.current_user.username}",
                fg=self.COLOR_ACCENT
            )
            # Ocultar pestañas restringidas para el operador
            try:
                self.notebook.forget(self.tab_configuracion)
            except Exception:
                pass
            try:
                self.notebook.forget(self.tab_seguridad)
            except Exception:
                pass

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # Pestaña 1: Control de Acceso para Guardias
        self.tab_acceso = tk.Frame(self.notebook, bg=self.COLOR_BG)
        self.notebook.add(self.tab_acceso, text="   🛡️  Control de Acceso (En Vivo)   ")
        self._build_tab_acceso()

        # Pestaña 2: Registro Guiado (Biometría Primero)
        self.tab_registro = tk.Frame(self.notebook, bg=self.COLOR_BG)
        self.notebook.add(self.tab_registro, text="   👤  Registro de Estudiante (Biometría Primero)   ")
        self._build_tab_registro()

        # Pestaña 3: Bitácora y Padrón Institucional
        self.tab_bitacora = tk.Frame(self.notebook, bg=self.COLOR_BG)
        self.notebook.add(self.tab_bitacora, text="   📋  Bitácora y Padrón ITSX   ")
        self._build_tab_bitacora()

        # Pestaña 4: Configuración de Cámaras (Administración)
        self.tab_configuracion = tk.Frame(self.notebook, bg=self.COLOR_BG)
        self.notebook.add(self.tab_configuracion, text="   ⚙️  Configuración   ")
        self._build_tab_configuracion()

        # Pestaña 5: Seguridad y Auditoría (Admin)
        self.tab_seguridad = tk.Frame(self.notebook, bg=self.COLOR_BG)
        self.notebook.add(self.tab_seguridad, text="   🔒  Seguridad y Auditoría   ")
        self._build_tab_seguridad()

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # -------------------------------------------------------------------------
    # PESTAÑA 1: CONTROL DE ACCESO EN VIVO (VIGILANCIA)
    # -------------------------------------------------------------------------
    def _build_tab_acceso(self):
        main_box = tk.Frame(self.tab_acceso, bg=self.COLOR_BG)
        main_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Panel izquierdo: Feed de Video
        video_box = tk.Frame(main_box, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID)
        video_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        v_head = tk.Frame(video_box, bg=self.COLOR_CARD, padx=14, pady=9)
        v_head.pack(fill=tk.X)
        tk.Label(v_head, text="📹 CÁMARA DEL PUNTO DE ACCESO (SENSOR BIOMÉTRICO)",
                 font=("Helvetica", 11, "bold"), fg="#ffffff", bg=self.COLOR_CARD).pack(side=tk.LEFT)

        self.lbl_gate_name = tk.Label(v_head, text="CASETA 1 - ACCESO PRINCIPAL ITSX",
                                      font=("Helvetica", 9, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_CARD)
        self.lbl_gate_name.pack(side=tk.RIGHT)

        self.video_label_acceso = tk.Label(video_box, bg="#050811")
        self.video_label_acceso.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Panel derecho: Tarjeta de Acceso y KPIs para el Guardia
        right_panel = tk.Frame(main_box, bg=self.COLOR_BG, width=420)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(12, 0))
        right_panel.pack_propagate(False)

        # Tarjeta Gigante de Verificación
        self.card_frame = tk.Frame(
            right_panel, bg=self.COLOR_CARD, bd=2, relief=tk.GROOVE, padx=18, pady=22
        )
        self.card_frame.pack(fill=tk.X, pady=(0, 15))

        self.lbl_card_icon = tk.Label(
            self.card_frame, text="🛡️", font=("Helvetica", 42), bg=self.COLOR_CARD, fg=self.COLOR_ACCENT
        )
        self.lbl_card_icon.pack(pady=(0, 4))

        self.lbl_card_title = tk.Label(
            self.card_frame, text="ESPERANDO SUJETO",
            font=("Helvetica", 17, "bold"), fg=self.COLOR_TEXT, bg=self.COLOR_CARD
        )
        self.lbl_card_title.pack()

        self.lbl_card_subtitle = tk.Label(
            self.card_frame, text="Aproxime el rostro hacia el sensor biométrico",
            font=("Helvetica", 10), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD
        )
        self.lbl_card_subtitle.pack(pady=(0, 10))

        sep = tk.Frame(self.card_frame, bg=self.COLOR_CARD_BORDER, height=2)
        sep.pack(fill=tk.X, pady=10)

        # Rejilla de información del alumno
        info_grid = tk.Frame(self.card_frame, bg=self.COLOR_CARD)
        info_grid.pack(fill=tk.X)

        self.lbl_card_name = tk.Label(
            info_grid, text="Alumno: ---", font=("Helvetica", 13, "bold"),
            fg="#ffffff", bg=self.COLOR_CARD, anchor=tk.W
        )
        self.lbl_card_name.pack(fill=tk.X, pady=3)

        self.lbl_card_mat = tk.Label(
            info_grid, text="Matrícula: ---", font=("Helvetica", 12),
            fg="#ffffff", bg=self.COLOR_CARD, anchor=tk.W
        )
        self.lbl_card_mat.pack(fill=tk.X, pady=3)

        self.lbl_card_car = tk.Label(
            info_grid, text="Carrera: ---", font=("Helvetica", 11),
            fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD, anchor=tk.W, wraplength=370, justify=tk.LEFT
        )
        self.lbl_card_car.pack(fill=tk.X, pady=3)

        self.lbl_card_metric = tk.Label(
            info_grid, text="Distancia L2: ---", font=("Helvetica", 10, "bold"),
            fg=self.COLOR_ACCENT, bg=self.COLOR_CARD, anchor=tk.W
        )
        self.lbl_card_metric.pack(fill=tk.X, pady=3)

        # Panel de Contadores / KPIs del Día
        kpi_frame = tk.Frame(right_panel, bg=self.COLOR_PANEL, padx=14, pady=14, bd=1, relief=tk.SOLID)
        kpi_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(kpi_frame, text="REGISTRO DE FLUJO DE ACCESO (HOY)",
                 font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 10))

        kpi_cols = tk.Frame(kpi_frame, bg=self.COLOR_PANEL)
        kpi_cols.pack(fill=tk.X)

        # Caja Autorizados
        b_auth = tk.Frame(kpi_cols, bg="#064E3B", padx=12, pady=10, bd=1, relief=tk.GROOVE)
        b_auth.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        tk.Label(b_auth, text="AUTORIZADOS", font=("Helvetica", 9, "bold"), fg=self.COLOR_GREEN, bg="#064E3B").pack()
        self.lbl_count_auth = tk.Label(b_auth, text="0", font=("Helvetica", 22, "bold"), fg="#ffffff", bg="#064E3B")
        self.lbl_count_auth.pack()

        # Caja Denegados
        b_den = tk.Frame(kpi_cols, bg="#4C1D24", padx=12, pady=10, bd=1, relief=tk.GROOVE)
        b_den.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        tk.Label(b_den, text="DENEGADOS", font=("Helvetica", 9, "bold"), fg=self.COLOR_RED, bg="#4C1D24").pack()
        self.lbl_count_den = tk.Label(b_den, text="0", font=("Helvetica", 22, "bold"), fg="#ffffff", bg="#4C1D24")
        self.lbl_count_den.pack()

        # Botones de Acción de Guardia
        btn_reload = tk.Button(
            right_panel, text="🔄  Sincronizar Base de Datos", font=("Helvetica", 11, "bold"),
            bg=self.COLOR_CARD, fg="#ffffff", activebackground="#334155", activeforeground="#ffffff",
            relief=tk.FLAT, pady=9, cursor="hand2", command=self._recargar_alumnos
        )
        btn_reload.pack(fill=tk.X, pady=(0, 8))

        btn_go_reg = tk.Button(
            right_panel, text="➕  Registrar Nuevo Alumno", font=("Helvetica", 11, "bold"),
            bg=self.COLOR_GOLD_ITSX, fg="#0F172A", activebackground="#D97706", activeforeground="#0F172A",
            relief=tk.FLAT, pady=10, cursor="hand2",
            command=lambda: self.notebook.select(1)
        )
        btn_go_reg.pack(fill=tk.X)

    # -------------------------------------------------------------------------
    # PESTAÑA 2: REGISTRO "BIOMETRÍA PRIMERO" (INSTITUCIONAL)
    # -------------------------------------------------------------------------
    def _build_tab_registro(self):
        main_box = tk.Frame(self.tab_registro, bg=self.COLOR_BG)
        main_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Panel izquierdo: Video para captura
        video_box = tk.Frame(main_box, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID)
        video_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        v_head = tk.Frame(video_box, bg=self.COLOR_CARD, padx=14, pady=9)
        v_head.pack(fill=tk.X)
        tk.Label(v_head, text="📸 ENROLAMIENTO FACIAL (MODO ESPEJO CON MALLA)",
                 font=("Helvetica", 11, "bold"), fg="#ffffff", bg=self.COLOR_CARD).pack(side=tk.LEFT)

        self.video_label_registro = tk.Label(video_box, bg="#050811")
        self.video_label_registro.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Panel derecho: Flujo Guiado en 2 Pasos
        right_panel = tk.Frame(main_box, bg=self.COLOR_PANEL, width=470, padx=22, pady=18)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(12, 0))
        right_panel.pack_propagate(False)

        tk.Label(right_panel, text="ALTA DE ESTUDIANTE EN EL PADRÓN", font=("Helvetica", 14, "bold"),
                 fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 4))

        tk.Label(right_panel, text="Flujo Inteligente: El sistema escanea y valida primero para no duplicar.",
                 font=("Helvetica", 9), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 16))

        # =====================================================================
        # PASO 1: Validación Facial Inmediata
        # =====================================================================
        step1_box = tk.LabelFrame(
            right_panel, text="  PASO 1: Validación Facial Inmediata (Biometría Primero)  ",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_ACCENT, bg=self.COLOR_PANEL, padx=12, pady=12
        )
        step1_box.pack(fill=tk.X, pady=(0, 15))

        self.btn_escanear = tk.Button(
            step1_box, text="📸  1. Escanear Rostro y Verificar en BD",
            font=("Helvetica", 11, "bold"), bg="#0284C7", fg="#ffffff",
            activebackground="#0369A1", activeforeground="#ffffff",
            relief=tk.FLAT, pady=11, cursor="hand2", command=self._accion_escanear_rostro
        )
        self.btn_escanear.pack(fill=tk.X, pady=4)

        # Tarjeta informativa de resultado del escaneo
        self.lbl_scan_result = tk.Label(
            step1_box,
            text="Coloque al estudiante de frente con buena iluminación y presione 'Escanear Rostro'.",
            font=("Helvetica", 9), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL, wraplength=410, justify=tk.LEFT
        )
        self.lbl_scan_result.pack(fill=tk.X, pady=6)

        # =====================================================================
        # PASO 2: Formulario Institucional (Desbloqueado solo si es nuevo)
        # =====================================================================
        self.step2_box = tk.LabelFrame(
            right_panel, text="  PASO 2: Datos Institucionales (Rostro Nuevo)  ",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL, padx=12, pady=12
        )
        self.step2_box.pack(fill=tk.X, pady=(0, 15))

        # Matrícula
        tk.Label(self.step2_box, text="Matrícula Oficial:*", font=("Helvetica", 9, "bold"),
                 fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(2, 2))
        self.ent_matricula = tk.Entry(
            self.step2_box, font=("Helvetica", 11), bg=self.COLOR_CARD,
            fg="#ffffff", insertbackground="#ffffff", state=tk.DISABLED
        )
        self.ent_matricula.pack(fill=tk.X, pady=(0, 8))

        # Nombre Completo
        tk.Label(self.step2_box, text="Nombre Completo:*", font=("Helvetica", 9, "bold"),
                 fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(2, 2))
        self.ent_nombre = tk.Entry(
            self.step2_box, font=("Helvetica", 11), bg=self.COLOR_CARD,
            fg="#ffffff", insertbackground="#ffffff", state=tk.DISABLED
        )
        self.ent_nombre.pack(fill=tk.X, pady=(0, 8))

        # Carrera (Combobox Institucional del ITSX)
        tk.Label(self.step2_box, text="Programa Académico / Carrera:*", font=("Helvetica", 9, "bold"),
                 fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(2, 2))
        self.cmb_carrera = ttk.Combobox(
            self.step2_box, values=CARRERAS_ITSX, font=("Helvetica", 10), state=tk.DISABLED
        )
        self.cmb_carrera.set("Ingeniería en Sistemas Computacionales")
        self.cmb_carrera.pack(fill=tk.X, pady=(0, 14))

        # Botón Guardar
        self.btn_guardar = tk.Button(
            self.step2_box, text="💾  2. Guardar Template Biométrico (1024 bytes)",
            font=("Helvetica", 11, "bold"), bg=self.COLOR_GREEN, fg="#ffffff",
            activebackground="#059669", activeforeground="#ffffff",
            relief=tk.FLAT, pady=11, cursor="hand2", state=tk.DISABLED,
            command=self._accion_guardar_alumno
        )
        self.btn_guardar.pack(fill=tk.X)

    # -------------------------------------------------------------------------
    # PESTAÑA 3: BITÁCORA Y PADRÓN INSTITUCIONAL
    # -------------------------------------------------------------------------
    def _build_tab_bitacora(self):
        main_box = tk.Frame(self.tab_bitacora, bg=self.COLOR_BG, padx=15, pady=15)
        main_box.pack(fill=tk.BOTH, expand=True)

        toolbar = tk.Frame(main_box, bg=self.COLOR_BG)
        toolbar.pack(fill=tk.X, pady=(0, 12))

        tk.Label(toolbar, text="AUDITORÍA DE ACCESOS Y PADRÓN DE ESTUDIANTES",
                 font=("Helvetica", 13, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_BG).pack(side=tk.LEFT)

        btn_export = tk.Button(
            toolbar, text="📥  Exportar Auditoría a CSV", font=("Helvetica", 10, "bold"),
            bg="#0284C7", fg="#ffffff", relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self._exportar_csv
        )
        btn_export.pack(side=tk.RIGHT, padx=5)

        btn_refresh = tk.Button(
            toolbar, text="🔄  Actualizar", font=("Helvetica", 10, "bold"),
            bg=self.COLOR_PANEL, fg="#ffffff", relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self._cargar_tablas_bitacora
        )
        btn_refresh.pack(side=tk.RIGHT, padx=5)

        # Tablas con división horizontal
        paned = tk.PanedWindow(main_box, orient=tk.HORIZONTAL, bg=self.COLOR_BG, sashwidth=5)
        paned.pack(fill=tk.BOTH, expand=True)

        # Tabla de Accesos
        f_left = tk.Frame(paned, bg=self.COLOR_PANEL, padx=12, pady=12)
        paned.add(f_left, minsize=520)

        tk.Label(f_left, text="BITÁCORA EN TIEMPO REAL (ÚLTIMOS 100 REGISTROS)", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_ACCENT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 8))

        cols_acc = ("id", "fecha", "matricula", "nombre", "dist", "estado")
        self.tree_accesos = ttk.Treeview(f_left, columns=cols_acc, show="headings", height=16)
        self.tree_accesos.heading("id", text="ID")
        self.tree_accesos.heading("fecha", text="Fecha / Hora")
        self.tree_accesos.heading("matricula", text="Matrícula")
        self.tree_accesos.heading("nombre", text="Nombre")
        self.tree_accesos.heading("dist", text="Distancia L2")
        self.tree_accesos.heading("estado", text="Estado")

        self.tree_accesos.column("id", width=45, anchor=tk.CENTER)
        self.tree_accesos.column("fecha", width=145)
        self.tree_accesos.column("matricula", width=95, anchor=tk.CENTER)
        self.tree_accesos.column("nombre", width=140)
        self.tree_accesos.column("dist", width=85, anchor=tk.CENTER)
        self.tree_accesos.column("estado", width=100, anchor=tk.CENTER)

        scroll_acc = ttk.Scrollbar(f_left, orient=tk.VERTICAL, command=self.tree_accesos.yview)
        self.tree_accesos.configure(yscroll=scroll_acc.set)
        self.tree_accesos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_acc.pack(side=tk.RIGHT, fill=tk.Y)

        # Tabla de Padrón de Alumnos
        f_right = tk.Frame(paned, bg=self.COLOR_PANEL, padx=12, pady=12)
        paned.add(f_right, minsize=460)

        r_top = tk.Frame(f_right, bg=self.COLOR_PANEL)
        r_top.pack(fill=tk.X, pady=(0, 8))
        tk.Label(r_top, text="PADRÓN BIOMÉTRICO (ALUMNOS ACTIVOS)", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL).pack(side=tk.LEFT)

        btn_del = tk.Button(
            r_top, text="🗑️  Eliminar Alumno", font=("Helvetica", 9, "bold"),
            bg=self.COLOR_RED, fg="#ffffff", relief=tk.FLAT, padx=9, pady=4, cursor="hand2",
            command=self._eliminar_alumno_seleccionado
        )
        btn_del.pack(side=tk.RIGHT)

        btn_edit = tk.Button(
            r_top, text="✏️  Editar Alumno", font=("Helvetica", 9, "bold"),
            bg="#D97706", fg="#ffffff", relief=tk.FLAT, padx=9, pady=4, cursor="hand2",
            command=self._editar_alumno_seleccionado
        )
        btn_edit.pack(side=tk.RIGHT, padx=(0, 6))

        cols_est = ("id", "matricula", "nombre", "carrera", "tam")
        self.tree_estudiantes = ttk.Treeview(f_right, columns=cols_est, show="headings", height=16)
        self.tree_estudiantes.heading("id", text="ID")
        self.tree_estudiantes.heading("matricula", text="Matrícula")
        self.tree_estudiantes.heading("nombre", text="Nombre")
        self.tree_estudiantes.heading("carrera", text="Carrera")
        self.tree_estudiantes.heading("tam", text="Tam. Vector")

        self.tree_estudiantes.column("id", width=40, anchor=tk.CENTER)
        self.tree_estudiantes.column("matricula", width=95, anchor=tk.CENTER)
        self.tree_estudiantes.column("nombre", width=140)
        self.tree_estudiantes.column("carrera", width=130)
        self.tree_estudiantes.column("tam", width=85, anchor=tk.CENTER)

        scroll_est = ttk.Scrollbar(f_right, orient=tk.VERTICAL, command=self.tree_estudiantes.yview)
        self.tree_estudiantes.configure(yscroll=scroll_est.set)
        self.tree_estudiantes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_est.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=self.COLOR_PANEL, height=28, padx=16)
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = tk.Label(
            bar, text="🟢 Sistema Biométrico ITSX Operativo | Red Neuronal ResNet-34 en línea",
            font=("Helvetica", 9), fg=self.COLOR_GREEN, bg=self.COLOR_PANEL
        )
        self.lbl_status.pack(side=tk.LEFT)

        lbl_legal = tk.Label(
            bar, text="Normativa LFPDPPP: CERO imágenes de rostros almacenadas en disco ni BD",
            font=("Helvetica", 9), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL
        )
        lbl_legal.pack(side=tk.RIGHT)

    # -------------------------------------------------------------------------
    # MOTOR DE CÁMARA Y VIDEO
    # -------------------------------------------------------------------------
    def _iniciar_camara(self):
        try:
            # Lector en hilo aparte: siempre entrega el cuadro MÁS RECIENTE (sin delay acumulado)
            self.cap = ThreadedCamera(self.video_source)
            if not self.cap.start():
                self.cap = None
                self.lbl_status.config(
                    text=f"⚠️ No se pudo acceder a la fuente de video '{self.nombre_camara_activa}'.",
                    fg=self.COLOR_GOLD_ITSX
                )
                return
            self.is_camera_running = True
            if hasattr(self, "lbl_gate_name"):
                self.lbl_gate_name.config(text=f"SENSOR: {self.nombre_camara_activa.upper()}")
            self.lbl_status.config(
                text=f"🟢 Transmitiendo en vivo desde: {self.nombre_camara_activa} | ResNet-34 en línea",
                fg=self.COLOR_GREEN
            )
            self._loop_camara()
        except Exception as e:
            self.lbl_status.config(text=f"[-] Error al abrir video: {e}", fg=self.COLOR_RED)

    def _cambiar_fuente_camara(self, nueva_fuente, nombre_camara: str) -> bool:
        """
        Cambia dinámicamente la fuente de video en vivo sin reiniciar el programa.
        Detiene el lector previo y arranca la nueva conexión RTSP o dispositivo.
        """
        self.is_camera_running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        self.video_source = nueva_fuente
        self.nombre_camara_activa = nombre_camara

        if hasattr(self, "lbl_gate_name"):
            self.lbl_gate_name.config(text=f"SENSOR: {nombre_camara.upper()}")

        try:
            self.cap = ThreadedCamera(self.video_source)
            if not self.cap.start():
                self.cap = None
                self.lbl_status.config(
                    text=f"⚠️ No se pudo conectar con la cámara '{nombre_camara}'. Verifique la red.",
                    fg=self.COLOR_GOLD_ITSX
                )
                return False

            self.is_camera_running = True
            self.lbl_status.config(
                text=f"🟢 Transmitiendo en vivo desde: {nombre_camara} | ResNet-34 en línea",
                fg=self.COLOR_GREEN
            )
            return True
        except Exception as e:
            self.lbl_status.config(text=f"[-] Error al cambiar de cámara: {e}", fg=self.COLOR_RED)
            return False

    def _loop_camara(self):
        if not getattr(self, "is_camera_running", False) or self.cap is None:
            # Reintentar en 200 ms si la cámara está en pausa o cambiando
            self.root.after(200, self._loop_camara)
            return

        # timeout=0 -> no bloquea la interfaz: si no hay cuadro nuevo, simplemente se reintenta
        ret, frame = self.cap.read(timeout=0)
        if ret:
            self._frame_counter += 1
            try:
                current_tab = self.notebook.index(self.notebook.select())
                if current_tab == 0:
                    self._procesar_cuadro_acceso(frame)
                elif current_tab == 1:
                    self._procesar_cuadro_registro(frame)
            except Exception:
                pass

        self.root.after(10, self._loop_camara)

    def _procesar_cuadro_acceso(self, frame):
        ahora = time.time()

        # Detección + encoding + matching SOLO 1 de cada N cuadros; los demás reutilizan la caché
        if self._frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # Detección sobre copia reducida (rápido); encoding sobre el cuadro completo (mejor vector)
            boxes = self.encoder.detect_face_locations_scaled(rgb_frame, config.DETECTION_WIDTH)
            encodings = self.encoder.extract_encodings(rgb_frame, boxes)

            self._cache_acceso = []
            alguien_reconocido = False

            for box, encoding in zip(boxes, encodings):
                match = self.matcher.match_candidate(encoding)

                if match.reconocido and match.estudiante:
                    alguien_reconocido = True
                    est = match.estudiante

                    self.access_card_state = {
                        "status": "AUTORIZADO",
                        "name": est.nombre,
                        "matricula": est.matricula,
                        "carrera": est.carrera or "Sin Carrera",
                        "distancia": match.distancia,
                        "confianza": match.confianza_pct,
                        "timer": ahora
                    }

                    self._cache_acceso.append({
                        "box": box, "nombre": est.nombre, "matricula": est.matricula,
                        "distancia": match.distancia, "confianza": match.confianza_pct, "auth": True
                    })

                    last_log = self.db_cooldown.get(est.matricula, 0.0)
                    if ahora - last_log >= config.ACCESS_LOG_COOLDOWN_SECONDS:
                        self.db_cooldown[est.matricula] = ahora
                        self.db.log_acceso(
                            estudiante_id=est.id, matricula=est.matricula,
                            nombre=est.nombre, distancia=match.distancia, estado="PERMITIDO"
                        )
                        self.conteo_autorizados += 1
                        self.lbl_count_auth.config(text=str(self.conteo_autorizados))

                else:
                    self._cache_acceso.append({
                        "box": box, "nombre": "Desconocido", "matricula": None,
                        "distancia": match.distancia, "confianza": match.confianza_pct, "auth": False
                    })

                    if not alguien_reconocido and (ahora - self.access_card_state["timer"] > config.VISUAL_STATUS_PERSISTENCE_SECONDS):
                        self.access_card_state = {
                            "status": "DENEGADO",
                            "name": "Persona No Registrada",
                            "matricula": "---",
                            "carrera": "Acceso Restringido",
                            "distancia": match.distancia,
                            "confianza": match.confianza_pct,
                            "timer": ahora
                        }

                        last_log = self.db_cooldown.get("UNKNOWN", 0.0)
                        if ahora - last_log >= config.ACCESS_LOG_COOLDOWN_SECONDS:
                            self.db_cooldown["UNKNOWN"] = ahora
                            self.db.log_acceso(
                                estudiante_id=None, matricula=None,
                                nombre="Desconocido", distancia=match.distancia, estado="DENEGADO"
                            )
                            self.conteo_denegados += 1
                            self.lbl_count_den.config(text=str(self.conteo_denegados))

        # Dibujar SIEMPRE las cajas en caché sobre el cuadro actual (video fluido entre detecciones)
        for det in self._cache_acceso:
            Visualizer.draw_recognition_box(
                frame=frame, box=det["box"], nombre=det["nombre"], matricula=det["matricula"],
                distancia=det["distancia"], confianza=det["confianza"], es_autorizado=det["auth"]
            )

        self._renderizar_tarjeta_acceso(ahora)
        self._mostrar_en_label(frame, self.video_label_acceso)

    def _renderizar_tarjeta_acceso(self, ahora):
        estado = self.access_card_state["status"]
        tiempo_transcurrido = ahora - self.access_card_state["timer"]

        if estado == "AUTORIZADO" and tiempo_transcurrido <= config.VISUAL_STATUS_PERSISTENCE_SECONDS:
            self.card_frame.config(bg="#064E3B")
            self.lbl_card_icon.config(text="✅", fg=self.COLOR_GREEN, bg="#064E3B")
            self.lbl_card_title.config(text="ACCESO AUTORIZADO", fg=self.COLOR_GREEN, bg="#064E3B")
            self.lbl_card_subtitle.config(text="Estudiante verificado en padrón ITSX", fg="#ffffff", bg="#064E3B")
            self.lbl_card_name.config(text=f"Alumno: {self.access_card_state['name']}", bg="#064E3B")
            self.lbl_card_mat.config(text=f"Matrícula: {self.access_card_state['matricula']}", bg="#064E3B")
            self.lbl_card_car.config(text=f"Carrera: {self.access_card_state['carrera']}", bg="#064E3B")
            self.lbl_card_metric.config(
                text=f"Distancia L2: {self.access_card_state['distancia']:.3f}  |  {self.access_card_state['confianza']:.0f}% certeza",
                fg=self.COLOR_GREEN, bg="#064E3B"
            )

        elif estado == "DENEGADO" and tiempo_transcurrido <= config.VISUAL_STATUS_PERSISTENCE_SECONDS:
            self.card_frame.config(bg="#4C1D24")
            self.lbl_card_icon.config(text="⛔", fg=self.COLOR_RED, bg="#4C1D24")
            self.lbl_card_title.config(text="ACCESO DENEGADO", fg=self.COLOR_RED, bg="#4C1D24")
            self.lbl_card_subtitle.config(text="Sujeto NO identificado en padrón institucional", fg="#ffffff", bg="#4C1D24")
            self.lbl_card_name.config(text="Alumno: Desconocido", bg="#4C1D24")
            self.lbl_card_mat.config(text="Matrícula: ---", bg="#4C1D24")
            self.lbl_card_car.config(text="Acceso Restringido", bg="#4C1D24")
            self.lbl_card_metric.config(
                text=f"Distancia mínima: {self.access_card_state['distancia']:.3f} > {config.FACE_DISTANCE_THRESHOLD:.2f}",
                fg=self.COLOR_RED, bg="#4C1D24"
            )

        else:
            self.card_frame.config(bg=self.COLOR_CARD)
            self.lbl_card_icon.config(text="🛡️", fg=self.COLOR_ACCENT, bg=self.COLOR_CARD)
            self.lbl_card_title.config(text="ESPERANDO SUJETO", fg=self.COLOR_TEXT, bg=self.COLOR_CARD)
            self.lbl_card_subtitle.config(text="Aproxime el rostro hacia el sensor biométrico", fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD)
            self.lbl_card_name.config(text="Alumno: ---", bg=self.COLOR_CARD)
            self.lbl_card_mat.config(text="Matrícula: ---", bg=self.COLOR_CARD)
            self.lbl_card_car.config(text="Carrera: ---", bg=self.COLOR_CARD)
            self.lbl_card_metric.config(text="Distancia L2: ---", fg=self.COLOR_ACCENT, bg=self.COLOR_CARD)

    def _procesar_cuadro_registro(self, frame):
        frame_mirror = cv2.flip(frame, 1)

        # Detección + landmarks solo 1 de cada N cuadros (sobre copia reducida); el resto usa la caché
        if self._frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
            rgb_frame = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)
            boxes = self.encoder.detect_face_locations_scaled(rgb_frame, config.DETECTION_WIDTH)
            self._cache_n_rostros_reg = len(boxes)
            self._cache_landmarks = (
                face_recognition.face_landmarks(rgb_frame, face_locations=boxes)
                if len(boxes) == 1 else []
            )

        if self._cache_n_rostros_reg == 1 and self._cache_landmarks:
            Visualizer.draw_facial_landmarks(frame_mirror, self._cache_landmarks[0])
            Visualizer.draw_banner(frame_mirror, "Rostro Enfocado | Presione 'Escanear Rostro'", color=(46, 204, 113))
        elif self._cache_n_rostros_reg == 0:
            Visualizer.draw_banner(frame_mirror, "Buscando rostro... Enfoquese al centro", color=(23, 192, 235))
        else:
            Visualizer.draw_banner(frame_mirror, "Multiples personas detectadas", color=(52, 73, 235))

        self._mostrar_en_label(frame_mirror, self.video_label_registro)

    def _mostrar_en_label(self, frame, label_widget):
        h, w, _ = frame.shape
        target_w = max(420, label_widget.winfo_width())
        target_h = max(320, label_widget.winfo_height())

        scale = min(target_w / w, target_h / h)
        new_w = max(10, int(w * scale))
        new_h = max(10, int(h * scale))

        resized = cv2.resize(frame, (new_w, new_h))
        rgb_img = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(rgb_img)
        img_tk = ImageTk.PhotoImage(image=img_pil)

        label_widget.img_tk = img_tk
        label_widget.configure(image=img_tk)

    # -------------------------------------------------------------------------
    # ACCIONES DE REGISTRO: BIOMETRÍA PRIMERO
    # -------------------------------------------------------------------------
    def _accion_escanear_rostro(self):
        if self.cap is None or not self.cap.isOpened():
            messagebox.showerror("Error de Cámara", "La cámara no está disponible.")
            return

        ret, frame = self.cap.read(timeout=2.0)
        if not ret:
            messagebox.showerror("Error", "No se pudo leer el fotograma.")
            return

        frame_mirror = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)

        boxes = self.encoder.detect_face_locations_scaled(rgb_frame, max(config.DETECTION_WIDTH, 640))
        if len(boxes) == 0:
            self.lbl_scan_result.config(
                text="❌ No se detectó ningún rostro. Pida al alumno colocarse de frente al centro.",
                fg=self.COLOR_RED
            )
            return

        if len(boxes) > 1:
            self.lbl_scan_result.config(
                text="❌ Múltiples personas en el encuadre. Solo debe colocarse UNA persona.",
                fg=self.COLOR_RED
            )
            return

        encodings = self.encoder.extract_encodings(rgb_frame, boxes)
        if not encodings:
            self.lbl_scan_result.config(text="❌ No se pudo extraer el template biométrico.", fg=self.COLOR_RED)
            return

        candidato_vector = encodings[0]

        # VALIDACIÓN BIOMÉTRICA INMEDIATA EN BD
        ya_registrado, est_existente, dist = verificar_rostro_previo(candidato_vector, self.db)

        if ya_registrado and est_existente:
            self.nuevo_vector_candidato = None
            self._deshabilitar_formulario()

            alerta_msg = (
                f"⚠️ ¡ALTO! Este rostro YA ESTÁ REGISTRADO en el ITSX:\n\n"
                f"• Nombre: {est_existente.nombre}\n"
                f"• Matrícula: {est_existente.matricula}\n"
                f"• Carrera: {est_existente.carrera or 'Sin Carrera'}\n"
                f"• Distancia L2: {dist:.4f} (<= {config.FACE_DISTANCE_THRESHOLD:.2f})\n\n"
                f"No es necesario volver a registrarlo."
            )
            self.lbl_scan_result.config(
                text=f"⚠️ ROSTRO YA REGISTRADO en el ITSX:\n{est_existente.nombre} ({est_existente.matricula}).\nNo se requieren datos.",
                fg=self.COLOR_GOLD_ITSX
            )
            messagebox.showwarning("Rostro Ya Registrado en el ITSX", alerta_msg)
            return

        # Rostro nuevo y legítimo
        self.nuevo_vector_candidato = candidato_vector
        self._habilitar_formulario()

        self.lbl_scan_result.config(
            text="✅ ¡Rostro nuevo y verificado! Ingrese los datos del alumno para concluir el registro.",
            fg=self.COLOR_GREEN
        )
        self.ent_matricula.focus_set()

    def _habilitar_formulario(self):
        self.step2_box.config(fg=self.COLOR_GREEN)
        self.ent_matricula.config(state=tk.NORMAL)
        self.ent_nombre.config(state=tk.NORMAL)
        self.cmb_carrera.config(state="readonly")
        self.btn_guardar.config(state=tk.NORMAL)

    def _deshabilitar_formulario(self):
        self.step2_box.config(fg=self.COLOR_TEXT_MUTED)
        self.ent_matricula.delete(0, tk.END)
        self.ent_nombre.delete(0, tk.END)
        self.ent_matricula.config(state=tk.DISABLED)
        self.ent_nombre.config(state=tk.DISABLED)
        self.cmb_carrera.config(state=tk.DISABLED)
        self.btn_guardar.config(state=tk.DISABLED)

    def _accion_guardar_alumno(self):
        if self.nuevo_vector_candidato is None:
            messagebox.showerror("Error", "Primero debe escanear y validar un rostro.")
            return

        matricula = self.ent_matricula.get().strip()
        nombre = self.ent_nombre.get().strip()
        carrera = self.cmb_carrera.get().strip()

        if not matricula or not nombre:
            messagebox.showerror("Campos Incompletos", "La matrícula y el nombre completo son obligatorios.")
            return

        alumno_m = self.db.get_estudiante_by_matricula(matricula)
        if alumno_m:
            messagebox.showerror(
                "Matrícula Duplicada",
                f"La matrícula '{matricula}' ya pertenece a '{alumno_m.nombre}'. Ingrese una matrícula válida."
            )
            return

        try:
            self.db.save_estudiante(
                matricula=matricula,
                nombre=nombre,
                carrera=carrera,
                embedding=self.nuevo_vector_candidato
            )

            self.nuevo_vector_candidato = None
            self._deshabilitar_formulario()
            self.lbl_scan_result.config(
                text=f"🎉 ¡Éxito! Estudiante '{nombre}' incorporado al padrón del ITSX (1024 bytes).",
                fg=self.COLOR_GREEN
            )

            self._recargar_alumnos()

            messagebox.showinfo(
                "Registro Exitoso en ITSX",
                f"Estudiante {nombre} ({matricula})\n"
                f"Carrera: {carrera}\n\n"
                f"✓ Vector biométrico de 1024 bytes almacenado.\n"
                f"✓ Fotograma destruido de memoria RAM (LFPDPPP)."
            )

        except Exception as e:
            messagebox.showerror("Error al Guardar", f"No se pudo completar el registro: {e}")

    # -------------------------------------------------------------------------
    # GESTIÓN DE PADRÓN Y AUDITORÍA
    # -------------------------------------------------------------------------
    # PESTAÑA 4: CONFIGURACIÓN DE CÁMARAS (ADMIN)
    # -------------------------------------------------------------------------
    def _build_tab_configuracion(self):
        """Construye la interfaz de la pestaña de Configuración de Cámaras."""
        main_box = tk.Frame(self.tab_configuracion, bg=self.COLOR_BG, padx=15, pady=15)
        main_box.pack(fill=tk.BOTH, expand=True)

        # Panel izquierdo: tabla de cámaras
        left_panel = tk.Frame(main_box, bg=self.COLOR_PANEL)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        tk.Label(left_panel, text="CÁMARAS CONFIGURADAS", font=("Helvetica", 12, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 8))

        cols = ("id", "nombre", "ip", "usuario", "puerto", "ruta_rtsp", "activa")
        self.tree_camaras = ttk.Treeview(left_panel, columns=cols, show="headings", height=12)
        for col in cols:
            self.tree_camaras.heading(col, text=col.upper())
        self.tree_camaras.column("id", width=40, anchor=tk.CENTER)
        self.tree_camaras.column("activa", width=60, anchor=tk.CENTER)
        self.tree_camaras.pack(fill=tk.BOTH, expand=True)
        self.tree_camaras.bind("<<TreeviewSelect>>", self._on_seleccionar_camara)

        # Panel derecho: formulario de edición/creación
        right_panel = tk.Frame(main_box, bg=self.COLOR_PANEL, width=350)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        right_panel.pack_propagate(False)

        tk.Label(right_panel, text="Detalle de Cámara", font=("Helvetica", 12, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL).pack(pady=(0, 8))

        form_frame = tk.Frame(right_panel, bg=self.COLOR_PANEL)
        form_frame.pack(fill=tk.X, pady=4)

        # Nombre
        tk.Label(form_frame, text="Nombre:", fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.ent_cam_nombre = tk.Entry(form_frame)
        self.ent_cam_nombre.grid(row=0, column=1, pady=2, sticky=tk.EW)
        # IP
        tk.Label(form_frame, text="IP:", fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.ent_cam_ip = tk.Entry(form_frame)
        self.ent_cam_ip.grid(row=1, column=1, pady=2, sticky=tk.EW)
        # Usuario
        tk.Label(form_frame, text="Usuario:", fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.ent_cam_user = tk.Entry(form_frame)
        self.ent_cam_user.grid(row=2, column=1, pady=2, sticky=tk.EW)
        # Contraseña
        tk.Label(form_frame, text="Contraseña:", fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).grid(row=3, column=0, sticky=tk.W, pady=2)
        self.ent_cam_pass = tk.Entry(form_frame, show="*")
        self.ent_cam_pass.grid(row=3, column=1, pady=2, sticky=tk.EW)
        # Puerto
        tk.Label(form_frame, text="Puerto:", fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).grid(row=4, column=0, sticky=tk.W, pady=2)
        self.ent_cam_puerto = tk.Entry(form_frame)
        self.ent_cam_puerto.grid(row=4, column=1, pady=2, sticky=tk.EW)
        # Ruta RTSP
        tk.Label(form_frame, text="Ruta RTSP:", fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).grid(row=5, column=0, sticky=tk.W, pady=2)
        self.ent_cam_rtsp = tk.Entry(form_frame)
        self.ent_cam_rtsp.grid(row=5, column=1, pady=2, sticky=tk.EW)
        # Activa (checkbox)
        self.var_cam_activa = tk.BooleanVar()
        chk_activa = tk.Checkbutton(form_frame, text="Activa", variable=self.var_cam_activa, bg=self.COLOR_PANEL, fg=self.COLOR_TEXT, selectcolor=self.COLOR_CARD)
        chk_activa.grid(row=6, column=0, columnspan=2, pady=4)

        for i in range(2):
            form_frame.columnconfigure(i, weight=1)

        # Botones de acción
        btn_box = tk.Frame(right_panel, bg=self.COLOR_PANEL)
        btn_box.pack(fill=tk.X, pady=12)

        btn_guardar = tk.Button(btn_box, text="💾 Guardar", bg=self.COLOR_GREEN, fg="#ffffff", command=self._guardar_camara)
        btn_guardar.pack(fill=tk.X, pady=2)
        btn_actualizar = tk.Button(btn_box, text="🔄 Actualizar", bg=self.COLOR_ACCENT, fg="#ffffff", command=self._actualizar_camara_seleccionada)
        btn_actualizar.pack(fill=tk.X, pady=2)
        btn_eliminar = tk.Button(btn_box, text="🗑️ Eliminar", bg=self.COLOR_RED, fg="#ffffff", command=self._eliminar_camara_seleccionada)
        btn_eliminar.pack(fill=tk.X, pady=2)
        btn_test = tk.Button(btn_box, text="⚙️ Probar Conexión", bg=self.COLOR_CARD, fg=self.COLOR_TEXT, command=self._probar_conexion_camara)
        btn_test.pack(fill=tk.X, pady=2)
        btn_activar = tk.Button(btn_box, text="🚀 Activar", bg=self.COLOR_GOLD_ITSX, fg="#0F172A", command=self._activar_camara_seleccionada)
        btn_activar.pack(fill=tk.X, pady=2)

        # Cargar datos iniciales
        self._cargar_tabla_camaras()

    def _cargar_tabla_camaras(self):
        """Recarga el Treeview con la lista de cámaras de la base de datos."""
        for row in getattr(self, "tree_camaras", []).get_children():
            self.tree_camaras.delete(row)
        camaras = self.db.obtener_camaras()
        for cam in camaras:
            self.tree_camaras.insert("", tk.END, values=(cam.id, cam.nombre, cam.ip, cam.usuario, cam.puerto, cam.ruta_rtsp, "✅" if cam.activa else "❌"))

    def _on_seleccionar_camara(self, event):
        """Puebla el formulario con los datos de la cámara seleccionada."""
        sel = self.tree_camaras.selection()
        if not sel:
            return
        item = self.tree_camaras.item(sel[0])
        vals = item["values"]
        # vals corresponde a (id, nombre, ip, usuario, puerto, ruta_rtsp, activa)
        self._camara_seleccionada_id = vals[0]
        self.ent_cam_nombre.delete(0, tk.END); self.ent_cam_nombre.insert(0, vals[1])
        self.ent_cam_ip.delete(0, tk.END); self.ent_cam_ip.insert(0, vals[2])
        self.ent_cam_user.delete(0, tk.END); self.ent_cam_user.insert(0, vals[3])
        # La contraseña no se almacena en texto plano, dejamos campo vacío.
        self.ent_cam_pass.delete(0, tk.END)
        self.ent_cam_puerto.delete(0, tk.END); self.ent_cam_puerto.insert(0, vals[4])
        self.ent_cam_rtsp.delete(0, tk.END); self.ent_cam_rtsp.insert(0, vals[5])
        self.var_cam_activa.set(vals[6] == "✅")

    def _prompt_admin(self):
        """Muestra el diálogo de confirmación de administrador y devuelve (usuario, password) o None."""
        # Utilizamos el método de clase 'solicitar' que maneja la lógica modal y devuelve (autorizado, usuario, password)
        autorizado, admin_user, admin_pass = ConfirmAdminDialog.solicitar(
            parent=self.root,
            db=self.db,
            accion_titulo="Operación Administrativa",
            mensaje_detalles="Se requiere confirmar credenciales de administrador para esta acción."
        )
        if autorizado and admin_user and admin_pass:
            return admin_user, admin_pass
        return None

    def _guardar_camara(self):
        """Guarda una nueva cámara después de validar credenciales de administrador."""
        creds = self._prompt_admin()
        if not creds:
            messagebox.showwarning("Permiso", "Operación cancelada o sin credenciales de administrador.")
            return
        admin_user, admin_pass = creds
        nombre = self.ent_cam_nombre.get().strip()
        ip = self.ent_cam_ip.get().strip()
        usuario = self.ent_cam_user.get().strip()
        password = self.ent_cam_pass.get().strip()
        puerto = int(self.ent_cam_puerto.get().strip() or 554)
        ruta = self.ent_cam_rtsp.get().strip() or "/stream2"
        activa = self.var_cam_activa.get()
        cam_id, msg = self.db.guardar_camara(nombre, ip, usuario, password, puerto, ruta, activa, admin_user, admin_pass)
        if cam_id:
            messagebox.showinfo("Éxito", msg)
            self._cargar_tabla_camaras()
        else:
            messagebox.showerror("Error", msg)

    def _actualizar_camara_seleccionada(self):
        """Actualiza la cámara seleccionada en el árbol."""
        if not hasattr(self, "_camara_seleccionada_id"):
            messagebox.showwarning("Selección", "Primero seleccione una cámara de la tabla.")
            return
        creds = self._prompt_admin()
        if not creds:
            return
        admin_user, admin_pass = creds
        nombre = self.ent_cam_nombre.get().strip()
        ip = self.ent_cam_ip.get().strip()
        usuario = self.ent_cam_user.get().strip()
        password = self.ent_cam_pass.get().strip()
        puerto = int(self.ent_cam_puerto.get().strip() or 554)
        ruta = self.ent_cam_rtsp.get().strip() or "/stream2"
        activa = self.var_cam_activa.get()
        ok, msg = self.db.actualizar_camara(
            camara_id=self._camara_seleccionada_id,
            nombre=nombre,
            ip=ip,
            usuario=usuario,
            password_plana=password,
            puerto=puerto,
            ruta_rtsp=ruta,
            activa=activa,
            admin_username=admin_user,
            admin_password=admin_pass
        )
        if ok:
            messagebox.showinfo("Éxito", msg)
            self._cargar_tabla_camaras()
        else:
            messagebox.showerror("Error", msg)

    def _eliminar_camara_seleccionada(self):
        """Elimina la cámara seleccionada tras confirmación y credenciales de admin."""
        if not hasattr(self, "_camara_seleccionada_id"):
            messagebox.showwarning("Selección", "Primero seleccione una cámara.")
            return
        if not messagebox.askyesno("Confirmar", "¿Eliminar la cámara seleccionada?"):
            return
        creds = self._prompt_admin()
        if not creds:
            return
        admin_user, admin_pass = creds
        ok, msg = self.db.eliminar_camara(self._camara_seleccionada_id, admin_user, admin_pass)
        if ok:
            messagebox.showinfo("Éxito", msg)
            self._cargar_tabla_camaras()
        else:
            messagebox.showerror("Error", msg)

    def _activar_camara_seleccionada(self):
        """Marca la cámara seleccionada como activa y actualiza el streaming."""
        if not hasattr(self, "_camara_seleccionada_id"):
            messagebox.showwarning("Selección", "Primero seleccione una cámara.")
            return
        if not self.db.activar_camara(self._camara_seleccionada_id):
            messagebox.showerror("Error", "No se pudo activar la cámara.")
            return
        # Recargar lista para reflejar cambio
        self._cargar_tabla_camaras()
        # Cambiar fuente de video en la aplicación
        cam = self.db.obtener_camara_por_id(self._camara_seleccionada_id)
        if cam:
            self._cambiar_fuente_camara(cam.get_rtsp_url() if cam.ip not in ("0", "", "localhost_cam") else int(cam.ip), cam.nombre)
            messagebox.showinfo("Activada", f"Cámara '{cam.nombre}' ahora es la activa.")

    def _probar_conexion_camara(self):
        """Prueba la conexión a la cámara usando la utilidad async y muestra el resultado."""
        # Obtener datos del formulario (no se requieren credenciales admin para prueba)
        ip = self.ent_cam_ip.get().strip()
        puerto = int(self.ent_cam_puerto.get().strip() or 554)
        ruta = self.ent_cam_rtsp.get().strip() or "/stream2"
        user = self.ent_cam_user.get().strip()
        pwd = self.ent_cam_pass.get().strip()
        url = build_rtsp_url(ip, puerto, ruta, user, pwd) if ip and ip not in ("0", "") else ip
        try:
            import asyncio
            resultado = asyncio.run(test_camera_connection_async(url))
        except Exception as e:
            resultado = f"Error al probar conexión: {e}"
        messagebox.showinfo("Prueba de Conexión", resultado)

    # -------------------------------------------------------------------------
    # PESTAÑA 5: SEGURIDAD Y AUDITORÍA (ADMIN)
    # -------------------------------------------------------------------------
    def _build_tab_seguridad(self):
        """Construye la interfaz de la pestaña de Seguridad y Auditoría (bitácora de eventos)."""
        main_box = tk.Frame(self.tab_seguridad, bg=self.COLOR_BG, padx=15, pady=15)
        main_box.pack(fill=tk.BOTH, expand=True)

        toolbar = tk.Frame(main_box, bg=self.COLOR_BG)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        tk.Label(toolbar, text="BITÁCORA DE AUDITORÍA", font=("Helvetica", 13, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_BG).pack(side=tk.LEFT)
        btn_refresh = tk.Button(toolbar, text="🔄  Actualizar", font=("Helvetica", 10, "bold"), bg=self.COLOR_PANEL, fg="#ffffff", relief=tk.FLAT, padx=14, pady=6, cursor="hand2", command=self._cargar_auditoria)
        btn_refresh.pack(side=tk.RIGHT, padx=5)

        cols_aud = ("id", "usuario", "operacion", "entidad", "detalles", "resultado", "timestamp")
        self.tree_auditoria = ttk.Treeview(main_box, columns=cols_aud, show="headings", height=20)
        for col in cols_aud:
            self.tree_auditoria.heading(col, text=col.upper())
        self.tree_auditoria.column("id", width=40, anchor=tk.CENTER)
        self.tree_auditoria.column("timestamp", width=150)
        self.tree_auditoria.pack(fill=tk.BOTH, expand=True)

        self._cargar_auditoria()

    def _cargar_auditoria(self):
        """Carga los últimos eventos de auditoría en el Treeview."""
        for row in getattr(self, "tree_auditoria", []).get_children():
            self.tree_auditoria.delete(row)
        logs = self.db.obtener_bitacora_auditoria(limit=200)
        for log in logs:
            self.tree_auditoria.insert("", tk.END, values=(log.id, log.usuario, log.operacion, log.entidad, log.detalles, log.resultado, log.timestamp))

    # -------------------------------------------------------------------------
    def _cargar_tablas_bitacora(self):
        for row in self.tree_accesos.get_children():
            self.tree_accesos.delete(row)

        logs = self.db.get_recent_accesos(limit=100)
        for log in logs:
            estado_tag = "auth" if log.estado == "PERMITIDO" else "den"
            self.tree_accesos.insert(
                "", tk.END,
                values=(
                    log.id,
                    log.timestamp,
                    log.matricula or "---",
                    log.nombre or "Desconocido",
                    f"{log.distancia:.3f}",
                    "✓ AUTORIZADO" if log.estado == "PERMITIDO" else "✗ DENEGADO"
                ),
                tags=(estado_tag,)
            )

        self.tree_accesos.tag_configure("auth", foreground=self.COLOR_GREEN)
        self.tree_accesos.tag_configure("den", foreground=self.COLOR_RED)

        for row in self.tree_estudiantes.get_children():
            self.tree_estudiantes.delete(row)

        alumnos = self.db.get_all_active_estudiantes()
        for al in alumnos:
            self.tree_estudiantes.insert(
                "", tk.END,
                values=(al.id, al.matricula, al.nombre, al.carrera or "N/A", "1024 bytes")
            )

    def _recargar_alumnos(self):
        self.estudiantes = self.db.get_all_active_estudiantes()
        self.matcher.set_known_students(self.estudiantes)
        self.lbl_db_badge.config(
            text=f"🟢 EN LÍNEA | MOTOR: {config.DB_ENGINE.upper()} | PADRÓN: {len(self.estudiantes)} ALUMNOS"
        )
        self._cargar_tablas_bitacora()

    def _eliminar_alumno_seleccionado(self):
        seleccion = self.tree_estudiantes.selection()
        if not seleccion:
            messagebox.showinfo("Aviso", "Por favor seleccione un estudiante del padrón.")
            return

        item = self.tree_estudiantes.item(seleccion[0])
        matricula = item["values"][1]
        nombre = item["values"][2]

        if messagebox.askyesno("Confirmar Baja", f"¿Desea dar de baja a {nombre} ({matricula}) del padrón institucional?"):
            if self.db.delete_estudiante(matricula):
                messagebox.showinfo("Baja Confirmada", f"El alumno {nombre} y su vector fueron eliminados.")
                self._recargar_alumnos()
            else:
                messagebox.showerror("Error", "No se pudo eliminar el registro.")

    def _exportar_csv(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv")],
            initialfile=f"itsx_auditoria_accesos_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not filename:
            return

        try:
            from src.modules.admin import exportar_accesos_csv
            exportar_accesos_csv(filename)
            messagebox.showinfo("Exportación Completada", f"Auditoría exportada exitosamente a:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error al Exportar", f"Ocurrió un error: {e}")

    def _on_tab_changed(self, event):
        # Limpiar cachés de detección para no mostrar cajas/landmarks de otra pestaña
        self._cache_acceso = []
        self._cache_landmarks = []
        self._cache_n_rostros_reg = 0
        if self.notebook.index(self.notebook.select()) == 2:
            self._cargar_tablas_bitacora()

    def _on_close(self):
        self.is_camera_running = False
        if self.cap is not None:
            self.cap.release()
        self.root.destroy()


def iniciar_gui():
    """Punto de entrada de la aplicación gráfica del ITSX."""
    root = tk.Tk()
    app = GuardApp(root)
    root.mainloop()


if __name__ == "__main__":
    iniciar_gui()
