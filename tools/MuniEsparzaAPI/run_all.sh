#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
  echo "Falta .env. Copie .env.example como .env y complete ESPARZA_API_KEY." >&2
  exit 1
fi

# Detect Python: prefer venv if present.
PYTHON="python"
if [[ -f .venv/bin/python ]]; then
  PYTHON=".venv/bin/python"
elif [[ -f venv/bin/python ]]; then
  PYTHON="venv/bin/python"
fi

echo "[1/3] Descargando catálogo..."
$PYTHON scripts/01_snapshot_catalog.py

echo "[2/3] Descargando datastreams y endpoints..."
$PYTHON scripts/02_download_datastreams.py

echo "[3/3] Construyendo inventario y reporte..."
$PYTHON scripts/03_build_inventory.py

echo ""
echo "✓ Completado. Archivos generados:"
echo "  data/raw/catalog/resources_unique.json"
echo "  data/raw/catalog/resources_raw_all_pages.json"
echo "  data/processed/download_manifest.json"
echo "  audit/inventory.csv"
echo "  audit/category_summary.csv"
echo "  audit/topic_summary.csv"
echo "  audit/audit_summary.json"
echo "  audit/API_DEEP_AUDIT_REPORT.md"
