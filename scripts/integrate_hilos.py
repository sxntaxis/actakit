#!/usr/bin/env python3
"""
Integrate episodes from processed actas into Hilo files in Base Cantonal.

Reads the pipeline config to determine:
  - Which Hilos exist and their block/category membership
  - Where actas and Hilo files live
  - Alias mappings for Hilo names

Usage:
    python integrate_hilos.py --config config.yaml
    python integrate_hilos.py --actas-dir PATH --hilos-dir PATH [--hilos-config FILE]
"""

import os
import re
import sys
import json
from collections import OrderedDict, defaultdict
from pathlib import Path

from entity_index import extract_entities, build_entity_frequency, entity_overlap


def load_config(config_path):
    """Load pipeline configuration from YAML or JSON."""
    import json as _json
    path = Path(config_path)
    if path.suffix in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError:
            print("Error: PyYAML required for .yaml config. Install: pip install pyyaml")
            sys.exit(1)
        with open(path) as f:
            return yaml.safe_load(f)
    elif path.suffix == '.json':
        with open(path) as f:
            return _json.load(f)
    else:
        print(f"Error: unsupported config format: {path.suffix}")
        sys.exit(1)


def build_official_hilos(config):
    """Build OrderedDict of hilo_name -> block_name from config."""
    hilos = OrderedDict()
    for bloque in config.get('hilos', {}).get('bloques', []):
        block_name = bloque['nombre']
        for hilo_name in bloque.get('hilos', []):
            hilos[hilo_name] = block_name
    return hilos


def build_alias_map(config):
    """Build alias mapping from config."""
    return config.get('hilos', {}).get('alias', {})


HILO_REGEX = re.compile(r'^### → Hilo: `([^`]+)`\s*(?:\(condensado\))?\s*$')
EPISODE_REGEX = re.compile(r'^#### (\d{4}-\d{2}-\d{2}) — (.+)$')
SECTION_REGEX = re.compile(r'^## ')
FUENTE_REGEX = re.compile(r'^> Fuente:')
EMPTY_LINE_REGEX = re.compile(r'^\s*$')
HILO_EPISODE_REGEX = re.compile(r'^### (\d{4}-\d{2}-\d{2}) — (.+)$', re.MULTILINE)

# Directories that MUST NOT be used as HILOS_DIR (safety guard)
PROTECTED_DIRS = {Path('/'), Path.home()}


def is_safe_hilos_dir(hilos_dir: Path) -> bool:
    """Ensure HILOS_DIR is not a system or home directory to prevent data loss."""
    resolved = hilos_dir.resolve()
    if resolved in PROTECTED_DIRS:
        return False
    if resolved == Path.cwd().resolve():
        return False
    return True


def parse_acta(filepath):
    """Parse an acta file and return list of episodes grouped by Hilo."""
    filename = os.path.basename(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    metadata = parse_frontmatter(lines)
    if isinstance(metadata.get('episodios'), list):
        return parse_structured_episodes(metadata, filename)

    in_episodes = False
    episodes = []
    current_hilo = None
    current_episode = None
    current_body = []
    current_fuente = []
    in_fuente = False

    for line in lines:
        stripped = line.rstrip('\n')

        if stripped == '## Episodios':
            in_episodes = True
            continue

        if not in_episodes:
            continue

        if SECTION_REGEX.match(stripped) and stripped != '## Episodios':
            break

        m = HILO_REGEX.match(stripped)
        if m:
            if current_episode is not None:
                episodes.append({
                    'hilo': current_hilo,
                    'date': current_episode['date'],
                    'title': current_episode['title'],
                    'body': '\n'.join(current_body).strip(),
                    'fuente': '\n'.join(current_fuente).strip(),
                    'source_file': filename,
                })
            current_hilo = m.group(1).strip()
            current_episode = None
            current_body = []
            current_fuente = []
            in_fuente = False
            continue

        m = EPISODE_REGEX.match(stripped)
        if m:
            if current_episode is not None:
                episodes.append({
                    'hilo': current_hilo,
                    'date': current_episode['date'],
                    'title': current_episode['title'],
                    'body': '\n'.join(current_body).strip(),
                    'fuente': '\n'.join(current_fuente).strip(),
                    'source_file': filename,
                })
            current_episode = {'date': m.group(1), 'title': m.group(2)}
            current_body = []
            current_fuente = []
            in_fuente = False
            continue

        if current_episode is not None:
            if FUENTE_REGEX.match(stripped):
                in_fuente = True
                current_fuente.append(stripped)
            elif in_fuente:
                if EMPTY_LINE_REGEX.match(stripped):
                    in_fuente = False
                else:
                    current_fuente.append(stripped)
            else:
                current_body.append(stripped)

    if current_episode is not None:
        episodes.append({
            'hilo': current_hilo,
            'date': current_episode['date'],
            'title': current_episode['title'],
            'body': '\n'.join(current_body).strip(),
            'fuente': '\n'.join(current_fuente).strip(),
            'source_file': filename,
        })

    return episodes


def parse_frontmatter(lines):
    """Return YAML frontmatter when present; legacy actas have none."""
    if not lines or lines[0].strip() != '---':
        return {}
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == '---')
    except StopIteration:
        return {}
    try:
        import yaml
        return yaml.safe_load(''.join(lines[1:end])) or {}
    except Exception as exc:
        print(f"WARNING: frontmatter invalido, se usa Markdown: {exc}")
        return {}


