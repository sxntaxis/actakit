# actakit

> Pipeline documental para actas de gobierno local — procesamiento con IA y sin lock-in.

[![CI](https://github.com/sxntaxis/actakit/actions/workflows/ci.yml/badge.svg)](https://github.com/sxntaxis/actakit/actions)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![License: CC-BY-4.0](https://img.shields.io/badge/license-CC--BY--4.0-blue.svg)](LICENSE.CC-BY)

---

## English · Quick Summary

**actakit** transforms Costa Rican municipal council meeting minutes (actas)
into structured, searchable knowledge: topic-based threads (hilos), findings,
and verifiable documentary records.

- **What it does**: Download PDFs → extract text → classify with AI → integrate
  into topical threads → generate outputs for civic use.
- **For whom**: Costa Rican citizen oversight groups, journalists, researchers,
  and LLMs working on local government accountability.
- **Key feature**: Bootstrap mode auto-generates the topic taxonomy from your
  existing documents — no manual setup required.

> **For AI assistants**: Read `AGENTS.md` before working with this project.
> It contains the complete technical context, configuration reference, and
> pipeline workflow that LLMs need.

---

## En español · Qué es

**actakit** es una herramienta de código abierto para procesar actas del
Concejo Municipal de Costa Rica y convertirlas en conocimiento estructurado.

Con actakit podés:

- Descargar actas desde el sitio web municipal automáticamente.
- Extraer texto de PDFs y DOCXs sin dependencias externas de API.
- Procesar actas con asistentes de IA (Claude, opencode, Cursor, etc.)
  siguiendo un formato estructurado y verificable.
- Generar una taxonomía de temas (hilos) automáticamente a partir de
  tus actas — sin empezar desde cero.
- Extraer anuncios, clasificar contenido y generar salidas para
  publicaciones, oficios y reportes ciudadanos.
- Reconstruir hilos temáticos automáticamente a partir de episodios
  extraídos de múltiples actas.

No requiere cuenta en ninguna plataforma. Todo funciona con scripts
locales y archivos JSON/YAML de configuración.

---

## Arquitectura

> The current file pipeline is stable for existing work. The proposed durable
> civic-record architecture and implementation gates are in
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
> [`docs/ROADMAP.md`](docs/ROADMAP.md), and [`docs/STATUS.md`](docs/STATUS.md).
> The full proposed 1.0 contracts, implementation plan, and distribution gates
> are in [`docs/CONTRACTS.md`](docs/CONTRACTS.md),
> [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md), and
> [`docs/RELEASE_1_0.md`](docs/RELEASE_1_0.md).

```
┌──────────────┐   ┌───────────────┐   ┌─────────────────┐
│  Scrapeo      │──→│  Extracción    │──→│  Procesamiento   │
│  scrape_actas │   │  pdftotext      │   │  skill AI / humano │
└──────────────┘   └───────────────┘   └─────────────────┘
                                               │
                       ┌────────────────────────┘
                       ↓
┌──────────────┐   ┌───────────────┐   ┌─────────────────┐
│  Tablero      │──→│  Clasificación │──→│  Graduación      │
│  extract      │   │  generate      │   │  aplicar          │
└──────────────┘   └───────────────┘   └─────────────────┘
                                               │
─────────────────────── INTEGRACIÓN ─────────────────────────
                       ↓
          ┌──────────────────────────┐
          │  Integración             │
          │  integrate_hilos         │
          └──────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ↓                         ↓
   [hilos/*.md]            [actas procesadas]
```

**Flujo de datos:**

```
[sitio web municipal]
      ↓ scrape_actas.py
[PDFs en actas/descargadas/]
      ↓ pdftotext_actas.py
[_texto_md/] ← texto plano
      ↓ procesar-acta (skill AI o humano)
[borrador en inbox/] ← revisión humana
      ↓ aprobación
[acta procesada en actas/procesadas/]
      ↓                          ↕
  integrate_hilos.py       extract_tablero.py
      ↓                          ↓
[hilos/]           [anuncios → clasificación → graduación]
```

---

## Características principales

| Característica | Descripción |
|---|---|
| **Scraping automático** | Descarga actas desde el CMS de la municipalidad sin API |
| **Extracción sin API** | pdftotext + python-docx, sin costos de API externa |
| **Procesamiento con IA** | Skill para asistentes AI con formato intermedio verificable |
| **Bootstrap automático** | Genera taxonomía de hilos desde las actas existentes |
| **Multi-municipalidad** | Configuración extensible para cualquier cantón costarricense |
| **Entidades CR** | Patrones para instituciones, leyes, lugares y roles costarricenses |
| **Idempotencia** | Los scripts se pueden ejecutar múltiples veces sin corrupto |
| **Seguridad** | Sin command injection, symlink protection, path traversal mitigado |

---

## Primeros pasos

### 1 — Clonar e instalar

```bash
git clone https://github.com/sxntaxis/actakit.git
cd actakit
pip install -r requirements.txt

# Dependencia del sistema (Linux/macOS)
sudo apt install poppler-utils   # Linux
brew install poppler             # macOS
```

### 2 — Configurar para tu municipalidad

```bash
cp config.example.yaml config.yaml
# Editar config.yaml con el nombre del cantón, URL del sitio, paths
```

### 3 — Ejecutar bootstrap (opcional, recomendado)

```bash
# Genera la taxonomía de hilos automáticamente desde tus actas existentes
bash scripts/run_bootstrap.sh
```

### 4 — Procesar actas

```bash
# 0. Descargar PDFs
python scripts/scrape_actas.py --config config.yaml

# 1. Extraer texto
python scripts/pdftotext_actas.py --input-dir actas/descargadas --vault actas/descargadas

# 2. Procesar con IA → seguir skills/procesar-acta/SKILL.md

# 3. Extraer tablero de anuncios
python scripts/extract_tablero.py --actas-dir actas/procesadas

# 4. Integrar en hilos
python scripts/integrate_hilos.py --config config.yaml
```

---

## Para LLMs y asistentes AI

> **Importante:** Antes de trabajar con este proyecto, leé `AGENTS.md`.
> Ese archivo contiene toda la información que un modelo de lenguaje
> necesita para configurar, ejecutar y extender el pipeline correctamente.

Breve resumen de los archivos clave:

| Archivo | Propósito |
|---|---|
| `AGENTS.md` | Documentación universal para cualquier LLM |
| `skills/procesar-acta/SKILL.md` | Workflow de procesamiento de actas |
| `skills/procesar-acta/config/ejemplo/enrutamiento.yaml` | Taxonomía de ejemplo |
| `config.example.yaml` | Configuración base del pipeline |
| `_formato-intermedio.md` | Contrato de formato entre etapas |

---

## Estructura del proyecto

```
actakit/
├── README.md                    ← este archivo
├── AGENTS.md                    ← documentación para LLMs
├── LICENSE                      ← AGPL v3 (código fuente)
├── LICENSE.CC-BY                ← CC-BY 4.0 (documentación)
├── requirements.txt             ← dependencias Python
├── config.example.yaml           ← configuración de ejemplo
├── FIX_ROADMAP.md               ← registro de cambios
│
├── scripts/                     ← pipeline CLI
│   ├── scrape_actas.py          ← descarga PDFs del sitio municipal
│   ├── pdftotext_actas.py       ← extrae texto de PDFs/DOCX
│   ├── extract_tablero.py       ← extrae anuncios de actas procesadas
│   ├── generate_anuncios.py     ← genera episodios desde clasificaciones
│   ├── aplicar_graduacion.py    ← gradúa anuncios a episodios en actas
│   ├── merge_clasificaciones.py ← fusiona clasificaciones de múltiples fuentes
│   │
│   ├── entity_index.py          ← extracción de entidades (regex CR)
│   ├── bootstrap_hilos.py       ← bootstrap automático de taxonomía
│   ├── generate_enrutamiento.py ← genera enrutamiento.yaml desde bootstrap
│   ├── integrate_hilos.py       ← integra episodios en archivos de hilo
│   ├── setup_municipio.py       ← descubrimiento LLM de lugares locales
│   └── run_bootstrap.sh         ← orquestación del bootstrap
│
└── skills/                      ← instrucciones para asistentes AI
    ├── _formato-intermedio.md   ← contrato de formato entre skills
    ├── _principios-compartidos.md
    ├── procesar-acta/           ← procesamiento de actas
    │   ├── SKILL.md
    │   └── config/ejemplo/
    │       ├── enrutamiento.yaml
    │       ├── fuentes.yaml
    │       └── inbox.yaml
    ├── tejer-hilo/SKILL.md      ← integración en hilos
    └── procesar-prensa/SKILL.md ← prensa y comunicados
```

---

## Scripts principales

| Script | Qué hace |
|---|---|
| `scrape_actas.py` | Descarga actas en PDF/DOCX desde el sitio municipal |
| `pdftotext_actas.py` | Convierte PDFs y DOCXs a texto plano |
| `bootstrap_hilos.py` | Extrae entidades + clasifica + propone nueva taxonomía |
| `generate_enrutamiento.py` | Convierte el output del bootstrap en `enrutamiento.yaml` |
| `extract_tablero.py` | Extrae el tablero de anuncios de actas ya procesadas |
| `generate_anuncios.py` | Genera episodios desde clasificaciones de anuncios |
| `aplicar_graduacion.py` | Mueve anuncios clasificados a episodios en las actas |
| `integrate_hilos.py` | Reconstruye archivos de hilo desde episodios de actas |
| `setup_municipio.py` | Guía de investigación asistida por LLM para nuevos cantones |

---

## Licencia

**Código fuente:** [AGPL v3](LICENSE) — publicado por sxntaxis.

**Documentación y contenido creativo:** [CC-BY 4.0](LICENSE.CC-BY) — atribuación requerida.

---

## Autor

**sxntaxis** — https://github.com/sxntaxis

Preguntas, issues y contribuciones bienvenidas a través de GitHub Issues.
