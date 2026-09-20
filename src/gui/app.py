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
from typing import Optional, Dict, List

import config
from src.db.database import Database
from src.db.models import Estudiante
from src.biometrics.encoder import FaceEncoder
from src.biometrics.matcher import FaceMatcher, MatchResult
from src.modules.registro import verificar_rostro_previo
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

        # Base de datos y motor biométrico
        self.db = Database()
        self.db.init_db()
        self.encoder = FaceEncoder(model=config.DETECTION_MODEL)
        self.matcher = FaceMatcher(threshold=config.FACE_DISTANCE_THRESHOLD)
        self.estudiantes: List[Estudiante] = self.db.get_all_active_estudiantes()

        # Dispositivo de video
        self.video_source = config.VIDEO_SOURCE
        self.cap = None
        self.is_camera_running = False

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

        # Iniciar reloj y cámara
        self._actualizar_reloj()
        self._iniciar_camara()

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

        # Lado derecho: Reloj en vivo y Status Badge
        right_box = tk.Frame(header, bg=self.COLOR_PANEL)
        right_box.pack(side=tk.RIGHT, fill=tk.Y)

        # Reloj digital institucional
        self.lbl_clock = tk.Label(
            right_box,
            text="--:--:--  |  --/--/----",
            font=("Helvetica", 11, "bold"),
            fg=self.COLOR_ACCENT,
            bg=self.COLOR_PANEL
        )
        self.lbl_clock.pack(anchor=tk.E, pady=(2, 4))

        # Badge de estado de BD y cámara
        badge = tk.Frame(right_box, bg=self.COLOR_CARD, padx=12, pady=5, bd=1, relief=tk.GROOVE)
        badge.pack(anchor=tk.E)

        self.lbl_db_badge = tk.Label(
            badge,
            text=f"🟢 EN LÍNEA | MOTOR: {config.DB_ENGINE.upper()} | PADRÓN: {len(self.estudiantes)} ALUMNOS",
            font=("Helvetica", 9, "bold"),
            fg=self.COLOR_GREEN,
            bg=self.COLOR_CARD
        )
        self.lbl_db_badge.pack()

    def _actualizar_reloj(self):
        """Actualiza el reloj institucional cada segundo."""
        ahora = datetime.now().strftime("%H:%M:%S  |  %d/%m/%Y")
        self.lbl_clock.config(text=ahora)
        self.root.after(1000, self._actualizar_reloj)

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
            self.cap = cv2.VideoCapture(self.video_source)
            if not self.cap.isOpened():
                self.lbl_status.config(
                    text=f"⚠️ No se pudo acceder a la fuente de video '{self.video_source}'.",
                    fg=self.COLOR_GOLD_ITSX
                )
                return
            self.is_camera_running = True
            self._loop_camara()
        except Exception as e:
            self.lbl_status.config(text=f"[-] Error al abrir video: {e}", fg=self.COLOR_RED)

    def _loop_camara(self):
        if not self.is_camera_running or self.cap is None:
            return

        ret, frame = self.cap.read()
        if ret:
            current_tab = self.notebook.index(self.notebook.select())
            if current_tab == 0:
                self._procesar_cuadro_acceso(frame)
            elif current_tab == 1:
                self._procesar_cuadro_registro(frame)

        self.root.after(30, self._loop_camara)

    def _procesar_cuadro_acceso(self, frame):
        h, w, _ = frame.shape
        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        boxes = self.encoder.detect_face_locations(rgb_small)
        encodings = self.encoder.extract_encodings(rgb_small, boxes)

        ahora = time.time()
        alguien_reconocido = False

        for small_box, encoding in zip(boxes, encodings):
            top, right, bottom, left = small_box
            box = (top * 2, right * 2, bottom * 2, left * 2)

            match = self.matcher.match(encoding, self.estudiantes)

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

                Visualizer.draw_recognition_box(
                    frame=frame, box=box, nombre=est.nombre, matricula=est.matricula,
                    distancia=match.distancia, confianza=match.confianza_pct, es_autorizado=True
                )

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
                Visualizer.draw_recognition_box(
                    frame=frame, box=box, nombre="Desconocido", matricula=None,
                    distancia=match.distancia, confianza=match.confianza_pct, es_autorizado=False
                )

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
                text=f"Distancia mínima: {self.access_card_state['distancia']:.3f} > 0.55",
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
        rgb_frame = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)

        landmarks_list = face_recognition.face_landmarks(rgb_frame)
        if len(landmarks_list) == 1:
            Visualizer.draw_facial_landmarks(frame_mirror, landmarks_list[0])
            Visualizer.draw_banner(frame_mirror, "Rostro Enfocado | Presione 'Escanear Rostro'", color=(46, 204, 113))
        elif len(landmarks_list) == 0:
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

        ret, frame = self.cap.read()
        if not ret:
            messagebox.showerror("Error", "No se pudo leer el fotograma.")
            return

        frame_mirror = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame_mirror, cv2.COLOR_BGR2RGB)

        boxes = self.encoder.detect_face_locations(rgb_frame)
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
                f"• Distancia L2: {dist:.4f} (<= 0.55)\n\n"
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
