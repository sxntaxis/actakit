#!/usr/bin/env python3
"""
Conversor de PDF/DOCX de actas a extractos .md — MuniEsparza API pipeline.

Toma los PDFs y DOCXs descargados por 09_scrape_actas.py y produce
extractos de texto plano en _texto_md/ usando pdftotext (PDF) y
python-docx (DOCX).

Uso:
    python 11_pdftotext_actas.py [--input-dir PATH] [--output-dir PATH]
                                 [--vault PATH] [--dry-run] [--force]

Salida:
    <input-dir>/_texto_md/   — extractos .md de cada acta
    (opcional) <vault>/_texto_md/ — copia al vault si se especifica --vault

Ejemplos:
    python 11_pdftotext_actas.py
    python 11_pdftotext_actas.py --vault "../../../3 Fuentes/Municipalidad/Actas/concejo"
    python 11_pdftotext_actas.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

try:
    from docx import Document
except ImportError:
    Document = None


def find_documents(input_dir: Path) -> list[Path]:
    pdfs = sorted(input_dir.glob("*.pdf"))
    docxs = sorted(input_dir.glob("*.docx"))
    return pdfs + docxs


def convert_pdf_to_text(path: Path) -> str | None:
    """Run pdftotext on a PDF, return stdout as string."""
    try:
        # Default pdftotext (no -layout) produces line-numbered output that
        # matches the existing _texto_md/ corpus.  -layout yields near-empty
        # results on these scanned/OCR municipal PDFs.
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


def convert_docx_to_text(path: Path) -> str | None:
    """Extract text from a DOCX using python-docx."""
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


def needs_conversion(doc_path: Path, md_path: Path, force: bool) -> bool:
    if force:
        return True
    if not md_path.exists():
        return True
    doc_mtime = doc_path.stat().st_mtime
    md_mtime = md_path.stat().st_mtime
    return doc_mtime > md_mtime


def convert_document(doc_path: Path, output_dir: Path, force: bool) -> str:
    stem = doc_path.stem
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

    md_path.write_text(text, encoding="utf-8")
    return "ok"


def sync_to_vault(output_dir: Path, vault_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Copy .md files from output_dir to vault_dir/_texto_md/.
    Returns (copied, skipped)."""
    vault_md = vault_dir / "_texto_md"
    if not dry_run:
        vault_md.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for src in sorted(output_dir.glob("*.md")):
        dst = vault_md / src.name
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            skipped += 1
            continue
        if dry_run:
            print(f"    · copiaría {src.name} → {dst}")
        else:
            import shutil
            shutil.copy2(src, dst)
            print(f"    ✓ {src.name}")
        copied += 1
    return copied, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Convierte PDF/DOCX de actas a extractos .md"
    )
    parser.add_argument(
        "--input-dir", default=None,
        help="Directorio con PDFs/DOCX (default: data/actas/concejo/)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directorio de salida para .md (default: <input-dir>/_texto_md/)"
    )
    parser.add_argument(
        "--vault", default=None,
        help="Copiar resultados al vault: ruta a 3 Fuentes/.../concejo/"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo listar, no convertir"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Reconvertir aunque el .md ya exista y esté actualizado"
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent

    input_dir = Path(args.input_dir) if args.input_dir else root_dir / "data" / "actas" / "concejo"
    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "_texto_md"

    if not input_dir.exists():
        print(f"Error: input dir not found: {input_dir}")
        print("Run 09_scrape_actas.py first to download PDFs.")
        sys.exit(1)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    documents = find_documents(input_dir)
    if not documents:
        print(f"No se encontraron PDFs ni DOCXs en {input_dir}")
        sys.exit(0)

    print(f"Documentos encontrados: {len(documents)}")
    print(f"Salida: {output_dir}")
    if args.dry_run:
        print("Modo dry-run — no se escribe nada\n")

    results = {"ok": 0, "skip": 0, "error": 0}
    for doc_path in documents:
        if args.dry_run:
            md_path = output_dir / f"{doc_path.stem}.md"
            exists = " (ya existe)" if md_path.exists() else ""
            print(f"  · {doc_path.name}{exists}")
            results["ok"] += 1
            continue

        status = convert_document(doc_path, output_dir, args.force)
        marker = {"ok": "✓", "skip": "·", "error": "✗"}.get(status, "?")
        print(f"  {marker} {doc_path.name}")
        results[status] = results.get(status, 0) + 1

    print(f"\nResumen: {results.get('ok', 0)} convertidos, "
          f"{results.get('skip', 0)} saltados, "
          f"{results.get('error', 0)} errores")

    # Sync to vault if requested
    if args.vault:
        vault_path = Path(args.vault).resolve()
        print(f"\nSincronizando con vault: {vault_path}")
        copied, skipped = sync_to_vault(output_dir, vault_path, args.dry_run)
        print(f"Vault: {copied} copiados, {skipped} saltados")


if __name__ == "__main__":
    main()
