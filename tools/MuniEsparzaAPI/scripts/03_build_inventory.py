#!/usr/bin/env python3
"""Build CSV/JSON audit inventories from catalog and download manifest."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

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
    safe_slug,
    setup_logging,
    write_json,
)


CATALOG_FIELDS = [
    "guid",
    "title",
    "category",
    "resource_type",
    "description",
    "link",
    "endpoint",
    "created_at",
    "modified_at",
    "updated_at",
    "frequency",
    "source",
    "publisher",
    "topics_detected",
    "datastream_attempted",
    "status_best",
    "formats_ok",
    "formats_failed",
    "row_count_best",
    "col_count_best",
    "possible_truncation",
    "pagination_warning",
    "warning_reason",
    "contains_possible_pii",
    "pii_terms_detected",
    "endpoint_status",
    "audit_status",
    "local_paths",
    "notes",
]


def text_blob(resource: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "name", "description", "category_name", "category", "tags", "source", "sources"):
        value = resource.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def detect_topics(resource: dict[str, Any], keyword_map: dict[str, list[str]]) -> list[str]:
    blob = text_blob(resource)
    return [topic for topic, keywords in keyword_map.items() if any(kw.lower() in blob for kw in keywords)]


def get_any(resource: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in resource and resource[key] not in (None, ""):
            return resource[key]
    return ""


def normalize_manifest(manifest: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["guid"]): item for item in manifest if item.get("guid")}


def audit_status_from_manifest(manifest_item: dict[str, Any] | None) -> str:
    if not manifest_item:
        return "catalog_only"
    statuses = [d.get("status", "unknown") for d in manifest_item.get("downloads", [])]
    endpoint_status = (manifest_item.get("endpoint_download") or {}).get("status")
    # "skipped_existing" means the output file already existed from a prior successful download.
    success = {"ok", "skipped_existing", "ok_redirect_followed"}
    if any(s in success for s in statuses):
        return "usable_datastream"
    if endpoint_status in success:
        return "endpoint_only"
    if any(s == "possible_truncation_repeated_payload" for s in statuses):
        return "possible_truncation"
    if statuses:
        return "datastream_failed_or_empty"
    return "metadata_only"


def best_download(manifest_item: dict[str, Any] | None) -> dict[str, Any]:
    """Return the download entry with the best status and most rows."""
    if not manifest_item:
        return {}
    downloads = manifest_item.get("downloads", [])
    success = {"ok", "skipped_existing", "ok_redirect_followed"}
    ok_downloads = [d for d in downloads if d.get("status") in success]
    if ok_downloads:
        # Prefer the one with the most rows.
        ok_downloads.sort(key=lambda d: d.get("rows_detected") or 0, reverse=True)
        return ok_downloads[0]
    # Return first available for partial info.
    return downloads[0] if downloads else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye inventario de auditoría.")
    parser.add_argument("--catalog", default=None)
    parser.add_argument("--manifest", default="data/processed/download_manifest.json")
    args = parser.parse_args()

    logger = setup_logging("03_build_inventory")
    config = load_config()
    keyword_map = config.get("keyword_map", {})

    # Prefer unique catalog; fall back to legacy name.
    if args.catalog:
        catalog_path = ROOT / args.catalog
    else:
        catalog_path = ROOT / "data/raw/catalog/resources_unique.json"
        if not catalog_path.exists():
            catalog_path = ROOT / "data/raw/catalog/resources_all.json"

    manifest_path = ROOT / args.manifest
    if not catalog_path.exists():
        raise SystemExit(f"No existe catálogo: {catalog_path}")

    resources: list[dict[str, Any]] = read_json(catalog_path)
    manifest: list[dict[str, Any]] = read_json(manifest_path) if manifest_path.exists() else []
    manifest_by_guid = normalize_manifest(manifest)

    rows: list[dict[str, Any]] = []
    topic_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    years_by_topic: dict[str, set[str]] = defaultdict(set)

    # Aggregate stats for summary.
    total_downloads_ok = 0
    total_downloads_failed = 0
    http_500_count = 0
    http_429_count = 0
    redirects_followed = 0
    possible_truncation_count = 0
    pii_flagged_count = 0

    for resource in resources:
        guid = resource_guid(resource) or ""
        category = resource_category(resource)
        title = resource_title(resource)
        topics = detect_topics(resource, keyword_map)
        for topic in topics:
            topic_counter[topic] += 1
        category_counter[category] += 1

        m = manifest_by_guid.get(guid)
        downloads = m.get("downloads", []) if m else []
        statuses = [str(d.get("status", "")) for d in downloads]

        success_statuses = {"ok", "skipped_existing", "ok_redirect_followed"}
        ok_formats = [str(d.get("format", "")) for d in downloads if d.get("status") in success_statuses]
        failed_formats = [str(d.get("format", "")) for d in downloads if d.get("status") not in success_statuses and d.get("status")]

        best = best_download(m)
        row_count_best = best.get("rows_detected") if best else None
        col_count_best = best.get("cols_detected") if best else None

        possible_truncation = any(d.get("possible_truncation") for d in downloads)
        # Also infer from rows_detected at page boundaries (for entries downloaded before the flag existed).
        if not possible_truncation:
            for d in downloads:
                rd = d.get("rows_detected")
                if isinstance(rd, int) and rd in PAGINATION_BOUNDARY_ROWS:
                    possible_truncation = True
                    break
        pagination_warning = any(d.get("pagination_warning") for d in downloads) or possible_truncation
        warning_reason = next((d.get("warning_reason") for d in downloads if d.get("warning_reason")), "")
        if not warning_reason and possible_truncation:
            warning_reason = "row_count_matches_page_boundary"

        endpoint_status_val = ""
        if m and isinstance(m.get("endpoint_download"), dict):
            endpoint_status_val = str(m["endpoint_download"].get("status", ""))

        audit_status = audit_status_from_manifest(m)
        status_counter[audit_status] += 1

        contains_pii = bool(m.get("contains_possible_pii")) if m else False
        pii_terms = m.get("pii_terms_detected", []) if m else []

        # Aggregate stats.
        for d in downloads:
            s = d.get("status", "")
            if s in success_statuses:
                total_downloads_ok += 1
            elif s:
                total_downloads_failed += 1
            if "500" in s:
                http_500_count += 1
            if "429" in s:
                http_429_count += 1
            if s == "ok_redirect_followed":
                redirects_followed += 1
        if possible_truncation:
            possible_truncation_count += 1
        if contains_pii:
            pii_flagged_count += 1

        blob = text_blob(resource)
        for year in range(2000, 2031):
            if str(year) in blob:
                for topic in topics:
                    years_by_topic[topic].add(str(year))

        # Collect local paths.
        local_paths = []
        for d in downloads:
            p = d.get("path") or d.get("saved_path")
            if p:
                local_paths.append(p)

        rows.append({
            "guid": guid,
            "title": title,
            "category": category,
            "resource_type": resource_type(resource),
            "description": get_any(resource, "description"),
            "link": get_any(resource, "link", "url"),
            "endpoint": endpoint_url(resource) or "",
            "created_at": get_any(resource, "created_at", "created"),
            "modified_at": get_any(resource, "modified_at", "modified", "last_modified"),
            "updated_at": get_any(resource, "updated_at", "updated", "last_update"),
            "frequency": get_any(resource, "frequency", "update_frequency"),
            "source": get_any(resource, "source", "sources"),
            "publisher": get_any(resource, "user", "publisher", "organization"),
            "topics_detected": ";".join(topics),
            "datastream_attempted": bool(m and m.get("datastream_attempted")),
            "status_best": audit_status,
            "formats_ok": ";".join(ok_formats),
            "formats_failed": ";".join(failed_formats),
            "row_count_best": row_count_best if row_count_best is not None else "",
            "col_count_best": col_count_best if col_count_best is not None else "",
            "possible_truncation": possible_truncation,
            "pagination_warning": pagination_warning,
            "warning_reason": warning_reason,
            "contains_possible_pii": contains_pii,
            "pii_terms_detected": ";".join(pii_terms),
            "endpoint_status": endpoint_status_val,
            "audit_status": audit_status,
            "local_paths": "|".join(local_paths[:3]),
            "notes": "",
        })

    audit_dir = ROOT / "audit"
    audit_dir.mkdir(exist_ok=True)

    inventory_csv = audit_dir / "inventory.csv"
    with inventory_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    category_csv = audit_dir / "category_summary.csv"
    with category_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "resource_count"])
        writer.writeheader()
        for cat, count in category_counter.most_common():
            writer.writerow({"category": cat, "resource_count": count})

    topic_csv = audit_dir / "topic_summary.csv"
    with topic_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["topic", "resource_count", "years_detected_in_metadata"])
        writer.writeheader()
        for topic, count in topic_counter.most_common():
            writer.writerow({
                "topic": topic,
                "resource_count": count,
                "years_detected_in_metadata": ",".join(sorted(years_by_topic[topic])),
            })

    write_json(
        audit_dir / "audit_summary.json",
        {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "resources_total_unique": len(resources),
            "downloads_ok": total_downloads_ok,
            "downloads_failed": total_downloads_failed,
            "http_500_count": http_500_count,
            "http_429_count": http_429_count,
            "redirects_followed": redirects_followed,
            "possible_truncation_count": possible_truncation_count,
            "pii_flagged_count": pii_flagged_count,
            "category_counts": dict(category_counter.most_common()),
            "topic_counts": dict(topic_counter.most_common()),
            "audit_status_counts": dict(status_counter.most_common()),
        },
    )

    _write_report(audit_dir, rows, topic_counter, category_counter, status_counter,
                  total_downloads_ok, total_downloads_failed, http_500_count,
                  redirects_followed, possible_truncation_count, pii_flagged_count, len(resources))

    logger.info("Inventario: %s", inventory_csv)
    logger.info("Resumen: audit/audit_summary.json")
    logger.info("Reporte: audit/API_DEEP_AUDIT_REPORT.md")


def _write_report(
    audit_dir: Path,
    rows: list[dict[str, Any]],
    topic_counter: Counter[str],
    category_counter: Counter[str],
    status_counter: Counter[str],
    downloads_ok: int,
    downloads_failed: int,
    http_500_count: int,
    redirects_followed: int,
    possible_truncation_count: int,
    pii_flagged_count: int,
    total_resources: int,
) -> None:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    usable = status_counter.get("usable_datastream", 0) + status_counter.get("possible_truncation", 0)
    meta_only = status_counter.get("metadata_only", 0) + status_counter.get("catalog_only", 0)
    failed = status_counter.get("datastream_failed_or_empty", 0)

    top_categories = "\n".join(
        f"  - **{cat}**: {cnt}" for cat, cnt in category_counter.most_common(10)
    )

    # Build topic coverage table.
    strategic_topics = [
        "presupuesto", "modificaciones_presupuestarias", "ejecucion_presupuestaria",
        "liquidacion_presupuestaria", "contabilidad", "patentes", "permisos_construccion",
        "clausuras", "bienes_inmuebles", "visados", "catastro_mapas", "demografia",
        "empleo", "educacion", "recursos_humanos", "plan_vial", "obras",
        "canon_puerto_caldera", "participacion_ciudadana", "asociaciones_adi", "asadas",
        "concejo_actas", "comisiones_municipales", "ambiente", "tivives_caldera",
    ]
    topic_rows: list[str] = []
    missing_topics: list[str] = []
    for topic in strategic_topics:
        cnt = topic_counter.get(topic, 0)
        if cnt == 0:
            status = "FALTANTE"
            missing_topics.append(topic)
        elif cnt < 5:
            status = "parcial"
        else:
            status = "cubierto"
        topic_rows.append(f"| {topic} | {cnt} | {status} |")
    topic_table = "\n".join(topic_rows)

    # PII resources.
    pii_rows_str = ""
    pii_rows = [r for r in rows if r.get("contains_possible_pii")]
    if pii_rows:
        pii_rows_str = "\n".join(
            f"  - [{r['guid']}] {r['title'][:60]} — términos: {r['pii_terms_detected']}"
            for r in pii_rows[:20]
        )

    # Truncation resources.
    trunc_rows = [r for r in rows if r.get("possible_truncation")]
    trunc_str = "\n".join(
        f"  - [{r['guid']}] {r['title'][:60]} (filas: {r['row_count_best']}, razón: {r['warning_reason']})"
        for r in trunc_rows[:20]
    ) if trunc_rows else "  Ninguno detectado."

    # Missing topics for solicitudes.
    solicitudes = "\n".join(
        f"  - Solicitud de información pública: datos sobre **{t.replace('_', ' ')}** de la Municipalidad de Esparza"
        for t in missing_topics
    )

    report = f"""# Auditoría profunda de la API de datos abiertos — Municipalidad de Esparza

