"""
Módulo de Validación de Matrículas y Claves Institucionales del ITSX.
Sprint 3 (U3P3) - Responsabilidad: Darian.

Regla definida por el equipo:
El campo de alumno solo debe aceptar matrículas del ITSX desde la primera generación hasta la actual (267O):
- Formato de alumno: AA7O##### (9 caracteres exactos):
  * 2 dígitos de año (AA) entre ANIO_INICIO_ITSX (07) y ANIO_ACTUAL_ITSX (26).
  * 1 dígito 7 (clave ITSX).
  * Letra 'O' (se tolera dígito '0' en su lugar por digitación humana).
  * 5 dígitos numéricos (#####).
  Ejemplos válidos: 237O00728, 267O00123, 237000728.
- Se rechazan: vacío, caracteres especiales (23#..., $ % & / ? ! * =),
  longitud distinta de 9 para alumnos, letras donde van dígitos, y generaciones futuras (277O...) o inexistentes (< 07).
- Se mantienen aparte los folios INV-... (invitados) y las claves DOC-/ADM- (docentes/administrativos).
"""

import re
from typing import Tuple

ANIO_INICIO_ITSX = 7   # Primera generación considerada (2007)
ANIO_ACTUAL_ITSX = 26  # Generación actual (2026: 267O)


def validar_matricula_itsx(matricula: str, solo_alumno: bool = False) -> Tuple[bool, str]:
    """
    Valida la sintaxis y rango de una matrícula o número de control institucional del ITSX.
    
    Args:
        matricula: Texto ingresado como número de control o matrícula.
        solo_alumno: Si es True, no permite folios INV- ni DOC-/ADM-.
        
    Retorna:
        Tuple[bool, str]: (es_valida, mensaje_o_motivo)
    """
    if not matricula or not isinstance(matricula, str):
        return False, "La matrícula o número de control no puede estar vacía."

    mat = matricula.strip().upper()

    if not mat:
        return False, "La matrícula o número de control no puede estar vacía."

    # Rechazar caracteres especiales inválidos (#, $, %, &, /, ?, !, *, =, etc.)
    caracteres_invalidos = re.findall(r"[^A-Z0-9\-_]", mat)
    if caracteres_invalidos:
        simbolos_unicos = "".join(sorted(set(caracteres_invalidos)))
        return False, (
            f"La matrícula '{mat}' contiene caracteres inválidos: '{simbolos_unicos}'. "
            "Solo se permiten caracteres alfanuméricos y guiones institucionales."
        )

    # 1. Folio de invitados (INV-...)
    if mat.startswith("INV-"):
        if solo_alumno:
            return False, f"El folio '{mat}' corresponde a un invitado y no a una matrícula de alumno."
        if len(mat) < 8:
            return False, "El formato de folio de invitado debe ser tipo 'INV-YYYYMMDD-XXXX'."
        return True, "Folio de invitado válido."

    # 2. Claves de Personal Docente / Administrativo (DOC-..., ADM-...)
    if mat.startswith("DOC-") or mat.startswith("ADM-"):
        if solo_alumno:
            return False, f"La clave '{mat}' corresponde a personal docente/administrativo y no a un alumno."
        if len(mat) < 5:
            return False, f"La clave de nómina '{mat}' es demasiado corta."
        return True, "Clave institucional de docente/administrativo válida."

    # 3. Matrícula de Alumno ITSX (Formato estricto AA7O##### / AA70#####)
    if len(mat) != 9:
        return False, (
            f"La matrícula de alumno '{mat}' debe tener exactamente 9 caracteres "
            f"(formato AA7O#####, ej. 237O00728). Longitud actual: {len(mat)}."
        )

    # Verificar estructura AA7[O|0]#####
    # Dos dígitos de año
    if not (mat[0].isdigit() and mat[1].isdigit()):
        return False, f"Los primeros dos caracteres de la matrícula '{mat}' deben ser el año de generación (dígitos numéricos)."

    anio = int(mat[0:2])
    if anio < ANIO_INICIO_ITSX or anio > ANIO_ACTUAL_ITSX:
        return False, (
            f"La generación '{anio:02d}' en la matrícula '{mat}' es inválida. "
            f"El rango permitido para alumnos ITSX va de la generación {ANIO_INICIO_ITSX:02d} a la {ANIO_ACTUAL_ITSX:02d} (actual 267O)."
        )

    # Tercer carácter debe ser '7'
    if mat[2] != "7":
        return False, f"El tercer carácter de la matrícula escolar '{mat}' debe ser '7' (código institucional ITSX)."

    # Cuarto carácter debe ser 'O' o '0'
    if mat[3] not in ("O", "0"):
        return False, f"El cuarto carácter de la matrícula '{mat}' debe ser 'O' (o tolerado '0'). Carácter encontrado: '{mat[3]}'."

    # Los últimos 5 caracteres deben ser dígitos
    consecutivo = mat[4:]
    if not consecutivo.isdigit() or len(consecutivo) != 5:
        return False, f"Los últimos 5 caracteres de la matrícula '{mat}' deben ser exclusivamente dígitos numéricos (encontrado: '{consecutivo}')."

    return True, "Matrícula escolar del ITSX válida."