def parse_structured_episodes(metadata, filename):
    """Read v2 structured episodes while preserving the legacy output shape."""
    episodes = []
    for item in metadata['episodios']:
        if not isinstance(item, dict):
            continue
        hilo = item.get('hilo_destino')
        date = str(item.get('fecha', ''))
        title = str(item.get('titulo', '')).strip()
        if not hilo or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) or not title:
            print(f"WARNING: episodio v2 invalido en {filename}, se omite")
            continue
        source = str(item.get('cita', '')).strip()
        if source and not source.startswith('> Fuente:'):
            source = f"> Fuente: {source}"
        episodes.append({
            'hilo': str(hilo).strip(),
            'date': date,
            'title': title,
            'body': str(item.get('cuerpo', '')).strip(),
            'fuente': source,
            'source_file': filename,
            'episode_id': str(item.get('episodio_id', '')).strip(),
            'tipo': str(item.get('tipo', 'evidencia')).strip(),
        })
    return episodes


def format_episode(ep):
    """Format an episode for inclusion in a Hilo file."""
    parts = [f"### {ep['date']} — {ep['title']}", ""]
    if ep['body']:
        parts.append(ep['body'])
        parts.append("")
    if ep['fuente']:
        parts.append(ep['fuente'])
    result = '\n'.join(parts)
    if result:
        result += '\n\n'
    return result


def episode_key(ep):
    """Stable key for avoiding duplicate integration without rewriting Hilos."""
    if ep.get('episode_id'):
        return f"id:{ep['episode_id']}"
    source = re.sub(r'\s+', ' ', ep.get('fuente', '')).strip()
    return f"legacy:{ep['date']}\x1f{ep['title']}\x1f{source}"


def existing_episode_keys(filepath):
    """Read existing Hilo headings and citations without altering its prose."""
    if not filepath.exists():
        return set()
    text = filepath.read_text(encoding='utf-8')
    keys = set()
    matches = list(HILO_EPISODE_REGEX.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end]
        source_match = re.search(r'^> Fuente:.*$', block, re.MULTILINE)
        source = re.sub(r'\s+', ' ', source_match.group(0)).strip() if source_match else ''
        keys.add(f"legacy:{match.group(1)}\x1f{match.group(2).strip()}\x1f{source}")
    return keys


