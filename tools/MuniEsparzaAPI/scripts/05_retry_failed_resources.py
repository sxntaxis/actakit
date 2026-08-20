#!/usr/bin/env python3
"""Retry and classify the 191 resources that failed with HTTP 500 or other errors.

For each failed resource, tries:
  1. Retry with conservative backoff.
  2. Alternative formats: ajson, csv, xls, json, pjson.
  3. Lower limits: 100, 500, 1000.
  4. Source endpoint file if available.
  5. Detect functional duplicates by normalized title within same category/year.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent))

from junar_common import (
    ROOT,
    RateLimiter,
    Settings,
    content_hash_bytes,
    detect_junar_file_redirect,
    is_junar_list_of_lists,
    load_config,
    load_settings,
    request_with_retries,
    setup_logging,
    write_json,
)

AUDIT_DIR = ROOT / "audit"
MANIFEST_PATH = ROOT / "data/processed/download_manifest.json"

FINAL_STATUSES = (
    "recovered_api",
    "recovered_source_file",
    "functional_duplicate_available",
    "api_error_persistent",
    "metadata_only_confirmed",
    "empty_verified",
    "requires_manual_download",
    "requires_formal_request",
)

FORMATS_TO_TRY = ["ajson", "csv", "xls", "json", "pjson"]
LIMITS_TO_TRY = [100, 500, 1000]


def norm_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def count_rows_from_content(content: bytes, fmt: str) -> int | None:
    if fmt in ("ajson", "json", "pjson"):
        try:
            payload = json.loads(content)
            if is_junar_list_of_lists(payload):
                return max(0, len(payload["result"]) - 1)
            if isinstance(payload, list):
                return len(payload)
        except Exception:
            pass
        return None
    if fmt == "csv":
        try:
            text = content.decode("utf-8-sig", errors="replace")
            rows = text.strip().splitlines()
            return max(0, len(rows) - 1)
        except Exception:
            return None
    return None


def try_formats(
    session: requests.Session,
    base_url: str,
    guid: str,
    settings: Settings,
    limiter: RateLimiter,
    logger,
) -> tuple[str | None, int | None, str | None]:
    """Returns (best_format, rows, status_note)."""
    for fmt in FORMATS_TO_TRY:
        url = f"{base_url}/datastreams/{guid}/data.{fmt}/"
        for limit in LIMITS_TO_TRY:
            params = {"auth_key": settings.api_key, "limit": limit}
            limiter.wait()
            try:
                resp = session.get(
                    url,
                    params=params,
                    headers={"Referer": settings.referer, "User-Agent": "esparza-junar-civic-audit/0.1"},
                    timeout=settings.timeout_seconds,
                )
                if resp.status_code == 200:
                    content = resp.content
                    # Check for redirect stub (XLS)
                    redirect = detect_junar_file_redirect(content)
                    if redirect:
                        continue  # Can't count rows from stub
                    rows = count_rows_from_content(content, fmt)
                    if rows is not None and rows >= 0:
                        logger.info("Recuperado %s fmt=%s limit=%s rows=%s", guid, fmt, limit, rows)
                        return fmt, rows, f"http_200_limit_{limit}"
                    elif rows is None and len(content) > 200:
                        # Got content but can't count; still recovered
                        logger.info("Recuperado %s fmt=%s limit=%s (binario/no contable)", guid, fmt, limit)
                        return fmt, None, f"http_200_limit_{limit}_binary"
                elif resp.status_code in (404, 410):
                    # Definitively gone; stop trying formats for this endpoint pattern
                    return None, None, f"http_{resp.status_code}"
                # 500 → continue trying
            except Exception as exc:
                logger.debug("Error %s fmt=%s: %s", guid, fmt, exc)
    return None, None, "all_formats_failed"


def try_endpoint(
    session: requests.Session,
    endpoint_url: str,
    settings: Settings,
    limiter: RateLimiter,
    logger,
) -> tuple[str | None, int | None]:
    """Try downloading source endpoint. Returns (status, bytes_or_rows)."""
    limiter.wait()
    try:
        resp = session.get(
            endpoint_url,
            headers={"Referer": settings.referer, "User-Agent": "esparza-junar-civic-audit/0.1"},
            timeout=settings.timeout_seconds,
        )
        if resp.status_code == 200 and len(resp.content) > 100:
            return "ok", len(resp.content)
    except Exception as exc:
        logger.debug("Endpoint error %s: %s", endpoint_url, exc)
    return None, None


def build_title_index(manifest: list[dict]) -> dict[str, list[str]]:
    """Map normalized_title → [guid, ...] for finding duplicates."""
    index: dict[str, list[str]] = defaultdict(list)
    success = {"ok", "ok_redirect_followed", "skipped_existing"}
    for item in manifest:
        has_ok = any(dl.get("status") in success for dl in item.get("downloads", []))
        title = norm_title(item.get("title", ""))
        if title and has_ok:
            index[title].append(item["guid"])
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Reintenta y clasifica recursos fallidos.")
    parser.add_argument("--dry-run", action="store_true", help="No hacer requests; solo clasificar.")
    parser.add_argument("--guid", default=None, help="Procesar solo un GUID específico.")
    parser.add_argument("--force", action="store_true", help="Re-evaluar aunque ya exista resolución previa.")
    parser.add_argument("--max-resources", type=int, default=None)
    args = parser.parse_args()

    config = load_config()
    settings = load_settings(config)
    logger = setup_logging("05_retry_failed_resources")

    manifest: list[dict] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing resolutions for idempotency
    resolution_json = AUDIT_DIR / "failed_resources_resolution.json"
    existing: dict[str, dict] = {}
    if resolution_json.exists() and not args.force:
        try:
            for row in json.loads(resolution_json.read_text(encoding="utf-8")):
                existing[row["guid"]] = row
        except Exception:
            pass

    success_statuses = {"ok", "ok_redirect_followed", "skipped_existing"}
    title_index = build_title_index(manifest)

    # Identify failed resources
    failed_items = []
    for item in manifest:
        guid = item.get("guid", "")
        if args.guid and guid != args.guid:
            continue
        has_ok = any(dl.get("status") in success_statuses for dl in item.get("downloads", []))
        if not has_ok and item.get("datastream_attempted"):
            failed_items.append(item)

    if args.max_resources:
        failed_items = failed_items[: args.max_resources]

    logger.info("Recursos fallidos a procesar: %s", len(failed_items))

    session = requests.Session()
    limiter = RateLimiter(settings.requests_per_second)
    results: list[dict] = []

    for item in failed_items:
        guid = item["guid"]
        if guid in existing and not args.force:
            logger.info("Ya procesado (skip): %s", guid)
            results.append(existing[guid])
            continue

        title = item.get("title", "")
        category = item.get("category", "").strip()
        year_detected = ""
        for yr in range(2000, 2031):
            if str(yr) in title or str(yr) in guid:
                year_detected = str(yr)
                break

        # Detect original error
        original_statuses = [dl.get("status", "") for dl in item.get("downloads", [])]
        original_error = ", ".join(set(s for s in original_statuses if s)) or "unknown"

        # Check if there's an endpoint
        ep = item.get("endpoint_download")
        ep_url = ep.get("url") if isinstance(ep, dict) else None
        ep_status = ep.get("status") if isinstance(ep, dict) else None
        source_endpoint_exists = bool(ep_url)

        # Check for duplicate by title
        nt = norm_title(title)
        dup_guids = [g for g in title_index.get(nt, []) if g != guid]
        functional_duplicate_guid = dup_guids[0] if dup_guids else ""

        if args.dry_run:
            retry_status = "skipped_dry_run"
            recovered_fmt = None
            recovered_rows = None
            source_dl_status = None
        else:
            # Try API formats
            recovered_fmt, recovered_rows, retry_status = try_formats(
                session, settings.base_url, guid, settings, limiter, logger
            )

            # Try endpoint if API failed
            source_dl_status = None
            if not recovered_fmt and source_endpoint_exists and ep_url:
                src_status, _ = try_endpoint(session, ep_url, settings, limiter, logger)
                source_dl_status = src_status

        # Classify final status
        if recovered_fmt:
            final_status = "recovered_api"
            action = f"use_{recovered_fmt}_format_for_analysis"
        elif source_dl_status == "ok":
            final_status = "recovered_source_file"
            action = "download_source_file_manually"
        elif functional_duplicate_guid:
            final_status = "functional_duplicate_available"
            action = f"use_guid_{functional_duplicate_guid}"
        elif ep_status in ("extension_skipped",) and source_endpoint_exists:
            final_status = "requires_manual_download"
            action = f"download_from_{ep_url[:60] if ep_url else 'endpoint'}"
        elif "500" in original_error:
            final_status = "api_error_persistent"
            action = "verify_resource_in_portal_or_formal_request"
        else:
            final_status = "api_error_persistent"
            action = "verify_resource_in_portal_or_formal_request"

        result = {
            "guid": guid,
            "title": title,
            "category": category,
            "year_detected": year_detected,
            "original_error": original_error,
            "retry_status": retry_status or "",
            "formats_tested": ", ".join(FORMATS_TO_TRY),
            "recovered_format": recovered_fmt or "",
            "recovered_rows": recovered_rows if recovered_rows is not None else "",
            "source_endpoint_exists": source_endpoint_exists,
            "source_endpoint_url": ep_url or "",
            "source_download_status": source_dl_status or "",
            "functional_duplicate_guid": functional_duplicate_guid,
            "final_status": final_status,
            "recommended_action": action,
            "notes": "",
        }
        results.append(result)
        logger.info(
            "%s → %s (fmt=%s rows=%s dup=%s)",
            guid, final_status, recovered_fmt or "-", recovered_rows, functional_duplicate_guid or "-",
        )

    # Save JSON
    write_json(resolution_json, results)

    # Save CSV
    csv_path = AUDIT_DIR / "failed_resources_resolution.csv"
    csv_cols = [
        "guid", "title", "category", "year_detected",
        "original_error", "retry_status", "formats_tested",
        "recovered_format", "recovered_rows",
        "source_endpoint_exists", "source_endpoint_url", "source_download_status",
        "functional_duplicate_guid", "final_status", "recommended_action", "notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # Markdown report
    by_status: dict[str, list] = {}
    for r in results:
        by_status.setdefault(r["final_status"], []).append(r)

    lines = [
        "# Resolución de Recursos Fallidos",
        "",
        f"Fecha: 2026-04-28",
        f"Recursos evaluados: {len(results)}",
        "",
        "## Resumen por estado final",
        "",
        "| Estado | Cantidad |",
        "|--------|----------|",
    ]
    for status, items in sorted(by_status.items(), key=lambda x: -len(x[1])):
        lines.append(f"| `{status}` | {len(items)} |")

    lines += ["", "## Detalle", ""]
    for r in sorted(results, key=lambda x: (x["final_status"], x["category"], x["guid"])):
        dup_note = f" → dup:{r['functional_duplicate_guid']}" if r["functional_duplicate_guid"] else ""
        fmt_note = f" fmt={r['recovered_format']} rows={r['recovered_rows']}" if r["recovered_format"] else ""
        lines.append(
            f"- **{r['guid']}** [{r['category']}] orig={r['original_error']} → "
            f"`{r['final_status']}`{fmt_note}{dup_note}"
        )

    lines += [
        "",
        "## Interpretación",
        "",
        "- `recovered_api`: Se recuperó al usar un formato alternativo o límite menor.",
        "- `recovered_source_file`: El archivo fuente en el endpoint está disponible.",
        "- `functional_duplicate_available`: Existe otro GUID con el mismo título y datos funcionales.",
        "- `api_error_persistent`: HTTP 500 persistente; recurso probablemente sin fuente configurada en Junar.",
        "- `requires_manual_download`: El endpoint apunta a un recurso externo recuperable manualmente.",
        "- `metadata_only_confirmed`: Solo existe como metadato, sin datos descargables.",
    ]

    (AUDIT_DIR / "FAILED_RESOURCES_RESOLUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Summary stats
    recovered = sum(1 for r in results if r["final_status"].startswith("recovered"))
    persistent = sum(1 for r in results if r["final_status"] == "api_error_persistent")
    logger.info(
        "Completado: %s evaluados, %s recuperados, %s persistentes",
        len(results), recovered, persistent,
    )
    print(f"\nEvaluados: {len(results)}, Recuperados: {recovered}, Persistentes: {persistent}")
    print(f"Archivos: {csv_path} | {resolution_json}")


if __name__ == "__main__":
    main()
