#!/usr/bin/env bash
# Ejecuta Suize desde el código fuente, sin necesidad de instalarlo.
#
#   scripts/run.sh                      # menú interactivo
#   scripts/run.sh scan 127.0.0.1       # cualquier argumento se pasa tal cual
#   scripts/run.sh logs -p err --since 1h
#
# Si existe un archivo .env en la raíz del proyecto, sus variables SUIZE_* se
# exportan antes de arrancar (las variables ya definidas en el entorno ganan).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

if [[ -f "${ENV_FILE}" ]]; then
    while IFS= read -r line || [[ -n "${line}" ]]; do
        line="${line%$'\r'}"                                   # tolera .env con CRLF
        [[ -z "${line// /}" || "${line}" =~ ^[[:space:]]*# ]] && continue
        [[ "${line}" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || {
            echo "run.sh: línea ignorada en .env: ${line}" >&2
            continue
        }
        key="${BASH_REMATCH[2]}"
        value="${BASH_REMATCH[3]}"
        # Quita comillas envolventes simples o dobles.
        if [[ "${value}" =~ ^\"(.*)\"$ || "${value}" =~ ^\'(.*)\'$ ]]; then
            value="${BASH_REMATCH[1]}"
        fi
        # No pisa lo que el usuario ya exportó en su shell.
        if [[ -z "${!key+x}" ]]; then
            export "${key}=${value}"
        fi
    done < "${ENV_FILE}"
fi

# Prefiere el Python del entorno virtual del proyecto si existe.
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PYTHON="${ROOT}/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON}" -m suize "$@"
