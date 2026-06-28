#!/usr/bin/env python3
"""
Generic scraper for municipal council meeting minutes (actas).

Downloads PDF/DOCX files from a municipal website's CMS. The scraper
reads a configuration file (config.yaml or individual params) to
determine the URL structure, sections, and file naming.

Usage:
    python scrape_actas.py --config config.yaml [--dry-run] [--section concejo ...]
    python scrape_actas.py --url-base https://municipalidad.go.cr \\
        --section concejo=/articulo/123/actas \\
        [--output-dir ./data] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

HEADERS_DEFAULT = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-CR,es;q=0.9",
}
RATE_LIMIT_DEFAULT = 1.0


def load_config(config_path):
    """Load configuration from YAML or JSON."""
    path = Path(config_path)
    if path.suffix in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError:
            print("Error: PyYAML required for .yaml config. Install: pip install pyyaml")
            sys.exit(1)
        with open(path, encoding='utf-8') as f:
            return yaml.safe_load(f)
    elif path.suffix == '.json':
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    else:
        print(f"Error: unsupported config format: {path.suffix}")
        sys.exit(1)


def build_sections_from_config(config):
    """Build sections dict from scraping config section."""
    scrape_cfg = config.get('scraping', {})
    secciones = {}
    for name, sec_cfg in scrape_cfg.get('secciones', {}).items():
        secciones[name] = sec_cfg.get('path', f'/articulo/0/{name}')
    return secciones


def fetch_page(url: str, session: requests.Session, headers: dict) -> BeautifulSoup:
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_actas(soup: BeautifulSoup, seccion: str, url_base: str) -> list[dict]:
    """Extract acta entries from a fileTree page."""
    records = []
    current_year = None

    file_tree = soup.find("ul", class_="fileTree")
    if not file_tree:
        # Try alternative: look for any <ul> with document links
        file_tree = soup.find("ul", class_=re.compile(r"(files|documents|tree)", re.I))
    if not file_tree:
        print(f"  [!] No se encontró lista de archivos en {seccion}")
        return records

    for li in file_tree.find_all("li", recursive=True):
        year_link = li.find("a", href="#")
        if year_link and re.match(r"^\d{4}$", year_link.get_text(strip=True)):
            current_year = year_link.get_text(strip=True)
            continue

        onclick = li.find("a", onclick=True)
        if not onclick:
            continue

        match = re.search(r"openDocumentArticle\('([^']+)'\)", onclick["onclick"])
        if not match:
            continue

        filename = match.group(1)
        uuid, _, ext = filename.rpartition(".")
        title = onclick.get_text(strip=True)
        css_class = " ".join(li.get("class", []))

        records.append({
            "seccion": seccion,
            "year": current_year or "",
            "title": title,
            "uuid": uuid,
            "ext": ext.lower(),
            "filename": filename,
            "url": url_base.rstrip('/') + '/files/folder/' + quote(filename, safe=""),
            "css_class": css_class,
        })

    return records


def download_file(record: dict, dest_dir: Path, session: requests.Session,
                  headers: dict, url_base: str) -> str:
    """Download one acta file. Returns 'ok', 'skip', or 'error:<msg>'."""
    safe_title = re.sub(r'[^\w\s\-]', '', record.get("title") or '')[:80].strip()
    files_url = url_base.rstrip('/') + '/files/folder/'

    if record["ext"] not in ("pdf", "docx"):
        record["url"] = files_url + quote(record["filename"], safe="")
        try:
            resp = session.get(record["url"], headers=headers, timeout=60, stream=True)
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
            if out_path.is_symlink():
                return "error:symlink_detected"
            fd = os.open(out_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(head_bytes)
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
            except Exception:
                try:
                    os.unlink(out_path)
                except OSError:
                    pass
                raise
            return "ok"
        except FileExistsError:
            return "skip"
        except Exception as exc:
            return f"error:{exc}"

    out_name = f"{record['year']}_{safe_title}.{record['ext']}"
    out_path = dest_dir / out_name

    if out_path.exists():
        return "skip"

    if out_path.is_symlink():
        return "error:symlink_detected"

    try:
        resp = session.get(record["url"], headers=headers, timeout=60, stream=True)
        resp.raise_for_status()
        fd = os.open(out_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
        except Exception:
            try:
                os.unlink(out_path)
            except OSError:
                pass
            raise
        return "ok"
    except FileExistsError:
        return "skip"
    except Exception as exc:
        return f"error:{exc}"


def main():
    parser = argparse.ArgumentParser(description="Descarga actas municipales")
    parser.add_argument("--config", default=None, help="Ruta al archivo config.yaml")
    parser.add_argument("--url-base", default=None, help="URL base del sitio municipal")
    parser.add_argument("--section", nargs="*", default=None,
                        help="Sección(es) a procesar (formato: nombre=ruta, ej. concejo=/articulo/123/actas)")
    parser.add_argument("--output-dir", default=None, help="Directorio raíz de salida")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, no descargar")
    parser.add_argument("--years", nargs="*", default=None, help="Año(s) a incluir")
    args = parser.parse_args()

    # Resolve configuration
    config = None
    if args.config:
        config = load_config(args.config)

    if config:
        scrape_cfg = config.get('scraping', {})
        url_base = args.url_base or scrape_cfg.get('url_base', 'https://municipalidad-ejemplo.go.cr')
        headers = {**HEADERS_DEFAULT, **scrape_cfg.get('headers', {})}
        rate_limit = scrape_cfg.get('rate_limit_seg', RATE_LIMIT_DEFAULT)
        secciones = build_sections_from_config(config)
        vault_root = Path(config.get('vault_root', './'))
        output_root = Path(args.output_dir) if args.output_dir else \
            vault_root / scrape_cfg.get('output_dir', 'actas/descargadas')
    else:
        url_base = args.url_base or "https://municipalidad-ejemplo.go.cr"
        headers = HEADERS_DEFAULT
        rate_limit = RATE_LIMIT_DEFAULT
        secciones = {}
        if args.section:
            for s in args.section:
                if '=' in s:
                    name, path = s.split('=', 1)
                    secciones[name.strip()] = path.strip()
                else:
                    print(f"  [!] --section '{s}' no contiene '='; se ignora. Formato: nombre=ruta")
        output_root = Path(args.output_dir) if args.output_dir else Path("./actas/descargadas")

    if not secciones:
        print("Error: no hay secciones configuradas. Usá --section o config.yaml")
        sys.exit(1)

    session = requests.Session()
    all_records = []

    for seccion, path in secciones.items():
        url = url_base.rstrip('/') + path
        print(f"\n[{seccion}] {url}")
        dest_dir = output_root / seccion
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            soup = fetch_page(url, session, headers)
        except Exception as exc:
            print(f"  [!] Error al cargar página: {exc}")
            continue

        records = parse_actas(soup, seccion, url_base)
        print(f"  Encontradas: {len(records)} actas")

        if args.years:
            records = [r for r in records if r["year"] in args.years]
            print(f"  Filtradas por año {args.years}: {len(records)} actas")

        for rec in records:
            all_records.append(rec)
            if args.dry_run:
                print(f"    [{rec['year']}] {rec['title']} ({rec['ext']})")
            else:
                status = download_file(rec, dest_dir, session, headers, url_base)
                marker = "✓" if status == "ok" else ("·" if status == "skip" else "✗")
                print(f"    {marker} {rec['year']} — {rec['title'][:60]}")
                if status.startswith("error"):
                    print(f"       {status}")
                time.sleep(rate_limit)

    if all_records:
        csv_path = output_root / "inventario_actas.csv"
        if not args.dry_run:
            output_root.mkdir(parents=True, exist_ok=True)
            fieldnames = list(all_records[0].keys()) if all_records else []
            if csv_path.is_symlink():
                print(f"  ! Saltando escritura a symlink: {csv_path}")
            else:
                fd = os.open(csv_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
                try:
                    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(all_records)
                except FileExistsError:
                    print(f"  ! Archivo ya existe, se omite: {csv_path}")
                except Exception:
                    try:
                        os.unlink(csv_path)
                    except OSError:
                        pass
                    raise
            print(f"\nInventario guardado: {csv_path}")

        print(f"\nTotal: {len(all_records)} actas "
              f"({sum(1 for r in all_records if r['ext']=='pdf')} PDF, "
              f"{sum(1 for r in all_records if r['ext']=='docx')} DOCX)")


if __name__ == "__main__":
    main()