> Generado automáticamente por `esparza_junar_api_audit_kit`.
> Fecha: {now}
> Portal: https://datosabiertos.muniesparza.go.cr/
> API base: http://api.datosabiertos.muniesparza.go.cr/api/v2

---

## 1. Resumen ejecutivo

| Indicador | Valor |
|---|---|
| Total recursos únicos en catálogo | {total_resources} |
| Recursos con datos descargables (usables o posible truncamiento) | {usable} |
| Recursos solo metadatos o fallidos | {meta_only + failed} |
| Descargas exitosas (requests OK) | {downloads_ok} |
| Descargas fallidas (HTTP 500 u otro) | {downloads_failed} |
| HTTP 500 total | {http_500_count} |
| Redirects XLS/XLSX seguidos | {redirects_followed} |
| Datasets con posible truncamiento | {possible_truncation_count} |
| Datasets con posible PII | {pii_flagged_count} |

**Categorías con más recursos:**
{top_categories}

**Temas del dossier cantonal sin cobertura en la API:**
{chr(10).join(f'  - {t}' for t in missing_topics) if missing_topics else '  Todos los temas tienen al menos algún recurso.'}

---

## 2. Metodología

- Endpoint base: `http://api.datosabiertos.muniesparza.go.cr/api/v2/resources.json`
- Paginación: offset/limit, 100 recursos por página de catálogo.
- Formatos descargados: `ajson` (todos), `csv` + `xls` para categorías prioritarias.
- Rate limit: 1 req/s por defecto (configurable en `.env`).
- Reintentos: HTTP 500 → 1 reintento; HTTP 502/503/504 → backoff completo.
- HTTP 429 → pausa larga configurable.
- Redirects XLS: si Junar responde `{{"fUri": "...", "fType": "REDIRECT"}}`, se sigue la URL y se guarda el archivo real.
- Paginación: límite efectivo del servidor Junar ≈ 1000 elementos/página (incluyendo fila de encabezado).
- Datasets con exactamente 999 filas de datos o con payload repetido al paginar quedan marcados como `possible_truncation`.
- PII: heurística simple por términos en título, descripción y encabezados de columna.

