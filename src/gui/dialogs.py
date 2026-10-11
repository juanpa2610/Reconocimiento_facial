"""
Módulos de Diálogos y Modales de Seguridad para la Interfaz Gráfica ITSX.
Instituto Tecnológico Superior de Xalapa - Taller de Investigación II.

Incluye:
- LoginDialog: Pantalla modal de autenticación obligatoria y RBAC.
- ConfirmAdminDialog: Modal de re-autenticación para operaciones sensibles en BD.
- EditEstudianteDialog: Modal de actualización de datos de estudiantes.
- CrearUsuarioDialog: Modal para el alta de nuevos operadores y administradores.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple, List, Dict
from src.db.database import Database
from src.db.models import Usuario, Estudiante


class LoginDialog(tk.Toplevel):
    """
    Pantalla modal de Inicio de Sesión obligatoria antes de acceder al sistema.
    Valida credenciales contra la base de datos con contraseñas hasheadas (PBKDF2-HMAC-SHA256).
    """

    def __init__(self, parent: tk.Tk, db: Database, on_success, on_cancel=None):
        super().__init__(parent)
        self.db = db
        self.on_success = on_success
        self.on_cancel = on_cancel
        self.user_authenticated = False

        self.title("ITSX - Inicio de Sesión Seguro")
        self.geometry("460x540")
        self.resizable(False, False)

        # Paleta Institucional
        self.COLOR_BG = "#0B1120"
        self.COLOR_PANEL = "#151F32"
        self.COLOR_CARD = "#1E293B"
        self.COLOR_TEXT = "#F8FAFC"
        self.COLOR_TEXT_MUTED = "#94A3B8"
        self.COLOR_GOLD_ITSX = "#E5A823"
        self.COLOR_GREEN = "#10B981"
        self.COLOR_RED = "#EF4444"
        self.COLOR_ACCENT = "#38BDF8"

        self.configure(bg=self.COLOR_BG)

        # Modalidad
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_x()
            py = parent.winfo_y()
        except Exception:
            pw, ph, px, py = 1200, 800, 100, 100

        w, h = 460, 540
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main = tk.Frame(self, bg=self.COLOR_BG, padx=30, pady=24)
        main.pack(fill=tk.BOTH, expand=True)

        # Encabezado institucional
        lbl_escudo = tk.Label(main, text="🔐", font=("Helvetica", 38), bg=self.COLOR_BG, fg=self.COLOR_GOLD_ITSX)
        lbl_escudo.pack(pady=(0, 6))

        lbl_inst = tk.Label(
            main, text="INSTITUTO TECNOLÓGICO SUPERIOR DE XALAPA",
            font=("Helvetica", 11, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_BG
        )
        lbl_inst.pack()

        lbl_sys = tk.Label(
            main, text="Control de Acceso Biométrico Institucional",
            font=("Helvetica", 12, "bold"), fg="#ffffff", bg=self.COLOR_BG
        )
        lbl_sys.pack(pady=(2, 6))

        lbl_sub = tk.Label(
            main, text="Identifíquese con sus credenciales de usuario o administrador",
            font=("Helvetica", 9), fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_BG
        )
        lbl_sub.pack(pady=(0, 18))

        # Tarjeta de Formulario
        card = tk.Frame(main, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID, padx=22, pady=20)
        card.pack(fill=tk.BOTH, expand=True)

        # Campo Usuario
        tk.Label(
            card, text="Nombre de Usuario:", font=("Helvetica", 10, "bold"),
            fg=self.COLOR_TEXT, bg=self.COLOR_PANEL
        ).pack(anchor=tk.W, pady=(0, 4))

        self.ent_user = tk.Entry(
            card, font=("Helvetica", 11), bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#ffffff", relief=tk.FLAT, bd=6
        )
        self.ent_user.pack(fill=tk.X, pady=(0, 14))
        self.ent_user.insert(0, "admin#ITSX26")

        # Campo Contraseña
        tk.Label(
            card, text="Contraseña del Sistema:", font=("Helvetica", 10, "bold"),
            fg=self.COLOR_TEXT, bg=self.COLOR_PANEL
        ).pack(anchor=tk.W, pady=(0, 4))

        pass_frame = tk.Frame(card, bg=self.COLOR_CARD, bd=0)
        pass_frame.pack(fill=tk.X, pady=(0, 6))

        self.ent_pass = tk.Entry(
            pass_frame, font=("Helvetica", 11), bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#ffffff", relief=tk.FLAT, bd=6, show="•"
        )
        self.ent_pass.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._show_pass = False
        self.btn_eye = tk.Button(
            pass_frame, text="👁", font=("Helvetica", 9), bg=self.COLOR_CARD, fg=self.COLOR_TEXT_MUTED,
            relief=tk.FLAT, cursor="hand2", command=self._toggle_show_pass
        )
        self.btn_eye.pack(side=tk.RIGHT, padx=4)

        # Label de error
        self.lbl_error = tk.Label(
            card, text="", font=("Helvetica", 9, "bold"),
            fg=self.COLOR_RED, bg=self.COLOR_PANEL, wraplength=360, justify=tk.LEFT
        )
        self.lbl_error.pack(fill=tk.X, pady=(2, 8))

        # Botón Iniciar Sesión
        self.btn_login = tk.Button(
            card, text="🔑  Iniciar Sesión", font=("Helvetica", 11, "bold"),
            bg=self.COLOR_GREEN, fg="#ffffff", activebackground="#059669",
            relief=tk.FLAT, pady=10, cursor="hand2", command=self._ejecutar_login
        )
        self.btn_login.pack(fill=tk.X, pady=(4, 6))

        # Botón Salir
        btn_exit = tk.Button(
            card, text="Cerrar Aplicación", font=("Helvetica", 9),
            bg=self.COLOR_PANEL, fg=self.COLOR_TEXT_MUTED, relief=tk.FLAT,
            cursor="hand2", command=self._on_window_close
        )
        btn_exit.pack(fill=tk.X)

        # Atajos de teclado
        self.ent_user.bind("<Return>", lambda e: self.ent_pass.focus_set())
        self.ent_pass.bind("<Return>", lambda e: self._ejecutar_login())
        self.bind("<Escape>", lambda e: self._on_window_close())

        self.ent_pass.focus_set()

    def _toggle_show_pass(self):
        self._show_pass = not self._show_pass
        self.ent_pass.config(show="" if self._show_pass else "•")
        self.btn_eye.config(fg=self.COLOR_GOLD_ITSX if self._show_pass else self.COLOR_TEXT_MUTED)

    def _ejecutar_login(self):
        usuario = self.ent_user.get().strip()
        password = self.ent_pass.get()

        if not usuario or not password:
            self.lbl_error.config(text="⚠️ Ingrese tanto usuario como contraseña.")
            return

        user_obj = self.db.autenticar_usuario(usuario, password)
        if user_obj:
            self.user_authenticated = True
            self.db.log_auditoria(
                user_obj.username,
                "INICIO_SESION",
                "SISTEMA",
                f"Sesión iniciada correctamente con rol '{user_obj.rol}'",
                "EXITO"
            )
            self.on_success(user_obj)
            self.destroy()
        else:
            self.db.log_auditoria(
                usuario,
                "INICIO_SESION",
                "SISTEMA",
                f"Intento fallido de inicio de sesión para el usuario '{usuario}'",
                "FALLIDO_AUTENTICACION"
            )
            self.lbl_error.config(text="❌ Credenciales incorrectas. Verifique usuario o contraseña.")
            self.ent_pass.delete(0, tk.END)
            self.ent_pass.focus_set()

    def _on_window_close(self):
        if not self.user_authenticated and self.on_cancel:
            self.on_cancel()
        self.destroy()


class ConfirmAdminDialog(tk.Toplevel):
    """
    Diálogo modal de confirmación y re-autenticación con credenciales de Administrador.
    Obligatorio para autorizar modificaciones y eliminaciones de registros en la base de datos.
    """

    def __init__(
        self,
        parent,
        db: Database,
        accion_titulo: str,
        mensaje_detalles: str,
        default_user: str = ""
    ):
        super().__init__(parent)
        self.db = db
        self.accion_titulo = accion_titulo
        self.mensaje_detalles = mensaje_detalles
        self.default_user = default_user
        self.resultado = (False, None, None)

        self.title("ITSX - Re-autenticación de Seguridad")
        self.geometry("480x420")
        self.resizable(False, False)

        self.COLOR_BG = "#0B1120"
        self.COLOR_PANEL = "#151F32"
        self.COLOR_CARD = "#1E293B"
        self.COLOR_TEXT = "#F8FAFC"
        self.COLOR_TEXT_MUTED = "#94A3B8"
        self.COLOR_GOLD_ITSX = "#E5A823"
        self.COLOR_GREEN = "#10B981"
        self.COLOR_RED = "#EF4444"

        self.configure(bg=self.COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            pw, ph, px, py = parent.winfo_width(), parent.winfo_height(), parent.winfo_x(), parent.winfo_y()
        except Exception:
            pw, ph, px, py = 1200, 800, 100, 100
        w, h = 480, 420
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main = tk.Frame(self, bg=self.COLOR_BG, padx=24, pady=18)
        main.pack(fill=tk.BOTH, expand=True)

        head = tk.Frame(main, bg=self.COLOR_BG)
        head.pack(fill=tk.X, pady=(0, 10))

        tk.Label(head, text="⚠️", font=("Helvetica", 24), bg=self.COLOR_BG, fg=self.COLOR_GOLD_ITSX).pack(side=tk.LEFT, padx=(0, 10))
        t_box = tk.Frame(head, bg=self.COLOR_BG)
        t_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            t_box, text="OPERACIÓN SENSIBLE EN BASE DE DATOS",
            font=("Helvetica", 11, "bold"), fg=self.COLOR_RED, bg=self.COLOR_BG
        ).pack(anchor=tk.W)

        tk.Label(
            t_box, text=self.accion_titulo,
            font=("Helvetica", 10, "bold"), fg="#ffffff", bg=self.COLOR_BG
        ).pack(anchor=tk.W)

        # Detalles del registro
        card_desc = tk.Frame(main, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID, padx=14, pady=10)
        card_desc.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            card_desc, text=self.mensaje_detalles,
            font=("Helvetica", 9), fg=self.COLOR_TEXT, bg=self.COLOR_PANEL,
            justify=tk.LEFT, wraplength=410
        ).pack(anchor=tk.W)

        # Formulario de credenciales
        form_card = tk.Frame(main, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID, padx=16, pady=12)
        form_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tk.Label(
            form_card, text="Usuario Administrador:", font=("Helvetica", 9, "bold"),
            fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL
        ).pack(anchor=tk.W, pady=(0, 2))

        self.ent_admin_user = tk.Entry(
            form_card, font=("Helvetica", 10), bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#ffffff", relief=tk.FLAT, bd=5
        )
        self.ent_admin_user.pack(fill=tk.X, pady=(0, 8))
        if self.default_user:
            self.ent_admin_user.insert(0, self.default_user)
        else:
            self.ent_admin_user.insert(0, "admin#ITSX26")

        tk.Label(
            form_card, text="Contraseña de Administrador:", font=("Helvetica", 9, "bold"),
            fg=self.COLOR_TEXT_MUTED, bg=self.COLOR_PANEL
        ).pack(anchor=tk.W, pady=(0, 2))

        self.ent_admin_pass = tk.Entry(
            form_card, font=("Helvetica", 10), bg=self.COLOR_CARD, fg="#ffffff",
            insertbackground="#ffffff", relief=tk.FLAT, bd=5, show="•"
        )
        self.ent_admin_pass.pack(fill=tk.X, pady=(0, 4))

        self.lbl_error = tk.Label(
            form_card, text="", font=("Helvetica", 9, "bold"),
            fg=self.COLOR_RED, bg=self.COLOR_PANEL, wraplength=410, justify=tk.LEFT
        )
        self.lbl_error.pack(fill=tk.X, pady=(2, 0))

        # Botones
        btn_box = tk.Frame(main, bg=self.COLOR_BG)
        btn_box.pack(fill=tk.X)

        self.btn_cancel = tk.Button(
            btn_box, text="✖ Cancelar Operación", font=("Helvetica", 10, "bold"),
            bg="#475569", fg="#ffffff", relief=tk.FLAT, padx=14, pady=7,
            cursor="hand2", command=self._on_cancel
        )
        self.btn_cancel.pack(side=tk.LEFT)

        self.btn_auth = tk.Button(
            btn_box, text="✔ Autorizar y Ejecutar", font=("Helvetica", 10, "bold"),
            bg=self.COLOR_RED, fg="#ffffff", activebackground="#B91C1C",
            relief=tk.FLAT, padx=16, pady=7, cursor="hand2", command=self._on_auth
        )
        self.btn_auth.pack(side=tk.RIGHT)

        self.ent_admin_pass.bind("<Return>", lambda e: self._on_auth())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.ent_admin_pass.focus_set()

    def _on_auth(self):
        u = self.ent_admin_user.get().strip()
        p = self.ent_admin_pass.get()

        if not u or not p:
            self.lbl_error.config(text="⚠️ Ingrese usuario y contraseña de administrador.")
            return

        ok, admin_obj, msg = self.db.verificar_credenciales_admin(u, p)
        if not ok:
            self.lbl_error.config(text=f"❌ {msg}")
            self.ent_admin_pass.delete(0, tk.END)
            self.ent_admin_pass.focus_set()
            return

        self.resultado = (True, admin_obj.username, p)
        self.destroy()

    def _on_cancel(self):
        self.resultado = (False, None, None)
        self.destroy()

    @classmethod
    def solicitar(
        cls,
        parent,
        db: Database,
        accion_titulo: str,
        mensaje_detalles: str,
        default_user: str = ""
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Abre el modal sincrónicamente y retorna (autorizado, admin_user, admin_pass)."""
        dlg = cls(parent, db, accion_titulo, mensaje_detalles, default_user)
        dlg.wait_window()
        return dlg.resultado