def append_episodes(filepath, episodes):
    """Append approved new episodes without changing existing Hilo content."""
    if filepath.is_symlink():
        raise OSError(f"Refusing to write to symlink: {filepath}")
    addition = ''.join(format_episode(ep) for ep in episodes)
    prefix = "\n" if filepath.exists() and filepath.stat().st_size else ""
    fd = os.open(filepath, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(prefix + addition)


def resolve_hilo(name, alias_map=None):
    if alias_map is None:
        return name
    return alias_map.get(name, name)


def clean_hilos_dir(hilos_dir: Path, dry_run: bool = False):
    """Remove all .md files under hilos_dir, with safety checks."""
    resolved = hilos_dir.resolve()
    if not resolved.exists():
        return
    if not is_safe_hilos_dir(resolved):
        print(f"Error: HILOS_DIR {resolved} es un directorio protegido. Abortando.")
        sys.exit(1)

    # Warn if deleting files outside the project workspace
    cwd = Path.cwd().resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError:
        print(f"Advertencia: HILOS_DIR ({resolved}) está fuera del directorio de trabajo ({cwd}).")
        print("Para proceder, use la flag --force-delete")
        if not dry_run:
            return 0

    removed = 0
    for root, dirs, files in os.walk(resolved):
        for f in files:
            if f.endswith('.md'):
                fpath = os.path.join(root, f)
                if os.path.islink(fpath):
                    print(f"  ! Es un enlace simbólico, se omite: {fpath}")
                    continue
                if dry_run:
                    print(f"  · se eliminaría: {fpath}")
                else:
                    os.remove(fpath)
                removed += 1

    if not dry_run:
        for root, dirs, files in os.walk(resolved):
            if not os.listdir(root) and root != str(resolved):
                os.rmdir(root)

    return removed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Integra episodios de actas en archivos de Hilo")
    parser.add_argument("--config", default=None, help="Ruta al archivo config.yaml")
    parser.add_argument("--actas-dir", default=None, help="Directorio con actas procesadas")
    parser.add_argument("--hilos-dir", default=None, help="Directorio raíz de Hilos")
    parser.add_argument("--hilos-config", default=None, help="Archivo JSON/YAML con definición de hilos")
    parser.add_argument("--pendientes", default=None, help="Archivo de pendientes (opcional)")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, no modificar archivos")
    parser.add_argument("--since", default=None, help="Integrar episodios desde YYYY-MM-DD")
    parser.add_argument("--rebuild", action="store_true", help="Reconstruir Hilos desde cero (destructivo)")
    parser.add_argument("--force-delete", action="store_true", help="Confirmar eliminación requerida por --rebuild")
    args = parser.parse_args()

    dry_run = args.dry_run

    # Resolve config
    config = None
    if args.config:
        config = load_config(args.config)
        vault_root = Path(config.get('vault_root', './'))
        proc = config.get('procesamiento', {})
        ACTAS_DIR = vault_root / proc.get('actas_dir', 'actas/procesadas')
        HILOS_DIR = vault_root / proc.get('hilos_dir', 'hilos')
        PENDIENTES = vault_root / proc.get('pendientes', 'pendientes.md')
        OFFICIAL_HILOS = build_official_hilos(config)
        HILO_ALIAS = build_alias_map(config)
        default_since = proc.get('integrar_desde')
    else:
        ACTAS_DIR = Path(args.actas_dir) if args.actas_dir else Path("actas/procesadas")
        HILOS_DIR = Path(args.hilos_dir) if args.hilos_dir else Path("hilos")
        PENDIENTES = Path(args.pendientes) if args.pendientes else Path("pendientes.md")

        if args.hilos_config:
            hconfig = load_config(args.hilos_config)
            OFFICIAL_HILOS = build_official_hilos(hconfig)
            HILO_ALIAS = build_alias_map(hconfig)
        else:
            print("Error: se necesita --config o --hilos-config")
            sys.exit(1)
        default_since = None

    integration_since = args.since or default_since
    if integration_since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', integration_since):
        parser.error("--since debe usar el formato YYYY-MM-DD")

    unknown_hilos = set()
    unknown_hilo_episodes = defaultdict(list)
    hilo_episodes = defaultdict(list)
    alias_used = defaultdict(list)
    total_episodes = 0
    total_skipped = 0
    total_filtered = 0
    processed_actas = set()

    if not ACTAS_DIR.exists():
        print(f"Error: no existe el directorio de actas: {ACTAS_DIR}")
        sys.exit(1)

    for fname in sorted(os.listdir(ACTAS_DIR)):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(ACTAS_DIR, fname)
        try:
            episodes = parse_acta(fpath)
        except Exception as e:
            print(f"ERROR parsing {fname}: {e}")
            continue

        if episodes:
            processed_actas.add(fname)

        for ep in episodes:
            total_episodes += 1
            if integration_since and ep['date'] < integration_since:
                total_filtered += 1
                continue
            raw_name = ep['hilo']
            official_name = resolve_hilo(raw_name, HILO_ALIAS)

            if raw_name != official_name:
                alias_used[official_name].append(raw_name)

            if official_name not in OFFICIAL_HILOS:
                unknown_hilos.add(raw_name)
                unknown_hilo_episodes[raw_name].append(ep)
                total_skipped += 1
                continue

            ep['hilo'] = official_name
            hilo_episodes[official_name].append(ep)

    for hilo_name in hilo_episodes:
        hilo_episodes[hilo_name].sort(key=lambda e: e['date'] or '')

    propuestas_data = []
    for raw_name in sorted(unknown_hilos):
        unknown_eps = unknown_hilo_episodes.get(raw_name, [])
        text = ' '.join(e.get('body', '') + ' ' + (e.get('title', '') or '') for e in unknown_eps)
        ents = extract_entities(text)
        propuestas_data.append({
            'name': raw_name,
            'count': len(unknown_eps),
            'entities': {
                'all_names': sorted(ents['all_names']),
                'institutions': sorted(ents['institutions']),
                'places': sorted(ents['places']),
            },
        })

    if args.force_delete and not args.rebuild:
        parser.error("--force-delete requiere --rebuild")
    if args.rebuild and not args.force_delete:
        parser.error("--rebuild requiere --force-delete; la integración normal es aditiva")

    # Rebuild is reserved for disposable output directories. Canonical use is additive.
    if args.rebuild and HILOS_DIR.exists():
        if not is_safe_hilos_dir(HILOS_DIR):
            print(f"Error: HILOS_DIR {HILOS_DIR.resolve()} es un directorio protegido. Abortando.")
            sys.exit(1)
        removed = clean_hilos_dir(HILOS_DIR, dry_run=dry_run)
        if dry_run:
            print(f"\n[dry-run] Se eliminarían {removed} archivos .md")
        else:
            print(f"Eliminados {removed} archivos .md existentes en HILOS_DIR")

    files_modified = []
    episodes_added = 0
    episodes_unchanged = 0
    propuestas_nuevas = list(unknown_hilos)

    for hilo_name, block in OFFICIAL_HILOS.items():
        if hilo_name not in hilo_episodes:
            continue

        eps = hilo_episodes[hilo_name]
        block_dir = HILOS_DIR / block
        block_dir.mkdir(parents=True, exist_ok=True)

        filepath = block_dir / f"{hilo_name}.md"
        known = set() if args.rebuild else existing_episode_keys(filepath)
        pending = [ep for ep in eps if episode_key(ep) not in known]
        episodes_unchanged += len(eps) - len(pending)
        if pending:
            if not dry_run:
                block_dir.mkdir(parents=True, exist_ok=True)
                append_episodes(filepath, pending)
            files_modified.append(str(filepath))
            episodes_added += len(pending)
        alias_info = ""
        if hilo_name in alias_used:
            alias_info = f" (aliases: {', '.join(set(alias_used[hilo_name]))})"
        action = "would update" if dry_run else "updated"
        print(f"{'[dry-run] ' if dry_run else ''}{action}: {filepath} ({len(pending)} new, {len(eps) - len(pending)} existing{alias_info})")

    coverage_pct = (total_episodes - total_skipped) / max(total_episodes, 1) * 100

    print("\n" + "=" * 60)
    print("## Reporte de integración — integrate_hilos")
    print(f"- Actas procesadas: {len(processed_actas)} ({total_episodes} episodios, {total_skipped} omitidos)")
    if integration_since:
        print(f"- Episodios anteriores a {integration_since}: {total_filtered} sin integrar")
    print(f"- Cobertura: {coverage_pct:.1f}%")
    print(f"- Archivos modificados: {len(files_modified)}")
    print(f"- Episodios agregados: {episodes_added}; ya presentes: {episodes_unchanged}")
    if propuestas_nuevas:
        print(f"- Propuestas de Hilo nuevo: {len(propuestas_nuevas)}")
        for h in propuestas_nuevas:
            print(f"  - `{h}` — sin bloque asignado en inventario")
    print("- Pendientes: ninguno")
    print("=" * 60)

    if not dry_run:
        propuestas_path = Path(str(ACTAS_DIR)).parent / '_propuestas_hilos.json'
        with open(propuestas_path, 'w', encoding='utf-8') as f:
            json.dump({
                'propuestas': propuestas_data,
                'total_episodes': total_episodes,
                'classified': total_episodes - total_skipped,
                'unclassified': total_skipped,
                'coverage_pct': round(coverage_pct, 1),
                'hilo_distribution': {
                    h: len(eps) for h, eps in sorted(hilo_episodes.items())
                },
            }, f, ensure_ascii=False, indent=2)
        print(f"- Propuestas exportadas: {propuestas_path}")


if __name__ == '__main__':
    main()