---

## 3. Inventario general del portal

| Campo | Valor |
|---|---|
| Total recursos únicos | {total_resources} |
| Tipo `ds` (datastreams) | {sum(1 for r in rows if r.get('resource_type') == 'ds')} |
| Tipo `dt` (tablas/archivos) | {sum(1 for r in rows if r.get('resource_type') == 'dt')} |
| Tipo `vz` (visualizaciones, sin datos) | {sum(1 for r in rows if r.get('resource_type') == 'vz')} |
| Con al menos 1 formato descargado OK | {usable} |
| Solo metadata / fallidos | {meta_only + failed} |

Ver detalles completos en: `audit/inventory.csv`

---

## 4. Cobertura por categoría

| Categoría | Recursos |
|---|---|
{"".join(f'| {cat} | {cnt} |' + chr(10) for cat, cnt in category_counter.most_common())}
Ver: `audit/category_summary.csv`

---

## 5. Cobertura por tema estratégico

| Tema | Recursos detectados | Estado |
|---|---|---|
{topic_table}

Ver: `audit/topic_summary.csv`

> **Nota sobre canon portuario**: Los 58+ hits en el campo `caldera` son patentes comerciales del
> Distrito Caldera (nombre geográfico), NO datos del canon portuario que INCOP/Ley 8461 transfiere
> a la municipalidad. El canon portuario **no está en la API** y requiere solicitud de información.

