#!/usr/bin/env python3
"""
Scraper general de documentos CMS — muniesparza.go.cr

Descarga todos los documentos publicados en secciones del CMS municipal
que no son actas (ya cubiertas por 09_scrape_actas.py).

URL de descarga: https://muniesparza.go.cr/files/folder/<UUID>.<ext>

Uso:
    python 10_scrape_documentos_cms.py [--dry-run] [--output-dir PATH]

Salida por carpeta:
    data/cms/transparencia/        — rendición de cuentas, PAO, planes, plan vial
    data/cms/presupuestos/         — presupuestos ordinarios (PDFs)
    data/cms/auditoria/            — informes de auditoría interna
    data/cms/reglamentos/          — reglamentos municipales y nacionales
    data/cms/estudios_tarifarios/  — estudios tarifarios 2021-2025
    data/cms/cobros/               — morosos, cobros judiciales, arreglos de pago
    data/cms/comisiones/           — composición y documentos de comisiones
    data/cms/cartografia/          — mapas de valores por zonas homogéneas
    data/cms/varios/               — manuales, becas, perfil Ley 8461, denuncias
    data/cms/inventario_cms.csv    — índice completo
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://muniesparza.go.cr"
FILES_URL = "https://muniesparza.go.cr/files/folder/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-CR,es;q=0.9",
}

RATE_LIMIT_SECS = 0.8

# (carpeta_destino, [(articulo_id, path, nombre_seccion), ...])
SECCIONES = [
    ("transparencia", [
        (430, "/articulo/430/informes-planes-y",          "Informes Planes y Evaluaciones"),
        (335, "/articulo/335/planes-anuales-operativos",  "Planes Anuales Operativos"),
        (433, "/articulo/433/recaudacion-por-periodo",    "Recaudacion por Periodo Fiscal"),
        (339, "/articulo/339/listado-de-morosos",         "Listado de Morosos"),
        (340, "/articulo/340/cobros-judiciales",          "Cobros Judiciales"),
        (341, "/articulo/341/arreglos-de-pago",           "Arreglos de Pago"),
    ]),
    ("presupuestos", [
        (336, "/articulo/336/presupuestos",               "Presupuestos Ordinarios"),
    ]),
    ("auditoria", [
        (611, "/articulo/611/informes-de-auditoria",      "Informes de Auditoria Interna"),
        (586, "/articulo/586/denuncias-ante-la",          "Denuncias ante Auditoria"),
    ]),
    ("reglamentos", [
        (515, "/articulo/515/reglamentos-municipales",    "Reglamentos Municipales"),
        (516, "/articulo/516/reglamentos-nacionales-",    "Reglamentos Nacionales"),
    ]),
    ("estudios_tarifarios", [
        (589, "/articulo/589/estudios-tarifarios-2021",   "Estudios Tarifarios 2021"),
        (587, "/articulo/587/estudios-tarifarios-2022",   "Estudios Tarifarios 2022"),
        (588, "/articulo/588/estudios-tarifarios-2023",   "Estudios Tarifarios 2023"),
        (600, "/articulo/600/estudios-tarifarios-2024",   "Estudios Tarifarios 2024"),
        (608, "/articulo/608/estudios-tarifarios-2025",   "Estudios Tarifarios 2025"),
    ]),
    ("comisiones", [
        (75,  "/articulo/75/comisiones-municipales",      "Comisiones Municipales"),
    ]),
    ("cartografia", [
        (571, "/articulo/571/mapa-de-valores",            "Mapa Valores Zonas Homogeneas"),
    ]),
    ("varios", [
        (226, "/articulo/226/manual-de-clases",           "Manual Clases Puestos"),
        (227, "/articulo/227/manual-de-organizacion",     "Manual Organizacion"),
        (89,  "/articulo/89/becas",                       "Becas"),
        (594, "/articulo/594/perfil-para-la",             "Perfil Ley 8461"),
    ]),
]


def fetch_page(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_docs(soup: BeautifulSoup, seccion_nombre: str, articulo_id: int) -> list[dict]:
    records = []
    for a in soup.find_all("a", onclick=True):
        m = re.search(r"openDocumentArticle\('([^']+)'\)", a["onclick"])
        if not m:
            continue
        filename = m.group(1)
        uuid, _, ext = filename.rpartition(".")
        title = a.get_text(strip=True)
        records.append({
            "seccion": seccion_nombre,
            "articulo_id": articulo_id,
            "title": title,
            "uuid": uuid,
            "ext": ext.lower(),
            "filename": filename,
            "url": FILES_URL + filename,
        })
    return records


def download_file(record: dict, dest_dir: Path, session: requests.Session) -> str:
    safe_title = re.sub(r'[^\w\s\-]', '', record["title"])[:80].strip()
    out_name = f"{safe_title}.{record['ext']}"
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
    parser = argparse.ArgumentParser(description="Descarga documentos CMS Municipalidad Esparza")
    parser.add_argument("--dry-run", action="store_true", help="Solo listar, no descargar")
    parser.add_argument("--output-dir", default=None, help="Directorio raíz (default: ../data/cms)")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    output_root = Path(args.output_dir) if args.output_dir else root_dir / "data" / "cms"

    session = requests.Session()
    all_records: list[dict] = []

    for carpeta, paginas in SECCIONES:
        dest_dir = output_root / carpeta
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        for aid, path, nombre in paginas:
            url = BASE_URL + path
            print(f"\n[{carpeta}/{nombre}] {url}")

            try:
                soup = fetch_page(url, session)
                time.sleep(RATE_LIMIT_SECS)
            except Exception as exc:
                print(f"  [!] Error: {exc}")
                continue

            records = parse_docs(soup, nombre, aid)
            print(f"  Encontrados: {len(records)} documentos")

            for rec in records:
                all_records.append({**rec, "carpeta": carpeta})
                if args.dry_run:
                    print(f"    {rec['title'][:70]} ({rec['ext']})")
                else:
                    status = download_file(rec, dest_dir, session)
                    marker = "✓" if status == "ok" else ("·" if status == "skip" else "✗")
                    print(f"    {marker} {rec['title'][:65]}")
                    if status.startswith("error"):
                        print(f"       {status}")
                    time.sleep(RATE_LIMIT_SECS)

    if all_records:
        if not args.dry_run:
            output_root.mkdir(parents=True, exist_ok=True)
        csv_path = output_root / "inventario_cms.csv"
        if not args.dry_run:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(all_records[0].keys()))
                writer.writeheader()
                writer.writerows(all_records)
            print(f"\nInventario: {csv_path}")

        by_carpeta: dict[str, int] = {}
        for r in all_records:
            by_carpeta[r["carpeta"]] = by_carpeta.get(r["carpeta"], 0) + 1

        print(f"\nTotal: {len(all_records)} documentos")
        for c, n in sorted(by_carpeta.items(), key=lambda x: -x[1]):
            print(f"  {n:4d}  {c}/")


if __name__ == "__main__":
    main()
