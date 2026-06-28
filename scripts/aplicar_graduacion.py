#!/usr/bin/env python3
"""Apply graduation edits to acta files: move Tablero items to Episodios."""

import json, os, re, shutil, sys
from collections import defaultdict
from pathlib import Path


def write_acta_safely(fpath, content):
    """Write content to acta file, refusing to follow symlinks."""
    resolved = Path(fpath).resolve()
    if Path(fpath).is_symlink():
        raise OSError(f"Refusing to write to symlink: {fpath}")
    fd = os.open(fpath, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        try:
            os.unlink(fpath)
        except OSError:
            pass
        raise


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gradua anuncios clasificados a episodios en actas")
    parser.add_argument("--actas-dir", required=True, help="Directorio con actas procesadas")
    parser.add_argument("--herramientas-dir", required=True, help="Directorio con los JSONs de entrada")
    parser.add_argument("--backup-dir", default=None, help="Directorio para backups (default: <actas-dir>/bak_graduacion)")
    parser.add_argument("--reset", action="store_true", help="Restaurar desde backup y reprocesar")
    args = parser.parse_args()

    actas_dir = Path(args.actas_dir)
    her_dir = Path(args.herramientas_dir)
    backup_dir = Path(args.backup_dir) if args.backup_dir else actas_dir / "bak_graduacion"

    if not actas_dir.exists():
        print(f"Error: no existe el directorio de actas: {actas_dir}")
        sys.exit(1)

    episodios_file = her_dir / "_episodios_generados.json"
    candidatos_file = her_dir / "_candidatos_con_texto_completo.json"
    anuncios_file = her_dir / "_anuncios_data.json"

    for f in [episodios_file, candidatos_file, anuncios_file]:
        if not f.exists():
            print(f"Error: no existe {f}")
            sys.exit(1)

    try:
        with open(episodios_file, encoding='utf-8') as f:
            episodios = json.load(f)
        with open(candidatos_file, encoding='utf-8') as f:
            candidatos = json.load(f)
        cand_by_id = {r['id']: r for r in candidatos}
        with open(anuncios_file, encoding='utf-8') as f:
            anuncios = json.load(f)
        anuncios_by_id = {a['id']: a for a in anuncios}
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: no se pudieron leer los archivos JSON: {e}")
        sys.exit(1)

    id_to_acta = {}
    for a in anuncios:
        id_to_acta[a['id']] = a['acta_num']

    def find_acta_file(acta_num):
        if not re.match(r'^\d+$', str(acta_num)):
            return None
        for fname in os.listdir(str(actas_dir)):
            if fname.startswith(f"Acta_{acta_num}_") or fname.startswith(f"Acta_{acta_num}E_"):
                return os.path.join(str(actas_dir), fname)
        return None

    by_acta_file = defaultdict(list)
    for epid, ep_text in episodios.items():
        acta_num = id_to_acta.get(epid)
        if not acta_num:
            print(f"ERROR: no acta_num for {epid}")
            continue
        fpath = find_acta_file(acta_num)
        if not fpath:
            print(f"ERROR: no file for Acta_{acta_num}")
            continue
        by_acta_file[fpath].append((epid, ep_text))

    os.makedirs(backup_dir, exist_ok=True)

    if args.reset:
        for fpath in sorted(by_acta_file.keys()):
            fname = os.path.basename(fpath)
            backup = os.path.join(backup_dir, fname)
            if os.path.isfile(backup):
                shutil.copy2(backup, fpath)
                print(f"  Restaurado desde backup: {fname}")

    print(f"Actas a editar: {len(by_acta_file)}")
    total_edited = 0
    total_skipped = 0

    for fpath, items in sorted(by_acta_file.items()):
        fname = os.path.basename(fpath)
        acta_num = fname.split('_')[1].rstrip('E')

        with open(fpath, encoding='utf-8') as f:
            content = f.read()

        episode_blocks = []
        for epid, ep_text in items:
            ep_stripped = ep_text.strip()
            episode_blocks.append(ep_stripped)

        already_done = all(block in content for block in episode_blocks)
        if already_done:
            print(f"  {fname}: ya tiene los episodios, se omite")
            total_skipped += len(items)
            continue

        shutil.copy2(fpath, os.path.join(backup_dir, fname))

        tablero_match = re.search(r'(## Tablero de anuncios\n)(.*?)(?=\n## |\Z)', content, re.DOTALL)
        if not tablero_match:
            print(f"  {fname}: NO TABLERO SECTION")
            continue

        tablero_header = tablero_match.group(1)
        tablero_body = tablero_match.group(2)

        tablero_lines = tablero_body.strip().split('\n')

        tablero_entries = []
        current_entry = []
        for line in tablero_lines:
            stripped = line.strip()
            if line.startswith('- ') and current_entry:
                tablero_entries.append('\n'.join(current_entry))
                current_entry = [line]
            elif stripped.startswith('- ') and not current_entry:
                current_entry = [line]
            elif current_entry:
                current_entry.append(line)
        if current_entry:
            tablero_entries.append('\n'.join(current_entry))

        ids_in_this_acta = [epid for epid, _ in items]
        local_indices = set()
        for epid in ids_in_this_acta:
            cand = cand_by_id.get(epid, {})
            li = cand.get('local_idx')
            if li is not None:
                local_indices.add(li)

        if not local_indices:
            print(f"  {fname}: no local indices found")
            continue

        sorted_indices = sorted(local_indices, reverse=True)
        removed_texts = []
        for idx in sorted_indices:
            if idx < len(tablero_entries):
                removed_texts.append(tablero_entries.pop(idx))

        new_tablero_body = ''
        if tablero_entries:
            new_tablero_body = '\n\n'.join(tablero_entries) + '\n'
        else:
            new_tablero_body = '- No se registraron anuncios comunitarios o logísticos en esta sesión.\n'

        old_tablero_section = tablero_header + tablero_body
        new_tablero_section = tablero_header + new_tablero_body
        content = content.replace(old_tablero_section, new_tablero_section)

        new_episodes = '\n\n'.join(episode_blocks)

        episodios_match = re.search(r'(## Episodios\n)', content)
        if not episodios_match:
            print(f"  {fname}: NO EPISODIOS SECTION")
            shutil.copy2(os.path.join(backup_dir, fname), fpath)
            continue

        content = content[:episodios_match.end()] + '\n' + new_episodes + '\n' + content[episodios_match.end():]

        write_acta_safely(fpath, content)

        print(f"  {fname}: removed {len(removed_texts)} from Tablero, added {len(items)} episodes")
        total_edited += len(items)

    print(f"\nTotal episodes added to actas: {total_edited}")
    print(f"Backup saved in: {backup_dir}")


if __name__ == '__main__':
    main()