---

## 6. Calidad de datos

### Datos actuales (modificados > 2022)

Las categorías con datos actualizados incluyen: Patentes (I-2025), Presupuesto (modificaciones 2025),
Contabilidad (Q3-2025), Clausuras (Q3-2025), Visados (Q3-2025), Bienes Inmuebles (2024),
Recursos Humanos (I-2025).

### Datos históricos/estáticos

- **Permisos de construcción**: cubre 2018-2021 y 2024; falta 2022-2023.
- **Educación, Demografía, Empleo**: datos del Censo 2011 (INEC), publicados 2019-2020. Estáticos.
- **Mapas**: mayormente sin actualización reciente.

### Posible truncamiento

Los siguientes datasets pueden estar incompletos (filas en límite de página o payload repetido):

{trunc_str}

### Redirects XLS seguidos

Se encontraron **{redirects_followed}** archivos XLS que Junar sirve como redirect a S3. El kit
sigue automáticamente esos redirects y guarda el archivo real (`.xlsx`). Las URLs S3 son temporales
(pre-firmadas); si se re-ejecuta con `--force`, se seguirá el redirect de nuevo con las URLs vigentes.

---

## 7. Hallazgos útiles para el dossier cantonal

### Presupuesto y ejecución fiscal
- La API tiene ejecución trimestral de ingresos desde 2018 hasta Q3-2025.
- Modificaciones presupuestarias disponibles por programa (1, 2, 3) desde 2018.
- Presupuestos iniciales y extraordinarios disponibles.
- Los datos de egresos tienen estructura: `Código por OBG`, `Clasificador por Objeto del Gasto`, `GENERAL`.
- Los datos de ingresos tienen: `Rubro`, `Nombre`, `Ordinario`, `Aumentos`, `Disminuciones`, `Definitivo`, `Anterior`, `Periodo`, `Acumulado`, `%`.
- **Faltante**: liquidación presupuestaria. Requiere solicitud de información.

