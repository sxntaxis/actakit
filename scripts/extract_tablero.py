#!/usr/bin/env python3
"""Extract announcement board (Tablero de anuncios) from processed actas."""

import os, re, json, sys
from pathlib import Path

MESES = {
    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
    'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
    'setiembre': '09', 'septiembre': '09', 'octubre': '10',
    'noviembre': '11', 'diciembre': '12',
}


def spanish_date_to_iso(fecha_es):
    """Convert '27 de abril del 2026' or '27 de abril de 2026' to '2026-04-27'."""
    m = re.match(r'(\d{1,2})\s+de\s+(\w+)\s+del?\s+(\d{4})', fecha_es.strip())
    if not m:
        return ''
    dia, mes_str, anio = m.group(1), m.group(2).lower(), m.group(3)
    mes = MESES.get(mes_str, '')
    if not mes:
        print(f"WARNING: mes no reconocido '{mes_str}' en fecha: {fecha_es}")
        return ''
    return f'{anio}-{mes}-{int(dia):02d}'


SECTION = re.compile(r'^## ')
BULLET = re.compile(r'^- ')
ANUNCIO_FOOTER = re.compile(
    r'\*\*?Anuncio material (con acuerdo de recibo|sin acuerdo formal)'
    r' — `Acta N° (.+?)`, \*\*(\d{1,2} de \w+ del? \d{4})\*\*, (.+?)\*$',
    re.MULTILINE
)
ACTA_NUM = re.compile(r'\d+')
TIPO_SESION = re.compile(r'^# Acta N° .+?— (Sesión Ordinaria|Sesión Extraordinaria|Sesión Solemne)')


def get_session_type(lines):
    for line in lines[:5]:
        m = TIPO_SESION.search(line)
        if m:
            return m.group(1)
    return "Sesión Ordinaria"


def extract(filepath):
    with open(filepath, encoding='utf-8') as f:
        lines = f.readlines()

    filename = os.path.basename(filepath)
    tablero_start = None
    for i, line in enumerate(lines):
        if line.rstrip('\n') == '## Tablero de anuncios':
            tablero_start = i
            break
    if tablero_start is None:
        return []

    tablero_end = len(lines)
    for i in range(tablero_start + 1, len(lines)):
        if SECTION.match(lines[i]):
            tablero_end = i
            break

    tablero_lines = lines[tablero_start:tablero_end]
    if not re.search(r'\*Anuncio material', ''.join(tablero_lines)):
        return []

    session_type = get_session_type(lines)
    announcements = []
    current = []

    for line in tablero_lines[1:]:
        s = line.rstrip('\n')
        if BULLET.match(s) and current:
            combined = '\n'.join(current)
            m = ANUNCIO_FOOTER.search(combined)
            if m:
                body = ANUNCIO_FOOTER.sub('', combined).strip()
                body = re.sub(r'^- (?:\[[^\]]*\]\s*)?', '', body).strip()
                acta_ref = m.group(2)
                acta_num_m = ACTA_NUM.search(acta_ref)
                acta_num = acta_num_m.group(0) if acta_num_m else '0'
                announcements.append(dict(
                    acta_num=acta_num,
                    acta_ref=acta_ref,
                    fecha_es=m.group(3),
                    fecha=spanish_date_to_iso(m.group(3)),
                    tipo=m.group(1),
                    ref=m.group(4).rstrip('.'),
                    sesion=session_type,
                    body=body,
                ))
            current = [s]
        else:
            current.append(s)

    if current:
        combined = '\n'.join(current)
        m = ANUNCIO_FOOTER.search(combined)
        if m:
            body = ANUNCIO_FOOTER.sub('', combined).strip()
            body = re.sub(r'^- (?:\[[^\]]*\]\s*)?', '', body).strip()
            acta_ref = m.group(2)
            acta_num_m = ACTA_NUM.search(acta_ref)
            acta_num = acta_num_m.group(0) if acta_num_m else '0'
            announcements.append(dict(
                acta_num=acta_num,
                acta_ref=acta_ref,
                fecha_es=m.group(3),
                fecha=spanish_date_to_iso(m.group(3)),
                tipo=m.group(1),
                ref=m.group(4).rstrip('.'),
                sesion=session_type,
                body=body,
            ))

    return announcements


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extrae tablero de anuncios de actas procesadas")
    parser.add_argument("--actas-dir", required=True, help="Directorio con actas procesadas")
    parser.add_argument("--output", required=True, help="Archivo JSON de salida")
    parser.add_argument("--clasif", default=None, help="Archivo JSON de clasificaciones existentes (opcional)")
    args = parser.parse_args()

    actas_dir = Path(args.actas_dir)
    if not actas_dir.exists():
        print(f"Error: no existe {actas_dir}")
        sys.exit(1)

    all_anns = []
    for fname in sorted(os.listdir(actas_dir)):
        if not fname.endswith('.md'):
            continue
        all_anns.extend(extract(os.path.join(actas_dir, fname)))

    all_anns.sort(key=lambda a: int(a['acta_num']))

    for i, a in enumerate(all_anns):
        a['id'] = f"Acta_{a['acta_num']}-{i}"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_anns, f, ensure_ascii=False, indent=2)

    existing = set()
    if args.clasif and os.path.exists(args.clasif):
        with open(args.clasif, encoding='utf-8') as f:
            existing = set(json.load(f).keys())

    ids = set(a['id'] for a in all_anns)
    pending = ids - existing
    classified = ids & existing

    print(f"{len(all_anns)} anuncios extraídos → {args.output}")
    print(f"  Ya clasificados: {len(classified)}")
    print(f"  Pendientes: {len(pending)}")

    if pending:
        pending_data = [a for a in all_anns if a['id'] in pending]
        pending_path = output_path.with_stem(output_path.stem.replace('_data', '_pending'))
        with open(pending_path, 'w', encoding='utf-8') as f:
            json.dump(pending_data, f, ensure_ascii=False, indent=2)
        print(f"  Pendientes guardados en {pending_path}")


if __name__ == '__main__':
    main()
