#!/bin/bash
# ==============================================================================
# SISTEMA BIOMÉTRICO INSTITUCIONAL - CONTROL DE ACCESO (Taller de Investigación II)
# Script de inicio rápido: Lanza la Interfaz Gráfica (GUI) para Guardias de Seguridad
# ==============================================================================
set -e

# Cambiar al directorio del script
cd "$(dirname "$0")"

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Si se pasa el argumento --cli, abrir consola: ./iniciar.sh --cli
# De lo contrario, abrir la Interfaz Gráfica para el Guardia
python3 main.py "$@"
