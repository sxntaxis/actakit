#!/usr/bin/env python3
"""
Generate enrutamiento.yaml from bootstrap results.

Reads the bootstrap_summary.json produced by bootstrap_hilos.py and
produces a ready-to-use enrutamiento.yaml for the pipeline.

Usage:
  python generate_enrutamiento.py --input ./bootstrap/bootstrap_summary.json --output ./enrutamiento.yaml
"""

import argparse
import json
import os
import sys
from collections import OrderedDict

from entity_index import INSTITUTIONS, INSTITUTION_CATEGORY


YAML_HEADER = """# enrutamiento.yaml — Mapeo de señales a hilos
# Generado automaticamente por bootstrap. Editar manualmente para ajustar.
# Formato:
#   Hilo Name:
#     señales:
#       - palabra clave 1
#       - palabra clave 2
#     aliases:
#       - nombre alternativo
#     entidades:
#       - SIGLA

"""


def load_seed_taxonomy():
    """Import seed hilos from bootstrap_hilos without triggering main."""
    # Direct import would run CLI, so we define the seed inline
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bootstrap_hilos",
        os.path.join(os.path.dirname(__file__), "bootstrap_hilos.py")
    )
    mod = importlib.util.module_from_spec(spec)
    # Don't exec, just extract the dict through the file
    # Instead, we read the seed from the summary's hilo_distribution
    return None


def build_enrutamiento(summary, output_path, seed_mapping=None):
    """Build enrutamiento YAML from bootstrap summary."""
    lines = [YAML_HEADER]

    hilo_dist = summary.get('hilo_distribution', {})
    clusters = summary.get('clusters', [])
    top_entities = summary.get('top_entities', [])

    # Map from entity -> hilo suggestions from clusters
    cluster_entity_map = {}
    for cl in clusters:
        name = cl.get('suggested_name', '')
        for ent, _ in cl.get('top_entities', []):
            cluster_entity_map[ent] = name

    # Build entity-to-hilo reverse map from institutional knowledge
    entity_to_hilo = {}
    for sigla, hilo_name in INSTITUTION_CATEGORY.items():
        if hilo_name not in entity_to_hilo:
            entity_to_hilo[hilo_name] = []
        entity_to_hilo[hilo_name].append(sigla)

    # Write each hilo from the distribution
    written_hilos = set()

    for hilo_name in sorted(hilo_dist.keys()):
        _write_hilo_block(lines, hilo_name, entity_to_hilo, summary)
        written_hilos.add(hilo_name)

    # Write clusters as new hilos (if not already present)
    for cl in clusters:
        name = cl.get('suggested_name', '')
        if name and name not in written_hilos:
            _write_cluster_block(lines, cl, written_hilos)
            written_hilos.add(name)

    # Add known institutions not yet represented
    # (catch-all for institutions that didn't appear in the data)
    _add_missing_institutions(lines, written_hilos, entity_to_hilo)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"  -> Enrutamiento guardado: {output_path}")
    print(f"  -> {len(written_hilos)} hilos en total")

    return output_path


def _write_hilo_block(lines, hilo_name, entity_to_hilo, summary):
    """Write a hilo block based on known entity mappings."""
    lines.append(f"{hilo_name}:\n")
    lines.append("  señales:\n")

    entities = entity_to_hilo.get(hilo_name, [])
    for e in entities:
        full_name = INSTITUTIONS.get(e, '')
        lines.append(f"    - '{e}'\n")
        if full_name:
            lines.append(f"    - '{full_name}'\n")

    # Add some generic signal suggestions based on hilo name
    generic_signals = _generic_signals_for(hilo_name)
    for s in generic_signals:
        lines.append(f"    - '{s}'\n")

    if entities:
        lines.append("\n  entidades:\n")
        for e in entities:
            lines.append(f"    - '{e}'\n")

    lines.append("\n")


def _write_cluster_block(lines, cluster, written_hilos):
    """Write a new hilo block from a cluster analysis."""
    name = cluster.get('suggested_name', 'Cluster')
    # Avoid duplicate names
    base_name = name
    counter = 2
    while name in written_hilos:
        name = f"{base_name} ({counter})"
        counter += 1

    lines.append(f"{name}:\n")
    lines.append("  señales:\n")

    for ent, count in cluster.get('top_entities', []):
        lines.append(f"    - '{ent}'\n")

    lines.append("\n  entidades:\n")
    for ent, count in cluster.get('top_entities', []):
        lines.append(f"    - '{ent}'\n")

    lines.append("\n  # Generado de cluster por bootstrap\n")
    lines.append("\n")


def _add_missing_institutions(lines, written_hilos, entity_to_hilo):
    """Add hilos for institutions not yet in the enrutamiento."""
    for hilo_name in sorted(set(entity_to_hilo.values())):
        if hilo_name not in written_hilos:
            _write_hilo_block(lines, hilo_name, entity_to_hilo, {})
            written_hilos.add(hilo_name)


STOPWORDS = {
    'municipal', 'publica', 'publico', 'local', 'cantonal',
    'provincia', 'distrito', 'gobierno', 'consejo', 'regimen',
    'servicio', 'servicios', 'sistema', 'sedes', 'oficina',
    'direccion', 'gerencia', 'asunto', 'asuntos', 'tema', 'temas',
    'politica', 'politicas', 'ley', 'leyes', 'norma', 'normas',
    'articulo', 'articulos', 'capitulo', 'seccion', 'parte',
    'del', 'los', 'las', 'una', 'unos', 'para', 'con', 'por',
    'que', 'como', 'este', 'esta', 'estos', 'estas', 'ese',
    'esa', 'esos', 'esas', 'aquel', 'aquella', 'aquellos',
    'aquellas', 'su', 'sus', 'el', 'la', 'en', 'de', 'y', 'o',
}


def _generic_signals_for(hilo_name):
    """Generate generic signal suggestions from hilo name."""
    signals = []
    name_lower = hilo_name.lower()

    parts = name_lower.replace(',', '').replace(' y ', ' ').split()
    for p in parts:
        if len(p) >= 4 and p not in STOPWORDS and not p.isdigit():
            signals.append(p)

    return signals[:8]


def main():
    parser = argparse.ArgumentParser(
        description="Generar enrutamiento.yaml desde bootstrap summary"
    )
    parser.add_argument(
        '--input', required=True,
        help='Archivo bootstrap_summary.json'
    )
    parser.add_argument(
        '--output', default='./enrutamiento.yaml',
        help='Archivo de salida (default: ./enrutamiento.yaml)'
    )

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: {args.input} no existe.")
        sys.exit(1)

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: no se pudo leer {args.input}: {e}")
        sys.exit(1)

    build_enrutamiento(summary, args.output)


if __name__ == '__main__':
    main()
