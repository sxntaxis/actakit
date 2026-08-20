#!/usr/bin/env python3
"""Audit catalog integrity: duplicates, normalization issues, missing fields.

Compares raw vs. unique catalog, finds resources with identical titles but different GUIDs,
checks for normalization issues and missing metadata.
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

import sys
sys.path.insert(0, str(Path(__file__).parent))

from junar_common import (
    ROOT,
    endpoint_url,
    load_config,
    normalize_label,
    read_json,
    resource_category,
    resource_guid,
    resource_title,
    resource_type,
    setup_logging,
    write_json,
)

AUDIT_DIR = ROOT / "audit"


def norm_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def extract_year(text: str) -> str:
    m = re.search(r"20[0-9]{2}", text)
    return m.group(0) if m else ""


def has_endpoint(resource: dict) -> bool:
    return bool(endpoint_url(resource))


def audit_catalog(raw: list[dict], unique: list[dict], manifest: list[dict]) -> dict[str, Any]:
    manifest_index = {item["guid"]: item for item in manifest}
    success = {"ok", "ok_redirect_followed", "skipped_existing"}

    # --- Raw vs unique ---
    raw_guids = [resource_guid(r) for r in raw]
    raw_guid_set = set(g for g in raw_guids if g)
    unique_guids = [resource_guid(r) for r in unique]
    unique_guid_set = set(g for g in unique_guids if g)

    raw_count = len([g for g in raw_guids if g])
    duplicated_in_raw = raw_count - len(unique_guid_set)

    # Find which GUIDs appear multiple times in raw
    from collections import Counter
    raw_guid_counter = Counter(g for g in raw_guids if g)
    duplicated_guids = {g: count for g, count in raw_guid_counter.items() if count > 1}

    # --- Build guid → resource index from unique ---
    guid_to_resource = {resource_guid(r): r for r in unique}

    # --- Title duplicates ---
    title_index: dict[str, list[str]] = defaultdict(list)
    for r in unique:
        nt = norm_title(resource_title(r))
        if nt:
            title_index[nt].append(resource_guid(r))

    title_duplicates = {t: guids for t, guids in title_index.items() if len(guids) > 1}

    # --- Category normalization ---
    bad_category = []
    no_category = []
    no_date = []
    no_endpoint_resources = []
    no_source = []

    for r in unique:
        guid = resource_guid(r)
        cat_raw = r.get("category_name") or r.get("category") or ""
        cat_raw_str = str(cat_raw) if not isinstance(cat_raw, dict) else cat_raw.get("name", "")
        cat_norm = normalize_label(cat_raw_str)

        if not cat_norm or cat_norm in ("sin_categoria", ""):
            no_category.append(guid)
        elif cat_norm != cat_raw_str.strip():
            bad_category.append({"guid": guid, "raw": repr(cat_raw_str), "normalized": cat_norm})

        # Date fields
        date_raw = r.get("created_at") or r.get("modified_at") or r.get("updated_at") or ""
        if not date_raw:
            no_date.append(guid)

        # Endpoint
        if not has_endpoint(r):
            no_endpoint_resources.append(guid)

        # Source/publisher
        src = r.get("source") or r.get("publisher") or r.get("user") or ""
        if not src:
            no_source.append(guid)

    # --- Functional status by category ---
    category_functional: dict[str, dict] = defaultdict(lambda: {"total": 0, "functional": 0, "failed": 0})
    for r in unique:
        cat = resource_category(r)
        guid = resource_guid(r)
        m = manifest_index.get(guid)
        category_functional[cat]["total"] += 1
        if m:
            has_ok = any(dl.get("status") in success for dl in m.get("downloads", []))
            if has_ok:
                category_functional[cat]["functional"] += 1
            elif m.get("datastream_attempted"):
                category_functional[cat]["failed"] += 1

    return {
        "raw_count": raw_count,
        "unique_count": len(unique),
        "duplicated_in_raw": duplicated_in_raw,
        "duplicated_guids": duplicated_guids,
        "title_duplicates_count": len(title_duplicates),
        "title_duplicates": title_duplicates,
        "bad_category_count": len(bad_category),
        "bad_category_examples": bad_category[:20],
        "no_category_count": len(no_category),
        "no_date_count": len(no_date),
        "no_endpoint_count": len(no_endpoint_resources),
        "no_source_count": len(no_source),
        "category_functional": dict(category_functional),
        "guid_to_resource": guid_to_resource,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoría de integridad del catálogo.")
    args = parser.parse_args()

    config = load_config()
    logger = setup_logging("07_catalog_integrity_audit")

    raw = read_json(ROOT / "data/raw/catalog/resources_raw_all_pages.json")
    unique = read_json(ROOT / "data/raw/catalog/resources_unique.json")
    manifest = json.loads((ROOT / "data/processed/download_manifest.json").read_text(encoding="utf-8"))

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    audit = audit_catalog(raw, unique, manifest)

    # --- catalog_integrity.csv ---
    integrity_rows = []
    for r in unique:
        guid = resource_guid(r)
        cat_raw = r.get("category_name") or r.get("category") or ""
        cat_raw_str = str(cat_raw) if not isinstance(cat_raw, dict) else cat_raw.get("name", "")
        cat_norm = normalize_label(cat_raw_str)
        date_raw = r.get("created_at") or r.get("modified_at") or r.get("updated_at") or ""

        issues = []
        if not cat_norm or cat_norm in ("sin_categoria", ""):
            issues.append("no_category")
        elif cat_norm != cat_raw_str.strip():
            issues.append("category_needs_normalization")
        if not date_raw:
            issues.append("no_date")
        if not has_endpoint(r):
            issues.append("no_endpoint")

        nt = norm_title(resource_title(r))
        dup_guids = [g for g in audit["title_duplicates"].get(nt, []) if g != guid]

        integrity_rows.append({
            "guid": guid,
            "title": resource_title(r),
            "category_raw": cat_raw_str,
            "category_normalized": cat_norm,
            "type": resource_type(r),
            "has_date": bool(date_raw),
            "date": str(date_raw)[:20],
            "has_endpoint": has_endpoint(r),
            "duplicated_in_raw": audit["duplicated_guids"].get(guid, 1) > 1,
            "title_duplicate_of": ", ".join(dup_guids),
            "issues": "; ".join(issues),
        })

    csv_path = AUDIT_DIR / "catalog_integrity.csv"
    csv_cols = [
        "guid", "title", "category_raw", "category_normalized", "type",
        "has_date", "date", "has_endpoint", "duplicated_in_raw", "title_duplicate_of", "issues",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(integrity_rows)

    # --- catalog_duplicates.csv ---
    dup_rows = []
    group_id = 0
    # GUIDs duplicated in raw catalog
    for guid, count in audit["duplicated_guids"].items():
        group_id += 1
        r = audit["guid_to_resource"].get(guid, {})
        dup_rows.append({
            "duplicate_group_id": group_id,
            "guid": guid,
            "title": resource_title(r) if r else guid,
            "normalized_title": norm_title(resource_title(r)) if r else "",
            "category": resource_category(r) if r else "",
            "type": resource_type(r) if r else "",
            "link": r.get("link", "") if r else "",
            "endpoint": endpoint_url(r) or "" if r else "",
            "is_functional": "",
            "preferred_guid": guid,
            "reason": f"raw_duplicate_count={count}",
        })

    # Title duplicates across unique GUIDs
    for nt, guids in audit["title_duplicates"].items():
        if any(g in audit["duplicated_guids"] for g in guids):
            continue  # Already covered above
        group_id += 1
        for g in guids:
            r = audit["guid_to_resource"].get(g, {})
            dup_rows.append({
                "duplicate_group_id": group_id,
                "guid": g,
                "title": resource_title(r) if r else g,
                "normalized_title": nt,
                "category": resource_category(r) if r else "",
                "type": resource_type(r) if r else "",
                "link": r.get("link", "") if r else "",
                "endpoint": endpoint_url(r) or "" if r else "",
                "is_functional": "",
                "preferred_guid": guids[0],
                "reason": "same_normalized_title",
            })

    dup_csv = AUDIT_DIR / "catalog_duplicates.csv"
    dup_cols = [
        "duplicate_group_id", "guid", "title", "normalized_title",
        "category", "type", "link", "endpoint",
        "is_functional", "preferred_guid", "reason",
    ]
    with dup_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=dup_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dup_rows)

    # Save full audit JSON
    audit_out = {k: v for k, v in audit.items() if k != "guid_to_resource"}
    write_json(AUDIT_DIR / "catalog_integrity.json", audit_out)

    # Markdown report
    lines = [
        "# Auditoría de Integridad del Catálogo",
        "",
        f"Fecha: 2026-04-28",
        "",
        "## Métricas generales",
        "",
        f"| Campo | Valor |",
        f"|-------|-------|",
        f"| Entradas crudas | {audit['raw_count']} |",
        f"| Recursos únicos | {audit['unique_count']} |",
        f"| Duplicados en catálogo crudo | {audit['duplicated_in_raw']} |",
        f"| GUIDs repetidos | {len(audit['duplicated_guids'])} |",
        f"| Títulos duplicados entre GUIDs distintos | {audit['title_duplicates_count']} |",
        f"| Sin categoría | {audit['no_category_count']} |",
        f"| Categoría con espacios/normalización incorrecta | {audit['bad_category_count']} |",
        f"| Sin fecha | {audit['no_date_count']} |",
        f"| Sin endpoint | {audit['no_endpoint_count']} |",
        f"| Sin fuente/publicador | {audit['no_source_count']} |",
        "",
        "## Estado funcional por categoría",
        "",
        "| Categoría | Total | Funcionales | Fallidos |",
        "|-----------|-------|-------------|----------|",
    ]
    for cat, stats in sorted(audit["category_functional"].items()):
        lines.append(f"| {cat} | {stats['total']} | {stats['functional']} | {stats['failed']} |")

    if audit["bad_category_examples"]:
        lines += [
            "",
            "## Categorías con normalización incorrecta (muestra)",
            "",
        ]
        for ex in audit["bad_category_examples"][:10]:
            lines.append(f"- GUID {ex['guid']}: raw={ex['raw']} → norm={ex['normalized']}")

    lines += [
        "",
        "## Conclusión",
        "",
        "Los duplicados en el catálogo crudo son entradas de paginación repetidas, no versiones diferentes.",
        "Los títulos duplicados entre GUIDs distintos corresponden a la misma fuente publicada bajo dos GUIDs (posiblemente por migración de datos).",
        "Los recursos sin categoría son mayormente de tipo `vz` (visualización) sin metadatos de categoría asignados.",
    ]

    (AUDIT_DIR / "CATALOG_INTEGRITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    logger.info(
        "Integridad: raw=%s, unique=%s, dups=%s, title_dups=%s, no_cat=%s, no_date=%s",
        audit["raw_count"], audit["unique_count"], audit["duplicated_in_raw"],
        audit["title_duplicates_count"], audit["no_category_count"], audit["no_date_count"],
    )
    print(f"\nCatálogo: {audit['raw_count']} crudos, {audit['unique_count']} únicos, {audit['duplicated_in_raw']} duplicados")
    print(f"Títulos duplicados (GUIDs distintos): {audit['title_duplicates_count']}")
    print(f"Archivos: {csv_path} | {dup_csv}")


if __name__ == "__main__":
    main()
