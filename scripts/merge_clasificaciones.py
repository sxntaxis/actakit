#!/usr/bin/env python3
"""Merge batch classifications into _clasificaciones.json with validation."""

import json, os, sys
from collections import Counter
from pathlib import Path

VALID_CATEGORIES = [
    "Corresp", "Evento", "Reconoc", "Infraest", "Ambiente",
    "Deporte", "Educación", "Salud", "Gestión", "Seguridad",
]

TYPO_FIX = {"Gestion": "Gestión", "gestion": "Gestión"}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fusiona clasificaciones por lote")
    parser.add_argument("--herramientas-dir", required=True, help="Directorio con los JSONs")
    parser.add_argument("--anuncios", default="_anuncios_data.json", help="Nombre del JSON de anuncios")
    parser.add_argument("--output", default="_clasificaciones.json", help="Nombre del JSON de salida")
    parser.add_argument("--valid", nargs="*", default=VALID_CATEGORIES, help="Categorías válidas")
    args = parser.parse_args()

    her_dir = Path(args.herramientas_dir)
    anuncios_file = her_dir / args.anuncios
    output_file = her_dir / args.output
    valid_set = set(args.valid)

    if not anuncios_file.exists():
        print(f"Error: no existe {anuncios_file}")
        sys.exit(1)

    try:
        with open(anuncios_file, encoding='utf-8') as f:
            all_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: no se pudo leer {anuncios_file}: {e}")
        sys.exit(1)
    expected_ids = {a['id'] for a in all_data}

    batch_results = {}
    result_files = sorted([f for f in os.listdir(her_dir)
                          if f.startswith('_batch_result_')])
    if result_files:
        for fname in result_files:
            try:
                with open(os.path.join(her_dir, fname), encoding='utf-8') as f:
                    data = json.load(f)
                    batch_results.update(data)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Error: no se pudo leer {fname}: {e}")
                continue
        print(f"Cargados {len(batch_results)} de {len(result_files)} archivos")
    else:
        print("WARNING: No se encontraron archivos _batch_result_")

    normalized = {}
    invalid_entries = {}
    for k, v in batch_results.items():
        v_clean = str(v).strip()
        v_clean = TYPO_FIX.get(v_clean, v_clean)
        if v_clean not in valid_set:
            invalid_entries[k] = v_clean
            print(f"WARNING: Categoría inválida '{v_clean}' para {k}")
            continue
        normalized[k] = v_clean

    classified_ids = set(normalized.keys())
    unclassified = expected_ids - classified_ids
    extra = classified_ids - expected_ids

    print(f"\nEsperados: {len(expected_ids)}")
    print(f"Clasificados: {len(classified_ids)}")
    print(f"No clasificados: {len(unclassified)}")
    print(f"Sobrantes: {len(extra)}")

    if invalid_entries:
        print(f"\nEntradas con categoría inválida ({len(invalid_entries)}):")
        for uid, cat in sorted(invalid_entries.items())[:10]:
            print(f"  {uid}: '{cat}'")

    if unclassified:
        print(f"\nIDs no clasificados ({len(unclassified)}):")
        for uid in sorted(unclassified)[:10]:
            print(f"  {uid}")

    dist = Counter(normalized.values())
    print(f"\n=== DISTRIBUCIÓN ===")
    for cat in sorted(dist, key=lambda c: -dist[c]):
        print(f"  {cat:12s} {dist[cat]:3d} ({dist[cat]/len(normalized)*100:4.1f}%)")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado: {output_file} ({len(normalized)} clasificaciones)")


if __name__ == '__main__':
    main()