class EditEstudianteDialog(tk.Toplevel):
    """
    Diálogo para editar los datos de un estudiante registrado.
    """

    def __init__(self, parent, estudiante: Estudiante, carreras_catalogo: List[str]):
        super().__init__(parent)
        self.estudiante = estudiante
        self.carreras_catalogo = carreras_catalogo
        self.confirmado = False
        self.nuevo_nombre = estudiante.nombre
        self.nueva_carrera = estudiante.carrera or ""

        self.title("ITSX - Editar Estudiante")
        self.geometry("460x360")
        self.resizable(False, False)

        self.COLOR_BG = "#0B1120"
        self.COLOR_PANEL = "#151F32"
        self.COLOR_CARD = "#1E293B"
        self.COLOR_TEXT = "#F8FAFC"
        self.COLOR_GOLD_ITSX = "#E5A823"
        self.COLOR_GREEN = "#10B981"

        self.configure(bg=self.COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            pw, ph, px, py = parent.winfo_width(), parent.winfo_height(), parent.winfo_x(), parent.winfo_y()
        except Exception:
            pw, ph, px, py = 1200, 800, 100, 100
        w, h = 460, 360
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main = tk.Frame(self, bg=self.COLOR_BG, padx=24, pady=18)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main, text="✏️  MODIFICAR DATOS DEL ESTUDIANTE",
            font=("Helvetica", 12, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_BG
        ).pack(anchor=tk.W, pady=(0, 4))

        tk.Label(
            main, text=f"Matrícula Institucional: {self.estudiante.matricula} (Clave única)",
            font=("Helvetica", 9), fg="#94A3B8", bg=self.COLOR_BG
        ).pack(anchor=tk.W, pady=(0, 14))

        card = tk.Frame(main, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID, padx=16, pady=14)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        tk.Label(card, text="Nombre Completo:", font=("Helvetica", 9, "bold"), fg="#ffffff", bg=self.COLOR_PANEL).pack(anchor=tk.W)
        self.ent_nombre = tk.Entry(card, font=("Helvetica", 10), bg=self.COLOR_CARD, fg="#ffffff", insertbackground="#fff", bd=5, relief=tk.FLAT)
        self.ent_nombre.pack(fill=tk.X, pady=(2, 10))
        self.ent_nombre.insert(0, self.estudiante.nombre)

        tk.Label(card, text="Carrera / Programa Académico:", font=("Helvetica", 9, "bold"), fg="#ffffff", bg=self.COLOR_PANEL).pack(anchor=tk.W)
        self.cmb_carrera = ttk.Combobox(card, values=self.carreras_catalogo, font=("Helvetica", 10), state="readonly")
        self.cmb_carrera.pack(fill=tk.X, pady=(2, 4))
        if self.estudiante.carrera in self.carreras_catalogo:
            self.cmb_carrera.set(self.estudiante.carrera)
        elif self.carreras_catalogo:
            self.cmb_carrera.set(self.carreras_catalogo[0])

        tk.Label(
            card, text="ℹ️ Se solicitarán credenciales de administrador para autorizar el cambio.",
            font=("Helvetica", 8, "italic"), fg="#38BDF8", bg=self.COLOR_PANEL
        ).pack(anchor=tk.W, pady=(6, 0))

        btn_box = tk.Frame(main, bg=self.COLOR_BG)
        btn_box.pack(fill=tk.X)

        tk.Button(
            btn_box, text="Cancelar", font=("Helvetica", 10), bg="#475569", fg="#ffffff",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2", command=self.destroy
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_box, text="Continuar con Autorización ➡️", font=("Helvetica", 10, "bold"),
            bg=self.COLOR_GREEN, fg="#ffffff", relief=tk.FLAT, padx=16, pady=6,
            cursor="hand2", command=self._on_guardar
        ).pack(side=tk.RIGHT)

    def _on_guardar(self):
        nom = self.ent_nombre.get().strip()
        car = self.cmb_carrera.get().strip()
        if not nom:
            messagebox.showerror("Campo Requerido", "El nombre completo no puede estar vacío.", parent=self)
            return
        self.nuevo_nombre = nom
        self.nueva_carrera = car
        self.confirmado = True
        self.destroy()


class CrearUsuarioDialog(tk.Toplevel):
    """
    Diálogo modal para el alta de nuevos usuarios y roles en el sistema (RBAC).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.confirmado = False
        self.datos = {}

        self.title("ITSX - Registrar Nuevo Usuario del Sistema")
        self.geometry("460x420")
        self.resizable(False, False)

        self.COLOR_BG = "#0B1120"
        self.COLOR_PANEL = "#151F32"
        self.COLOR_CARD = "#1E293B"
        self.COLOR_GOLD_ITSX = "#E5A823"
        self.COLOR_GREEN = "#10B981"

        self.configure(bg=self.COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            pw, ph, px, py = parent.winfo_width(), parent.winfo_height(), parent.winfo_x(), parent.winfo_y()
        except Exception:
            pw, ph, px, py = 1200, 800, 100, 100
        w, h = 460, 420
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main = tk.Frame(self, bg=self.COLOR_BG, padx=24, pady=18)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main, text="👤  ALTA DE USUARIO / ROL INSTITUCIONAL",
            font=("Helvetica", 11, "bold"), fg=self.COLOR_GOLD_ITSX, bg=self.COLOR_BG
        ).pack(anchor=tk.W, pady=(0, 12))

        card = tk.Frame(main, bg=self.COLOR_PANEL, bd=1, relief=tk.SOLID, padx=16, pady=14)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        tk.Label(card, text="Nombre Completo:", font=("Helvetica", 9, "bold"), fg="#ffffff", bg=self.COLOR_PANEL).pack(anchor=tk.W)
        self.ent_nombre = tk.Entry(card, font=("Helvetica", 10), bg=self.COLOR_CARD, fg="#ffffff", insertbackground="#fff", bd=5, relief=tk.FLAT)
        self.ent_nombre.pack(fill=tk.X, pady=(2, 8))

        tk.Label(card, text="Nombre de Usuario (Login):", font=("Helvetica", 9, "bold"), fg="#ffffff", bg=self.COLOR_PANEL).pack(anchor=tk.W)
        self.ent_username = tk.Entry(card, font=("Helvetica", 10), bg=self.COLOR_CARD, fg="#ffffff", insertbackground="#fff", bd=5, relief=tk.FLAT)
        self.ent_username.pack(fill=tk.X, pady=(2, 8))

        tk.Label(card, text="Contraseña:", font=("Helvetica", 9, "bold"), fg="#ffffff", bg=self.COLOR_PANEL).pack(anchor=tk.W)
        self.ent_pass = tk.Entry(card, font=("Helvetica", 10), bg=self.COLOR_CARD, fg="#ffffff", insertbackground="#fff", bd=5, relief=tk.FLAT, show="•")
        self.ent_pass.pack(fill=tk.X, pady=(2, 8))

        tk.Label(card, text="Rol del Usuario:", font=("Helvetica", 9, "bold"), fg="#ffffff", bg=self.COLOR_PANEL).pack(anchor=tk.W)
        self.cmb_rol = ttk.Combobox(card, values=["operador", "administrador"], font=("Helvetica", 10), state="readonly")
        self.cmb_rol.pack(fill=tk.X, pady=(2, 2))
        self.cmb_rol.set("operador")

        btn_box = tk.Frame(main, bg=self.COLOR_BG)
        btn_box.pack(fill=tk.X)

        tk.Button(
            btn_box, text="Cancelar", font=("Helvetica", 10), bg="#475569", fg="#ffffff",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2", command=self.destroy
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_box, text="Continuar con Autorización ➡️", font=("Helvetica", 10, "bold"),
            bg=self.COLOR_GREEN, fg="#ffffff", relief=tk.FLAT, padx=16, pady=6,
            cursor="hand2", command=self._on_guardar
        ).pack(side=tk.RIGHT)

    def _on_guardar(self):
        nom = self.ent_nombre.get().strip()
        usr = self.ent_username.get().strip()
        pwd = self.ent_pass.get()
        rol = self.cmb_rol.get().strip()

        if not nom or not usr or not pwd:
            messagebox.showerror("Campos Requeridos", "Todos los campos son obligatorios.", parent=self)
            return

        self.datos = {"nombre": nom, "username": usr, "password": pwd, "rol": rol}
        self.confirmado = True
        self.destroy()