### Patentes comerciales y de licores
- Cobertura semestral por distrito, 2019 a I-2025.
- Distritos cubiertos: Caldera, Espíritu Santo, Macacona, San Juan Grande, San Rafael, San Jerónimo, Esparza centro.
- Útil para análisis de actividad económica local.

### Contabilidad
- Balance de comprobación trimestral, 2020-Q3 2025.
- Estructura: código de segmento, cuenta, nombre, saldo inicial, débitos, créditos, saldo final.
- Alta densidad de datos: 999 filas por balance (posible truncamiento — verificar vs fuente).

### Permisos de construcción y visados
- Permisos: cobertura mensual 2018-2021 y 2024. **Brecha 2022-2023 sin explicación visible**.
- Visados: cobertura trimestral 2019-Q3 2025 (con brecha Q2-2024).

### Clausuras
- Cobertura trimestral 2019-Q3 2025. Dato útil para fiscalización.

### Bienes Inmuebles
- Exoneraciones 2018-2024 (anual y mensual).
- Declaraciones de Bienes Inmuebles 2018-2024.
- Órdenes de uso de suelo (sin año especificado).

---

## 8. Faltantes críticos

Los siguientes temas del dossier cantonal **no tienen ningún dataset** en la API:

| Tema faltante | Consecuencia para el dossier |
|---|---|
| Canon portuario (Ley 8461, INCOP) | No se puede verificar transferencias a la municipalidad |
| Participación ciudadana | No hay registro de audiencias, consultas o procesos |
| Asociaciones de desarrollo (ADI/DINADECO) | No hay padrón ni datos de organizaciones comunales |
| ASADAS (acueductos comunales) | No hay datos de cobertura de agua ni de asociaciones |
| Concejo municipal (actas y sesiones) | No hay acuerdos publicados ni sesiones registradas |
| Comisiones municipales (COMAD, Ambiente, etc.) | No hay registro de actividades |
| Ambiente y residuos sólidos | No hay datos ambientales ni de gestión de residuos |
| Zona Protectora Tivives-Caldera | No hay datos de manglares ni zona costera |
| Plan vial detallado y obras | Solo 3 recursos (red vial general, sin proyectos específicos) |
| Liquidación presupuestaria | Solo hay ejecución; no aparece liquidación anual oficial |

