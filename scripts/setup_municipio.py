#!/usr/bin/env python3
"""
Setup script for a new municipality.

Designed to be run BY an LLM during onboarding. The LLM researches the
municipality via web search, then calls this script to generate local
config files (places, institutions, scraping hints) that customize the
pipeline for that canton.

Usage (LLM-guided flow):
  1. python setup_municipio.py --municipio "Atenas" --provincia "Alajuela" --guide
     → Prints research prompts for the LLM
  2. LLM does web research, then:
     python setup_municipio.py --municipio "Atenas" --lugares-json '{"lugares": [...]}'
     → Generates lugares_local.json

Usage (manual):
  python setup_municipio.py --municipio "Atenas" --output ./config
"""

import argparse
import json
import os
import sys
import re
import unicodedata
from typing import Dict, List, Optional


# ── Output filenames ─────────────────────────────────────────────────────

LUGARES_FILE = "lugares_local.json"
INSTITUCIONES_FILE = "instituciones_local.json"
SCRAPING_FILE = "scraping_hints.json"


# ── Guided research prompts ───────────────────────────────────────────────

GUIDE_TEMPLATE = """
=== GUIA DE INVESTIGACION PARA {municipio}, {provincia} ===

Para configurar el pipeline para este canton, investiga lo siguiente:

1. DISTRITOS Y CENTROS POBLADOS
   Buscar: "{municipio} distritos" o Wikipedia "{municipio} (cantón)"
   Extraer: lista de todos los distritos y centros poblados principales.

2. LUGARES GEOGRAFICOS LOCALES
   Buscar: "rios {municipio}", "cerros {municipio}", "playas {municipio}"
   Extraer: rios, cerros, playas, volcanes, parques nacionales, areas protegidas.

3. ASADAS Y COMITES LOCALES
   Buscar: "ASADAS {municipio}", "comites {municipio}"
   Extraer: nombres de ASADAS, comites cantonales, asociaciones de desarrollo.

4. SITIO WEB MUNICIPAL
   Buscar: "municipalidad de {municipio} actas concejo"
   Extraer: URL base del sitio, paths de secciones de actas, selectores CSS.

5. INSTITUCIONES LOCALES UNICAS
   Buscar: "hospital {municipio}", "colegio {municipio}", "programas municipales"
   Extraer: instituciones que solo existen en este canton.

CUANDO TENGAS LOS DATOS, ejecuta:
  python setup_municipio.py --municipio "{municipio}" \\
    --lugares-json '<JSON>' \\
    --instituciones-json '<JSON>' \\
    --scraping-json '<JSON>' \\
    --output ./config

Donde <JSON> es un string JSON con los datos investigados.
Usa --dry-run para validar sin escribir archivos.

=== FORMATOS ESPERADOS ===

--lugares-json:
  {"lugares": ["Distrito Central", "Nombre Rio", "Cerro X", "Playa Y"]}

--instituciones-json:
  {"instituciones": {"ASADA X": "Agua Potable, AyA y ASADAS", "Comite Y": "..."}}

--scraping-json:
  {"url_base": "https://municipalidad-ejemplo.go.cr",
   "secciones": {"concejo": "/actas-concejo", "comisiones": "/actas-comisiones"},
   "selectores": {"link": "a.fileLink", "pdf": "a[href$=.pdf]"}}
"""


# ── Validation ────────────────────────────────────────────────────────────

def validate_lugares(data: Dict) -> List[str]:
    """Validate lugares_local data."""
    errors = []
    if 'lugares' not in data:
        errors.append("falta clave 'lugares'")
    elif not isinstance(data['lugares'], list):
        errors.append("'lugares' debe ser una lista")
    elif not data['lugares']:
        errors.append("'lugares' esta vacia")
    else:
        for i, l in enumerate(data['lugares']):
            if not isinstance(l, str) or not l.strip():
                errors.append(f"lugar[{i}] no es un string valido")
    return errors


def validate_instituciones(data: Dict) -> List[str]:
    """Validate instituciones_local data."""
    errors = []
    if 'instituciones' not in data:
        return []  # optional
    if not isinstance(data['instituciones'], dict):
        errors.append("'instituciones' debe ser un dict")
    return errors


def validate_scraping(data: Dict) -> List[str]:
    """Validate scraping_hints data."""
    errors = []
    if 'url_base' in data and not data['url_base'].startswith('http'):
        errors.append("url_base debe empezar con http:// o https://")
    if 'secciones' in data:
        if not isinstance(data['secciones'], dict):
            errors.append("'secciones' debe ser un dict")
        else:
            for name, path in data['secciones'].items():
                if not isinstance(path, str):
                    errors.append(f"seccion '{name}' debe ser string")
    return errors


