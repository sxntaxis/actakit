#!/usr/bin/env bash
# =============================================================================
# Pipeline de Actas Municipales — Bootstrap de Hilos
# =============================================================================
# Orquestación completa: desde actas procesadas hasta enrutamiento.yaml.
#
# Uso:
#   bash scripts/run_bootstrap.sh                     # con valores por defecto
#   bash scripts/run_bootstrap.sh ./actas/procesadas
#
# Requisitos:
#   - Python 3.8+
#   - pip install pyyaml
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

ACTAS_DIR="${1:-"$REPO_DIR/actas/procesadas"}"
BOOTSTRAP_DIR="${2:-"$REPO_DIR/bootstrap"}"
ENRUTAMIENTO_OUT="${3:-"$REPO_DIR/skills/procesar-acta/config/ejemplo/enrutamiento.yaml"}"
LUGARES="${4:-""}"

# ── 1. Validar dependencias ───────────────────────────────────────────────

echo ""
echo "============================================================"
echo "  Pipeline Actas - Bootstrap de Hilos"
echo "============================================================"
echo ""

if ! python3 -c "import yaml" 2>/dev/null; then
    echo "PyYAML no encontrado. Instalando con hash verificado..."
    pip install --require-hashes -r "$REPO_DIR/requirements.txt" 2>/dev/null || \
    pip install pyyaml==6.0.1
fi

if [ ! -d "$ACTAS_DIR" ]; then
    echo "Error: No existe el directorio de actas: $ACTAS_DIR"
    echo ""
    echo "Uso: $0 [actas_dir] [output_dir] [enrutamiento_out]"
    echo ""
    echo "  actas_dir:         directorio con actas procesadas .md"
    echo "  output_dir:        directorio para salida de bootstrap (default: ./bootstrap)"
    echo "  enrutamiento_out:  ruta del enrutamiento generado"
    exit 1
fi

# ── 2. Ejecutar bootstrap ────────────────────────────────────────────────

echo "Paso 1: Extrayendo entidades y clasificando..."
LUGARES_ARG=()
if [ -n "$LUGARES" ]; then
    LUGARES_ARG=(--lugares "$LUGARES")
fi

python3 "$SCRIPT_DIR/bootstrap_hilos.py" \
    --actas-dir "$ACTAS_DIR" \
    --output "$BOOTSTRAP_DIR" \
    --min-shared 2 \
    --min-jaccard 0.15 \
    "${LUGARES_ARG[@]}"

if [ ! -f "$BOOTSTRAP_DIR/bootstrap_summary.json" ]; then
    echo "Error: No se generó bootstrap_summary.json"
    exit 1
fi

# ── 3. Generar enrutamiento ──────────────────────────────────────────────

echo ""
echo "Paso 2: Generando enrutamiento.yaml..."

mkdir -p "$(dirname "$ENRUTAMIENTO_OUT")"

python3 "$SCRIPT_DIR/generate_enrutamiento.py" \
    --input "$BOOTSTRAP_DIR/bootstrap_summary.json" \
    --output "$ENRUTAMIENTO_OUT"

# ── 4. Resumen ───────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo "  Bootstrap completado"
echo "============================================================"
echo ""
echo "  Reporte:     $BOOTSTRAP_DIR/bootstrap_report.md"
echo "  Resumen:     $BOOTSTRAP_DIR/bootstrap_summary.json"
echo "  Enrutamiento: $ENRUTAMIENTO_OUT"
echo ""
echo "Siguientes pasos:"
echo "  1. Revisá el reporte en $BOOTSTRAP_DIR/bootstrap_report.md"
echo "  2. Ajustá $ENRUTAMIENTO_OUT si es necesario"
echo "  3. Ejecutá la pipeline completa:"
echo "     bash scripts/scrape_actas.sh && \\"
echo "     bash scripts/pdftotext_actas.sh && \\"
echo "     bash scripts/procesar_actas.sh && \\"
echo "     python3 scripts/integrate_hilos.py"
echo ""
