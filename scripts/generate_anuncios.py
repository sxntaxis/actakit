#!/usr/bin/env python3
"""Generate episode content from classified announcements."""

import json, os, sys
from pathlib import Path


def build_episodio_text(anuncio, clasif):
    """Build a Markdown episode block from an announcement + classification."""
    hilo = clasif.get('hilo_destino', 'Sin Hilo')
    titulo = clasif.get('titulo_generado', anuncio.get('body', '')[:60])
    fecha = anuncio.get('fecha', '') or anuncio.get('fecha_es', '')
    acta_ref = anuncio.get('acta_ref', '')
    sesion = anuncio.get('sesion', '')
    ref_line = anuncio.get('ref', '')

    lines = [f"### → Hilo: `{hilo}`", ""]
    lines.append(f"#### {fecha} — {titulo}")
    lines.append("")
    lines.append(anuncio.get('body', ''))
    lines.append("")

    fuente = f"> Fuente: Acta N° {acta_ref}, {fecha}"
    if ref_line:
        fuente += f", {ref_line}"
    if sesion:
        fuente += f", {sesion.lower()}"
    lines.append(fuente)
    lines.append("")

    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Genera episodios desde clasificaciones")
    parser.add_argument("--anuncios", required=True, help="JSON con anuncios extraídos")
    parser.add_argument("--clasificaciones", required=True, help="JSON con clasificaciones")
    parser.add_argument("--output", required=True, help="JSON de salida con episodios generados")
    parser.add_argument("--candidatos", required=True, help="JSON de candidatos con texto completo")
    args = parser.parse_args()

    for f in [args.anuncios, args.clasificaciones]:
        if not os.path.exists(f):
            print(f"Error: no existe {f}")
            sys.exit(1)

    with open(args.anuncios, encoding='utf-8') as f:
        anuncios = json.load(f)
    with open(args.clasificaciones, encoding='utf-8') as f:
        clasificaciones = json.load(f)

    anuncios_by_id = {a['id']: a for a in anuncios}
    episodios = {}
    candidatos = []

    for epid, clasif in clasificaciones.items():
        if isinstance(clasif, str):
            clasif = {'accion': 'levantar_a_hilo', 'categoria': clasif}
        if clasif.get('accion') != 'levantar_a_hilo':
            continue
        anuncio = anuncios_by_id.get(epid)
        if not anuncio:
            continue

        ep_text = build_episodio_text(anuncio, clasif)
        episodios[epid] = ep_text

        candidatos.append({
            'id': epid,
            'local_idx': int(clasif.get('local_idx', 0)),
            'hilo_destino': clasif.get('hilo_destino', ''),
            'titulo_generado': clasif.get('titulo_generado', ''),
            'texto_completo': ep_text,
        })

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(episodios, f, ensure_ascii=False, indent=2)

    with open(args.candidatos, 'w', encoding='utf-8') as f:
        json.dump(candidatos, f, ensure_ascii=False, indent=2)

    print(f"{len(episodios)} episodios generados → {args.output}")
    print(f"{len(candidatos)} candidatos → {args.candidatos}")


if __name__ == '__main__':
    main()
