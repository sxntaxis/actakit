#!/usr/bin/env python3
"""Common utilities for the Esparza Junar API audit kit."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "audit_config.yaml"

# Junar's ajson endpoint caps pages at this many list items (header row included).
JUNAR_SERVER_PAGE_CAP = 1000

# Row counts at these boundaries may indicate server-side truncation.
PAGINATION_BOUNDARY_ROWS = {999, 1000, 1998, 1999, 2000, 2998, 2999, 3000}

# Terms that suggest personally identifiable information in field names or titles.
PII_TERMS = [
    "cedula", "cédula", "identificacion", "identificación",
    "nombre", "telefono", "teléfono", "correo", "email",
    "direccion", "dirección", "propietario", "contribuyente",
    "notificado", "apoderado", "solicitante",
]


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    referer: str
    requests_per_second: float
    timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: list[int]
    sleep_on_429_seconds: int


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self.min_interval = 1.0 / max(requests_per_second, 0.1)
        self.last_call = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self.last_call
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self.last_call = time.monotonic()


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings(config: dict[str, Any]) -> Settings:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("ESPARZA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta ESPARZA_API_KEY. Copie .env.example como .env y complete la clave.")

    rate_cfg = config.get("rate_limit", {})
    return Settings(
        api_key=api_key,
        base_url=os.getenv("JUNAR_BASE_URL", config.get("api_base_url", "")).rstrip("/"),
        referer=os.getenv("JUNAR_REFERER", config.get("referer", "")),
        requests_per_second=float(os.getenv("REQUESTS_PER_SECOND", rate_cfg.get("requests_per_second", 1))),
        timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", rate_cfg.get("timeout_seconds", 45))),
        max_retries=int(rate_cfg.get("max_retries", 4)),
        retry_backoff_seconds=list(rate_cfg.get("retry_backoff_seconds", [2, 5, 10, 20])),
        sleep_on_429_seconds=int(rate_cfg.get("sleep_on_429_seconds", 15)),
    )


def setup_logging(log_name: str) -> logging.Logger:
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    file_handler = logging.FileHandler(logs_dir / f"{log_name}.log", encoding="utf-8")
    file_handler.setFormatter(fmt)

    logger.addHandler(stream)
    logger.addHandler(file_handler)
    return logger


def normalize_label(value: Any) -> str:
    """Collapse internal whitespace and strip leading/trailing spaces."""
    return " ".join(str(value or "").split()).strip()


def safe_slug(value: str | None, max_len: int = 90) -> str:
    if not value:
        return "sin_nombre"
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", normalized).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    return slug[:max_len] or "sin_nombre"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def content_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def get_resource_field(resource: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in resource and resource[name] not in (None, ""):
            return resource[name]
    return None


def resource_guid(resource: dict[str, Any]) -> str | None:
    return get_resource_field(resource, "guid", "id", "name")


def resource_title(resource: dict[str, Any]) -> str:
    raw = get_resource_field(resource, "title", "name", "description") or "sin_titulo"
    return normalize_label(raw)


def resource_category(resource: dict[str, Any]) -> str:
    category = get_resource_field(resource, "category_name", "category", "category_title")
    if isinstance(category, dict):
        raw = category.get("name") or category.get("title") or "sin_categoria"
    else:
        raw = category or "sin_categoria"
    return normalize_label(raw)


def resource_type(resource: dict[str, Any]) -> str:
    value = get_resource_field(resource, "type", "resource_type", "kind")
    if isinstance(value, dict):
        return str(value.get("code") or value.get("name") or value)
    return str(value or "")


def endpoint_url(resource: dict[str, Any]) -> str | None:
    endpoint = get_resource_field(resource, "endpoint", "url", "download_url")
    if isinstance(endpoint, dict):
        endpoint = endpoint.get("url") or endpoint.get("href")
    if isinstance(endpoint, str) and endpoint.startswith(("http://", "https://")):
        return endpoint
    return None


def detect_junar_file_redirect(content: bytes, content_type: str | None = None) -> dict[str, Any] | None:
    """Return the redirect payload if content is a Junar REDIRECT JSON, else None."""
    if not content or content[:1] not in (b"{", b" "):
        return None
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(payload, dict) and payload.get("fType") == "REDIRECT" and payload.get("fUri"):
        return payload
    return None


def detect_pii_in_resource(resource: dict[str, Any], header_row: list[Any] | None = None) -> list[str]:
    """Return list of PII terms detected in title, description, or column headers."""
    blobs: list[str] = []
    for key in ("title", "name", "description"):
        val = resource.get(key)
        if val:
            blobs.append(str(val).lower())
    if header_row:
        blobs.append(" ".join(str(c).lower() for c in header_row))
    combined = " ".join(blobs)
    return [term for term in PII_TERMS if term in combined]


def request_with_retries(
    session: requests.Session,
    url: str,
    settings: Settings,
    limiter: RateLimiter,
    logger: logging.Logger,
    *,
    params: dict[str, Any] | None = None,
    stream: bool = False,
) -> requests.Response:
    headers = {"Referer": settings.referer, "User-Agent": "esparza-junar-civic-audit/0.1"}
    attempts = settings.max_retries + 1
    last_error: Exception | None = None

    for attempt in range(attempts):
        limiter.wait()
        try:
            response = session.get(
                url,
                headers=headers,
                params=params,
                timeout=settings.timeout_seconds,
                stream=stream,
            )
            if response.status_code == 429:
                sleep_s = settings.sleep_on_429_seconds
                logger.warning("HTTP 429 rate-limited; durmiendo %ss: %s", sleep_s, url)
                time.sleep(sleep_s)
                continue
            # HTTP 500 en Junar suele indicar datastream sin fuente configurada (no transitorio).
            # Se reintenta solo una vez; 502/503/504 sí son transitorios.
            if response.status_code == 500 and attempt == 0:
                sleep_s = settings.retry_backoff_seconds[0]
                logger.warning("HTTP 500; 1 reintento en %ss: %s", sleep_s, url)
                time.sleep(sleep_s)
                continue
            if response.status_code in {502, 503, 504} and attempt < attempts - 1:
                sleep_s = settings.retry_backoff_seconds[min(attempt, len(settings.retry_backoff_seconds) - 1)]
                logger.warning("HTTP %s; reintento en %ss: %s", response.status_code, sleep_s, url)
                time.sleep(sleep_s)
                continue
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < attempts - 1:
                sleep_s = settings.retry_backoff_seconds[min(attempt, len(settings.retry_backoff_seconds) - 1)]
                logger.warning("Error de red; reintento en %ss: %s", sleep_s, exc)
                time.sleep(sleep_s)
            else:
                break

    raise RuntimeError(f"Falló la solicitud después de {attempts} intentos: {url}; último error={last_error}")


def extract_results(payload: Any) -> list[dict[str, Any]]:
    """Extract resource records from common Junar/Django-style envelopes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "result", "data", "records", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for nested_key in ("records", "results", "data", "items"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
    return []


def is_junar_list_of_lists(payload: Any) -> bool:
    """Detect Junar's ajson list-of-lists format: {"result": [[header...], [row...], ...]}."""
    if not isinstance(payload, dict):
        return False
    result = payload.get("result")
    return isinstance(result, list) and bool(result) and isinstance(result[0], list)


def count_rows_and_columns(payload: Any) -> tuple[int | None, int | None]:
    if is_junar_list_of_lists(payload):
        result = payload["result"]
        header = result[0]
        data_rows = result[1:]
        return len(data_rows), len(header) if header else None
    records = extract_results(payload)
    if records:
        cols: set[str] = set()
        for row in records[:5000]:
            cols.update(str(k) for k in row.keys())
        return len(records), len(cols)
    if isinstance(payload, list):
        return len(payload), None
    return None, None


def detect_extension_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix or ".bin"


def chunks(iterable: Iterable[Any], size: int) -> Iterable[list[Any]]:
    bucket: list[Any] = []
    for item in iterable:
        bucket.append(item)
        if len(bucket) >= size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket
