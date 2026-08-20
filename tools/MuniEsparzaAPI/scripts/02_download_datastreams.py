#!/usr/bin/env python3
"""Download datastream payloads and original endpoint files from the Esparza Junar catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from junar_common import (
    JUNAR_SERVER_PAGE_CAP,
    PAGINATION_BOUNDARY_ROWS,
    ROOT,
    RateLimiter,
    content_hash_json,
    count_rows_and_columns,
    detect_extension_from_url,
    detect_junar_file_redirect,
    detect_pii_in_resource,
    endpoint_url,
    is_junar_list_of_lists,
    load_config,
    load_settings,
    read_json,
    request_with_retries,
    resource_category,
    resource_guid,
    resource_title,
    resource_type,
    safe_slug,
    setup_logging,
    write_json,
)


JSON_FORMATS = {"json", "ajson", "pjson"}


def formats_for_resource(resource: dict[str, Any], config: dict[str, Any]) -> list[str]:
    ds_cfg = config.get("datastreams", {})
    default = list(ds_cfg.get("formats_default", ["ajson"]))
    category = resource_category(resource)
    priority = ds_cfg.get("formats_priority_categories", {})
    return list(dict.fromkeys(priority.get(category, default)))


def looks_like_datastream(resource: dict[str, Any]) -> bool:
    guid = resource_guid(resource)
    if not guid:
        return False
    rtype = resource_type(resource).lower()
    if not rtype:
        return True
    return rtype in {"ds", "dt", "datastream", "dataset", "table", "data"}


def datastream_url(base_url: str, guid: str, fmt: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", f"datastreams/{guid}/data.{fmt}/")


def save_binary(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def follow_xls_redirect(
    session: requests.Session,
    redirect_payload: dict[str, Any],
    out_base: Path,
    settings,
    limiter,
    logger,
) -> dict[str, Any]:
    """Follow a Junar REDIRECT JSON to download the real XLS/XLSX file."""
    furi = redirect_payload.get("fUri", "")
    redirect_host = urlparse(furi).netloc if furi else "unknown"

    # Save the redirect metadata alongside the real file.
    redirect_meta_path = out_base.with_suffix(out_base.suffix + ".redirect.json")
    save_binary(redirect_meta_path, json.dumps(redirect_payload, ensure_ascii=False, indent=2).encode("utf-8"))

    try:
        limiter.wait()
        resp = session.get(furi, timeout=settings.timeout_seconds)
        if resp.status_code != 200:
            logger.warning("XLS redirect falló HTTP %s: %s", resp.status_code, furi[:80])
            return {
                "status": "redirect_failed",
                "redirect_http_status": resp.status_code,
                "redirect_uri_host": redirect_host,
                "redirect_metadata_path": str(redirect_meta_path.relative_to(ROOT)),
            }

        # Determine real extension from Content-Disposition or URL.
        real_ext = ".xlsx"
        content_disp = resp.headers.get("Content-Disposition", "")
        if ".xls" in content_disp and ".xlsx" not in content_disp:
            real_ext = ".xls"
        elif ".xlsx" in furi:
            real_ext = ".xlsx"
        elif ".xls" in furi:
            real_ext = ".xls"

        real_path = out_base.with_suffix(real_ext) if real_ext != out_base.suffix else out_base
        save_binary(real_path, resp.content)
        logger.info("XLS redirect seguido OK (%s bytes): %s", len(resp.content), real_path.name)
        return {
            "status": "ok_redirect_followed",
            "redirect_followed": True,
            "redirect_uri_host": redirect_host,
            "bytes": len(resp.content),
            "path": str(real_path.relative_to(ROOT)),
            "redirect_metadata_path": str(redirect_meta_path.relative_to(ROOT)),
        }
    except Exception as exc:
        logger.warning("Excepción siguiendo XLS redirect: %s", exc)
        return {
            "status": "redirect_failed",
            "redirect_uri_host": redirect_host,
            "error": str(exc),
            "redirect_metadata_path": str(redirect_meta_path.relative_to(ROOT)),
        }


def download_json_pages(
    session: requests.Session,
    url: str,
    params_base: dict[str, Any],
    settings,
    limiter,
    logger,
    out_base: Path,
    page_limit: int,
    max_pages: int,
) -> dict[str, Any]:
    """Download JSON-ish datastream pages. Handles Junar list-of-lists and dict formats."""
    pages_dir = out_base.with_suffix("")
    pages_dir.mkdir(parents=True, exist_ok=True)
    combined_records: list[Any] = []
    page_hashes: set[str] = set()
    status = "ok"
    last_status_code: int | None = None
    row_count: int | None = None
    col_count: int | None = None
    lol_header: list[Any] | None = None
    data_offset = 0
    last_page_items = 0

    for page_idx in range(max_pages):
        offset = data_offset if lol_header is not None or page_idx == 0 else page_idx * page_limit
        params = {**params_base, "limit": page_limit, "offset": offset}
        response = request_with_retries(session, url, settings, limiter, logger, params=params)
        last_status_code = response.status_code
        page_path = pages_dir / f"page_{page_idx + 1:04d}_offset_{offset}.json"

        if response.status_code != 200:
            save_binary(page_path.with_suffix(f".http_{response.status_code}.txt"), response.content)
            status = f"http_{response.status_code}"
            break

        try:
            payload = response.json()
        except ValueError:
            save_binary(page_path.with_suffix(".raw"), response.content)
            status = "non_json"
            break

        payload_hash = content_hash_json(payload)
        if payload_hash in page_hashes:
            logger.warning("Payload repetido; posible offset ignorado: %s", url)
            # Keep as explicit uncertain status; do NOT convert to ok.
            status = "possible_truncation_repeated_payload"
            break
        page_hashes.add(payload_hash)
        write_json(page_path, payload)

        if is_junar_list_of_lists(payload):
            result: list[Any] = payload["result"]
            total_items = len(result)
            last_page_items = total_items

            if page_idx == 0:
                lol_header = result[0] if result else []
                data_rows = result[1:]
                combined_records.extend(result)
            else:
                data_rows = result[1:] if result and result[0] == lol_header else result
                combined_records.extend(data_rows)

            rows = len(data_rows)
            cols = len(lol_header) if lol_header else None
            row_count = (row_count or 0) + rows
            col_count = cols if cols is not None else col_count
            data_offset += rows

            if total_items < JUNAR_SERVER_PAGE_CAP or rows == 0:
                break
        else:
            rows, cols = count_rows_and_columns(payload)
            last_page_items = rows or 0
            row_count = rows if row_count is None else row_count + (rows or 0)
            col_count = max(col_count or 0, cols or 0) if cols is not None else col_count

            if isinstance(payload, list):
                combined_records.extend(payload)
            elif isinstance(payload, dict):
                for key in ("results", "records", "data", "items"):
                    if isinstance(payload.get(key), list):
                        combined_records.extend(payload[key])
                        break
                else:
                    result_val = payload.get("result")
                    if isinstance(result_val, dict):
                        for nested in ("records", "results", "data", "items"):
                            if isinstance(result_val.get(nested), list):
                                combined_records.extend(result_val[nested])
                                break

            if rows is None or rows == 0 or rows < page_limit:
                break

    if combined_records:
        write_json(out_base, combined_records)
    else:
        write_json(out_base, {"status": status, "note": "Ver páginas crudas en el directorio contiguo."})

    # Detect possible truncation: row count at a known boundary.
    possible_truncation = False
    pagination_warning = False
    warning_reason = ""
    if status == "possible_truncation_repeated_payload":
        possible_truncation = True
        pagination_warning = True
        warning_reason = "repeated_payload_offset_stop"
    elif isinstance(row_count, int) and row_count in PAGINATION_BOUNDARY_ROWS:
        possible_truncation = True
        pagination_warning = True
        warning_reason = "row_count_matches_page_boundary"

    return {
        "status": status,
        "http_status": last_status_code,
        "rows_detected": row_count,
        "cols_detected": col_count,
        "pages_downloaded": len(page_hashes),
        "last_page_items": last_page_items,
        "possible_truncation": possible_truncation,
        "pagination_warning": pagination_warning,
        "warning_reason": warning_reason if warning_reason else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga vistas de datos y endpoints originales.")
    parser.add_argument("--catalog", default="data/raw/catalog/resources_unique.json")
    parser.add_argument("--only-guid", default=None, help="Descargar solo un GUID específico.")
    parser.add_argument("--max-resources", type=int, default=None, help="Límite para pruebas.")
    parser.add_argument("--force", action="store_true", help="Re-descargar aunque los archivos existan.")
    parser.add_argument("--no-endpoints", action="store_true", help="No descargar endpoint original.")
    args = parser.parse_args()

    config = load_config()
    settings = load_settings(config)
    logger = setup_logging("02_download_datastreams")
    limiter = RateLimiter(settings.requests_per_second)

    # Fallback to legacy catalog name if unique file not found yet.
    catalog_path = ROOT / args.catalog
    if not catalog_path.exists():
        fallback = ROOT / "data/raw/catalog/resources_all.json"
        if fallback.exists():
            catalog_path = fallback
        else:
            raise SystemExit(f"No existe el catálogo: {catalog_path}. Ejecute primero 01_snapshot_catalog.py")

    resources: list[dict[str, Any]] = read_json(catalog_path)
    if args.only_guid:
        resources = [r for r in resources if resource_guid(r) == args.only_guid]
    if args.max_resources:
        resources = resources[: args.max_resources]

    ds_cfg = config.get("datastreams", {})
    out_dir = ROOT / str(ds_cfg.get("output_dir", "data/raw/datastreams"))
    page_limit = int(ds_cfg.get("page_limit", 5000))
    max_pages = int(ds_cfg.get("max_pages_per_datastream", 200))
    skip_existing = bool(ds_cfg.get("skip_existing", True)) and not args.force

    endpoint_cfg = config.get("endpoint_downloads", {})
    endpoints_enabled = bool(endpoint_cfg.get("enabled", True)) and not args.no_endpoints
    endpoints_dir = ROOT / str(endpoint_cfg.get("output_dir", "data/raw/endpoints"))
    endpoint_skip_existing = bool(endpoint_cfg.get("skip_existing", True)) and not args.force
    allowed_extensions = set(endpoint_cfg.get("allowed_extensions", []))

    session = requests.Session()
    manifest: list[dict[str, Any]] = []

    logger.info("Recursos a evaluar: %s", len(resources))
    for idx, resource in enumerate(resources, start=1):
        guid = resource_guid(resource)
        if not guid:
            continue
        title = resource_title(resource)
        category = resource_category(resource)
        rtype = resource_type(resource)
        category_slug = safe_slug(category)
        title_slug = safe_slug(title, max_len=60)
        prefix = f"{category_slug}/{guid}__{title_slug}"

        # PII detection from metadata alone.
        pii_terms_meta = detect_pii_in_resource(resource)

        item_manifest: dict[str, Any] = {
            "guid": guid,
            "title": title,
            "category": category,
            "type": rtype,
            "datastream_attempted": False,
            "downloads": [],
            "endpoint_download": None,
            "contains_possible_pii": bool(pii_terms_meta),
            "pii_terms_detected": pii_terms_meta,
        }

        logger.info("[%s/%s] %s | %s | %s", idx, len(resources), guid, category, title)

        if looks_like_datastream(resource):
            item_manifest["datastream_attempted"] = True
            for fmt in formats_for_resource(resource, config):
                url = datastream_url(settings.base_url, guid, fmt)
                params = {"auth_key": settings.api_key}
                out_path = out_dir / f"{prefix}.{fmt}"

                if skip_existing and out_path.exists():
                    logger.info("Existe, omitiendo: %s", out_path)
                    item_manifest["downloads"].append({
                        "format": fmt,
                        "status": "skipped_existing",
                        "path": str(out_path.relative_to(ROOT)),
                    })
                    continue

                try:
                    if fmt in JSON_FORMATS:
                        result = download_json_pages(
                            session, url, params, settings, limiter, logger,
                            out_path, page_limit, max_pages,
                        )
                        result.update({"format": fmt, "path": str(out_path.relative_to(ROOT)), "url": url})
                        # Check downloaded data for PII in column headers.
                        if result.get("status") in ("ok", "possible_truncation_repeated_payload"):
                            try:
                                page_dir = out_path.with_suffix("")
                                first_page = page_dir / "page_0001_offset_0.json"
                                if first_page.exists():
                                    import json as _json
                                    page_data = _json.loads(first_page.read_bytes())
                                    if is_junar_list_of_lists(page_data):
                                        header = page_data["result"][0]
                                        pii_from_data = detect_pii_in_resource(resource, header)
                                        if pii_from_data:
                                            item_manifest["contains_possible_pii"] = True
                                            merged = list(set(item_manifest["pii_terms_detected"] + pii_from_data))
                                            item_manifest["pii_terms_detected"] = merged
                            except Exception:
                                pass
                        item_manifest["downloads"].append(result)
                    else:
                        # Non-JSON format (csv, xls, xlsx).
                        response = request_with_retries(
                            session, url, settings, limiter, logger,
                            params={**params, "limit": page_limit},
                        )
                        if response.status_code == 200:
                            content = response.content
                            redirect_payload = detect_junar_file_redirect(
                                content, response.headers.get("Content-Type")
                            )
                            if redirect_payload:
                                # Follow the S3 redirect to get the real file.
                                redirect_result = follow_xls_redirect(
                                    session, redirect_payload, out_path, settings, limiter, logger
                                )
                                redirect_result["format"] = fmt
                                redirect_result["url"] = url
                                item_manifest["downloads"].append(redirect_result)
                            else:
                                save_binary(out_path, content)
                                item_manifest["downloads"].append({
                                    "format": fmt,
                                    "status": "ok",
                                    "http_status": 200,
                                    "bytes": len(content),
                                    "path": str(out_path.relative_to(ROOT)),
                                    "url": url,
                                })
                        else:
                            err_path = out_path.with_suffix(out_path.suffix + f".http_{response.status_code}.txt")
                            save_binary(err_path, response.content)
                            item_manifest["downloads"].append({
                                "format": fmt,
                                "status": f"http_{response.status_code}",
                                "http_status": response.status_code,
                                "path": str(err_path.relative_to(ROOT)),
                                "url": url,
                            })
                except Exception as exc:
                    logger.exception("Falló %s %s: %s", guid, fmt, exc)
                    item_manifest["downloads"].append({
                        "format": fmt,
                        "status": "exception",
                        "error": str(exc),
                        "url": url,
                    })

        if endpoints_enabled:
            ep_url = endpoint_url(resource)
            if ep_url:
                ext = detect_extension_from_url(ep_url)
                if allowed_extensions and ext not in allowed_extensions:
                    item_manifest["endpoint_download"] = {
                        "status": "extension_skipped",
                        "extension": ext,
                        "url": ep_url,
                    }
                else:
                    ep_path = endpoints_dir / f"{prefix}{ext}"
                    if endpoint_skip_existing and ep_path.exists():
                        item_manifest["endpoint_download"] = {
                            "status": "skipped_existing",
                            "path": str(ep_path.relative_to(ROOT)),
                            "url": ep_url,
                        }
                    else:
                        try:
                            response = request_with_retries(session, ep_url, settings, limiter, logger)
                            if response.status_code == 200:
                                save_binary(ep_path, response.content)
                                item_manifest["endpoint_download"] = {
                                    "status": "ok",
                                    "http_status": 200,
                                    "bytes": len(response.content),
                                    "path": str(ep_path.relative_to(ROOT)),
                                    "url": ep_url,
                                }
                            else:
                                item_manifest["endpoint_download"] = {
                                    "status": f"http_{response.status_code}",
                                    "http_status": response.status_code,
                                    "url": ep_url,
                                }
                        except Exception as exc:
                            logger.exception("Falló endpoint %s: %s", ep_url, exc)
                            item_manifest["endpoint_download"] = {
                                "status": "exception",
                                "error": str(exc),
                                "url": ep_url,
                            }

        manifest.append(item_manifest)
        if idx % 25 == 0:
            write_json(ROOT / "data/processed/download_manifest.partial.json", manifest)

    write_json(ROOT / "data/processed/download_manifest.json", manifest)
    logger.info("Descarga terminada. Manifest: data/processed/download_manifest.json")


if __name__ == "__main__":
    main()
