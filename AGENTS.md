# AGENTS.md

> **Documentación para asistentes de IA — actakit v1.0**
>
> Antes de trabajar con este proyecto, leé este archivo completo.
> Contiene todo lo que un modelo de lenguaje necesita para configurar,
> ejecutar y extender el pipeline correctamente.

---

## ¿Qué es actakit?

actakit procesa actas del Conceho Municipal de Costa Rica y las convierte
en conocimiento estructurado: hilos temáticos, hallazgos y memoria
documental verificable.

Cada acta pasa por 5 etapas: scraping → extracción de texto → procesamiento
clasificado → extracción de anuncios → integración en hilos. El resultado
son archivos `.md` por tema (hilo) que agrupan todos los episodios
relacionados de múltiples actas, con atribuación completa.

**Idioma del proyecto:** Español (documentación, código, configuración).
Los patrones de extracción están calibrados para español costarricense.

---

## Project Layout

```
actakit/
├── scripts/
│   ├── scrape_actas.py          # Etapa 0: descargar PDFs
│   ├── pdftotext_actas.py       # Etapa 1: texto plano
│   ├── extract_tablero.py        # Etapa 3: extraer anuncios
│   ├── generate_anuncios.py     # Etapa 3: generar episodios
│   ├── aplicar_graduacion.py     # Etapa 4: mover anuncios a episodios
│   ├── merge_clasificaciones.py # Fusionar clasificaciones
│   │
│   ├── entity_index.py           # Extracción de entidades (regex)
│   ├── bootstrap_hilos.py        # Bootstrap de taxonomía
│   ├── generate_enrutamiento.py  # Generar enrutamiento.yaml
│   ├── integrate_hilos.py         # Etapa 5: integrar en hilos
│   ├── setup_municipio.py         # Guía para nuevos cantones
│   └── run_bootstrap.sh          # Orquestación bootstrap
│
├── skills/                       # Instrucciones para procesamiento AI
│   ├── _formato-intermedio.md    # Contrato de formato entre etapas
│   ├── _principios-compartidos.md
│   ├── procesar-acta/            # Skill principal de procesamiento
│   │   ├── SKILL.md
│   │   └── config/ejemplo/
│   │       ├── enrutamiento.yaml # Taxonomía de hilos (palabras clave)
│   │       ├── fuentes.yaml
│   │       └── inbox.yaml
│   ├── tejer-hilo/               # Integración en hilos
│   └── procesar-prensa/           # Prensa y comunicados
│
├── config.example.yaml           # Configuración base
└── requirements.txt               # Dependencias Python
```

---

## Configuración

### config.yaml

Archivo central del pipeline. Copiar desde `config.example.yaml`:

```yaml
municipio: "Atenas"                    # Nombre del cantón
vault_root: "./mi-vault"               # Raíz del vault (cada comunidad define)

hilos:
  bloques:
    - nombre: "GobernanzaLocal"
      hilos:
        - "Concejo Municipal y Funcionamiento"
        - "Auditoría y Control Interno"
        - ...
  alias:
    "Viejo nombre": "Nombre oficial"

scraping:
  url_base: "https://municipalidad-atenas.go.cr"
  secciones:
    concejo:
      path: "/actas-concejo"

procesamiento:
  actas_dir: "actas/procesadas"
  hilos_dir: "hilos"
```

### enrutamiento.yaml

El archivo más específico del cantón. Define **señales** (palabras clave,
instituciones, leyes, lugares) que mapean contenido a hilos temáticos.

```yaml
hilos:
  - nombre: "Concejo Municipal y Funcionamiento"
    señales:
      - "regidor"
      - "alcalde"
      - "sesión ordinaria"
      - "sesión extraordinaria"
      - "acta de sesión"
  - nombre: "Auditoría y Control Interno"
    señales:
      - "CGR"
      - "contraloría"
      - "informe de auditoría"
      - "hallazgo"
```

**Para un nuevo municipio:** ejecutar `bash scripts/run_bootstrap.sh` genera
automáticamente un `enrutamiento.yaml` desde las actas existentes.

---

## Pipeline — 5 etapas

### Etapa 0: Scraping

```bash
python scripts/scrape_actas.py --config config.yaml
python scripts/scrape_actas.py --config config.yaml --section concejo
python scripts/scrape_actas.py --config config.yaml --dry-run  # solo listar
```

Descarga PDFs desde el CMS de la municipalidad. Genera:
- PDFs en `actas/descargadas/[seccion]/`
- `inventario_actas.csv` en el directorio de salida