def save_json(data: Dict, filepath: str, dry_run: bool = False) -> str:
    """Save data to a JSON file."""
    if dry_run:
        status = "VALIDAR"
        result = json.dumps(data, ensure_ascii=False, indent=2)
        return f"[{status}] {filepath}:\n{result}"
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    if os.path.islink(filepath):
        raise OSError(f"Refusing to write to symlink: {filepath}")
    fd = os.open(filepath, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        try:
            os.unlink(filepath)
        except OSError:
            pass
        raise
    return f"  -> Creado: {filepath}"


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Setup de municipio para Pipeline de Actas"
    )
    parser.add_argument('--municipio', required=True, help='Nombre del canton')
    parser.add_argument('--provincia', default='', help='Provincia (opcional)')
    parser.add_argument('--output', default='./config',
                        help='Directorio de salida (default: ./config)')
    parser.add_argument('--guide', action='store_true',
                        help='Mostrar guia de investigacion para el LLM')
    parser.add_argument('--lugares-json', type=str, default=None,
                        help='JSON con lugares locales')
    parser.add_argument('--instituciones-json', type=str, default=None,
                        help='JSON con instituciones locales')
    parser.add_argument('--scraping-json', type=str, default=None,
                        help='JSON con hints de scraping')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validar sin escribir archivos')

    args = parser.parse_args()

    # ── Guided mode ───────────────────────────────────────────────────
    if args.guide:
        print(GUIDE_TEMPLATE.format(
            municipio=args.municipio,
            provincia=args.provincia or '(provincia desconocida)'
        ))
        return

    # ── Data mode ─────────────────────────────────────────────────────
    output_dir = args.output
    results = []
    has_errors = False
    raw = unicodedata.normalize('NFKD', args.municipio).encode('ascii', 'ignore').decode('ascii')
    basename = re.sub(r'[^\w\-]+', '_', raw.lower()).strip('_')

    # Process lugares
    if args.lugares_json:
        try:
            data = json.loads(args.lugares_json)
        except json.JSONDecodeError as e:
            print(f"Error: lugares-json no es JSON valido: {e}")
            sys.exit(1)
        errors = validate_lugares(data)
        if errors:
            print(f"Error en lugares-json:")
            for e in errors:
                print(f"  - {e}")
            has_errors = True
        else:
            filepath = os.path.join(output_dir, f"{basename}_{LUGARES_FILE}")
            result = save_json(data, filepath, args.dry_run)
            results.append(result)
            print(f"Lugares: {len(data['lugares'])} lugares")

    # Process instituciones
    if args.instituciones_json:
        try:
            data = json.loads(args.instituciones_json)
        except json.JSONDecodeError as e:
            print(f"Error: instituciones-json no es JSON valido: {e}")
            sys.exit(1)
        errors = validate_instituciones(data)
        if errors:
            print(f"Error en instituciones-json:")
            for e in errors:
                print(f"  - {e}")
            has_errors = True
        else:
            filepath = os.path.join(output_dir, f"{basename}_{INSTITUCIONES_FILE}")
            result = save_json(data, filepath, args.dry_run)
            results.append(result)
            if 'instituciones' in data:
                print(f"Instituciones: {len(data['instituciones'])} instituciones")

    # Process scraping
    if args.scraping_json:
        try:
            data = json.loads(args.scraping_json)
        except json.JSONDecodeError as e:
            print(f"Error: scraping-json no es JSON valido: {e}")
            sys.exit(1)
        errors = validate_scraping(data)
        if errors:
            print(f"Error en scraping-json:")
            for e in errors:
                print(f"  - {e}")
            has_errors = True
        else:
            filepath = os.path.join(output_dir, f"{basename}_{SCRAPING_FILE}")
            result = save_json(data, filepath, args.dry_run)
            results.append(result)
            if 'url_base' in data:
                print(f"Scraping URL: {data['url_base']}")

    if has_errors:
        print("\nCorrige los errores e intenta de nuevo.")
        sys.exit(1)

    if not results:
        print("No se proporcionaron datos. Usa --guide para ver la guia de investigacion.")
        parser.print_help()
        return

    print("\n" + "=" * 50)
    if args.dry_run:
        print("  VALIDACION COMPLETADA (dry-run)")
    else:
        print(f"  MUNICIPIO CONFIGURADO: {args.municipio}")
    print("=" * 50)
    for r in results:
        print(r)
    print()
    print("Siguiente paso: ejecutar el bootstrap con los lugares locales:")
    print(f"  python scripts/bootstrap_hilos.py --actas-dir ... --lugares ./config/{basename}_{LUGARES_FILE}")


if __name__ == '__main__':
    main()
