"""
Módulo de Validación de Matrículas y Claves Institucionales del ITSX.
Sprint 3 (U3P3) - Responsabilidad: Darian.

Reglas institucionales:
1. Alumnos ITSX:
   - Formato tradicional de número de control: usualmente 8 a 10 caracteres alfanuméricos
     iniciando con año (ej. 237O00728, 237O01367, 197O00123, 207O...).
   - Caracteres permitidos: Letras [A-Z] y Dígitos [0-9].
2. Personal Docente / Administrativo:
   - Claves de nómina o control como DOC-123, ADM-456 o alfanumérico limpio.
3. Invitados / Proveedores:
   - Claves con prefijo INV- (ej. INV-20261019-1234).
4. Restricciones estrictas:
   - Rechazar entradas vacías.
   - Rechazar caracteres especiales inválidos como #, $, %, &, /, ?, !, *, =, etc.
   - Rechazar longitudes anormales (< 4 caracteres o > 30 caracteres).
"""

import re
from typing import Tuple


def validar_matricula_itsx(matricula: str) -> Tuple[bool, str]:
    """
    Valida la sintaxis y rango de una matrícula o número de control institucional.
    
    Retorna:
        Tuple[bool, str]: (es_valida, mensaje_o_motivo)
    """
    if not matricula or not isinstance(matricula, str):
        return False, "La matrícula o número de control no puede estar vacía."

    mat = matricula.strip().upper()

    if len(mat) < 4:
        return False, f"La matrícula '{mat}' es demasiado corta (mínimo 4 caracteres)."

    if len(mat) > 30:
        return False, f"La matrícula '{mat}' excede la longitud máxima permitida (30 caracteres)."

    # Rechazar caracteres especiales peligrosos o malformados (como 23#...)
    caracteres_invalidos = re.findall(r"[^A-Z0-9\-_]", mat)
    if caracteres_invalidos:
        simbolos_unicos = "".join(sorted(set(caracteres_invalidos)))
        return False, (
            f"La matrícula '{mat}' contiene caracteres inválidos: '{simbolos_unicos}'. "
            "Solo se permiten letras, números y guiones institucionales."
        )

    # Si es un folio de invitado
    if mat.startswith("INV-"):
        if len(mat) < 8:
            return False, "El formato de folio de invitado debe ser tipo 'INV-YYYYMMDD-XXXX'."
        return True, "Folio de invitado válido."

    # Si es clave de alumno tradicional (ej. 237O00526, 237000526, etc.)
    # Rechazar si solo contiene signos o no tiene ningún dígito
    if not any(c.isdigit() for c in mat):
        return False, f"La matrícula escolar '{mat}' debe contener al menos dígitos numéricos."

    return True, "Matrícula institucional válida."