**Dependencias:** `requests`, `beautifulsoup4`

---

### Etapa 1: Extracción de texto

```bash
python scripts/pdftotext_actas.py \
    --input-dir actas/descargadas \
    --output-dir _texto_md \
    --vault actas/descargadas
```

Convierte PDFs/DOCXs a texto plano Markdown. Genera archivos `.md`
en `_texto_md/` con el texto extraído.

**Dependencias:** `poppler-utils` (pdftotext), `python-docx`

**Seguridad:** No sobreescribe archivos existentes a menos que `--force`.
Backups automáticos antes de sobreescritura.

---

### Etapa 2: Procesamiento (AI o humano)

**Usar `skills/procesar-acta/SKILL.md`** como guía de trabajo.

El resultado es un borrador en el inbox que, tras revisión humana, se
mueve al directorio de actas procesadas (`actas/procesadas/`).

**Formato de salida:** Archivo Markdown por acta con:
```markdown
# Acta N° 123 — Sesión Ordinaria — 27 de abril del 2026

## Episodios
### 2026-04-27 — Título del episodio
Contenido estructurado...
> Fuente: Acta N° 123, ...

## Tablero de anuncios
- Anuncio 1
- Anuncio 2
```

El formato exacto está especificado en `_formato-intermedio.md`.

---

### Etapa 3: Tablero y clasificación

```bash
# Extraer anuncios del tablero
python scripts/extract_tablero.py \
    --actas-dir actas/procesadas \
    --output ./datos/_anuncios_data.json

# Generar episodios desde clasificaciones
python scripts/generate_anuncios.py \
    --anuncios ./datos/_anuncios_data.json \
    --clasificaciones ./datos/_clasificaciones.json \
    --output ./datos/_episodios_generados.json \
    --candidatos ./datos/_candidatos_con_texto_completo.json

# Aplicar graduación (mover anuncios → episodios en actas)
python scripts/aplicar_graduacion.py \
    --actas-dir actas/procesadas \
    --herramientas-dir ./datos
    # --reset  # restaurar desde backup y reprocesar
```

**Idempotencia:** `aplicar_graduacion.py` detecta si los episodios ya
fueron agregados y los omite. Usar `--reset` para restaurar desde
backup y reprocesar desde cero.

---

### Etapa 4: Integración en hilos

```bash
python scripts/integrate_hilos.py --config config.yaml
```

Lee todas las actas procesadas, extrae episodios y reconstruye archivos
de Hilo en `hilos/`. Cada hilo es un archivo `.md` por bloque temático.

**Formato de hilo:**
```markdown
### YYYY-MM-DD — Título del episodio

Contenido del episodio...

> Fuente: Acta N° 123, 27 de abril del 2026, ...
```

**Seguridad:** No sigue symlinks. Usa `O_NOFOLLOW` en todas las
operaciones de escritura.

---

## Extracción de entidades

`scripts/entity_index.py` provee extracción de entidades vía regex,
sin depender de APIs externas.

### Instituciones costarricenses

Incluye ~50 instituciones CR con acrónimos y nombres completos:
CGR, CCSS, MEP, ICE, ASADA, ARESEP, etc.

### Patrones de leyes

```
Ley N° 7794        → Ley 7794 (Concejo Municipal)
Ley No. 8422        → Ley 8422 (Ordenamiento Territorial)
Ley 833             → Ley 833 (corta, 3 dígitos)
```

### Lugares

Distritos, cantones, provincias, ríos, rutas. Todos calibrados
para топонимы costarricenses (con soporte para acentos y variantes).

### Roles

Alcalde, síndico, regidor, presidente municipal, auditor interno,
gestor jurídico, tesorero municipal, etc.

---

## Canonical Format — Formato intermedio

El formato de las actas procesadas está especificado en
`skills/_formato-intermedio.md`. Todo procesamiento debe producir
output que cumpla este contrato.

**Estructura básica:**

```markdown
# Acta N° {num} — {tipo sesión} — {fecha en español}

## Episodios
### {YYYY-MM-DD} — {título del episodio}
{contenido estructurado}
> Fuente: Acta N° {num}, {fecha}, ...

## Tablero de anuncios
- {anuncio 1}
- {anuncio 2}
```

---

## Configurar para un nuevo municipio

### Paso 1 — Clonar y configurar

```bash
git clone https://github.com/sxntaxis/actakit.git
cd actakit
cp config.example.yaml config.yaml
# Editar: municipio, url_base, scraping.secciones
```

