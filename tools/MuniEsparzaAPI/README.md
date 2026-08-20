# Esparza Junar API Audit Kit

Kit de scripts para descargar y auditar, de forma prudente y reproducible, el portal de datos abiertos de la Municipalidad de Esparza, Puntarenas.

No incluye API key. La clave debe ir en `.env`.

## Objetivo

Crear un **snapshot local** del catálogo y de las vistas públicas de Junar para responder:

- Qué datasets existen y qué años cubren.
- Qué categorías tienen datos usables.
- Qué recursos solo tienen metadatos.
- Qué archivos fuente se pueden descargar.
- Qué pendientes del dossier cantonal se pueden confirmar con API.
- Qué pendientes requieren solicitud formal de información pública.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Editar `.env`:

```bash
ESPARZA_API_KEY="PEGAR_AQUI_LA_KEY"
```

## Uso rápido

```bash
./run_all.sh
```

## Uso por fases

### 1. Descargar catálogo

```bash
python scripts/01_snapshot_catalog.py
```

Salidas:

```text
data/raw/catalog/resources_raw_all_pages.json   # todas las entradas crudas de todas las páginas
data/raw/catalog/resources_unique.json          # recursos únicos deduplicados
data/raw/catalog/resources_all.json             # alias de resources_unique.json (compatibilidad)
data/raw/catalog/catalog_manifest.json          # metadatos del catálogo
data/processed/catalog_summary.json            # resumen: crudos, únicos, duplicados
```

Prueba limitada:

```bash
python scripts/01_snapshot_catalog.py --max-pages 2
```

### 2. Descargar vistas y archivos fuente

```bash
python scripts/02_download_datastreams.py
```

Salidas:

```text
data/raw/datastreams/**
data/raw/endpoints/**
data/processed/download_manifest.json
```

Opciones:

```bash
# Prueba limitada
python scripts/02_download_datastreams.py --max-resources 20

# Solo un GUID específico
python scripts/02_download_datastreams.py --only-guid MODIF-PRESU-1-2025

# Forzar re-descarga
python scripts/02_download_datastreams.py --force

# Omitir archivos fuente (solo datastreams)
python scripts/02_download_datastreams.py --no-endpoints
```

### 3. Construir inventario

```bash
python scripts/03_build_inventory.py
```

Salidas:

```text
audit/inventory.csv
audit/category_summary.csv
audit/topic_summary.csv
audit/audit_summary.json
audit/API_DEEP_AUDIT_REPORT.md
```

### 4. Fix de redirects XLS (post-descarga)

Si los archivos `.xls` descargados contienen JSON de redirect (Junar los genera como pre-signed S3 URLs),
ejecutar:

```bash
python scripts/fix_xls_redirects.py
```

Las URLs S3 son temporales. Ejecutar este script el mismo día de la descarga para asegurar validez.
Después de correr el fix, re-ejecutar el inventario:

```bash
python scripts/03_build_inventory.py
```

## Reintentar recursos fallidos

Para re-intentar solo los recursos con HTTP 500 u otro error:

```bash
# Extraer GUIDs con errores del manifest
python3 -c "
import json
with open('data/processed/download_manifest.json') as f:
    manifest = json.load(f)
failed = [item['guid'] for item in manifest
    if item.get('datastream_attempted')
    and not any(d.get('status') in ('ok','skipped_existing','ok_redirect_followed')
                for d in item.get('downloads', []))]
print('\n'.join(failed))
" > /tmp/failed_guids.txt

# Re-intentar uno a uno
while IFS= read -r guid; do
  python scripts/02_download_datastreams.py --only-guid "$guid" --force
done < /tmp/failed_guids.txt
```

## Rate limit

El kit usa por defecto `REQUESTS_PER_SECOND=1`. Es intencionalmente conservador.

Se puede ajustar en `.env`, pero **no se recomienda superar 2 req/s** para un snapshot cívico normal.

Si aparece HTTP 429, aumentar `sleep_on_429_seconds` en `.env`.

## Estados del manifest

| Estado | Significado |
|--------|-------------|
| `ok` | Descarga exitosa |
| `ok_redirect_followed` | Junar respondió con redirect S3; se siguió y guardó el archivo real |
| `skipped_existing` | El archivo ya existía de una descarga previa |
| `http_500_after_retries` | HTTP 500 tras reintentos; recurso probablemente sin datos en Junar |
| `possible_truncation_repeated_payload` | La API devolvió el mismo payload al paginar; datos posiblemente incompletos |
| `possible_truncation_page_boundary` | El número de filas coincide con el límite de página del servidor (≈999 filas) |
| `metadata_only` | El recurso no tiene datastream ni endpoint descargable |
| `redirect_failed` | La URL S3 expiró o falló |
| `rate_limited_429` | La API devolvió HTTP 429 |
| `exception` | Error de red u otro; ver campo `error` en manifest |

## Qué se descarga

Por defecto:
- Catálogo completo con paginación.
- `data.ajson` para recursos con GUID consultable.
- `csv` y `xls` para categorías prioritarias: Presupuesto, Contabilidad, Patentes, Clausuras, Bienes Inmuebles, Visados, Permisos de Construcción, Recursos Humanos, Mapas.
- Endpoint original cuando el recurso publica una URL directa y la extensión es permitida.

La configuración está en `config/audit_config.yaml`.

## Qué no hace

Este kit no interpreta políticamente los datos. Solo produce una base local auditable.

Tampoco garantiza que el portal tenga todo lo que la municipalidad debería publicar. Lo que no aparezca en la API debe convertirse en una solicitud de información pública.

## Advertencia sobre PII

Aunque los datos sean públicos, para comunicación política o ciudadana se deben usar **solo agregados**. No publicar nombres, cédulas, teléfonos, direcciones ni datos individualizados salvo que exista justificación legal y ética clara.

El inventario (`audit/inventory.csv`) incluye la columna `contains_possible_pii` con los recursos que pueden contener información personal.

## Flujo recomendado

1. `./run_all.sh`
2. `python scripts/fix_xls_redirects.py` (si se descargaron XLS)
3. `python scripts/03_build_inventory.py` (re-ejecutar para actualizar con redirects)
4. Revisar `audit/API_DEEP_AUDIT_REPORT.md`
5. Abrir `audit/inventory.csv` en LibreOffice/Sheets
6. Marcar manualmente: `usable`, `viejo_pero_util`, `metadata_only`, `duplicado`, `requiere_oficio`

## Seguridad

No subir a Git:
- `.env`
- `data/raw/`
- `data/processed/`
- Logs con URLs si contienen `auth_key`

El `.gitignore` ya excluye esas rutas.

## Estructura

```text
.
├── config/
│   └── audit_config.yaml
├── scripts/
│   ├── junar_common.py
│   ├── 01_snapshot_catalog.py
│   ├── 02_download_datastreams.py
│   ├── 03_build_inventory.py
│   └── fix_xls_redirects.py      # fix post-descarga para XLS con redirect S3
├── data/
│   ├── raw/
│   │   ├── catalog/
│   │   ├── datastreams/
│   │   └── endpoints/
│   └── processed/
├── audit/
├── logs/
├── .env.example
├── .gitignore
├── requirements.txt
└── run_all.sh
```
