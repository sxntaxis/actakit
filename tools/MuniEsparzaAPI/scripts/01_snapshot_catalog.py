#!/usr/bin/env python3
"""Download the full Junar resource catalog for datosabiertos.muniesparza.go.cr."""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from junar_common import (
    ROOT,
    RateLimiter,
    extract_results,
    load_config,
    load_settings,
    request_with_retries,
    setup_logging,
    write_json,
)


def build_params(api_key: str, limit: int, offset: int, order: str) -> dict[str, Any]:
    return {"auth_key": api_key, "limit": limit, "offset": offset, "order": order}


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga el catálogo completo de recursos Junar.")
    parser.add_argument("--limit", type=int, default=None, help="Tamaño de página del catálogo.")
    parser.add_argument("--max-pages", type=int, default=None, help="Límite de páginas para pruebas.")
    parser.add_argument("--order", default=None, help="Orden Junar: last, viewed, downloaded, top, etc.")
    args = parser.parse_args()

    config = load_config()
    settings = load_settings(config)
    logger = setup_logging("01_snapshot_catalog")
    limiter = RateLimiter(settings.requests_per_second)

    catalog_cfg = config.get("catalog", {})
    page_limit = args.limit or int(catalog_cfg.get("page_limit", 100))
    order = args.order or str(catalog_cfg.get("order", "last"))
    output_dir = ROOT / str(catalog_cfg.get("output_dir", "data/raw/catalog"))
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # all_raw collects every entry returned by every page, including duplicates.
    all_raw: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    unique_resources: list[dict[str, Any]] = []
    offset = 0
    page_number = 1
    api_reported_count: int | None = None

    session = requests.Session()
    resources_url = urljoin(settings.base_url + "/", "resources.json")

    logger.info("Iniciando descarga de catálogo: %s", resources_url)
    while True:
        params = build_params(settings.api_key, page_limit, offset, order)
        response = request_with_retries(session, resources_url, settings, limiter, logger, params=params)
        page_path = pages_dir / f"resources_page_{page_number:04d}_offset_{offset}.json"

        try:
            payload = response.json()
        except ValueError:
            page_path.write_bytes(response.content)
            logger.error("Respuesta no JSON en offset %s; guardada en %s", offset, page_path)
            break

        write_json(page_path, payload)

        if isinstance(payload, dict) and isinstance(payload.get("count"), int):
            api_reported_count = payload["count"]

        results = extract_results(payload)
        logger.info("Página %s offset=%s: %s recursos", page_number, offset, len(results))

        if not results:
            break

        # Collect raw entries (all, including duplicates).
        all_raw.extend(results)

        # Deduplicate into unique_resources.
        new_unique = 0
        for item in results:
            uid = str(item.get("guid") or item.get("id") or item.get("link") or id(item))
            if uid not in seen_ids:
                seen_ids.add(uid)
                unique_resources.append(item)
                new_unique += 1

        if new_unique == 0:
            logger.warning("No hubo recursos nuevos en esta página; deteniendo para evitar bucle.")
            break

        if args.max_pages and page_number >= args.max_pages:
            logger.info("max-pages alcanzado: %s", args.max_pages)
            break

        if api_reported_count is not None and len(unique_resources) >= api_reported_count:
            logger.info("count alcanzado: %s", api_reported_count)
            break

        offset += page_limit
        page_number += 1

    # Save raw (all entries, including duplicates from pagination).
    write_json(output_dir / "resources_raw_all_pages.json", all_raw)
    # Save deduplicated (canonical list for downstream scripts).
    write_json(output_dir / "resources_unique.json", unique_resources)
    # Legacy name kept for backward compatibility.
    write_json(output_dir / "resources_all.json", unique_resources)

    duplicate_count = len(all_raw) - len(unique_resources)
    catalog_summary = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "api_reported_count": api_reported_count,
        "raw_entries_count": len(all_raw),
        "unique_resources_count": len(unique_resources),
        "duplicate_count": duplicate_count,
        "pages_downloaded": page_number,
        "page_limit": page_limit,
        "order": order,
    }
    write_json(ROOT / "data/processed/catalog_summary.json", catalog_summary)
    write_json(
        output_dir / "catalog_manifest.json",
        catalog_summary,
    )
    logger.info(
        "Catálogo terminado: %s únicos (%s crudos, %s duplicados)",
        len(unique_resources), len(all_raw), duplicate_count,
    )


if __name__ == "__main__":
    main()
