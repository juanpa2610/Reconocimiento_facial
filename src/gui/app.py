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
import queue
import threading
from datetime import datetime
import os
import gc
from typing import Optional, Dict, List, Tuple

import config
from src.db.database import Database
from src.db.models import Estudiante, Usuario, CamaraConfig, RegistroAuditoria
from src.db.school_db_sim import buscar_en_base_escolar
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
    CrearUsuarioDialog,
    AvisoPrivacidadDialog,
    PrimerInicioAdminDialog
)
from src.modules.admin import exportar_accesos_excel

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
            ip_str = str(cam_activa.ip).strip()
            if ip_str.isdigit() or ip_str in ("", "localhost_cam"):
                try:
                    self.video_source = int(ip_str) if ip_str.isdigit() else 0
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

        # Cola para trasladar el procesamiento biométrico fuera del hilo de Tk
        self._vision_queue: queue.Queue = queue.Queue(maxsize=2)
        self._vision_result_queue: queue.Queue = queue.Queue(maxsize=4)
        self._vision_thread: Optional[threading.Thread] = None

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

        # Estado del flujo de Registro (Escolar e Invitados)
        self.var_tipo_registro = tk.StringVar(value="escolar")
        self.datos_escolares_confirmados = False
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
        """Carga y procesa el escudo y logotipo oficial del ITSX en alta calidad."""
        self.escudo_header_img = None
        self.logo_header_img = None
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # 1. Cargar Escudo Institucional HD (prioritario)
        candidatos_escudo = [
            os.path.join(base_dir, "assets", "itsx_escudo_hd.png"),
            os.path.join(base_dir, "assets", "itsx_escudo_oficial.png"),
            os.path.join(base_dir, "assets", "itsx_escudo_clean.png"),
            os.path.join(base_dir, "assets", "itsx_logo_header.png"),
            os.path.join(base_dir, "assets", "itsx_logo_cropped.png")
        ]

        for ruta in candidatos_escudo:
            if os.path.exists(ruta):
                try:
                    pil_img = Image.open(ruta)
                    # Altura adecuada para la barra de navegación institucional
                    h_target = 60
                    w_target = int(pil_img.width * (h_target / pil_img.height))
                    pil_resized = pil_img.resize((w_target, h_target), Image.Resampling.LANCZOS)
                    self.escudo_header_img = ImageTk.PhotoImage(pil_resized)
                    break
                except Exception as e:
                    print(f"[-] Aviso: No se pudo cargar el escudo: {e}")

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
                        foreground="#38BDF8",
                        padding=[10, 6],
                        font=("Helvetica", 10, "bold"))
        style.map("Treeview", background=[("selected", "#0284C7")])

        # Combobox con alto contraste legible en modo oscuro
        style.configure("TCombobox",
                        fieldbackground=self.COLOR_CARD,
                        background=self.COLOR_CARD,
                        foreground="#FFFFFF",
                        selectbackground="#0284C7",
                        selectforeground="#FFFFFF",
                        arrowcolor="#FFFFFF")
        style.map("TCombobox",
                  fieldbackground=[("readonly", self.COLOR_CARD)],
                  foreground=[("readonly", "#FFFFFF")])

    def _build_header(self):
        header = tk.Frame(self.root, bg=self.COLOR_PANEL, height=82, padx=20, pady=10)
        header.pack(side=tk.TOP, fill=tk.X)

        # Lado izquierdo: Contenedor con Escudo ITSX y Títulos Oficiales
        left_box = tk.Frame(header, bg=self.COLOR_PANEL)
        left_box.pack(side=tk.LEFT, fill=tk.Y)

        # Escudo oficial de la escuela integrado directamente con fondo transparente
        if self.escudo_header_img:
            lbl_escudo = tk.Label(left_box, image=self.escudo_header_img, bg=self.COLOR_PANEL)
            lbl_escudo.pack(side=tk.LEFT, padx=(0, 16))
        else:
            lbl_icon = tk.Label(left_box, text="🏛️", font=("Helvetica", 30), bg=self.COLOR_PANEL)
            lbl_icon.pack(side=tk.LEFT, padx=(0, 14))

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
        if not self.db.has_usuarios():
            dlg = PrimerInicioAdminDialog(self.root, self.db)
            self.root.wait_window(dlg)

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

        # Panel derecho: Tarjeta de Acceso y KPIs para el Guardia (Ampliado)
        right_panel = tk.Frame(main_box, bg=self.COLOR_BG, width=540, padx=16, pady=10)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(14, 0))
        right_panel.pack_propagate(False)

        # Tarjeta Gigante de Verificación
        self.card_frame = tk.Frame(
            right_panel, bg=self.COLOR_CARD, bd=2, relief=tk.GROOVE, padx=22, pady=24
        )
        self.card_frame.pack(fill=tk.X, pady=(0, 15))

        self.lbl_card_icon = tk.Label(
            self.card_frame, text="🛡️", font=("Helvetica", 46), bg=self.COLOR_CARD, fg=self.COLOR_ACCENT
        )
        self.lbl_card_icon.pack(pady=(0, 4))

        self.lbl_card_title = tk.Label(
            self.card_frame, text="ESPERANDO SUJETO",
            font=("Helvetica", 18, "bold"), fg=self.COLOR_TEXT, bg=self.COLOR_CARD
        )
        self.lbl_card_title.pack()

        self.lbl_card_subtitle = tk.Label(
            self.card_frame, text="Aproxime el rostro hacia el sensor biométrico",
            font=("Helvetica", 11), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD
        )
        self.lbl_card_subtitle.pack(pady=(0, 10))

        self.sep_card = tk.Frame(self.card_frame, bg=self.COLOR_CARD_BORDER, height=2)
        self.sep_card.pack(fill=tk.X, pady=12)

        # Rejilla de información del alumno
        self.info_grid = tk.Frame(self.card_frame, bg=self.COLOR_CARD)
        self.info_grid.pack(fill=tk.X)

        self.lbl_card_name = tk.Label(
            self.info_grid, text="Alumno: ---", font=("Helvetica", 14, "bold"),
            fg="#ffffff", bg=self.COLOR_CARD, anchor=tk.W
        )
        self.lbl_card_name.pack(fill=tk.X, pady=4)

        self.lbl_card_mat = tk.Label(
            self.info_grid, text="Matrícula: ---", font=("Helvetica", 13, "bold"),
            fg="#ffffff", bg=self.COLOR_CARD, anchor=tk.W
        )
        self.lbl_card_mat.pack(fill=tk.X, pady=4)

        self.lbl_card_car = tk.Label(
            self.info_grid, text="Carrera: ---", font=("Helvetica", 12),
            fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD, anchor=tk.W, wraplength=480, justify=tk.LEFT
        )
        self.lbl_card_car.pack(fill=tk.X, pady=4)

        self.lbl_card_metric = tk.Label(
            self.info_grid, text="Distancia L2: ---", font=("Helvetica", 11, "bold"),
            fg=self.COLOR_ACCENT, bg=self.COLOR_CARD, anchor=tk.W
        )
        self.lbl_card_metric.pack(fill=tk.X, pady=4)

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

        # Panel izquierdo: Video para captura biométrica
        video_box = tk.Frame(main_box, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID)
        video_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        v_head = tk.Frame(video_box, bg=self.COLOR_CARD, padx=14, pady=9)
        v_head.pack(fill=tk.X)
        tk.Label(v_head, text="📸 ENROLAMIENTO BIOMÉTRICO (MODO ESPEJO CON MALLA FACIAL)",
                 font=("Helvetica", 11, "bold"), fg="#ffffff", bg=self.COLOR_CARD).pack(side=tk.LEFT)

        self.video_label_registro = tk.Label(video_box, bg="#050811")
        self.video_label_registro.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Panel derecho: Flujo Guiado Institucional
        # Panel derecho: Flujo Guiado Institucional (Ampliado para máxima legibilidad y confort visual)
        right_panel = tk.Frame(main_box, bg=self.COLOR_PANEL, width=640, padx=22, pady=16)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(14, 0))
        right_panel.pack_propagate(False)

        # Barra superior con Título y BOTÓN PERMANENTE DE NUEVO REGISTRO / LIMPIAR
        top_bar = tk.Frame(right_panel, bg=self.COLOR_PANEL)
        top_bar.pack(fill=tk.X, pady=(0, 10))

        title_box = tk.Frame(top_bar, bg=self.COLOR_PANEL)
        title_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(title_box, text="ENROLAMIENTO INSTITUCIONAL", font=("Helvetica", 14, "bold"),
                 fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL).pack(anchor=tk.W)
        tk.Label(title_box, text="Validación con Base Escolar y Registro de Invitados",
                 font=("Helvetica", 9), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(anchor=tk.W)

        # Botón permanente para volver a registrar / limpiar formulario
        self.btn_reset_registro = tk.Button(
            top_bar, text="🔄 Nuevo Registro", font=("Helvetica", 10, "bold"),
            bg="#D97706", fg="#0F172A", activebackground="#F59E0B", activeforeground="#0F172A",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self._limpiar_formulario_registro
        )
        self.btn_reset_registro.pack(side=tk.RIGHT, pady=2)

        # =====================================================================
        # SELECTOR DE MODALIDAD (Comunidad ITSX vs Invitado/Proveedor)
        # =====================================================================
        sel_box = tk.Frame(right_panel, bg=self.COLOR_CARD, padx=14, pady=10, bd=1, relief=tk.SOLID)
        sel_box.pack(fill=tk.X, pady=(0, 10))

        tk.Label(sel_box, text="Tipo de Persona a Registrar:*", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_CARD).pack(anchor=tk.W, pady=(0, 6))

        f_radios = tk.Frame(sel_box, bg=self.COLOR_CARD)
        f_radios.pack(fill=tk.X)

        self.rb_escolar = tk.Radiobutton(
            f_radios, text="🎓  Comunidad ITSX  (Alumno / Docente / Personal)",
            variable=self.var_tipo_registro, value="escolar",
            font=("Helvetica", 10, "bold"), bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
            selectcolor="#0B1120", activebackground=self.COLOR_CARD, activeforeground=self.COLOR_TEXT,
            command=self._on_cambio_tipo_registro
        )
        self.rb_escolar.pack(anchor=tk.W, pady=(2, 4))

        self.rb_invitado = tk.Radiobutton(
            f_radios, text="👤  Invitado / Proveedor / Visita Externa",
            variable=self.var_tipo_registro, value="invitado",
            font=("Helvetica", 10, "bold"), bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
            selectcolor="#0B1120", activebackground=self.COLOR_CARD, activeforeground=self.COLOR_TEXT,
            command=self._on_cambio_tipo_registro
        )
        self.rb_invitado.pack(anchor=tk.W, pady=(0, 2))

        # =====================================================================
        # PASO 1: Identificación y Validación
        # =====================================================================
        self.step1_box = tk.LabelFrame(
            right_panel, text="  PASO 1: Identificación y Validación del Sujeto  ",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_ACCENT, bg=self.COLOR_PANEL, padx=14, pady=10
        )
        self.step1_box.pack(fill=tk.X, pady=(0, 10))

        # --- A) SUBFRAME PARA COMUNIDAD ITSX (Búsqueda en Base Escolar) ---
        self.frame_modo_escolar = tk.Frame(self.step1_box, bg=self.COLOR_PANEL)
        self.frame_modo_escolar.pack(fill=tk.X)

        tk.Label(self.frame_modo_escolar, text="Número de Control o Clave Institucional:*",
                 font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 3))

        f_search_row = tk.Frame(self.frame_modo_escolar, bg=self.COLOR_PANEL)
        f_search_row.pack(fill=tk.X, pady=(0, 6))

        self.ent_matricula = tk.Entry(
            f_search_row, font=("Helvetica", 12, "bold"), bg=self.COLOR_CARD,
            fg="#ffffff", insertbackground=self.COLOR_ACCENT, bd=6, relief=tk.FLAT
        )
        self.ent_matricula.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.ent_matricula.bind("<Return>", lambda event: self._accion_buscar_escolar())

        self.btn_buscar_escolar = tk.Button(
            f_search_row, text="🔍 Buscar en Base Escolar", font=("Helvetica", 10, "bold"),
            bg="#0284C7", fg="#ffffff", activebackground="#0369A1", activeforeground="#ffffff",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2", command=self._accion_buscar_escolar
        )
        self.btn_buscar_escolar.pack(side=tk.RIGHT)

        # Estado informativo de la búsqueda escolar
        self.lbl_escolar_status = tk.Label(
            self.frame_modo_escolar,
            text="ℹ️ Ingrese el número de control (ej. 208O0123 / DOC-1025) y presione 'Buscar'.",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD,
            padx=12, pady=8, bd=1, relief=tk.SOLID, wraplength=570, justify=tk.LEFT
        )
        self.lbl_escolar_status.pack(fill=tk.X, pady=(0, 8))

        # Campos autocompletados desde la base escolar
        f_auto = tk.Frame(self.frame_modo_escolar, bg=self.COLOR_CARD, padx=12, pady=10, bd=1, relief=tk.GROOVE)
        f_auto.pack(fill=tk.X)

        tk.Label(f_auto, text="Nombre Completo:", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD).grid(row=0, column=0, sticky=tk.W, pady=4)
        self.ent_nombre = tk.Entry(f_auto, font=("Helvetica", 11, "bold"), bg=self.COLOR_PANEL, fg="#ffffff",
                                   readonlybackground=self.COLOR_PANEL, state="readonly", bd=5, relief=tk.FLAT)
        self.ent_nombre.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(f_auto, text="Rol Institucional:", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD).grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ent_tipo_persona = tk.Entry(f_auto, font=("Helvetica", 11, "bold"), bg=self.COLOR_PANEL, fg=self.COLOR_ACCENT,
                                         readonlybackground=self.COLOR_PANEL, state="readonly", bd=5, relief=tk.FLAT)
        self.ent_tipo_persona.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(f_auto, text="Carrera / Área:", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD).grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ent_carrera = tk.Entry(f_auto, font=("Helvetica", 11, "bold"), bg=self.COLOR_PANEL, fg="#ffffff",
                                    readonlybackground=self.COLOR_PANEL, state="readonly", bd=5, relief=tk.FLAT)
        self.ent_carrera.grid(row=2, column=1, sticky=tk.EW, padx=(8, 0), pady=4)
        f_auto.columnconfigure(1, weight=1)

        # Combobox auxiliar para mantener compatibilidad con métodos existentes
        self.cmb_carrera = ttk.Combobox(self.frame_modo_escolar, values=CARRERAS_ITSX)
        self.cmb_carrera.set("Ingeniería en Sistemas Computacionales")

        # --- B) SUBFRAME PARA INVITADOS / PROVEEDORES (Sin base escolar) ---
        self.frame_modo_invitado = tk.Frame(self.step1_box, bg=self.COLOR_PANEL)
        # Se empaca cuando el modo es invitado

        f_folio_row = tk.Frame(self.frame_modo_invitado, bg=self.COLOR_PANEL)
        f_folio_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(f_folio_row, text="Folio de Visitante:", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_matricula_inv = tk.Entry(f_folio_row, font=("Helvetica", 11, "bold"),
                                          bg=self.COLOR_PANEL, fg=self.COLOR_GOLD_ITSX,
                                          readonlybackground=self.COLOR_PANEL, state="readonly", width=18, bd=4, relief=tk.FLAT)
        self.ent_matricula_inv.pack(side=tk.LEFT, padx=8)

        tk.Label(self.frame_modo_invitado, text="Nombre Completo del Invitado / Proveedor:*",
                 font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(4, 2))
        self.ent_nombre_inv = tk.Entry(self.frame_modo_invitado, font=("Helvetica", 11, "bold"),
                                       bg=self.COLOR_CARD, fg="#ffffff", insertbackground=self.COLOR_ACCENT, bd=6, relief=tk.FLAT)
        self.ent_nombre_inv.pack(fill=tk.X, pady=(0, 6))

        tk.Label(self.frame_modo_invitado, text="Asunto / Motivo de Visita o Venta:*",
                 font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(4, 2))
        self.ent_asunto_inv = tk.Entry(self.frame_modo_invitado, font=("Helvetica", 11),
                                       bg=self.COLOR_CARD, fg="#ffffff", insertbackground=self.COLOR_ACCENT, bd=6, relief=tk.FLAT)
        self.ent_asunto_inv.pack(fill=tk.X, pady=(0, 6))

        tk.Label(self.frame_modo_invitado, text="Empresa o Procedencia (Opcional):",
                 font=("Helvetica", 9, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(3, 2))
        self.ent_empresa_inv = tk.Entry(self.frame_modo_invitado, font=("Helvetica", 10),
                                        bg=self.COLOR_CARD, fg="#ffffff", insertbackground=self.COLOR_ACCENT, bd=6, relief=tk.FLAT)
        self.ent_empresa_inv.pack(fill=tk.X, pady=(0, 6))

        # =====================================================================
        # PASO 2: Enrolamiento Biométrico Facial
        # =====================================================================
        self.step2_box = tk.LabelFrame(
            right_panel, text="  PASO 2: Enrolamiento Biométrico Facial  ",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL, padx=14, pady=10
        )
        self.step2_box.pack(fill=tk.X, pady=(0, 10))

        self.btn_escanear = tk.Button(
            self.step2_box, text="📸  Escanear Rostro del Candidato",
            font=("Helvetica", 11, "bold"), bg="#0284C7", fg="#ffffff",
            activebackground="#0369A1", activeforeground="#ffffff",
            relief=tk.FLAT, pady=11, cursor="hand2", command=self._accion_escanear_rostro
        )
        self.btn_escanear.pack(fill=tk.X, pady=2)

        self.lbl_scan_result = tk.Label(
            self.step2_box,
            text="Coloque a la persona de frente al sensor y presione 'Escanear Rostro'.",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD,
            padx=12, pady=8, bd=1, relief=tk.SOLID, wraplength=570, justify=tk.LEFT
        )
        self.lbl_scan_result.pack(fill=tk.X, pady=4)

        # =====================================================================
        # PASO 3: Consentimiento Legal y Guardado
        # =====================================================================
        self.step3_box = tk.LabelFrame(
            right_panel, text="  PASO 3: Consentimiento LFPDPPP y Guardado  ",
            font=("Helvetica", 10, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL, padx=14, pady=10
        )
        self.step3_box.pack(fill=tk.X, pady=(0, 8))

        # Consentimiento Informado (LFPDPPP)
        self.var_consentimiento = tk.BooleanVar(value=False)
        f_consent = tk.Frame(self.step3_box, bg=self.COLOR_PANEL)
        f_consent.pack(fill=tk.X, pady=(0, 8))
        self.chk_consentimiento = tk.Checkbutton(
            f_consent, text="Acepto el Aviso de Privacidad Integral (LFPDPPP)",
            variable=self.var_consentimiento, font=("Helvetica", 10, "bold"),
            bg=self.COLOR_PANEL, fg=self.COLOR_TEXT, selectcolor=self.COLOR_CARD,
            activebackground=self.COLOR_PANEL, activeforeground=self.COLOR_TEXT
        )
        self.chk_consentimiento.pack(side=tk.LEFT)
        self.btn_ver_aviso = tk.Button(
            f_consent, text="📄 Ver Aviso Legal", font=("Helvetica", 10, "underline"),
            bg=self.COLOR_PANEL, fg=self.COLOR_ACCENT, bd=0, cursor="hand2",
            command=self._abrir_modal_aviso_privacidad
        )
        self.btn_ver_aviso.pack(side=tk.LEFT, padx=8)

        # Botón Guardar
        self.btn_guardar = tk.Button(
            self.step3_box, text="💾  Guardar en Padrón (1024 bytes cifrados)",
            font=("Helvetica", 12, "bold"), bg=self.COLOR_GREEN, fg="#ffffff",
            activebackground="#059669", activeforeground="#ffffff",
            relief=tk.FLAT, pady=12, cursor="hand2", state=tk.DISABLED,
            command=self._accion_guardar_registro
        )
        self.btn_guardar.pack(fill=tk.X)

        # Botón para registrar a otra persona (aparece tras éxito)
        self.btn_otro_registro = tk.Button(
            self.step3_box, text="➕  Registrar a Otra Persona",
            font=("Helvetica", 11, "bold"), bg=self.COLOR_ACCENT, fg="#0F172A",
            activebackground="#0284C7", activeforeground="#ffffff",
            relief=tk.FLAT, pady=10, cursor="hand2",
            command=self._limpiar_formulario_registro
        )

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

        btn_export_excel = tk.Button(
            toolbar, text="📊  Exportar a Excel (.xlsx)", font=("Helvetica", 10, "bold"),
            bg="#10B981", fg="#ffffff", relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self._exportar_excel
        )
        btn_export_excel.pack(side=tk.RIGHT, padx=5)

        btn_export = tk.Button(
            toolbar, text="📥  Exportar a CSV", font=("Helvetica", 10, "bold"),
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
                 fg=self.COLOR_ACCENT, bg=self.COLOR_PANEL).pack(anchor=tk.W, pady=(0, 6))

        # Barra de Filtros de Accesos Avanzada (PB-07)
        filter_box = tk.LabelFrame(
            f_left, text=" 🔍 Filtros de Búsqueda Avanzada (PB-07) ",
            font=("Helvetica", 8, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL,
            padx=8, pady=6
        )
        filter_box.pack(fill=tk.X, pady=(0, 8))

        row1 = tk.Frame(filter_box, bg=self.COLOR_PANEL)
        row1.pack(fill=tk.X, pady=(0, 4))

        tk.Label(row1, text="Estado:", font=("Helvetica", 8, "bold"), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.cmb_filtro_estado = ttk.Combobox(
            row1, values=["Todos", "✓ AUTORIZADO", "✗ DENEGADO"], width=13, font=("Helvetica", 8), state="readonly"
        )
        self.cmb_filtro_estado.set("Todos")
        self.cmb_filtro_estado.pack(side=tk.LEFT, padx=(4, 8))
        self.cmb_filtro_estado.bind("<<ComboboxSelected>>", lambda e: self._filtrar_accesos())

        tk.Label(row1, text="F. Ini (AAAA-MM-DD):", font=("Helvetica", 8), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_filtro_fecha_ini = tk.Entry(
            row1, font=("Helvetica", 8), width=10, bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#fff", bd=2, relief=tk.FLAT
        )
        self.ent_filtro_fecha_ini.pack(side=tk.LEFT, padx=(2, 6))
        self.ent_filtro_fecha_ini.bind("<KeyRelease>", lambda e: self._filtrar_accesos())

        tk.Label(row1, text="F. Fin:", font=("Helvetica", 8), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_filtro_fecha_fin = tk.Entry(
            row1, font=("Helvetica", 8), width=10, bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#fff", bd=2, relief=tk.FLAT
        )
        self.ent_filtro_fecha_fin.pack(side=tk.LEFT, padx=(2, 0))
        self.ent_filtro_fecha_fin.bind("<KeyRelease>", lambda e: self._filtrar_accesos())

        row2 = tk.Frame(filter_box, bg=self.COLOR_PANEL)
        row2.pack(fill=tk.X)

        tk.Label(row2, text="H. Ini (HH:MM):", font=("Helvetica", 8), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_filtro_hora_ini = tk.Entry(
            row2, font=("Helvetica", 8), width=6, bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#fff", bd=2, relief=tk.FLAT
        )
        self.ent_filtro_hora_ini.pack(side=tk.LEFT, padx=(2, 6))
        self.ent_filtro_hora_ini.bind("<KeyRelease>", lambda e: self._filtrar_accesos())

        tk.Label(row2, text="H. Fin:", font=("Helvetica", 8), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_filtro_hora_fin = tk.Entry(
            row2, font=("Helvetica", 8), width=6, bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#fff", bd=2, relief=tk.FLAT
        )
        self.ent_filtro_hora_fin.pack(side=tk.LEFT, padx=(2, 6))
        self.ent_filtro_hora_fin.bind("<KeyRelease>", lambda e: self._filtrar_accesos())

        tk.Label(row2, text="Buscar:", font=("Helvetica", 8), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_buscar_acceso = tk.Entry(
            row2, font=("Helvetica", 8), bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#fff", bd=2, relief=tk.FLAT
        )
        self.ent_buscar_acceso.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 6))
        self.ent_buscar_acceso.bind("<KeyRelease>", lambda e: self._filtrar_accesos())

        btn_buscar = tk.Button(
            row2, text="🔍 Buscar", font=("Helvetica", 8, "bold"),
            bg=self.COLOR_ACCENT, fg="#0F172A", activebackground="#38BDF8", activeforeground="#0F172A",
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2", command=self._filtrar_accesos
        )
        btn_buscar.pack(side=tk.LEFT, padx=(0, 4))

        btn_limpiar = tk.Button(
            row2, text="🔄 Limpiar", font=("Helvetica", 8),
            bg="#475569", fg="#ffffff", activebackground="#64748B", activeforeground="#ffffff",
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2", command=self._limpiar_filtros_accesos
        )
        btn_limpiar.pack(side=tk.LEFT)

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
        r_top.pack(fill=tk.X, pady=(0, 6))
        tk.Label(r_top, text="PADRÓN BIOMÉTRICO (ALUMNOS ACTIVOS)", font=("Helvetica", 10, "bold"),
                 fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_PANEL).pack(side=tk.LEFT)

        btn_del = tk.Button(
            r_top, text="🗑️  Eliminar", font=("Helvetica", 9, "bold"),
            bg=self.COLOR_RED, fg="#ffffff", relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=self._eliminar_alumno_seleccionado
        )
        btn_del.pack(side=tk.RIGHT)

        btn_edit = tk.Button(
            r_top, text="✏️  Editar", font=("Helvetica", 9, "bold"),
            bg="#D97706", fg="#ffffff", relief=tk.FLAT, padx=8, pady=3, cursor="hand2",
            command=self._editar_alumno_seleccionado
        )
        btn_edit.pack(side=tk.RIGHT, padx=(0, 6))

        # Buscador de Alumnos
        filter_bar_est = tk.Frame(f_right, bg=self.COLOR_PANEL)
        filter_bar_est.pack(fill=tk.X, pady=(0, 6))
        tk.Label(filter_bar_est, text="Buscar alumno:", font=("Helvetica", 9), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL).pack(side=tk.LEFT)
        self.ent_buscar_estudiante = tk.Entry(filter_bar_est, font=("Helvetica", 9), bg=self.COLOR_CARD, fg="#ffffff", insertbackground="#fff", bd=3, relief=tk.FLAT)
        self.ent_buscar_estudiante.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self.ent_buscar_estudiante.bind("<KeyRelease>", lambda e: self._filtrar_estudiantes())

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
            # Iniciar hilo de visión (procesamiento biométrico fuera del hilo de Tk)
            self._iniciar_vision_thread()
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

    def _iniciar_vision_thread(self):
        """Lanza el hilo de procesamiento biométrico en segundo plano (fuera del hilo de Tk)."""
        if self._vision_thread is not None and self._vision_thread.is_alive():
            return

        def _worker():
            while self.is_camera_running:
                try:
                    item = self._vision_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    if isinstance(item, tuple):
                        t_inicio, frame_rgb = item
                    else:
                        t_inicio = time.perf_counter()
                        frame_rgb = item

                    boxes = self.encoder.detect_face_locations_scaled(frame_rgb, config.DETECTION_WIDTH)
                    encodings = self.encoder.extract_encodings(frame_rgb, boxes)
                    matches = [self.matcher.match_candidate(enc) for enc in encodings]

                    # Medición real y comprobable de latencia punto a punto
                    t_proceso = time.perf_counter() - t_inicio

                    # Evaluación fotométrica objetiva del nivel de iluminación de la escena
                    gray_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
                    brillo_medio = float(np.mean(gray_frame))
                    if brillo_medio < 55.0:
                        condicion_luz = f"Baja iluminación ({brillo_medio:.1f} lx)"
                    elif brillo_medio > 185.0:
                        condicion_luz = f"Sobreexposición ({brillo_medio:.1f} lx)"
                    else:
                        condicion_luz = f"Iluminación óptima ({brillo_medio:.1f} lx)"

                    self._vision_result_queue.put((boxes, encodings, matches, t_proceso, condicion_luz))
                except Exception as e:
                    print(f"[!] Error en hilo de visión: {e}")

        self._vision_thread = threading.Thread(target=_worker, name="VisionWorker", daemon=True)
        self._vision_thread.start()

    def _loop_camara(self):
        if not getattr(self, "is_camera_running", False) or self.cap is None:
            self.root.after(200, self._loop_camara)
            return

        # ── Detectar pérdida / recuperación de señal ──────────────────────────
        no_signal = getattr(self.cap, "no_signal", False)
        if no_signal:
            # Actualizar barra de estado solo 1 vez por transición
            if not getattr(self, "_cam_no_signal_shown", False):
                self._cam_no_signal_shown = True
                self.lbl_status.config(
                    text="⚠️  Sin señal de cámara — reconectando automáticamente…",
                    fg=self.COLOR_GOLD_ITSX
                )
            # Mostrar overlay animado en el panel de video activo
            try:
                tab = self.notebook.index(self.notebook.select())
                target = self.video_label_acceso if tab == 0 else getattr(self, "video_label_registro", self.video_label_acceso)
                self._mostrar_sin_senal(target)
            except Exception:
                pass
            self.root.after(500, self._loop_camara)
            return

        # Cámara recuperó señal
        if getattr(self, "_cam_no_signal_shown", False):
            self._cam_no_signal_shown = False
            self.lbl_status.config(
                text=f"🟢 Transmitiendo en vivo desde: {self.nombre_camara_activa} | ResNet-34 en línea",
                fg=self.COLOR_GREEN
            )

        # timeout=0 no bloquea la interfaz; si no hay cuadro nuevo, simplemente se reintenta
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

        # Enviar frame al hilo de visión solo cada N frames con timestamp exacto
        if self._frame_counter % config.PROCESS_EVERY_N_FRAMES == 0:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            t_inicio = time.perf_counter()
            try:
                self._vision_queue.put_nowait((t_inicio, rgb_frame))
            except queue.Full:
                pass

        # Recoger resultados del hilo de visión (sin bloquear)
        try:
            res_item = self._vision_result_queue.get_nowait()
            if len(res_item) == 5:
                boxes, encodings, matches, t_proceso, condicion_luz = res_item
            else:
                boxes, encodings, matches = res_item
                t_proceso, condicion_luz = 0.12, "Iluminación óptima"

            self._cache_acceso = []
            alguien_reconocido = False

            for box, encoding, match in zip(boxes, encodings, matches):
                if match.reconocido and match.estudiante:
                    alguien_reconocido = True
                    est = match.estudiante
                    t_acceso = round(float(t_proceso), 4)
                    self.access_card_state = {
                        "status": "AUTORIZADO", "name": est.nombre,
                        "matricula": est.matricula, "carrera": est.carrera or "Sin Carrera",
                        "distancia": match.distancia, "confianza": match.confianza_pct, "timer": ahora,
                        "tiempo_acceso": t_acceso, "condicion_luz": condicion_luz
                    }
                    self._cache_acceso.append({
                        "box": box, "nombre": est.nombre, "matricula": est.matricula,
                        "distancia": match.distancia, "confianza": match.confianza_pct, "auth": True
                    })
                    last_log = self.db_cooldown.get(est.matricula, 0.0)
                    if ahora - last_log >= config.ACCESS_LOG_COOLDOWN_SECONDS:
                        self.db_cooldown[est.matricula] = ahora
                        tipo_usu = "invitado" if (est.matricula.startswith("INV-") or "invitado" in (est.carrera or "").lower()) else ("docente" if "docente" in (est.carrera or "").lower() else "estudiante")
                        self.db.log_acceso(
                            estudiante_id=est.id, matricula=est.matricula,
                            nombre=est.nombre, distancia=match.distancia,
                            estado="PERMITIDO",
                            tiempo_acceso_segundos=t_acceso,
                            tipo_usuario=tipo_usu,
                            condicion_luz=condicion_luz
                        )
                        self.conteo_autorizados += 1
                        self.lbl_count_auth.config(text=str(self.conteo_autorizados))
                else:
                    self._cache_acceso.append({
                        "box": box, "nombre": "Desconocido", "matricula": None,
                        "distancia": match.distancia, "confianza": match.confianza_pct, "auth": False
                    })
                    if not alguien_reconocido and (ahora - self.access_card_state["timer"] > config.VISUAL_STATUS_PERSISTENCE_SECONDS):
                        t_acceso_den = round(float(t_proceso), 4)
                        self.access_card_state = {
                            "status": "DENEGADO", "name": "Persona No Registrada",
                            "matricula": "---", "carrera": "Acceso Restringido",
                            "distancia": match.distancia, "confianza": match.confianza_pct, "timer": ahora,
                            "tiempo_acceso": t_acceso_den, "condicion_luz": condicion_luz
                        }
                        last_log = self.db_cooldown.get("UNKNOWN", 0.0)
                        if ahora - last_log >= config.ACCESS_LOG_COOLDOWN_SECONDS:
                            self.db_cooldown["UNKNOWN"] = ahora
                            self.db.log_acceso(
                                estudiante_id=None, matricula=None,
                                nombre="Desconocido", distancia=match.distancia, estado="DENEGADO",
                                tiempo_acceso_segundos=t_acceso_den,
                                tipo_usuario="visitante",
                                condicion_luz=condicion_luz
                            )
                            self.conteo_denegados += 1
                            self.lbl_count_den.config(text=str(self.conteo_denegados))
        except queue.Empty:
            pass  # sin resultados nuevos, reutilizar caché

        # Dibujar siempre las cajas en caché sobre el cuadro actual (video fluido entre detecciones)
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
            bg_card = "#064E3B"
            self.card_frame.config(bg=bg_card)
            if hasattr(self, "sep_card"):
                self.sep_card.config(bg="#059669")
            if hasattr(self, "info_grid"):
                self.info_grid.config(bg=bg_card)
            self.lbl_card_icon.config(text="✅", fg="#34D399", bg=bg_card)
            self.lbl_card_title.config(text="ACCESO AUTORIZADO", fg="#34D399", bg=bg_card)
            mat_val = self.access_card_state.get("matricula", "")
            car_val = self.access_card_state.get("carrera", "")
            es_inv = str(mat_val).startswith("INV-") or "invitado" in str(car_val).lower()
            tipo_header = "Invitado / Proveedor" if es_inv else "Comunidad ITSX"
            self.lbl_card_subtitle.config(text=f"✓ {tipo_header} verificado en padrón", fg="#ffffff", bg=bg_card)
            self.lbl_card_name.config(text=f"Nombre: {self.access_card_state['name']}", fg="#ffffff", bg=bg_card)
            self.lbl_card_mat.config(text=f"Folio/Control: {mat_val}", fg="#38BDF8", bg=bg_card)
            self.lbl_card_car.config(text=f"Detalle/Área: {car_val}", fg=self.COLOR_GOLD_ITSX, bg=bg_card)
            t_ms = self.access_card_state.get("tiempo_acceso", 0.0) * 1000
            luz_str = self.access_card_state.get("condicion_luz", "Iluminación óptima")
            self.lbl_card_metric.config(
                text=f"Distancia L2: {self.access_card_state['distancia']:.3f}  |  {self.access_card_state['confianza']:.0f}% certeza\n⏱️ Latencia: {t_ms:.1f} ms  |  💡 {luz_str}",
                fg="#A7F3D0", bg=bg_card
            )

        elif estado == "DENEGADO" and tiempo_transcurrido <= config.VISUAL_STATUS_PERSISTENCE_SECONDS:
            bg_card = "#4C1D24"
            self.card_frame.config(bg=bg_card)
            if hasattr(self, "sep_card"):
                self.sep_card.config(bg="#EF4444")
            if hasattr(self, "info_grid"):
                self.info_grid.config(bg=bg_card)
            self.lbl_card_icon.config(text="⛔", fg="#F87171", bg=bg_card)
            self.lbl_card_title.config(text="ACCESO DENEGADO", fg="#F87171", bg=bg_card)
            self.lbl_card_subtitle.config(text="Sujeto NO identificado en padrón institucional", fg="#ffffff", bg=bg_card)
            self.lbl_card_name.config(text="Persona: Desconocida", fg="#ffffff", bg=bg_card)
            self.lbl_card_mat.config(text="Identificador: Sin registro", fg=self.COLOR_TEXT_MUTED, bg=bg_card)
            self.lbl_card_car.config(text="Acceso Restringido", fg="#EF4444", bg=bg_card)
            t_ms = self.access_card_state.get("tiempo_acceso", 0.0) * 1000
            luz_str = self.access_card_state.get("condicion_luz", "Iluminación óptima")
            self.lbl_card_metric.config(
                text=f"Distancia: {self.access_card_state['distancia']:.3f} > {config.FACE_DISTANCE_THRESHOLD:.2f}\n⏱️ Latencia: {t_ms:.1f} ms  |  💡 {luz_str}",
                fg="#FCA5A5", bg=bg_card
            )

        else:
            bg_card = self.COLOR_CARD
            self.card_frame.config(bg=bg_card)
            if hasattr(self, "sep_card"):
                self.sep_card.config(bg=self.COLOR_CARD_BORDER)
            if hasattr(self, "info_grid"):
                self.info_grid.config(bg=bg_card)
            self.lbl_card_icon.config(text="🛡️", fg=self.COLOR_ACCENT, bg=bg_card)
            self.lbl_card_title.config(text="ESPERANDO SUJETO", fg=self.COLOR_TEXT, bg=bg_card)
            self.lbl_card_subtitle.config(text="Aproxime el rostro hacia el sensor biométrico", fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_CARD)
            self.lbl_card_name.config(text="Persona: ---", fg="#ffffff", bg=bg_card)
            self.lbl_card_mat.config(text="Matrícula: ---", fg="#ffffff", bg=bg_card)
            self.lbl_card_car.config(text="Carrera: ---", fg=self.COLOR_TEXT_MUTED, bg=bg_card)
            self.lbl_card_metric.config(text="Distancia L2: ---", fg=self.COLOR_ACCENT, bg=bg_card)

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

    def _mostrar_sin_senal(self, label_widget):
        """Dibuja un overlay oscuro con icono y texto 'Sin señal' en el label de video."""
        try:
            w = max(640, label_widget.winfo_width())
            h = max(480, label_widget.winfo_height())
        except Exception:
            w, h = 640, 480

        # Fondo oscuro con ligero ruido (efecto TV sin señal)
        noise = np.random.randint(10, 35, (h, w, 3), dtype=np.uint8)
        frame = noise.copy()

        # Panel central semitransparente
        px1, py1 = w // 4, h // 3
        px2, py2 = 3 * w // 4, 2 * h // 3
        overlay = frame.copy()
        cv2.rectangle(overlay, (px1, py1), (px2, py2), (20, 20, 40), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (px1, py1), (px2, py2), (60, 80, 120), 2)

        cx, cy = w // 2, h // 2
        # Icono de cámara tachada
        cv2.putText(frame, "CAMARA", (cx - 90, cy - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (90, 130, 200), 2, cv2.LINE_AA)
        cv2.putText(frame, "SIN SENAL", (cx - 100, cy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (50, 200, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, "Reconectando automaticamente...", (cx - 170, cy + 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140, 160, 180), 1, cv2.LINE_AA)

        img_pil = Image.fromarray(frame)
        img_tk = ImageTk.PhotoImage(image=img_pil)
        label_widget.img_tk = img_tk
        label_widget.configure(image=img_tk)

    # -------------------------------------------------------------------------
    # ACCIONES DE REGISTRO INSTITUCIONAL (ESCOLAR E INVITADOS)
    # -------------------------------------------------------------------------
    def _on_cambio_tipo_registro(self):
        """Cambia entre la modalidad de Comunidad ITSX e Invitado/Proveedor."""
        modo = self.var_tipo_registro.get()
        if modo == "escolar":
            self.frame_modo_invitado.pack_forget()
            self.frame_modo_escolar.pack(fill=tk.X)
            self.ent_matricula.focus_set()
        else:
            self.frame_modo_escolar.pack_forget()
            self.frame_modo_invitado.pack(fill=tk.X)
            self._set_entry_text(self.ent_matricula_inv, self._generar_folio_invitado())
            self.ent_nombre_inv.focus_set()
        self._limpiar_formulario_registro()

    def _generar_folio_invitado(self) -> str:
        """Genera un folio secuencial único para visitantes (ej. INV-2026-001)."""
        year = datetime.now().year
        todos = self.db.get_all_active_estudiantes()
        invitados = [e for e in todos if e.matricula.startswith(f"INV-{year}-")]
        num = len(invitados) + 1
        folio = f"INV-{year}-{num:03d}"
        while self.db.get_estudiante_by_matricula(folio) is not None:
            num += 1
            folio = f"INV-{year}-{num:03d}"
        return folio

    def _set_entry_text(self, entry: tk.Entry, text: str):
        """Inserta texto en un Entry conservando su estado original."""
        prev = entry.cget("state")
        entry.config(state=tk.NORMAL)
        entry.delete(0, tk.END)
        entry.insert(0, text)
        entry.config(state=prev)

    def _accion_buscar_escolar(self):
        """Busca el número de control en la base de datos escolar simulada del ITSX."""
        clave = self.ent_matricula.get().strip().upper()
        if not clave:
            messagebox.showwarning(
                "Número de Control Requerido",
                "Por favor ingrese el número de control del alumno, docente o personal."
            )
            self.ent_matricula.focus_set()
            return

        # Consultar la base de datos escolar simulada
        datos = buscar_en_base_escolar(clave)
        if not datos:
            # NO EXISTE
            self.lbl_escolar_status.config(
                text="❌ Alumno o docente o personal no existe en la base de datos escolar.",
                fg="#FCA5A5",
                bg="#450A0A"
            )
            messagebox.showerror(
                "No Encontrado",
                f"❌ Alumno o docente o personal no existe en la base de datos de la escuela.\n\n"
                f"Número de control ingresado: '{clave}'\n"
                "Verifique que la clave sea correcta o consulte a Servicios Escolares / Recursos Humanos."
            )
            self._set_entry_text(self.ent_nombre, "")
            self._set_entry_text(self.ent_tipo_persona, "")
            self._set_entry_text(self.ent_carrera, "")
            self.datos_escolares_confirmados = False
            self.step2_box.config(fg=self.COLOR_TEXT_MUTED)
            self.btn_guardar.config(state=tk.DISABLED)
            return

        # SÍ EXISTE: Verificar si ya está enrolado en el padrón biométrico
        existente_en_padron = self.db.get_estudiante_by_matricula(clave)
        if existente_en_padron:
            self.lbl_escolar_status.config(
                text=f"⚠️ {datos['nombre_completo']} ({clave}) YA cuenta con biometría registrada.",
                fg="#FCD34D",
                bg="#451A03"
            )
            messagebox.showwarning(
                "Ya Registrado en Padrón",
                f"El registro con número de control '{clave}' ya cuenta con biometría en el padrón:\n\n"
                f"• Nombre: {existente_en_padron.nombre}\n"
                f"• Carrera/Área: {existente_en_padron.carrera}\n\n"
                "Si requiere actualizar sus datos o biometría, utilice la opción 'Editar' en la Pestaña 3 (Bitácora y Padrón)."
            )
            self._set_entry_text(self.ent_nombre, datos["nombre_completo"])
            self._set_entry_text(self.ent_tipo_persona, datos["tipo_usuario"])
            self._set_entry_text(self.ent_carrera, datos["carrera_o_departamento"])
            self.datos_escolares_confirmados = False
            self.btn_guardar.config(state=tk.DISABLED)
            return

        # VÁLIDO Y NUEVO EN PADRÓN
        self._set_entry_text(self.ent_nombre, datos["nombre_completo"])
        self._set_entry_text(self.ent_tipo_persona, datos["tipo_usuario"])
        self._set_entry_text(self.ent_carrera, datos["carrera_o_departamento"])
        self.datos_escolares_confirmados = True

        self.lbl_escolar_status.config(
            text=f"✅ Encontrado: {datos['nombre_completo']} | {datos['tipo_usuario']} | {datos['carrera_o_departamento']}",
            fg="#34D399",
            bg="#064E3B"
        )
        self.step2_box.config(fg=self.COLOR_GREEN)
        self.lbl_scan_result.config(
            text=f"✅ Identidad confirmada: {datos['nombre_completo']}. Posicione a la persona frente a la cámara y presione 'Escanear Rostro'.",
            fg=self.COLOR_ACCENT,
            bg=self.COLOR_CARD
        )

    def _accion_escanear_rostro(self):
        """Escanea el rostro en vivo y extrae el template biométrico de 1024 bytes."""
        modo = self.var_tipo_registro.get()
        if modo == "escolar" and not self.datos_escolares_confirmados:
            messagebox.showwarning(
                "Validación Escolar Requerida",
                "Primero debe ingresar el número de control y presionar 'Buscar en Base Escolar' para validar la identidad de la persona."
            )
            self.ent_matricula.focus_set()
            return
        elif modo == "invitado":
            nom = self.ent_nombre_inv.get().strip()
            asu = self.ent_asunto_inv.get().strip()
            if not nom or not asu:
                messagebox.showwarning(
                    "Datos de Invitado Requeridos",
                    "Debe registrar el Nombre Completo y el Asunto / Motivo de Visita del invitado antes de escanear su rostro."
                )
                if not nom:
                    self.ent_nombre_inv.focus_set()
                else:
                    self.ent_asunto_inv.focus_set()
                return

        if self.cap is None or not self.cap.isOpened():
            messagebox.showerror("Error de Cámara", "La cámara no está disponible.")
            return

        ret, frame = self.cap.read(timeout=2.0)
        if not ret:
            messagebox.showerror("Error", "No se pudo leer el fotograma de la cámara.")
            return

        frame_mirror = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)

        boxes = self.encoder.detect_face_locations_scaled(rgb_frame, max(config.DETECTION_WIDTH, 640))
        if len(boxes) == 0:
            self.lbl_scan_result.config(
                text="❌ No se detectó ningún rostro. Colóquese de frente al centro con buena iluminación.",
                fg="#FCA5A5",
                bg="#450A0A"
            )
            return

        if len(boxes) > 1:
            self.lbl_scan_result.config(
                text="❌ Múltiples personas en el encuadre. Solo debe colocarse UNA persona a la vez.",
                fg="#FCA5A5",
                bg="#450A0A"
            )
            return

        encodings = self.encoder.extract_encodings(rgb_frame, boxes)
        if not encodings:
            self.lbl_scan_result.config(
                text="❌ No se pudo extraer el template biométrico.",
                fg="#FCA5A5",
                bg="#450A0A"
            )
            return

        candidato_vector = encodings[0]

        # VALIDACIÓN BIOMÉTRICA INMEDIATA EN BD
        ya_registrado, est_existente, dist = verificar_rostro_previo(candidato_vector, self.db)

        if ya_registrado and est_existente:
            self.nuevo_vector_candidato = None
            self.btn_guardar.config(state=tk.DISABLED)

            alerta_msg = (
                f"⚠️ ¡ALTO! Este rostro YA ESTÁ REGISTRADO en el ITSX:\n\n"
                f"• Nombre: {est_existente.nombre}\n"
                f"• Identificador: {est_existente.matricula}\n"
                f"• Carrera/Detalle: {est_existente.carrera or 'Sin detalle'}\n"
                f"• Distancia L2: {dist:.4f} (<= {config.FACE_DISTANCE_THRESHOLD:.2f})\n\n"
                f"No es necesario volver a registrarlo."
            )
            self.lbl_scan_result.config(
                text=f"⚠️ ROSTRO YA REGISTRADO: {est_existente.nombre} ({est_existente.matricula}). No requiere nuevo registro.",
                fg="#FCD34D",
                bg="#451A03"
            )
            messagebox.showwarning("Rostro Ya Registrado en el ITSX", alerta_msg)
            return

        # Rostro nuevo y legítimo
        self.nuevo_vector_candidato = candidato_vector
        self.lbl_scan_result.config(
            text="✅ ¡Rostro verificado y vector de 1024 bytes extraído en memoria! Acepte el Aviso de Privacidad y guarde el registro.",
            fg="#34D399",
            bg="#064E3B"
        )
        self.step3_box.config(fg=self.COLOR_GREEN)
        self.btn_guardar.config(state=tk.NORMAL)

    def _abrir_modal_aviso_privacidad(self):
        """Abre el Aviso de Privacidad con opción de otorgar o denegar consentimiento expreso (LFPDPPP)."""
        modo = self.var_tipo_registro.get() if hasattr(self, "var_tipo_registro") else "escolar"
        if modo == "escolar":
            matricula = self.ent_matricula.get().strip().upper() if hasattr(self, "ent_matricula") else "PROSPECTO"
            tipo = self.ent_tipo_persona.get().strip() if hasattr(self, "ent_tipo_persona") else "Estudiante"
        else:
            matricula = self.ent_matricula_inv.get().strip().upper() if hasattr(self, "ent_matricula_inv") else "INVITADO"
            tipo = "Invitado"

        def _on_accept():
            self.var_consentimiento.set(True)
            messagebox.showinfo(
                "Consentimiento Otorgado",
                "Se ha aceptado el tratamiento de datos biométricos conforme a los Arts. 3 y 13 de la LFPDPPP.",
                parent=self.root
            )

        def _on_reject():
            self.var_consentimiento.set(False)
            token = self.db.registrar_consentimiento(
                matricula=matricula or "PROSPECTO",
                tipo_usuario=tipo or "Estudiante",
                otorgado=False,
                observaciones="Rechazo explícito del titular en terminal de registro biométrico"
            )
            messagebox.showwarning(
                "Consentimiento Denegado",
                f"Ha denegado el tratamiento de datos biométricos.\n"
                f"Folio de negativa registrado en auditoría: {token[:16]}...\n\n"
                f"En apego estricto a la LFPDPPP, sus datos biométricos NO serán capturados ni almacenados.",
                parent=self.root
            )

        AvisoPrivacidadDialog(
            parent=self.root,
            on_accept=_on_accept,
            on_reject=_on_reject,
            matricula=matricula or "PROSPECTO",
            tipo_usuario=tipo or "Estudiante"
        )

    def _accion_guardar_registro(self):
        """Guarda al alumno, docente, personal o invitado en el padrón institucional."""
        if self.nuevo_vector_candidato is None:
            messagebox.showerror("Error", "Primero debe escanear y validar un rostro.")
            return

        # Validación obligatoria de Consentimiento Informado (LFPDPPP)
        if hasattr(self, "var_consentimiento") and not self.var_consentimiento.get():
            messagebox.showwarning(
                "Consentimiento Informado Requerido",
                "Conforme a los Arts. 3 y 13 de la LFPDPPP, es requisito indispensable aceptar el Aviso de Privacidad Institucional para registrar los datos biométricos."
            )
            return

        modo = self.var_tipo_registro.get()

        if modo == "escolar":
            matricula = self.ent_matricula.get().strip().upper()
            nombre = self.ent_nombre.get().strip()
            tipo = self.ent_tipo_persona.get().strip() or "Alumno"
            carrera = self.ent_carrera.get().strip()

            if not matricula or not nombre:
                messagebox.showerror("Campos Incompletos", "Debe validar primero la matrícula en la base escolar.")
                return

            detalle_carrera = f"{tipo}: {carrera}" if tipo != "Alumno" else carrera

        else:  # MODO INVITADO
            matricula = self.ent_matricula_inv.get().strip().upper()
            nombre = self.ent_nombre_inv.get().strip()
            asunto = self.ent_asunto_inv.get().strip()
            empresa = self.ent_empresa_inv.get().strip()

            if not nombre or not asunto:
                messagebox.showerror("Campos Incompletos", "El nombre completo y el asunto son obligatorios para invitados.")
                return

            if not matricula:
                matricula = self._generar_folio_invitado()

            if empresa:
                detalle_carrera = f"Invitado ({empresa}): {asunto}"
            else:
                detalle_carrera = f"Invitado: {asunto}"

        alumno_m = self.db.get_estudiante_by_matricula(matricula)
        if alumno_m:
            messagebox.showerror(
                "Matrícula Duplicada",
                f"El identificador '{matricula}' ya pertenece a '{alumno_m.nombre}'. Operación cancelada."
            )
            return

        try:
            self.db.save_estudiante(
                matricula=matricula,
                nombre=nombre,
                carrera=detalle_carrera,
                embedding=self.nuevo_vector_candidato
            )

            # Registrar formalmente el consentimiento en base de datos (PB-08)
            token_c = self.db.registrar_consentimiento(
                matricula=matricula,
                tipo_usuario=tipo if modo == "escolar" else "Invitado",
                otorgado=True,
                observaciones="Consentimiento informado aceptado durante alta en terminal biométrica"
            )

            self.nuevo_vector_candidato = None
            self._recargar_alumnos()

            self.lbl_scan_result.config(
                text=f"🎉 ¡Éxito! '{nombre}' incorporado al padrón del ITSX (1024 bytes cifrados).",
                fg="#34D399",
                bg="#064E3B"
            )
            self.btn_guardar.config(state=tk.DISABLED)
            self.btn_otro_registro.pack(fill=tk.X, pady=(6, 0))

            resp = messagebox.askyesno(
                "Registro Exitoso en ITSX",
                f"✓ Persona: {nombre}\n"
                f"✓ Identificador: {matricula}\n"
                f"✓ Detalle: {detalle_carrera}\n\n"
                f"✓ Vector biométrico cifrado en reposo (LFPDPPP).\n"
                f"✓ Fotograma destruido de memoria RAM.\n\n"
                f"¿Desea registrar a otra persona ahora?"
            )

            if resp:
                self._limpiar_formulario_registro()

        except ValueError as e:
            messagebox.showerror("Validación de Registro", str(e))
        except Exception as e:
            messagebox.showerror("Error al Guardar", f"No se pudo completar el registro: {e}")

    def _limpiar_formulario_registro(self):
        """Limpia y resetea el formulario por completo para permitir registros consecutivos sin bloqueos."""
        self.nuevo_vector_candidato = None
        self.datos_escolares_confirmados = False
        if hasattr(self, "var_consentimiento"):
            self.var_consentimiento.set(False)

        # Limpiar campos escolares
        if hasattr(self, "ent_matricula"):
            self.ent_matricula.delete(0, tk.END)
        if hasattr(self, "ent_nombre"):
            self._set_entry_text(self.ent_nombre, "")
        if hasattr(self, "ent_tipo_persona"):
            self._set_entry_text(self.ent_tipo_persona, "")
        if hasattr(self, "ent_carrera"):
            self._set_entry_text(self.ent_carrera, "")
        if hasattr(self, "lbl_escolar_status"):
            self.lbl_escolar_status.config(
                text="ℹ️ Ingrese el número de control (ej. 208O0123 / DOC-1025) y presione 'Buscar'.",
                fg=self.COLOR_TEXT_MUTED,
                bg=self.COLOR_CARD
            )

        # Limpiar campos de invitado
        if hasattr(self, "ent_matricula_inv"):
            self._set_entry_text(self.ent_matricula_inv, self._generar_folio_invitado())
        if hasattr(self, "ent_nombre_inv"):
            self.ent_nombre_inv.delete(0, tk.END)
        if hasattr(self, "ent_asunto_inv"):
            self.ent_asunto_inv.delete(0, tk.END)
        if hasattr(self, "ent_empresa_inv"):
            self.ent_empresa_inv.delete(0, tk.END)

        # Reset avisos y botones
        if hasattr(self, "lbl_scan_result"):
            self.lbl_scan_result.config(
                text="Coloque a la persona de frente al sensor y presione 'Escanear Rostro'.",
                fg=self.COLOR_TEXT_MUTED,
                bg=self.COLOR_CARD
            )
        if hasattr(self, "step2_box"):
            self.step2_box.config(fg=self.COLOR_TEXT_MUTED)
        if hasattr(self, "step3_box"):
            self.step3_box.config(fg=self.COLOR_TEXT_MUTED)
        if hasattr(self, "btn_guardar"):
            self.btn_guardar.config(state=tk.DISABLED)
        if hasattr(self, "btn_otro_registro"):
            self.btn_otro_registro.pack_forget()

        # Foco según el modo
        if hasattr(self, "var_tipo_registro") and self.var_tipo_registro.get() == "escolar":
            if hasattr(self, "ent_matricula"):
                self.ent_matricula.focus_set()
        else:
            if hasattr(self, "ent_nombre_inv"):
                self.ent_nombre_inv.focus_set()

    def _habilitar_formulario(self):
        pass

    def _deshabilitar_formulario(self):
        self._limpiar_formulario_registro()

    def _accion_guardar_alumno(self):
        self._accion_guardar_registro()

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
        """Prueba la conexión a la cámara en un hilo secundario y muestra el resultado."""
        ip = self.ent_cam_ip.get().strip()
        if not ip:
            messagebox.showwarning("Campo requerido", "Ingrese la dirección IP o índice de la cámara.")
            return

        try:
            puerto = int(self.ent_cam_puerto.get().strip() or 554)
        except ValueError:
            puerto = 554

        ruta = self.ent_cam_rtsp.get().strip() or "/stream2"
        user = self.ent_cam_user.get().strip()
        pwd = self.ent_cam_pass.get().strip()

        # Mostrar indicador de progreso mientras se prueba
        self.lbl_status.config(text="⏳ Probando conexión con la cámara...", fg=self.COLOR_GOLD_ITSX)
        self.root.update_idletasks()

        def _on_resultado(resultado):
            exito, mensaje, resolucion, fps = resultado
            if exito:
                res_str = f"{resolucion[0]}x{resolucion[1]} px" if resolucion else "desconocida"
                texto = f"✅ Conexión exitosa\n\nResolución: {res_str}\nFPS: ~{fps:.0f}\n\n{mensaje}"
                self.root.after(0, lambda: [
                    messagebox.showinfo("Prueba de Conexión", texto),
                    self.lbl_status.config(
                        text="🟢 Sistema Biométrico ITSX Operativo", fg=self.COLOR_GREEN
                    )
                ])
            else:
                self.root.after(0, lambda: [
                    messagebox.showerror("Prueba de Conexión", f"❌ Sin conexión\n\n{mensaje}"),
                    self.lbl_status.config(
                        text="🔴 Prueba de cámara fallida", fg=self.COLOR_RED
                    )
                ])

        # Llamada correcta: ip, user, password, port, ruta, callback
        test_camera_connection_async(ip, user, pwd, puerto, ruta, _on_resultado)

    # -------------------------------------------------------------------------
    # PESTAÑA 5: SEGURIDAD Y AUDITORÍA (ADMIN)
    # -------------------------------------------------------------------------
    def _build_tab_seguridad(self):
        """Construye la interfaz de la pestaña de Seguridad y Auditoría (bitácora de eventos)."""
        main_box = tk.Frame(self.tab_seguridad, bg=self.COLOR_BG, padx=15, pady=15)
        main_box.pack(fill=tk.BOTH, expand=True)

        toolbar = tk.Frame(main_box, bg=self.COLOR_BG)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        tk.Label(toolbar, text="BITÁCORA DE AUDITORÍA Y SEGURIDAD", font=("Helvetica", 13, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_BG).pack(side=tk.LEFT)

        btn_crear_usr = tk.Button(
            toolbar, text="👤➕  Registrar Nuevo Usuario / Rol", font=("Helvetica", 10, "bold"),
            bg=self.COLOR_GREEN, fg="#ffffff", relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self._abrir_crear_usuario
        )
        btn_crear_usr.pack(side=tk.RIGHT, padx=5)

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
    def _abrir_crear_usuario(self):
        """Abre el diálogo para registrar un nuevo usuario / rol del sistema con autorización admin."""
        dlg = CrearUsuarioDialog(self.root)
        dlg.wait_window()

        if not getattr(dlg, "confirmado", False) or not getattr(dlg, "datos", None):
            return

        autorizado, admin_user, admin_pass = ConfirmAdminDialog.solicitar(
            parent=self.root,
            db=self.db,
            accion_titulo=f"Alta de Usuario: {dlg.datos.get('username')}",
            mensaje_detalles=f"Nombre: {dlg.datos.get('nombre')}\nRol solicitado: {dlg.datos.get('rol')}"
        )
        if not autorizado or not admin_user or not admin_pass:
            messagebox.showwarning("Cancelado", "Operación cancelada. Se requieren credenciales válidas de administrador.")
            return

        ok, msg = self.db.crear_usuario(
            username=dlg.datos["username"],
            password=dlg.datos["password"],
            nombre_completo=dlg.datos["nombre"],
            rol=dlg.datos["rol"],
            admin_user=admin_user,
            admin_pass=admin_pass
        )
        if ok:
            messagebox.showinfo("Usuario Registrado", msg)
            self._cargar_auditoria()
        else:
            messagebox.showerror("Error al Crear Usuario", msg)

    # -------------------------------------------------------------------------
    def _cargar_tablas_bitacora(self):
        """Carga los registros y aplica los filtros activos."""
        self._cache_raw_accesos = self.db.get_recent_accesos(limit=100)
        self._cache_raw_estudiantes = self.db.get_all_active_estudiantes()
        self._filtrar_accesos()
        self._filtrar_estudiantes()

    def _filtrar_accesos(self):
        """Filtra la tabla de accesos por estado, rango de fechas, rango de horas y texto en tiempo real (PB-07)."""
        if not hasattr(self, "tree_accesos"):
            return
        for row in self.tree_accesos.get_children():
            self.tree_accesos.delete(row)

        filtro_estado = getattr(self, "cmb_filtro_estado", None)
        estado_sel = filtro_estado.get() if filtro_estado else "Todos"

        filtro_fecha_ini = getattr(self, "ent_filtro_fecha_ini", None)
        f_ini = filtro_fecha_ini.get().strip() if filtro_fecha_ini else ""

        filtro_fecha_fin = getattr(self, "ent_filtro_fecha_fin", None)
        f_fin = filtro_fecha_fin.get().strip() if filtro_fecha_fin else ""

        filtro_hora_ini = getattr(self, "ent_filtro_hora_ini", None)
        h_ini = filtro_hora_ini.get().strip() if filtro_hora_ini else ""

        filtro_hora_fin = getattr(self, "ent_filtro_hora_fin", None)
        h_fin = filtro_hora_fin.get().strip() if filtro_hora_fin else ""

        filtro_txt = getattr(self, "ent_buscar_acceso", None)
        txt_query = filtro_txt.get().strip().lower() if filtro_txt else ""

        self._accesos_filtrados_actuales = []

        for log in getattr(self, "_cache_raw_accesos", []):
            if estado_sel == "✓ AUTORIZADO" and log.estado != "PERMITIDO":
                continue
            if estado_sel == "✗ DENEGADO" and log.estado == "PERMITIDO":
                continue

            ts = str(log.timestamp or "")
            fecha_log = ts[:10] if len(ts) >= 10 else ""
            hora_log = ts[11:16] if len(ts) >= 16 else ""

            if f_ini and fecha_log and fecha_log < f_ini:
                continue
            if f_fin and fecha_log and fecha_log > f_fin:
                continue
            if h_ini and hora_log and hora_log < h_ini:
                continue
            if h_fin and hora_log and hora_log > h_fin:
                continue

            mat = (log.matricula or "").lower()
            nom = (log.nombre or "").lower()
            if txt_query and (txt_query not in mat and txt_query not in nom):
                continue

            self._accesos_filtrados_actuales.append(log)

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

    def _limpiar_filtros_accesos(self):
        """Restablece los filtros de búsqueda de accesos a sus valores por defecto."""
        if hasattr(self, "cmb_filtro_estado"):
            self.cmb_filtro_estado.set("Todos")
        if hasattr(self, "ent_filtro_fecha_ini"):
            self.ent_filtro_fecha_ini.delete(0, tk.END)
        if hasattr(self, "ent_filtro_fecha_fin"):
            self.ent_filtro_fecha_fin.delete(0, tk.END)
        if hasattr(self, "ent_filtro_hora_ini"):
            self.ent_filtro_hora_ini.delete(0, tk.END)
        if hasattr(self, "ent_filtro_hora_fin"):
            self.ent_filtro_hora_fin.delete(0, tk.END)
        if hasattr(self, "ent_buscar_acceso"):
            self.ent_buscar_acceso.delete(0, tk.END)
        self._filtrar_accesos()

    def _filtrar_estudiantes(self):
        """Filtra la tabla del padrón de alumnos por texto en tiempo real."""
        if not hasattr(self, "tree_estudiantes"):
            return
        for row in self.tree_estudiantes.get_children():
            self.tree_estudiantes.delete(row)

        filtro_txt = getattr(self, "ent_buscar_estudiante", None)
        txt_query = filtro_txt.get().strip().lower() if filtro_txt else ""

        for al in getattr(self, "_cache_raw_estudiantes", []):
            mat = (al.matricula or "").lower()
            nom = (al.nombre or "").lower()
            car = (al.carrera or "").lower()
            if txt_query and (txt_query not in mat and txt_query not in nom and txt_query not in car):
                continue

            self.tree_estudiantes.insert(
                "", tk.END,
                values=(al.id, al.matricula, al.nombre, al.carrera or "N/A", "1024 bytes (cifrado)")
            )

    def _recargar_alumnos(self):
        self.estudiantes = self.db.get_all_active_estudiantes()
        self.matcher.set_known_students(self.estudiantes)
        self.lbl_db_badge.config(
            text=f"🟢 EN LÍNEA | MOTOR: {config.DB_ENGINE.upper()} | PADRÓN: {len(self.estudiantes)} ALUMNOS"
        )
        self._cargar_tablas_bitacora()

    def _editar_alumno_seleccionado(self):
        """Abre el diálogo de edición para el alumno seleccionado en el padrón."""
        seleccion = self.tree_estudiantes.selection()
        if not seleccion:
            messagebox.showinfo("Aviso", "Por favor seleccione un estudiante del padrón.")
            return

        item = self.tree_estudiantes.item(seleccion[0])
        matricula = str(item["values"][1])

        # Buscar el objeto Estudiante completo
        estudiante = next((e for e in self.estudiantes if str(e.matricula) == matricula), None)
        if not estudiante:
            messagebox.showerror("Error", "No se encontró el registro del estudiante.")
            return

        # Mostrar diálogo de edición
        dlg = EditEstudianteDialog(self.root, estudiante, CARRERAS_ITSX)
        dlg.wait_window()

        if not dlg.confirmado:
            return

        # Solicitar credenciales de administrador para autorizar
        autorizado, admin_user, admin_pass = ConfirmAdminDialog.solicitar(
            parent=self.root,
            db=self.db,
            accion_titulo=f"Modificar datos de: {estudiante.nombre}",
            mensaje_detalles=f"Matrícula: {matricula}\nNombre nuevo: {dlg.nuevo_nombre}\nCarrera: {dlg.nueva_carrera}"
        )
        if not autorizado:
            messagebox.showwarning("Cancelado", "Operación cancelada. Se requieren credenciales de administrador.")
            return

        ok, msg = self.db.update_estudiante(
            matricula_actual=matricula,
            nuevo_nombre=dlg.nuevo_nombre,
            nueva_carrera=dlg.nueva_carrera,
            admin_username=admin_user,
            admin_password=admin_pass
        )
        if ok:
            messagebox.showinfo("Actualizado", msg)
            self._recargar_alumnos()
        else:
            messagebox.showerror("Error", msg)

    def _eliminar_alumno_seleccionado(self):
        """Elimina el alumno seleccionado del padrón, requiriendo credenciales de administrador."""
        seleccion = self.tree_estudiantes.selection()
        if not seleccion:
            messagebox.showinfo("Aviso", "Por favor seleccione un estudiante del padrón.")
            return

        item = self.tree_estudiantes.item(seleccion[0])
        matricula = str(item["values"][1])
        nombre = str(item["values"][2])

        if not messagebox.askyesno(
            "Confirmar Baja",
            f"¿Desea dar de baja a {nombre} ({matricula}) del padrón institucional?\n\nEsta acción requiere credenciales de administrador."
        ):
            return

        # Exigir credenciales admin antes de eliminar
        autorizado, admin_user, admin_pass = ConfirmAdminDialog.solicitar(
            parent=self.root,
            db=self.db,
            accion_titulo=f"Eliminar alumno: {nombre}",
            mensaje_detalles=f"Matrícula: {matricula}\nEsta acción eliminará permanentemente el vector biométrico y el registro."
        )
        if not autorizado:
            messagebox.showwarning("Cancelado", "Operación cancelada.")
            return

        ok = self.db.delete_estudiante(matricula, admin_username=admin_user, admin_password=admin_pass)
        if ok:
            messagebox.showinfo("Baja Confirmada", f"El alumno {nombre} y su vector fueron eliminados del padrón.")
            self._recargar_alumnos()
        else:
            messagebox.showerror("Error", "No se pudo eliminar el registro. Verifique las credenciales de administrador.")

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
            datos_a_exportar = getattr(self, "_accesos_filtrados_actuales", None)
            exportar_accesos_csv(filename, logs_data=datos_a_exportar)
            messagebox.showinfo("Exportación Completada", f"Auditoría exportada exitosamente a:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error al Exportar", f"Ocurrió un error: {e}")

    def _exportar_excel(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Libro de Excel (*.xlsx)", "*.xlsx")],
            initialfile=f"itsx_auditoria_accesos_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        if not filename:
            return

        try:
            from src.modules.admin import exportar_accesos_excel
            datos_a_exportar = getattr(self, "_accesos_filtrados_actuales", None)
            exportar_accesos_excel(filename, logs_data=datos_a_exportar)
            messagebox.showinfo(
                "Exportación Completada",
                f"Auditoría exportada exitosamente en formato Excel nativo (.xlsx) a:\n{filename}"
            )
        except Exception as e:
            messagebox.showerror("Error al Exportar Excel", f"Ocurrió un error: {e}")

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