---

## 9. Solicitudes de información pública recomendadas

{solicitudes}

Además:
  - Solicitud: **actas del Concejo Municipal** (últimos 2 años, en formato abierto o PDF)
  - Solicitud: **informe de ejecución del Plan Vial** (MOPT-Municipalidad)
  - Solicitud: **monto y aplicación del canon portuario recibido** (Ley 8461, 2019-2025)
  - Solicitud: **contratos de obras públicas y proveedores** (2022-2025)
  - Solicitud: **permisos de construcción 2022-2023** (brecha no explicada en la API)
  - Solicitud: **planilla completa de funcionarios** (RH solo publica escalas salariales, no nómina)

---

## 10. Advertencia ética sobre datos con posible PII

Aunque los datos del portal son públicos, algunos datasets contienen o pueden contener
información personal (nombres, cédulas, patentes individuales, propietarios de fincas).

**Para comunicación ciudadana y política se deben usar SOLO agregados.**
No publicar nombres, cédulas, teléfonos, direcciones ni datos individualizados salvo
que exista justificación legal y ética clara.

Datasets con posible PII detectada ({pii_flagged_count}):
{pii_rows_str if pii_rows_str else '  No se detectaron términos PII en los datasets descargados.'}

---

## 11. Recomendaciones técnicas para mantener el snapshot

1. **Ejecutar mensualmente** `./run_all.sh` para capturar actualizaciones.
2. Los redirects XLS son URLs temporales de S3; re-ejecutar con `--force` para refrescarlos.
3. Los datasets marcados como `possible_truncation` deben validarse contra el portal web o por oficio.
4. Las categorías con espacios finales (`"Bienes Inmuebles "`) están normalizadas en esta versión del kit.
5. Mantener el rate limit en 1 req/s para no sobrecargar el portal.
6. Si aparece HTTP 429, aumentar `sleep_on_429_seconds` en `.env` o reducir `REQUESTS_PER_SECOND`.

---

## Anexos

- Inventario completo: `audit/inventory.csv`
- Resumen por categoría: `audit/category_summary.csv`
- Resumen por tema: `audit/topic_summary.csv`
- Resumen estadístico: `audit/audit_summary.json`
- Manifest de descargas: `data/processed/download_manifest.json`
- Catálogo crudo (con duplicados): `data/raw/catalog/resources_raw_all_pages.json`
- Catálogo único: `data/raw/catalog/resources_unique.json`
- Resumen del catálogo: `data/processed/catalog_summary.json`
"""

    (audit_dir / "API_DEEP_AUDIT_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