### Paso 2 — Bootstrap (recomendado)

```bash
# Requiere al menos 1 acta ya procesada en actas/procesadas/
bash scripts/run_bootstrap.sh
# Genera bootstrap/bootstrap_summary.json y bootstrap_report.md
```

### Paso 3 — Revisar taxonomía

```bash
# Revisar los outputs
cat bootstrap/bootstrap_report.md
cat bootstrap/bootstrap_summary.json

# Ajustar signals en enrutamiento.yaml
```

### Paso 4 — Procesar

```bash
# Descargar nuevas actas
python scripts/scrape_actas.py --config config.yaml

# Extraer texto
python scripts/pdftotext_actas.py --input-dir actas/descargadas

# Procesar actas (usar skills/procesar-acta/SKILL.md)

# Integrar
python scripts/integrate_hilos.py --config config.yaml
```

---

## Script reference

| Script | Entrada | Salida | Flags importantes |
|---|---|---|---|
| `scrape_actas.py` | URL municipal | PDFs + CSV | `--config`, `--section`, `--dry-run`, `--years` |
| `pdftotext_actas.py` | PDFs/DOCX | `.md` texto | `--input-dir`, `--output-dir`, `--vault`, `--force` |
| `extract_tablero.py` | Actas procesadas | JSON anuncios | `--actas-dir`, `--output` |
| `generate_anuncios.py` | Anuncios + clasificaciones | Episodios JSON | `--anuncios`, `--clasificaciones`, `--output` |
| `aplicar_graduacion.py` | Episodios + actas | Actas editadas | `--actas-dir`, `--herramientas-dir`, `--reset` |
| `integrate_hilos.py` | Actas procesadas | Hilos `.md` | `--config`, `--dry-run` |
| `bootstrap_hilos.py` | Actas procesadas | Reporte + JSON | `--actas-dir`, `--output`, `--lugares` |
| `generate_enrutamiento.py` | Bootstrap JSON | `enrutamiento.yaml` | `--input`, `--output` |
| `setup_municipio.py` | JSON de investigación | Config local | `--municipio`, `--lugares-json`, `--guide` |

---

## Common issues and solutions

### "No se encontraron actas" en scrape_actas

El sitio web de la municipalidad cambió su estructura. Revisar
los selectores CSS en `scraping.selectores` del config.yaml o usar
`--section` para especificar la ruta manualmente.

### pdftotext devuelve texto vacío

某些 PDFs están escaneados (imágenes, no texto). Se necesita OCR.
Solución temporal: procesar manualmente o usar `python-docx` para
DOCX únicamente.

### Bootstrap genera Coverage bajo (<60%)

Significa que la taxonomía semilla no cubre los temas de las actas.
Soluciones:
1. Procesar más actas (más datos = mejor clustering)
2. Agregar signals a `SEED_HILOS` en `scripts/bootstrap_hilos.py`
3. Crear nuevos hilos para topics detectados pero no clasificados

### apply_graduacion.py corrompe actas al re-ejecutar

Usar `--reset` para restaurar desde el último backup automático
(`actas/procesadas/bak_graduacion/`).

### Errores de encoding en textos

Todos los scripts usan `encoding='utf-8'` explicitado. Si hay
caracteres extraños, verificar que el archivo de entrada esté en UTF-8.

---

## Dependencias del sistema

```bash
# Linux
sudo apt install poppler-utils

# macOS
brew install poppler

# Python
pip install -r requirements.txt
```

`requirements.txt`:
- `pyyaml` — parsing de configuración
- `requests` — scraping HTTP
- `beautifulsoup4` — parsing HTML
- `python-docx` — extracción de DOCX

---

## Notas de seguridad

- No seguir symlinks en operaciones de escritura (mitigado en todos los scripts)
- Path traversal mitigado en nombres de archivo generados
- No hay command injection已知 — todos los subprocess usan listas, no shell strings
- Datos de producción siempre en vault local, nunca en el repo

---

## Referencias cruzadas

| Tema | Archivo |
|---|---|
| Formato de actas procesadas | `skills/_formato-intermedio.md` |
| Workflow de procesamiento AI | `skills/procesar-acta/SKILL.md` |
| Configuración completa | `config.example.yaml` |
| Patrones de entidades | `scripts/entity_index.py` (docstring) |
| Historial de cambios | `CHANGELOG.md` |

---

_Last reviewed: 2026-06-28 — actakit v1.0_
_Questions? Open a GitHub Issue or read the source._