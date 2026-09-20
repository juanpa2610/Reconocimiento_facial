#!/usr/bin/env python3
"""
SISTEMA DE CONTROL DE ACCESO FACIAL BASADO EN EMBEDDINGS BIOMÉTRICOS.
Taller de Investigación II.

Este sistema implementa reconocimiento facial prescindiendo del almacenamiento de fotografías,
guardando exclusivamente representaciones numéricas de 128 flotantes (templates)
en cumplimiento con el principio de minimización de datos y normativas de privacidad (LFPDPPP).
"""

import sys
import os
from pathlib import Path

# Auto-detección del entorno virtual: Si el usuario ejecuta con 'python3 main.py'
# sin haber activado el venv, relanzamos automáticamente el proceso usando el intérprete de .venv
if sys.prefix == sys.base_prefix:
    _venv_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if _venv_python.exists():
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

try:
    import cv2
    import config
    from src.db.database import Database
    from src.modules import (
        registrar_estudiante_en_vivo,
        iniciar_control_acceso,
        listar_estudiantes,
        consultar_historial_accesos,
        exportar_accesos_csv,
        eliminar_estudiante,
        generar_informe_metodologico
    )
    from src.gui import iniciar_gui
except ImportError as e:
    print(f"\n[-] Error al importar dependencias: {e}")
    print("    Por favor activa el entorno virtual ejecutando:")
    print("        source .venv/bin/activate")
    print("        python3 main.py\n")
    sys.exit(1)


def probar_camara():
    """Prueba rápida del dispositivo de captura de video."""
    print(f"\n[*] Probando fuente de video: {config.VIDEO_SOURCE} ...")
    cap = cv2.VideoCapture(config.VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"[-] ERROR: No se puede acceder a la cámara en '{config.VIDEO_SOURCE}'.")
        print("    Asegúrate de que la cámara esté conectada o ajusta VIDEO_SOURCE en .env")
        return

    print("[+] Cámara detectada exitosamente.")
    print("[*] Abriendo ventana de prueba. Presione 'Q' para cerrarla...")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[-] No se pudo leer el cuadro de la cámara.")
            break
        cv2.putText(
            frame, "PRUEBA DE CAMARA - Presione 'Q' para salir", (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
        )
        cv2.imshow("Test de Video - Proyecto Biometrico", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[+] Prueba de cámara finalizada.\n")


def mostrar_banner():
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║       SISTEMA BIOMÉTRICO BASADO EN EMBEDDINGS (SIN IMÁGENES)         ║
║                    Taller de Investigación II                         ║
║         Privacidad por Diseño (LFPDPPP) - Deep Metric Learning        ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)


def menu_principal():
    # Inicializar Base de Datos al arrancar
    db = Database()
    db.init_db()

    while True:
        mostrar_banner()
        print(f"  [Motor BD: {config.DB_ENGINE.upper()} | Umbral L2: {config.FACE_DISTANCE_THRESHOLD} | Fuente Video: {config.VIDEO_SOURCE}]")
        print("\n  Seleccione una opción:")
        print("   1. [Paso A] Registrar nuevo estudiante (Biometría Primero)")
        print("   2. [Paso B] Iniciar Reconocimiento Facial en Vivo (Control de Acceso)")
        print("   3. Abrir Interfaz Gráfica para Guardias (GUI de Escritorio)")
        print("   4. Listar estudiantes registrados (Inspección de Templates)")
        print("   5. Consultar bitácora de accesos y distancias euclidianas")
        print("   6. Exportar bitácora de accesos a CSV")
        print("   7. Eliminar estudiante del sistema")
        print("   8. Ver informe técnico de investigación (Almacenamiento / LFPDPPP)")
        print("   9. Probar conexión con cámara de video")
        print("   0. Salir")
        print("-" * 75)

        opcion = input("  Ingrese opción [0-9]: ").strip()

        if opcion == "1":
            registrar_estudiante_en_vivo()
        elif opcion == "2":
            iniciar_control_acceso()
        elif opcion == "3":
            print("\n[*] Iniciando Interfaz Gráfica para Guardias (GUI)...")
            try:
                iniciar_gui()
            except Exception as e:
                print(f"[-] No se pudo abrir la GUI: {e}")
        elif opcion == "4":
            listar_estudiantes()
        elif opcion == "5":
            consultar_historial_accesos()
        elif opcion == "6":
            exportar_accesos_csv()
        elif opcion == "7":
            eliminar_estudiante()
        elif opcion == "8":
            generar_informe_metodologico()
        elif opcion == "9":
            probar_camara()
        elif opcion == "0":
            print("\n[*] Saliendo del sistema. ¡Éxito en tu investigación!\n")
            sys.exit(0)
        else:
            print("\n[-] Opción no válida. Por favor elija un número del 0 al 9.")

        input("\nPresione [ENTER] para continuar...")


if __name__ == "__main__":
    # Si se pasa el argumento --cli, abrir consola directamente
    if "--cli" in sys.argv:
        menu_principal()
    else:
        # Intentar abrir la Interfaz Gráfica por defecto para máxima comodidad
        try:
            # Comprobar si hay servidor gráfico (DISPLAY o Windows)
            if os.environ.get("DISPLAY") or sys.platform.startswith("win"):
                print("[*] Iniciando Interfaz Gráfica (GUI) para Guardias de Seguridad...")
                iniciar_gui()
            else:
                menu_principal()
        except Exception as e:
            print(f"[!] Entorno gráfico no disponible ({e}). Iniciando menú de consola...")
            menu_principal()
