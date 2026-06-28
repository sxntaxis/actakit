#!/usr/bin/env python3
"""
Convert acta PDF/DOCX files to plain-text .md extracts.

Usage:
    python pdftotext_actas.py --input-dir PATH [--output-dir PATH]
                              [--vault PATH] [--dry-run] [--force]

Requires: poppler-utils (pdftotext), python-docx
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    from docx import Document
except ImportError:
    Document = None


def find_documents(input_dir: Path):
    pdfs = sorted(input_dir.rglob("*.pdf"))
    docxs = sorted(input_dir.rglob("*.docx"))
    return pdfs + docxs


def convert_pdf_to_text(path: Path):
    try:
        result = subprocess.run(
            ["pdftotext", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  [!] pdftotext error ({path.name}): {result.stderr.strip()}")
            return None
        return result.stdout
    except FileNotFoundError:
        print("  [!] pdftotext not found. Install poppler-utils.")
        return None
    except subprocess.TimeoutExpired:
        print(f"  [!] pdftotext timeout ({path.name})")
        return None


def convert_docx_to_text(path: Path):
    if Document is None:
        print("  [!] python-docx not available; install with: pip install python-docx")
        return None
    try:
        doc = Document(str(path))
        paras = [p.text for p in doc.paragraphs]
        return "\n".join(paras)
    except Exception as exc:
        print(f"  [!] docx error ({path.name}): {exc}")
        return None


def needs_conversion(doc_path: Path, md_path: Path, force: bool):
    if force:
        return True
    if not md_path.exists():
        return True
    return doc_path.stat().st_mtime > md_path.stat().st_mtime


def convert_document(doc_path: Path, output_dir: Path, force: bool):
    stem = doc_path.stem
    # Sanitize stem to prevent path traversal
    if '..' in stem or stem.startswith('.') or os.path.isabs(stem):
        return "error:invalid_filename"
    md_path = output_dir / f"{stem}.md"

    status = needs_conversion(doc_path, md_path, force)
    if not status:
        return "skip"

    if doc_path.suffix.lower() == ".pdf":
        text = convert_pdf_to_text(doc_path)
    elif doc_path.suffix.lower() == ".docx":
        text = convert_docx_to_text(doc_path)
    else:
        return "error:unsupported_format"

    if text is None:
        return "error:conversion_failed"

    if md_path.is_symlink():
        return "error:symlink_detected"
    fd = os.open(md_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
    except FileExistsError:
        return "skip"
    except Exception:
        try:
            os.unlink(md_path)
        except OSError:
            pass
        raise
    return "ok"


def sync_to_vault(output_dir: Path, vault_dir: Path, dry_run: bool):
    vault_md = vault_dir / "_texto_md"
    if not dry_run:
        vault_md.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for src in sorted(output_dir.glob("*.md")):
        dst = vault_md / src.name
        if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
            skipped += 1
            continue
        if dst.is_symlink():
            print(f"    ! Saltando symlink en destino: {dst}")
            skipped += 1
            continue
        if dry_run:
            print(f"    · would copy {src.name} → {dst}")
        else:
            import shutil
            shutil.copy2(src, dst, follow_symlinks=False)
            print(f"    ✓ {src.name}")
        copied += 1
    return copied, skipped


def main():
    parser = argparse.ArgumentParser(description="Convierte PDF/DOCX de actas a extractos .md")
    parser.add_argument("--input-dir", required=True, help="Directorio con PDFs/DOCX")
    parser.add_argument("--output-dir", default=None, help="Directorio de salida (default: <input-dir>/_texto_md/)")
    parser.add_argument("--vault", default=None, help="Copiar resultados al vault: ruta al directorio de actas")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, no convertir")
    parser.add_argument("--force", action="store_true", help="Reconvertir aunque el .md ya exista")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: input dir not found: {input_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "_texto_md"

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    if args.force and not args.dry_run:
        existing_md = list(output_dir.glob("*.md"))
        if existing_md:
            print(f"\n[ADVERTENCIA] --force está activado. Se sobreescribirán {len(existing_md)} archivos .md existentes.")
            print(f"  Los archivos serán sobreescritos con nueva conversión.")
            print(f"  Para preservar ediciones manuales, considere usar --output-dir diferente.")
            backup_dir = output_dir / "_bak_tex2md"
            backup_dir.mkdir(exist_ok=True)
            import shutil
            for md in existing_md:
                bak = backup_dir / md.name
                shutil.copy2(md, bak)
            print(f"  Backup manual guardado en: {backup_dir}")

    documents = find_documents(input_dir)
    if not documents:
        print(f"No se encontraron PDFs ni DOCXs en {input_dir}")
        sys.exit(0)

    print(f"Documentos encontrados: {len(documents)}")
    print(f"Salida: {output_dir}")

    results = {"ok": 0, "skip": 0, "error": 0}
    for doc_path in documents:
        if args.dry_run:
            md_path = output_dir / f"{doc_path.stem}.md"
            exists = " (ya existe)" if md_path.exists() else ""
            print(f"  · {doc_path.name}{exists}")
            results["ok"] += 1
            continue

        status = convert_document(doc_path, output_dir, args.force)
        status_key = 'error' if status.startswith('error') else status
        marker = {"ok": "✓", "skip": "·", "error": "✗"}.get(status_key, "?")
        print(f"  {marker} {doc_path.name}")
        results[status_key] = results.get(status_key, 0) + 1

    print(f"\nResumen: {results.get('ok', 0)} convertidos, "
          f"{results.get('skip', 0)} saltados, "
          f"{results.get('error', 0)} errores")

    if args.vault:
        vault_path = Path(args.vault).resolve()
        print(f"\nSincronizando con vault: {vault_path}")
        copied, skipped = sync_to_vault(output_dir, vault_path, args.dry_run)
        print(f"Vault: {copied} copiados, {skipped} saltados")


if __name__ == "__main__":
    main()
