"""
Módulo de Normalización y Filtros de Texto, Fechas y Horas.
Sprint 3 (U3P3) - Responsabilidad: Samantha.

Proporciona:
- Normalización de cadenas eliminando acentos/diacríticos y unificando a minúsculas.
- Coincidencia flexible de nombres multi-token en cualquier orden.
- Validación estricta de fechas (AAAA-MM-DD) y horas (HH:MM) reales.
- Validación de rangos cronológicos no invertidos.
"""

import unicodedata
from datetime import datetime, date, time
from typing import Tuple, Optional


def normalizar_texto(texto: str) -> str:
    """
    Normaliza una cadena de texto eliminando acentos, diacríticos y espacios sobrantes,
    convirtiéndola a minúsculas.
    
    Ejemplo:
        'Velázquez López Guadalupe' -> 'velazquez lopez guadalupe'
    """
    if not texto or not isinstance(texto, str):
        return ""
    # Descomponer caracteres acentuados (NFD / NFKD)
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin_tildes.lower().strip()


def coincide_nombre(query: str, texto_objetivo: str) -> bool:
    """
    Verifica si todos los tokens del query se encuentran presentes en el texto objetivo,
    sin importar el orden de las palabras (nombre primero o apellido primero)
    ni la presencia de acentos o mayúsculas.
    
    Ejemplo:
        coincide_nombre("velazquez guadalupe", "Velázquez López Guadalupe") -> True
        coincide_nombre("juan trujillo", "Trujillo Trujillo Juan Pablo") -> True
    """
    if not query:
        return True
    if not texto_objetivo:
        return False

    q_norm = normalizar_texto(query)
    obj_norm = normalizar_texto(texto_objetivo)

    tokens = [t for t in q_norm.split() if t]
    if not tokens:
        return True

    return all(tok in obj_norm for tok in tokens)


def validar_fecha(fecha_str: str) -> Tuple[bool, Optional[date], str]:
    """
    Valida sintaxis y existencia real de una fecha en formato AAAA-MM-DD.
    
    Rechaza fechas inexistentes como 2026-13-45 o 2026-02-30.
    
    Retorna:
        Tuple[bool, Optional[date], str]: (es_valida, objeto_date, mensaje)
    """
    if not fecha_str or not isinstance(fecha_str, str):
        return False, None, "La fecha no puede estar vacía."

    f_clean = fecha_str.strip()
    try:
        dt = datetime.strptime(f_clean, "%Y-%m-%d").date()
        return True, dt, "Fecha válida."
    except ValueError:
        return False, None, f"La fecha '{f_clean}' es inexistente o tiene un formato incorrecto (use AAAA-MM-DD)."


def validar_hora(hora_str: str) -> Tuple[bool, Optional[time], str]:
    """
    Valida sintaxis y existencia real de una hora en formato HH:MM (24 horas).
    
    Rechaza horas inexistentes como 25:99 o 12:78.
    
    Retorna:
        Tuple[bool, Optional[time], str]: (es_valida, objeto_time, mensaje)
    """
    if not hora_str or not isinstance(hora_str, str):
        return False, None, "La hora no puede estar vacía."

    h_clean = hora_str.strip()
    try:
        t = datetime.strptime(h_clean, "%H:%M").time()
        return True, t, "Hora válida."
    except ValueError:
        return False, None, f"La hora '{h_clean}' es inexistente o tiene un formato incorrecto (use HH:MM en formato 24 horas)."


def validar_rango_fechas(f_ini_str: str, f_fin_str: str) -> Tuple[bool, str]:
    """
    Valida que ambas fechas sean válidas y que la fecha inicial no sea posterior a la final.
    """
    ok_ini, d_ini, msg_ini = validar_fecha(f_ini_str)
    if not ok_ini:
        return False, f"Fecha Inicial inválida: {msg_ini}"

    ok_fin, d_fin, msg_fin = validar_fecha(f_fin_str)
    if not ok_fin:
        return False, f"Fecha Final inválida: {msg_fin}"

    if d_ini > d_fin:
        return False, f"Rango invertido: La Fecha Inicial ({f_ini_str}) no puede ser posterior a la Fecha Final ({f_fin_str})."

    return True, "Rango de fechas válido."


def validar_rango_horas(h_ini_str: str, h_fin_str: str) -> Tuple[bool, str]:
    """
    Valida que ambas horas sean válidas y que la hora inicial no sea posterior a la final.
    """
    ok_ini, t_ini, msg_ini = validar_hora(h_ini_str)
    if not ok_ini:
        return False, f"Hora Inicial inválida: {msg_ini}"

    ok_fin, t_fin, msg_fin = validar_hora(h_fin_str)
    if not ok_fin:
        return False, f"Hora Final inválida: {msg_fin}"

    if t_ini > t_fin:
        return False, f"Rango invertido: La Hora Inicial ({h_ini_str}) no puede ser posterior a la Hora Final ({h_fin_str})."

    return True, "Rango de horas válido."
