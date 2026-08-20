#!/usr/bin/env python3
"""
Scraper de actas — muniesparza.go.cr

Descarga todas las actas del Concejo Municipal, Comisiones y Junta Vial
desde el CMS de la Municipalidad de Esparza (sistema separado del API Junar).

URL base de descarga: https://muniesparza.go.cr/files/folder/<UUID>.<ext>
Hallado en /js/frontend.js: function openDocumentArticle(urlDocArticle){
    window.open(base_path + 'files/folder/' + urlDocArticle, "_blank");
}

Uso:
    python 09_scrape_actas.py [--dry-run] [--output-dir PATH]
                              [--section concejo [comisiones ...]]
                              [--years 2024 2025 2026]

Salida:
    data/actas/concejo/   — actas Concejo Municipal
    data/actas/comisiones/ — actas de Comisiones
    data/actas/junta_vial/ — actas Junta Vial
    data/actas/inventario_actas.csv — índice completo
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://muniesparza.go.cr"
FILES_URL = "https://muniesparza.go.cr/files/folder/"

SECCIONES = {
    "concejo": "/articulo/230/actas-concejo-municipal",
    "comisiones": "/articulo/609/actas-de-comisiones",
    "junta_vial": "/articulo/231/actas-junta-vial",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-CR,es;q=0.9",
}

RATE_LIMIT_SECS = 1.0


def fetch_page(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_actas(soup: BeautifulSoup, seccion: str) -> list[dict]:
    """Extract all acta entries from a fileTree page."""
    records = []
    current_year = None

    file_tree = soup.find("ul", class_="fileTree")
    if not file_tree:
        print(f"  [!] No se encontró fileTree en {seccion}")
        return records

    for li in file_tree.find_all("li", recursive=True):
        # Year header (contains a bare <a href="#">YYYY</a>)
        year_link = li.find("a", href="#")
        if year_link and re.match(r"^\d{4}$", year_link.get_text(strip=True)):
            current_year = year_link.get_text(strip=True)
            continue

        # Document entry — has onClick with openDocumentArticle
        onclick = li.find("a", onclick=True)
        if not onclick:
            continue

        match = re.search(r"openDocumentArticle\('([^']+)'\)", onclick["onclick"])
        if not match:
            continue

        filename = match.group(1)  # e.g. "110cc8dd-...pdf"
        uuid, _, ext = filename.rpartition(".")
        title = onclick.get_text(strip=True)
        css_class = " ".join(li.get("class", []))

        records.append(
            {
                "seccion": seccion,
                "year": current_year or "",
                "title": title,
                "uuid": uuid,
                "ext": ext.lower(),
                "filename": filename,
                "url": FILES_URL + quote(filename, safe=""),
                "css_class": css_class,
            }
        )

    return records


def download_file(record: dict, dest_dir: Path, session: requests.Session) -> str:
    """Download one acta file. Returns 'ok', 'skip', or 'error:<msg>'."""
    safe_title = re.sub(r'[^\w\s\-]', '', record["title"])[:80].strip()

    # Broken 2021/2022 entries: the 'filename' on the website is
    # "<UUID>. NN - DD mes YYYY" (no real extension). The 'ext' field ends up
    # holding the descriptive suffix. The actual file lives at the FULL
    # filename URL, not at <UUID>.pdf or <UUID>.docx (both 404). We don't know
    # the real format in advance, so we GET the file, peek at the magic bytes,
    # and write it under the correct extension.
    if record["ext"] not in ("pdf", "docx"):
        record["url"] = FILES_URL + quote(record["filename"], safe="")
        try:
            resp = session.get(record["url"], headers=HEADERS, timeout=60, stream=True)
            resp.raise_for_status()
            head_bytes = next(resp.iter_content(chunk_size=4), b"")
            if head_bytes.startswith(b"%PDF"):
                real_ext = "pdf"
            elif head_bytes.startswith(b"PK"):
                real_ext = "docx"
            else:
                resp.close()
                return "error:unknown_format"
            record["ext"] = real_ext
            out_name = f"{record['year']}_{safe_title}.{real_ext}"
            out_path = dest_dir / out_name
            if out_path.exists():
                resp.close()
                return "skip"
            with open(out_path, "wb") as f:
                f.write(head_bytes)
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return "ok"
        except Exception as exc:
            return f"error:{exc}"

    # Normal entry: ext is real, url is already set (URL-encoded in parse_actas).
    out_name = f"{record['year']}_{safe_title}.{record['ext']}"
    out_path = dest_dir / out_name

    if out_path.exists():
        return "skip"

    try:
        resp = session.get(record["url"], headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return "ok"
    except Exception as exc:
        return f"error:{exc}"


def main():
    parser = argparse.ArgumentParser(description="Descarga actas municipales Esparza")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo listar, no descargar archivos")
    parser.add_argument("--output-dir", default=None,
                        help="Directorio raíz de salida (default: ../data/actas)")
    parser.add_argument("--section", nargs="*",
                        choices=list(SECCIONES.keys()), default=list(SECCIONES.keys()),
                        help="Sección(es) a procesar (default: todas)")
    parser.add_argument("--years", nargs="*", default=None,
                        help="Año(s) a incluir, ej. 2024 2025 2026 (default: todos)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent
    output_root = Path(args.output_dir) if args.output_dir else root_dir / "data" / "actas"

    session = requests.Session()
    all_records: list[dict] = []

    secciones = {k: v for k, v in SECCIONES.items() if k in args.section}

    for seccion, path in secciones.items():
        url = BASE_URL + path
        print(f"\n[{seccion}] {url}")
        dest_dir = output_root / seccion
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            soup = fetch_page(url, session)
        except Exception as exc:
            print(f"  [!] Error al cargar página: {exc}")
            continue

        records = parse_actas(soup, seccion)
        print(f"  Encontradas: {len(records)} actas")

        if args.years is not None:
            records = [r for r in records if r["year"] in args.years]
            print(f"  Filtradas por año {args.years}: {len(records)} actas")

        for rec in records:
            all_records.append(rec)
            if args.dry_run:
                print(f"    [{rec['year']}] {rec['title']} ({rec['ext']})")
            else:
                status = download_file(rec, dest_dir, session)
                marker = "✓" if status == "ok" else ("·" if status == "skip" else "✗")
                print(f"    {marker} {rec['year']} — {rec['title'][:60]}")
                if status.startswith("error"):
                    print(f"       {status}")
                time.sleep(RATE_LIMIT_SECS)

    # Write inventory CSV
    if all_records:
        csv_path = output_root / "inventario_actas.csv"
        if not args.dry_run:
            output_root.mkdir(parents=True, exist_ok=True)
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(all_records[0].keys()))
                writer.writeheader()
                writer.writerows(all_records)
            print(f"\nInventario guardado: {csv_path}")

        print(f"\nTotal: {len(all_records)} actas "
              f"({sum(1 for r in all_records if r['ext']=='pdf')} PDF, "
              f"{sum(1 for r in all_records if r['ext']=='docx')} DOCX)")


if __name__ == "__main__":
    main()
