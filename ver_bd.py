#!/usr/bin/env python3
"""
Script de Utilidad para Visualizar la Base de Datos SQLite en Terminal.
SCAB - Instituto Tecnológico Superior de Xalapa (ITSX).
"""

import sys
import sqlite3
from tabulate import tabulate

DB_FILE = "biometric_templates.db"


def conectar():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Error al conectar con {DB_FILE}: {e}")
        sys.exit(1)


def ver_usuarios():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, rol, nombre_completo, activo, created_at FROM usuarios ORDER BY id")
    rows = cursor.fetchall()
    conn.close()

    print("\n" + "═" * 80)
    print("                    USUARIOS DEL SISTEMA (RBAC)")
    print("═" * 80)
    if not rows:
        print("  (No hay usuarios registrados)")
        return
    data = [[r["id"], r["username"], r["rol"].upper(), r["nombre_completo"], "SÍ" if r["activo"] else "NO", r["created_at"]] for r in rows]
    print(tabulate(data, headers=["ID", "Usuario", "Rol", "Nombre Completo", "Activo", "Fecha Creación"], tablefmt="rounded_grid"))


def ver_estudiantes_padron():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, matricula, nombre, carrera, activo, created_at, length(embedding_vector) as tam_bytes FROM estudiantes ORDER BY id")
    rows = cursor.fetchall()
    conn.close()

    print("\n" + "═" * 80)
    print("         PADRÓN DE ESTUDIANTES ENROLADOS (VECTORES DE 1024 BYTES)")
    print("═" * 80)
    if not rows:
        print("  (No hay estudiantes enrolados en el padrón actualmente)")
        return
    data = [[r["id"], r["matricula"], r["nombre"], r["carrera"], f"{r['tam_bytes']} B (cifrado)", "ACTIVO" if r["activo"] else "INACTIVO", r["created_at"]] for r in rows]
    print(tabulate(data, headers=["ID", "Matrícula", "Nombre", "Carrera / Detalle", "Template Biométrico", "Estatus", "Fecha"], tablefmt="rounded_grid"))


def ver_base_escolar():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, numero_control, nombre_completo, tipo_usuario, carrera_o_departamento, semestre, estatus FROM simulacion_escolar_itsx ORDER BY tipo_usuario, nombre_completo")
    rows = cursor.fetchall()
    conn.close()

    print("\n" + "═" * 95)
    print("            BASE DE DATOS ESCOLAR SIMULADA DEL ITSX (CONTROL ESCOLAR)")
    print("═" * 95)
    if not rows:
        print("  (Tabla escolar vacía)")
        return
    data = [[r["id"], r["numero_control"], r["nombre_completo"], r["tipo_usuario"], r["carrera_o_departamento"], r["semestre"], r["estatus"]] for r in rows]
    print(tabulate(data, headers=["ID", "N° Control", "Nombre Completo", "Tipo", "Carrera / Departamento", "Semestre", "Estatus"], tablefmt="rounded_grid"))


def ver_accesos(limite=20):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, matricula, nombre, distancia, estado,
               tiempo_acceso_segundos, tipo_usuario, condicion_luz
        FROM registro_accesos
        ORDER BY id DESC LIMIT ?
    """, (limite,))
    rows = cursor.fetchall()
    conn.close()

    print("\n" + "═" * 105)
    print(f"            ÚLTIMOS {limite} REGISTROS DE AUDITORÍA Y ACCESO EN TIEMPO REAL")
    print("═" * 105)
    if not rows:
        print("  (No hay eventos de acceso registrados en la bitácora)")
        return
    data = []
    for r in rows:
        est = "✓ " + r["estado"] if r["estado"] in ("PERMITIDO", "AUTORIZADO") else "✗ " + r["estado"]
        dist = f"{r['distancia']:.4f}" if r["distancia"] is not None else "---"
        t = f"{r['tiempo_acceso_segundos']:.3f} s" if r["tiempo_acceso_segundos"] else "---"
        data.append([
            r["id"], r["timestamp"], r["matricula"] or "---", r["nombre"] or "Desconocido",
            dist, est, t, r["tipo_usuario"], r["condicion_luz"]
        ])
    headers = ["ID", "Fecha / Hora", "Matrícula", "Nombre", "Dist. L2", "Estado", "Latencia", "Tipo", "Iluminación"]
    print(tabulate(data, headers=headers, tablefmt="rounded_grid"))


def ver_consentimientos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, matricula, tipo_usuario, firma_token, consentimiento_otorgado, fecha_firma, observaciones FROM consentimientos ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    conn.close()

    print("\n" + "═" * 90)
    print("                 CONSENTIMIENTOS INFORMADOS LFPDPPP (PB-08)")
    print("═" * 90)
    if not rows:
        print("  (No hay consentimientos registrados)")
        return
    data = []
    for r in rows:
        otorg = "✓ OTORGADO" if r["consentimiento_otorgado"] else "✗ DENEGADO"
        tok = r["firma_token"][:16] + "..." if r["firma_token"] else "---"
        data.append([r["id"], r["matricula"], r["tipo_usuario"], tok, otorg, r["fecha_firma"], r["observaciones"] or "---"])
    print(tabulate(data, headers=["ID", "Matrícula", "Tipo", "Token SHA-256", "Consentimiento", "Fecha", "Observaciones"], tablefmt="rounded_grid"))


def main():
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    if arg in ("--usuarios", "-u"):
        ver_usuarios()
    elif arg in ("--padron", "-p"):
        ver_estudiantes_padron()
    elif arg in ("--escolar", "-e"):
        ver_base_escolar()
    elif arg in ("--accesos", "-a"):
        ver_accesos()
    elif arg in ("--consentimientos", "-c"):
        ver_consentimientos()
    else:
        # Mostrar resumen completo por defecto
        ver_usuarios()
        ver_estudiantes_padron()
        ver_base_escolar()
        ver_accesos(10)
        ver_consentimientos()
        print("\n💡 TIP: Puedes ver tablas específicas usando:")
        print("   python3 ver_bd.py -u   (Solo usuarios)")
        print("   python3 ver_bd.py -p   (Solo padrón biométrico)")
        print("   python3 ver_bd.py -e   (Solo base escolar simulada)")
        print("   python3 ver_bd.py -a   (Solo bitácora de accesos)")
        print("   python3 ver_bd.py -c   (Solo consentimientos LFPDPPP)\n")


if __name__ == "__main__":
    main()
