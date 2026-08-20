#!/usr/bin/env python3
"""One-shot fix: follow S3 redirects for all XLS files that contain Junar REDIRECT JSON.

Run once after the initial download. Future runs use 02_download_datastreams.py which
handles this automatically.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import requests

from junar_common import ROOT, detect_junar_file_redirect, load_config, load_settings, setup_logging


def main() -> None:
    config = load_config()
    settings = load_settings(config)
    logger = setup_logging("fix_xls_redirects")

    manifest_path = ROOT / "data/processed/download_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("No existe download_manifest.json. Ejecute primero 02_download_datastreams.py")

    with manifest_path.open(encoding="utf-8") as f:
        manifest: list[dict] = json.load(f)

    session = requests.Session()
    headers = {"Referer": settings.referer, "User-Agent": "esparza-junar-civic-audit/0.1"}

    fixed = 0
    skipped = 0
    failed = 0

    for item in manifest:
        for dl in item.get("downloads", []):
            if dl.get("format") not in ("xls", "xlsx"):
                continue
            path_str = dl.get("path", "")
            if not path_str:
                continue
            xls_path = ROOT / path_str
            if not xls_path.exists():
                continue

            content = xls_path.read_bytes()
            redirect_payload = detect_junar_file_redirect(content)
            if not redirect_payload:
                skipped += 1
                continue

            furi = redirect_payload.get("fUri", "")
            if not furi:
                continue

            redirect_host = urlparse(furi).netloc

            # Save redirect metadata.
            meta_path = xls_path.with_suffix(xls_path.suffix + ".redirect.json")
            meta_path.write_bytes(json.dumps(redirect_payload, ensure_ascii=False, indent=2).encode())

            try:
                resp = session.get(furi, headers=headers, timeout=settings.timeout_seconds)
                if resp.status_code != 200:
                    logger.warning("Redirect falló HTTP %s para %s", resp.status_code, xls_path.name)
                    dl["status"] = "redirect_failed"
                    dl["redirect_http_status"] = resp.status_code
                    dl["redirect_uri_host"] = redirect_host
                    dl["redirect_metadata_path"] = str(meta_path.relative_to(ROOT))
                    failed += 1
                    continue

                real_ext = ".xlsx"
                if ".xls" in furi and ".xlsx" not in furi:
                    real_ext = ".xls"

                # Save real file next to the redirect JSON placeholder.
                real_path = xls_path.with_suffix(real_ext)
                real_path.write_bytes(resp.content)

                # Remove the fake placeholder (it's now replaced or alongside the real file).
                if real_path != xls_path:
                    xls_path.unlink(missing_ok=True)

                dl["status"] = "ok_redirect_followed"
                dl["redirect_followed"] = True
                dl["redirect_uri_host"] = redirect_host
                dl["bytes"] = len(resp.content)
                dl["path"] = str(real_path.relative_to(ROOT))
                dl["redirect_metadata_path"] = str(meta_path.relative_to(ROOT))
                fixed += 1
                logger.info("Fixed %s -> %s (%s bytes)", xls_path.name, real_path.name, len(resp.content))

            except Exception as exc:
                logger.warning("Error siguiendo redirect para %s: %s", xls_path.name, exc)
                dl["status"] = "redirect_failed"
                dl["error"] = str(exc)
                dl["redirect_uri_host"] = redirect_host
                dl["redirect_metadata_path"] = str(meta_path.relative_to(ROOT))
                failed += 1

    # Save updated manifest.
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info("Fix XLS: %s seguidos OK, %s ya eran reales, %s fallidos", fixed, skipped, failed)
    print(f"\nResultado: {fixed} redirects seguidos, {skipped} archivos ya eran reales, {failed} fallidos")
    print(f"Manifest actualizado: {manifest_path}")


if __name__ == "__main__":
    main()
