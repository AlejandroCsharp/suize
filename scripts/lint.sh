#!/usr/bin/env bash
# Comprobaciones de calidad: lint, formato, tipos y tests.
#
#   scripts/lint.sh          # solo comprueba (ideal para CI)
#   scripts/lint.sh --fix    # además aplica los arreglos automáticos de ruff
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    PYTHON="${ROOT}/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

FIX=0
case "${1:-}" in
    --fix) FIX=1 ;;
    "") ;;
    *) echo "uso: scripts/lint.sh [--fix]" >&2; exit 2 ;;
esac

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

if [[ "${FIX}" -eq 1 ]]; then
    step "ruff check --fix"
    "${PYTHON}" -m ruff check . --fix
    step "ruff format"
    "${PYTHON}" -m ruff format .
else
    step "ruff check"
    "${PYTHON}" -m ruff check .
    step "ruff format --check"
    "${PYTHON}" -m ruff format --check .
fi

step "mypy src"
"${PYTHON}" -m mypy src

step "pytest (con cobertura)"
# Mismo umbral que la CI, para enterarse aquí y no después del push.
"${PYTHON}" -m pytest -q --cov

printf '\n\033[1;32m✔ Todo en orden.\033[0m\n'
