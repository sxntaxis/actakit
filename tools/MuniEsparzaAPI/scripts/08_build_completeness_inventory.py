#!/usr/bin/env python3
"""Build final completeness inventory integrating results from phases 2-6.

Merges:
- Original inventory (audit/inventory.csv)
- Truncation resolution (audit/truncation_resolution.json)
- Failed resources resolution (audit/failed_resources_resolution.json)
- Excel file audit (audit/excel_file_audit.json)
- Catalog integrity (audit/catalog_integrity.json)

Outputs:
- audit/final_completeness_inventory.csv
- audit/final_completeness_inventory.json
- audit/FINAL_COMPLETENESS_REPORT.md
- audit/formal_request_candidates.csv
- audit/FORMAL_REQUEST_CANDIDATES.md
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent))

from junar_common import (
    ROOT,
    PAGINATION_BOUNDARY_ROWS,
    endpoint_url,
    load_config,
    read_json,
    resource_category,
    resource_guid,
    resource_title,
    resource_type,
    setup_logging,
    write_json,
)

AUDIT_DIR = ROOT / "audit"

COMPLETENESS_STATUS_ORDER = [
    "complete_verified",
    "complete_probable",
    "partial_possible_truncation",
    "partial_known_limit",
    "metadata_only",
    "api_error_retriable",
    "api_error_persistent",
    "empty_verified",
    "source_file_only",
    "requires_manual_download",
    "requires_formal_request",
]


def load_optional_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def determine_completeness(
    base_row: dict,
    trunc_res: dict | None,
    failed_res: dict | None,
    excel_rows: dict | None,
) -> tuple[str, str, str]:
    """Returns (completeness_status, completeness_confidence, known_issue)."""
    audit_status = base_row.get("audit_status", "")
    possible_trunc = base_row.get("possible_truncation", "").lower() == "true"
    row_count = base_row.get("row_count_best", "")
    has_valid_excel = excel_rows is not None and (excel_rows.get("rows_total") or 0) > 0

    if audit_status == "metadata_only":
        return "metadata_only", "high", "visualization_or_no_datastream"

    if audit_status == "datastream_failed_or_empty":
        if failed_res:
            fs = failed_res.get("final_status", "")
            if fs == "recovered_api":
                return "complete_probable", "medium", "recovered_in_retry"
            if fs == "recovered_source_file":
                return "source_file_only", "medium", "api_fails_source_ok"
            if fs == "functional_duplicate_available":
                return "complete_probable", "low", f"duplicate_of_{failed_res.get('functional_duplicate_guid', '')}"
            if fs == "requires_manual_download":
                return "requires_manual_download", "low", "endpoint_skipped"
        return "api_error_persistent", "high", "http_500_persistent"

    # Has successful downloads
    if possible_trunc or (isinstance(row_count, str) and row_count.isdigit() and int(row_count) in PAGINATION_BOUNDARY_ROWS):
        if trunc_res:
            ts = trunc_res.get("final_completeness_status", "")
            if ts == "complete_verified_by_source_file":
                return "complete_verified", "high", "verified_by_source_file"
            if ts == "complete_verified_by_csv_or_xlsx":
                return "complete_verified", "high", "verified_by_csv_or_xlsx"
            if ts == "complete_probable_exact_999_rows":
                return "complete_probable", "medium", "exactly_999_rows_no_more_found"
            if ts in ("partial_possible_truncation_server_repeats_payload",):
                return "partial_possible_truncation", "high", "server_repeats_payload_at_offset"
            return "partial_known_limit", "medium", "at_page_boundary_unresolved"
        if has_valid_excel:
            return "complete_probable", "medium", "excel_has_data_api_may_be_partial"
        return "partial_possible_truncation", "medium", "at_page_boundary_not_yet_resolved"

    # Normal successful download
    if has_valid_excel or (isinstance(row_count, str) and row_count.isdigit() and int(row_count) > 0):
        return "complete_probable", "medium", ""

    return "complete_probable", "low", "download_ok_no_row_count"


def usable_for_analysis(status: str, contains_pii: bool) -> str:
    if status in ("complete_verified", "complete_probable"):
        return "yes"
    if status in ("partial_possible_truncation", "partial_known_limit"):
        return "only_with_caution"
    if status in ("source_file_only",):
        return "only_with_caution"
    return "no"


def usable_for_public_communication(status: str, contains_pii: bool, audit_status: str) -> str:
    if contains_pii:
        return "no_contains_pii"
    if status == "metadata_only":
        return "no_incomplete"
    if status in ("api_error_persistent", "requires_manual_download", "requires_formal_request"):
        return "no_incomplete"
    if status in ("partial_possible_truncation", "partial_known_limit"):
        return "no_incomplete"
    # Budget data is generally public
    return "yes_aggregated_only"


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye inventario final de completitud.")
    args = parser.parse_args()

    config = load_config()
    logger = setup_logging("08_build_completeness_inventory")

    # Load all inputs
    unique = read_json(ROOT / "data/raw/catalog/resources_unique.json")
    manifest = json.loads((ROOT / "data/processed/download_manifest.json").read_text(encoding="utf-8"))

    # Base inventory rows
    base_inventory = {}
    inv_path = AUDIT_DIR / "inventory.csv"
    if inv_path.exists():
        for row in csv.DictReader(inv_path.open(encoding="utf-8")):
            base_inventory[row["guid"]] = row

    # Phase 2: truncation resolutions
    trunc_data = load_optional_json(AUDIT_DIR / "truncation_resolution.json") or []
    trunc_by_guid = {r["guid"]: r for r in trunc_data}

    # Phase 3: failed resource resolutions
    failed_data = load_optional_json(AUDIT_DIR / "failed_resources_resolution.json") or []
    failed_by_guid = {r["guid"]: r for r in failed_data}

    # Phase 4: excel audit
    excel_data = load_optional_json(AUDIT_DIR / "excel_file_audit.json") or []
    excel_by_guid: dict[str, list[dict]] = defaultdict(list)
    for e in excel_data:
        if e.get("guid"):
            excel_by_guid[e["guid"]].append(e)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_index = {item["guid"]: item for item in manifest}
    results = []
    pii_count = 0
    usable_count = 0

    for resource in unique:
        guid = resource_guid(resource)
        if not guid:
            continue

        base = base_inventory.get(guid, {})
        m = manifest_index.get(guid, {})
        trunc_res = trunc_by_guid.get(guid)
        failed_res = failed_by_guid.get(guid)

        # Best Excel data for this guid
        excel_for_guid = excel_by_guid.get(guid, [])
        best_excel = max(
            (e for e in excel_for_guid if e.get("rows_total") is not None),
            key=lambda e: e.get("rows_total", 0),
            default=None,
        )

        # Year detection
        title = resource_title(resource)
        year_detected = ""
        for yr in range(2000, 2031):
            if str(yr) in title or str(yr) in guid:
                year_detected = str(yr)
                break

        contains_pii = base.get("contains_possible_pii", "False").lower() == "true"
        has_api_data = base.get("audit_status") in ("usable_datastream", "possible_truncation", "endpoint_only")
        has_source_file = isinstance(m.get("endpoint_download"), dict) and m["endpoint_download"].get("status") in (
            "ok", "ok_redirect_followed", "skipped_existing"
        )
        has_valid_excel = best_excel is not None and (best_excel.get("rows_total") or 0) > 0

        rows_best = base.get("row_count_best", "")
        if best_excel and (best_excel.get("rows_total") or 0) > (int(rows_best) if rows_best.isdigit() else 0):
            rows_best = str(best_excel["rows_total"])
            best_fmt = best_excel.get("format_claimed", "xlsx")
        else:
            best_fmt = base.get("formats_ok", "").split(",")[0].strip() if base.get("formats_ok") else ""

        comp_status, comp_confidence, known_issue = determine_completeness(
            base, trunc_res, failed_res, best_excel
        )

        anal = usable_for_analysis(comp_status, contains_pii)
        pub = usable_for_public_communication(comp_status, contains_pii, base.get("audit_status", ""))

        if contains_pii:
            pii_count += 1
        if anal == "yes":
            usable_count += 1

        # Recommended next action
        if comp_status == "complete_verified":
            action = "ready_for_analysis"
        elif comp_status == "complete_probable":
            action = "ready_for_analysis_verify_if_critical"
        elif comp_status == "partial_possible_truncation":
            action = failed_res.get("recommended_action", "request_source_file_or_formal_request") if failed_res else "request_source_file"
        elif comp_status == "metadata_only":
            action = "no_data_available_check_portal"
        elif comp_status == "api_error_persistent":
            action = "formal_request_or_manual_check"
        elif comp_status == "requires_manual_download":
            action = "download_from_endpoint_manually"
        else:
            action = "formal_request"

        results.append({
            "guid": guid,
            "title": title,
            "category": resource_category(resource),
            "year_detected": year_detected,
            "resource_type": resource_type(resource),
            "has_api_data": has_api_data,
            "has_source_file": has_source_file,
            "has_valid_excel": has_valid_excel,
            "rows_best_available": rows_best,
            "best_available_format": best_fmt,
            "contains_possible_pii": contains_pii,
            "completeness_status": comp_status,
            "completeness_confidence": comp_confidence,
            "known_issue": known_issue,
            "recommended_next_action": action,
            "usable_for_analysis_now": anal,
            "usable_for_public_communication": pub,
            "notes": "",
        })

    # Save CSV
    csv_cols = [
        "guid", "title", "category", "year_detected", "resource_type",
        "has_api_data", "has_source_file", "has_valid_excel",
        "rows_best_available", "best_available_format",
        "contains_possible_pii",
        "completeness_status", "completeness_confidence", "known_issue",
        "recommended_next_action",
        "usable_for_analysis_now", "usable_for_public_communication",
        "notes",
    ]
    csv_path = AUDIT_DIR / "final_completeness_inventory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    write_json(AUDIT_DIR / "final_completeness_inventory.json", results)

    # --- Formal request candidates ---
    formal_topics = [
        {
            "topic": "concejo_actas",
            "why_needed_for_dossier": "Actas del Concejo Municipal revelan acuerdos, votaciones, quórum y toma de decisiones del órgano máximo de gobierno local.",
            "searched_in_api": "Sí — términos: concejo, acta, sesion, acuerdo",
            "api_result": "0 recursos",
            "missing_fields": "Actas completas, listas de asistencia, votaciones nominales",
            "recommended_institution": "Municipalidad de Esparza — Secretaría del Concejo",
            "recommended_office_or_contact": "Secretaría Municipal / Alcaldía",
            "legal_basis_hint": "Artículo 49 Código Municipal; Ley 8220 de Simplificación de Trámites",
            "priority": "alta",
            "notes": "El portal no tiene sección 'Concejo' ni 'Actas'",
        },
        {
            "topic": "comisiones_municipales",
            "why_needed_for_dossier": "Informes de comisiones (Hacienda, Ambiente, Mujer, Obras) documentan deliberaciones y dictámenes técnicos.",
            "searched_in_api": "Sí — términos: comision, comisiones, comad",
            "api_result": "0 recursos",
            "missing_fields": "Actas de comisiones, dictámenes, membresía",
            "recommended_institution": "Municipalidad de Esparza",
            "recommended_office_or_contact": "Secretaría Municipal",
            "legal_basis_hint": "Artículo 49 Código Municipal",
            "priority": "alta",
            "notes": "",
        },
        {
            "topic": "participacion_ciudadana_real",
            "why_needed_for_dossier": "Solo 1 hit en API (false positive). Audiencias públicas, consultas, planes reguladores participativos.",
            "searched_in_api": "Sí — 1 hit (falso positivo de nombre de proyecto)",
            "api_result": "1 recurso (falso positivo)",
            "missing_fields": "Audiencias públicas, consultas ciudadanas, registros de participación",
            "recommended_institution": "Municipalidad de Esparza — Proceso de Participación Ciudadana",
            "recommended_office_or_contact": "Dirección de Desarrollo Urbano / Alcaldía",
            "legal_basis_hint": "Artículos 4 y 13 Código Municipal; Ley 8801 Descentralización",
            "priority": "alta",
            "notes": "Esparza tiene Comisión de Participación Ciudadana (COPACI) según código municipal",
        },
        {
            "topic": "liquidacion_presupuestaria",
            "why_needed_for_dossier": "Liquidación al cierre del ejercicio fiscal — qué se ejecutó vs. lo aprobado. Clave para evaluar capacidad de gasto.",
            "searched_in_api": "Sí — términos: liquidacion, liquidación, cierre",
            "api_result": "0 recursos específicos (confunde con 'clausuras')",
            "missing_fields": "Liquidación presupuestaria anual por objeto del gasto y programa",
            "recommended_institution": "Municipalidad de Esparza — Contaduría o Presupuesto",
            "recommended_office_or_contact": "Proceso de Presupuesto Municipal / Contraloría DFOE",
            "legal_basis_hint": "Artículo 101 Código Municipal; Ley 8131 LAFRPP",
            "priority": "alta",
            "notes": "La Contraloría tiene liquidaciones desde 2010 en SIPP para consulta pública",
        },
        {
            "topic": "asadas",
            "why_needed_for_dossier": "Registro de ASADAS en el cantón, cobertura de agua potable rural, convenios con AyA.",
            "searched_in_api": "Sí — 0 resultados",
            "api_result": "0 recursos",
            "missing_fields": "Lista de ASADAS, comunidades cubiertas, caudales, auditorías",
            "recommended_institution": "AyA (Instituto Costarricense de Acueductos y Alcantarillados) / Municipalidad",
            "recommended_office_or_contact": "Departamento de Ingeniería / AyA Regional Puntarenas",
            "legal_basis_hint": "Ley 2726 AyA; Reglamento de ASADAS",
            "priority": "media",
            "notes": "Las ASADAS son entes comunales, datos dispersos",
        },
        {
            "topic": "canon_puerto_caldera_real",
            "why_needed_for_dossier": "El INCOP transfiere un canon a municipalidades costeras por el uso portuario. Esparza recibe canon de Puerto Caldera por Ley 8461.",
            "searched_in_api": "Sí — 58 hits pero son todos falsos positivos (Patentes del distrito Caldera)",
            "api_result": "58 recursos falsos positivos — ninguno real",
            "missing_fields": "Montos recibidos por año, uso dado, proyectos financiados",
            "recommended_institution": "INCOP / Municipalidad de Esparza — Alcaldía",
            "recommended_office_or_contact": "Alcaldía / INCOP Planificación",
            "legal_basis_hint": "Ley 8461 (canon portuario); Artículo 49 Ley Orgánica del INCOP",
            "priority": "alta",
            "notes": "Los 58 hits del término 'Caldera' son patentes del distrito Caldera, no canon INCOP",
        },
        {
            "topic": "plan_vial_ejecucion_real",
            "why_needed_for_dossier": "El plan vial cantonal define qué caminos se mantienen con el FEES y otros fondos. Solo 3 hits en API, superficiales.",
            "searched_in_api": "Sí — 3 recursos (plan vial general, sin detalle de ejecución)",
            "api_result": "3 recursos — solo metadatos básicos",
            "missing_fields": "Km de caminos, presupuesto por camino, estado de ejecución, MOPT-CONAVI asignaciones",
            "recommended_institution": "Municipalidad de Esparza — Ingeniería Vial / CONAVI",
            "recommended_office_or_contact": "Proceso de Ingeniería / Dirección de Obras",
            "legal_basis_hint": "Ley 8114 Ley de Simplificación y Eficiencia Tributaria (FEES vial)",
            "priority": "media",
            "notes": "",
        },
        {
            "topic": "asociaciones_desarrollo_adi",
            "why_needed_for_dossier": "Las ADI ejecutan proyectos comunales con financiamiento de DINADECO y municipalidad. Sin datos en API.",
            "searched_in_api": "Sí — 0 resultados",
            "api_result": "0 recursos",
            "missing_fields": "Lista de ADI activas, proyectos, presupuestos, estados",
            "recommended_institution": "DINADECO / Municipalidad de Esparza",
            "recommended_office_or_contact": "DINADECO Regional / Alcaldía",
            "legal_basis_hint": "Ley 3859 DINADECO",
            "priority": "media",
            "notes": "",
        },
        {
            "topic": "ambiente_gestion_residuos",
            "why_needed_for_dossier": "Gestión de residuos sólidos, reciclaje, gestión de riesgo ambiental. Solo hits vagos en API.",
            "searched_in_api": "Sí — hits menores en otras categorías, ningún dataset específico",
            "api_result": "0 datasets dedicados",
            "missing_fields": "Toneladas de residuos recolectadas, relleno sanitario, alertas de riesgo",
            "recommended_institution": "Municipalidad de Esparza — Gestión Ambiental / MINAE",
            "recommended_office_or_contact": "Proceso Gestión Ambiental / SETENA",
            "legal_basis_hint": "Ley 8839 Gestión Integral de Residuos; LGAP",
            "priority": "baja",
            "notes": "",
        },
        {
            "topic": "presupuesto_2026",
            "why_needed_for_dossier": "El presupuesto aprobado 2026 no aparece en la API. Los datos de presupuesto llegan hasta 2025.",
            "searched_in_api": "Sí — ningún dataset con año 2026",
            "api_result": "0 datasets para 2026",
            "missing_fields": "Presupuesto ordinario 2026, modificaciones aprobadas 2026",
            "recommended_institution": "Municipalidad de Esparza — Presupuesto",
            "recommended_office_or_contact": "Proceso de Presupuesto / Contraloría DFOE",
            "legal_basis_hint": "Artículo 101 Código Municipal",
            "priority": "alta",
            "notes": "El presupuesto ordinario debe estar aprobado desde noviembre 2025",
        },
    ]

    formal_csv = AUDIT_DIR / "formal_request_candidates.csv"
    formal_cols = [
        "topic", "why_needed_for_dossier", "searched_in_api", "api_result",
        "missing_fields", "recommended_institution", "recommended_office_or_contact",
        "legal_basis_hint", "priority", "notes",
    ]
    with formal_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=formal_cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(formal_topics)

    # Formal request markdown
    flines = [
        "# Candidatos para Solicitud Formal de Información Pública",
        "",
        "Fecha: 2026-04-28",
        "",
        "Estos temas no tienen cobertura real en la API Junar de la Municipalidad de Esparza",
        "y requieren solicitud formal al amparo de la Ley 8220 o el Código Municipal.",
        "",
    ]
    for t in formal_topics:
        flines += [
            f"## {t['topic']}",
            "",
            f"**Prioridad**: {t['priority']}  ",
            f"**Por qué se necesita**: {t['why_needed_for_dossier']}  ",
            f"**Buscado en API**: {t['searched_in_api']}  ",
            f"**Resultado API**: {t['api_result']}  ",
            f"**Campos faltantes**: {t['missing_fields']}  ",
            f"**Institución recomendada**: {t['recommended_institution']}  ",
            f"**Contacto**: {t['recommended_office_or_contact']}  ",
            f"**Base legal**: {t['legal_basis_hint']}  ",
            "" if not t["notes"] else f"**Nota**: {t['notes']}  ",
            "",
        ]

    (AUDIT_DIR / "FORMAL_REQUEST_CANDIDATES.md").write_text("\n".join(flines) + "\n", encoding="utf-8")

    # --- Final completeness counts ---
    status_counter = Counter(r["completeness_status"] for r in results)
    conf_counter = Counter(r["completeness_confidence"] for r in results)
    anal_counter = Counter(r["usable_for_analysis_now"] for r in results)
    pub_counter = Counter(r["usable_for_public_communication"] for r in results)

    complete_verified = status_counter.get("complete_verified", 0)
    complete_probable = status_counter.get("complete_probable", 0)
    partial_trunc = status_counter.get("partial_possible_truncation", 0)
    partial_limit = status_counter.get("partial_known_limit", 0)
    metadata_only = status_counter.get("metadata_only", 0)
    api_persistent = status_counter.get("api_error_persistent", 0)
    src_only = status_counter.get("source_file_only", 0)
    manual_dl = status_counter.get("requires_manual_download", 0)
    formal_req = status_counter.get("requires_formal_request", 0)

    # --- FINAL_COMPLETENESS_REPORT.md ---
    rlines = [
        "# Reporte Final de Completitud del Snapshot Junar Esparza",
        "",
        "Fecha: 2026-04-28",
        f"Recursos únicos analizados: {len(results)}",
        "",
        "## Resumen ejecutivo",
        "",
        "| Pregunta | Respuesta |",
        "|----------|-----------|",
        f"| ¿Cuántos recursos están completos y verificados? | {complete_verified} |",
        f"| ¿Cuántos son probablemente completos pero no verificados al 100%? | {complete_probable} |",
        f"| ¿Cuántos siguen con posible truncamiento? | {partial_trunc + partial_limit} |",
        f"| ¿Cuántos fallan por error persistente del portal/API? | {api_persistent} |",
        f"| ¿Cuántos solo tienen metadatos? | {metadata_only} |",
        f"| ¿Cuántos tienen archivo fuente aunque la API falle? | {src_only} |",
        f"| ¿Cuántos contienen PII probable? | {pii_count} |",
        f"| ¿Cuántos son seguros para análisis interno ahora? | {anal_counter.get('yes', 0)} |",
        f"| ¿Cuántos son seguros solo con cautela? | {anal_counter.get('only_with_caution', 0)} |",
        f"| ¿Cuántos temas requieren oficio formal? | {len(formal_topics)} |",
        "",
        "## Estado de completitud por categoría",
        "",
        "| Categoría | Total | Completos | Truncados | Errores | Solo metadatos |",
        "|-----------|-------|-----------|-----------|---------|----------------|",
    ]

    cat_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "complete": 0, "partial": 0, "error": 0, "meta": 0})
    for r in results:
        cat = r["category"]
        cat_stats[cat]["total"] += 1
        s = r["completeness_status"]
        if s in ("complete_verified", "complete_probable"):
            cat_stats[cat]["complete"] += 1
        elif "partial" in s:
            cat_stats[cat]["partial"] += 1
        elif "error" in s or "api_error" in s:
            cat_stats[cat]["error"] += 1
        elif s == "metadata_only":
            cat_stats[cat]["meta"] += 1

    for cat, st in sorted(cat_stats.items()):
        rlines.append(f"| {cat} | {st['total']} | {st['complete']} | {st['partial']} | {st['error']} | {st['meta']} |")

    rlines += [
        "",
        "## Estado de completitud global",
        "",
        "| Estado | Cantidad |",
        "|--------|----------|",
    ]
    for s in COMPLETENESS_STATUS_ORDER:
        n = status_counter.get(s, 0)
        if n:
            rlines.append(f"| `{s}` | {n} |")

    rlines += [
        "",
        "## Usabilidad para análisis",
        "",
        f"- **Listos para análisis interno**: {anal_counter.get('yes', 0)}",
        f"- **Con cautela**: {anal_counter.get('only_with_caution', 0)}",
        f"- **No listos**: {anal_counter.get('no', 0)}",
        "",
        "## Usabilidad para comunicación pública",
        "",
        f"- **Sí (solo agregados)**: {pub_counter.get('yes_aggregated_only', 0)}",
        f"- **Sí (datos presupuestarios públicos)**: {pub_counter.get('yes_public_budget_data', 0)}",
        f"- **No (incompletos)**: {pub_counter.get('no_incomplete', 0)}",
        f"- **No (contiene PII)**: {pub_counter.get('no_contains_pii', 0)}",
        f"- **Solo con revisión manual**: {pub_counter.get('only_after_manual_review', 0)}",
        "",
        "## Temas que requieren oficio formal",
        "",
    ]
    for t in formal_topics:
        rlines.append(f"- **{t['topic']}** (prioridad: {t['priority']}): {t['api_result']}")

    rlines += [
        "",
        "## Recomendación de cierre",
        "",
        "### ¿Está listo para normalización analítica?",
        "",
        "**PARCIALMENTE**",
        "",
        "### Subconjuntos listos ahora:",
        "",
        "- **Patentes** (450 recursos): ajson y CSV funcionales, categoría homogénea. Listo para análisis de tendencias de licencias comerciales.",
        "- **Presupuesto** (320 recursos, salvo 2026): series históricas con ajson + XLSX. Listo para análisis de estructura de gasto.",
        "- **Modificaciones presupuestarias** (175 recursos): ajson funcional. Listo para análisis de ajustes por año.",
        "- **Permisos de construcción** (144 recursos, salvo brecha 2022-2023): ajson + CSV funcionales.",
        "- **Visados** (29 recursos): funcionales.",
        "- **Clausuras** (34 recursos): funcionales.",
        "",
        "### Subconjuntos que requieren trabajo adicional:",
        "",
        "- **Contabilidad** (22 datasets con 999 filas): posible truncamiento no resuelto. Requiere comparar con XLSX antes de usar.",
        "- **Bienes Inmuebles** (14 datasets con 999 filas): ídem.",
        "- **Mapas** (9 errores persistentes HTTP 500): no hay datos descargables.",
        "- **Medidores Climáticos** (2 recursos): endpoints externos no descargables por extensión.",
        "",
        "### No listo (requiere oficio o fuente externa):",
        "",
        "- Actas del Concejo, Comisiones Municipales, Participación Ciudadana real, Canon Caldera (Ley 8461), ASADAS, Liquidación presupuestaria, ADI, Presupuesto 2026.",
    ]

    (AUDIT_DIR / "FINAL_COMPLETENESS_REPORT.md").write_text("\n".join(rlines) + "\n", encoding="utf-8")

    logger.info(
        "Inventario final: %s recursos, %s complete_verified, %s complete_probable, "
        "%s partial_trunc, %s api_persistent, %s metadata_only, %s pii",
        len(results), complete_verified, complete_probable, partial_trunc + partial_limit,
        api_persistent, metadata_only, pii_count,
    )
    print(f"\nInventario final: {len(results)} recursos")
    print(f"  complete_verified:  {complete_verified}")
    print(f"  complete_probable:  {complete_probable}")
    print(f"  partial_truncation: {partial_trunc + partial_limit}")
    print(f"  api_error:         {api_persistent}")
    print(f"  metadata_only:     {metadata_only}")
    print(f"  listos_analisis:   {anal_counter.get('yes', 0)}")
    print(f"Archivos: {csv_path}")


if __name__ == "__main__":
    main()
