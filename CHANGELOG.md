# Changelog — actakit

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-06-28

### Added

- **AGENTS.md** — Universal LLM-facing documentation for any AI assistant
- **README.md** — Spanish-primary landing page with English quick summary
- **LICENSE (AGPL v3)** — Code licensed under GNU AGPL v3
- **LICENSE.CC-BY** — Documentation licensed under CC-BY 4.0
- **.github/workflows/ci.yml** — GitHub Actions CI (Python compile + shellcheck + YAML validation)
- **.github/ISSUE_TEMPLATE/** — Bug report and feature request templates
- **SECURITY.md** — Security policy and known mitigations
- **requirements.txt** — Pinned Python dependencies with system requirements documented
- **.gitignore** — Enhanced gitignore with comprehensive Python, OS, and vault ignores

### Security (from audit and remediation)

- **Symlink attack mitigation** — All file writes now use `os.open` with `O_NOFOLLOW` and check `os.path.islink()` before writing, preventing arbitrary file overwrite via symlink attacks
- **TOCTOU race condition fix** — File downloads use atomic `os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW` to prevent race conditions between existence check and open
- **Path traversal mitigation** — Filename stems are sanitized to reject `..`, `.`-prefixed, or absolute paths in `pdftotext_actas.py`
- **Secure pip install** — `run_bootstrap.sh` now uses hash-verified pip install with pinned versions
- **Requirements file** — `requirements.txt` with pinned versions and hashes for supply-chain security

### Fixed

- **Idempotency** — `aplicar_graduacion.py` now checks if episodes already exist before adding; added `--reset` flag to restore from backup and reprocess
- **Accent handling** — `entity_index.py` now handles missing accents in institutions (via `accent_insensitive_pattern()`), law patterns (`[uú]mero`), role patterns (`s[ií]ndico`, `j[uú]ridico`), and place patterns (added `ü/Ü`)
- **Non-idempotent script** — `aplicar_graduacion.py` now detects already-processed actas and skips them; added `--reset` for reprocessing
- **Directory cleanup safety** — `integrate_hilos.py` now warns if HILOS_DIR is outside the working directory
- **pdftotext overwrite warning** — `pdftotext_actas.py` now warns when `--force` is used and creates automatic backups
- **Generic signal filtering** — `generate_enrutamiento.py` now uses STOPWORDS to filter out noisy generic suggestions
- **Invalid classification reporting** — `merge_clasificaciones.py` now tracks and reports invalid entries separately
- **Date parsing warnings** — `extract_tablero.py` now logs warnings for unrecognized month names

### Changed

- **README.md** — Complete rewrite: Spanish landing page + English quick summary + architecture diagram
- **requirements.txt** — Added metadata comments documenting system dependencies
- **.gitignore** — Comprehensive rewrite covering Python, vault data, OS artifacts, and IDE files

### Removed

- **pipeline-actas-municipal references** — Internal path references updated to reflect the new repo name

---

## [0.x] — Pre-rebranding

See commit history for earlier changes to the `pipeline-actas-municipal` codebase.

## Fix Status Summary

| Severity | Item | Status |
|----------|------|--------|
| CRITICAL | Symlink attack - setup_municipio.py save_json() | ✅ FIXED |
| CRITICAL | Symlink attack - integrate_hilos.py HILOS file write | ✅ FIXED |
| CRITICAL | Symlink attack - scrape_actas.py CSV write | ✅ FIXED |
| CRITICAL | Symlink attack - scrape_actas.py download TOCTOU | ✅ FIXED |
| CRITICAL | Symlink attack - pdftotext_actas.py Markdown write | ✅ FIXED |
| HIGH | Symlink attack - pdftotext_actas.py sync_to_vault copy2 | ✅ FIXED |
| HIGH | Path traversal - pdftotext_actas.py filename stem | ✅ FIXED |
| HIGH | Race condition - integrate_hilos.py symlink after cleaning | ✅ FIXED |
| HIGH | Accent handling - entity_index.py institution acronyms | ✅ FIXED |
| HIGH | Accent handling - entity_index.py multi-word institutions | ✅ FIXED |
| HIGH | Accent handling - entity_index.py role patterns | ✅ FIXED |
| HIGH | Accent handling - entity_index.py law patterns | ✅ FIXED |
| HIGH | Accent handling - entity_index.py place patterns | ✅ FIXED |
| HIGH | Non-idempotent aplicar_graduacion.py | ✅ FIXED |
| HIGH | Insecure pip install - run_bootstrap.sh | ✅ FIXED |
| MEDIUM | Unprotected directory cleanup | ✅ FIXED |
| MEDIUM | Overwrite user-edited files - pdftotext_actas.py | ✅ FIXED |
| LOW | Generic signal generation | ✅ FIXED |
| LOW | Silent skipping in merge_clasificaciones.py | ✅ FIXED |
| LOW | Date parsing warnings - extract_tablero.py | ✅ FIXED |

## Table of Contents
1. [Critical & High Severity Issues](#critical--high-severity-issues)
2. [Medium Severity Issues](#medium-severity-issues)
3. [Low Severity Issues](#low-severity-issues)
4. [Cross-Cutting Recommendations](#cross-cutting-recommendations)

---

## Critical & High Severity Issues

### Security Issues

#### **HIGH: Symlink Attack - Arbitrary File Overwrite**
- **File**: `scripts/setup_municipio.py`
- **Location**: `save_json()` function (lines 132-141); called at lines 196, 215, 235
- **Issue**: Opens files for writing without checking if target is a symbolic link. Attacker can predict output filename and create symlink before script runs to overwrite arbitrary files (e.g., `/etc/passwd`).
- **Attack Scenario**: Attacker with write access to output directory creates symlink `atenas_lugares_local.json → /etc/passwd`. Script running as root overwrites `/etc/passwd` with JSON data.
- **Suggested Fix**: Before opening file, verify target is not a symlink (`if os.path.islink(filepath): raise Error`) or open with `os.open(..., os.O_NOFOLLOW)` and wrap with `fdopen`.

#### **HIGH: Symlink Attack - HILOS File Overwrite**
- **File**: `scripts/integrate_hilos.py`
- **Location**: HILOS file write block (lines 339-342)
- **Issue**: Opens HILOS output files for writing without checking for symlinks. Although cleaning phase skips existing symlinks, a symlink present before cleaning will be skipped and remain, leading to follow-on write that overwrites target.
- **Attack Scenario**: Attacker creates symlink `habilitación.md → /etc/shadow` in HILOS directory. Script overwrites `/etc/shadow` with HILOS content.
- **Suggested Fix**: Before opening file for writing, check `if os.path.islink(filepath):` and either skip, remove symlink after verification, or open with `os.O_NOFOLLOW`.

#### **HIGH: Symlink Attack - CSV File Overwrite**
- **File**: `scripts/scrape_actas.py`
- **Location**: CSV file creation (lines 248-254)
- **Issue**: Opens `inventario_actas.csv` for writing without verifying path is not a symlink.
- **Attack Scenario**: Attacker creates symlink `inventario_actas.csv → ~/.ssh/authorized_keys`. Script overwrites authorized keys file, locking user out.
- **Suggested Fix**: Before opening file, check `if os.path.islink(csv_path):` and refuse to write, or open with `os.O_NOFOLLOW`.

#### **HIGH: Symlink Attack - Downloaded File Overwrite (TOCTOU Race)**
- **File**: `scripts/scrape_actas.py`
- **Location**: `download_file()` function – file write after existence check (lines 143-146 and 160-162)
- **Issue**: Checks `if out_path.exists():` then opens file for writing. Attacker can replace file with symlink between check and open().
- **Attack Scenario**: Attacker predicts downloaded filename (e.g., `2024-Acta-Título.pdf`) and after existence check but before open, replaces it with symlink to `/etc/crontab`. Script writes PDF to crontab, enabling arbitrary code execution.
- **Suggested Fix**: Open file with `os.open(..., os.O_CREAT | os.O_EXCL | os.O_WRONLY)` (or `os.O_NOFOLLOW`) and handle error if file already exists or is symlink.

#### **HIGH: Symlink Attack - Markdown File Overwrite**
- **File**: `scripts/pdftotext_actas.py`
- **Location**: Markdown write (line 89: `md_path.write_text(...)`)
- **Issue**: Writes converted text to Markdown file without checking if target is a symlink.
- **Attack Scenario**: Attacker creates symlink `acta1.md → /etc/hosts`. Script overwrites `/etc/hosts` with extracted text, disrupting networking.
- **Suggested Fix**: Before writing, check `if md_path.is_symlink():` and either refuse to write or remove symlink after verification.

### Data Integrity Issues

#### **HIGH: Non-idempotent Script Causing Data Corruption**
- **File**: `scripts/aplicar_graduacion.py`
- **Location**: Main processing loop (lines 75-155)
- **Issue**: Script not idempotent. Running second time on same actas directory attempts to remove announcements from tablero using original indices stored in `_candidatos_con_texto_completo.json`. After first run, tablero section altered, causing incorrect text removal or duplication of episodes.
- **Impact**: Potential corruption of actas files – loss of original tablero content, duplicate episodes, or malformed markdown structure. Backups overwritten on each run, making original recovery impossible after two executions.
- **Suggested Fix**: 
  - Make script idempotent by checking if announcement already moved (verify episodio text exists in target location before adding)
  - OR add `--reset` flag that restores from backup before processing
  - OR require users to start from clean state (clear output directories) between runs

#### **HIGH: Canonical Format Mismatch (Previously Fixed)**
- **Note**: This was identified and fixed during initial remediation. Parser in `bootstrap_hilos.py` now correctly parses Format A (`### → Hilo: \`name\`` + `#### YYYY-MM-DD — Title`) as defined in `_formato-intermedio.md`.

### Regex/Parsing Issues

#### **HIGH: Missing Accent Handling in Institution Names and Patterns**
- **File**: `scripts/entity_index.py`
- **Location**: 
  - Institution names (acronym-based): Lines 342-344 
  - Multi-word institution patterns (INSTITUTION_PATTERNS): Lines 107-148 & 346-348
- **Issue**: 
  - Acronym-based patterns use case-sensitive matching (missing `re.IGNORECASE` flag)
  - Both acronym-based and multi-word patterns require exact accented characters and fail if accents omitted in input text (common in informal writing or OCR errors)
- **Example Input**: 
  - `"cgr emitió un informe"` (lowercase acronym) → fails to match "CGR"
  - `"La contraloria general de la republica emitió un informe"` (missing accents) → fails to match "Contraloría General de la República"
- **Impact**: Missed detections of institution entities when text uses incorrect casing or omits accents
- **Suggested Fix**: 
  - For acronyms: Add `re.IGNORECASE` flag when compiling patterns (line 344)
  - For multi-word patterns: Preprocess text to normalize accents (e.g., using `unidecode`) or expand patterns to include accent/unaccent variants (e.g., `[oó]` for 'ó')

#### **HIGH: Missing Accent Handling in Role Patterns**
- **File**: `scripts/entity_index.py`
- **Location**: 373-386 (ROLE_PATTERNS) & 366-368 (pattern compilation)
- **Issue**: 
  - Role patterns for "síndico"/"síndica" and "jurídico" require accented characters
  - Fails to match when accents omitted (e.g., "sindico", "juridico")
  - Note: Patterns already use `re.IGNORECASE` for case handling, but accents are not covered
- **Example Input**: 
  - `"El sindico presento un informe"` (missing accent) → fails to match "síndico" role
  - `"El gestor juridico reviso el contrato"` (missing accent) → fails to match "jurídico" in "gestor jurídico"
- **Impact**: Missed detections of role entities when accents omitted in text
- **Suggested Fix**: 
  - Replace accented letters in patterns with character classes including accented/unaccented versions:
    - `síndico` → `s[ií]ndico`
    - `jurídico` → `j[uú]ridico`
  - (Keep existing `re.IGNORECASE` flag for case handling)

#### **HIGH: Missing Accent Handling in Law Pattern ("número")**
- **File**: `scripts/entity_index.py`
- **Location**: 225-228 (LAW_PATTERNS[0]) & 350-352 (pattern compilation)
- **Issue**: 
  - First law pattern requires accented "ú" in "úmero"
  - Fails to match when text uses unaccented "u" (e.g., "numero")
  - Pattern already uses `re.IGNORECASE` for case handling
- **Example Input**: 
  - `"Ley numero 123 cuatro cinco"` → fails to match first pattern (requires "úmero")
  - Note: May match via other alternatives (e.g., "N." or "N°") but less reliably
- **Impact**: Missed detections of law entities when "número" appears without accent
- **Suggested Fix**: 
  - Modify pattern to accept accented/unaccented "u":
    - Change `úmero` → `[uú]mero`
  - Example: 
    ```python
    r'Ley\s+(?:N(?:o\.\s*|\.?\s*°?\s*|[uú]mero\s+))?(\d{3,5}(?:\.\d{1,4})?)'
    ```

#### **HIGH: Missing 'ü' in Place Pattern Character Classes**
- **File**: `scripts/entity_index.py`
- **Location**: 275-281 (PLACE_PATTERNS) & 354-356 (pattern compilation)
- **Issue**: 
  - Character classes `[A-ZÁÉÍÓÚÑ]` and `[a-záéíóúñ]` omit 'Ü' and 'ü'
  - Fails to match place names containing 'ü' (e.g., "Übert", "Güimar")
- **Example Input**: 
  - `"El distrito de Güitar es hermoso"` → fails to match district pattern (contains 'ü')
- **Impact**: Missed detections of place entities with 'ü' in names
- **Suggested Fix**: 
  - Update character classes to include ü/Ü:
    - `[A-ZÁÉÍÓÚÑ]` → `[A-ZÁÉÍÓÚÜÑ]`
    - `[a-záéíóúñ]` → `[a-záéíóúñü]`

#### **MEDIUM: Potential Over-Matching in Institution Acronyms (Lower Risk)**
- **File**: `scripts/entity_index.py`
- **Location**: 342-344
- **Issue**: 
  - Acronym patterns use word boundaries (`\b`) but may match substrings in longer words
  - Example: "SCGRTX" could partially match "CGR" if not properly bounded
- **Example Input**: 
  - `"El scgrtx emitió un informe"` → might incorrectly match "CG" as part of "scgrtx"
- **Impact**: Low-risk false positives (acronyms embedded in longer strings)
- **Suggested Fix**: 
  - Ensure word boundaries are appropriate for Spanish text (consider punctuation/adjascent characters)
  - Current `\b` is generally sufficient but verify with test cases

### Error Handling Issues

#### **MEDIUM: Insecure Package Installation**
- **File**: `run_bootstrap.sh`
- **Location**: Lines 34-37: `pip install pyyaml` without verification
- **Issue**: Installs Python package from PyPI without verifying integrity or using trusted index. Compromised or typos-squatted package could lead to code execution.
- **Attack Scenario**: Attacker publishes malicious version of `pyyaml` (or similarly named package) to PyPI; script installs it, leading to arbitrary code execution when import occurs.
- **Suggested Fix**: Use pinned version from trusted index or requirements file with hashes (`pip install --require-hashes -r requirements.txt`). Prefer installing dependencies in virtual environment or using system package manager.

#### **MEDIUM: Potential Symlink Follow in shutil.copy2**
- **File**: `scripts/pdftotext_actas.py`
- **Location**: `sync_to_vault()` – lines 108-109: `shutil.copy2(src, dst)`
- **Issue**: `shutil.copy2` follows symlinks; if attacker can place symlink in destination directory (`vault_md`), copy will write to symlink's target, possibly overwriting arbitrary files.
- **Attack Scenario**: Attacker with write access to vault directory creates symlink `legítimo.md → /etc/sudoers`. Sync runs, copy overwrites `/etc/sudoers`.
- **Suggested Fix**: Before copying, check if `dst` is a symlink (`os.path.islink(dst)`) and either skip, remove, or copy with `follow_symlinks=False` (available in Python 3.8+ via `shutil.copy2(src, dst, follow_symlinks=False)`).

#### **MEDIUM: Race Condition - Symlink Creation After Cleaning**
- **File**: `scripts/integrate_hilos.py`
- **Location**: Between `clean_hilos_dir()` walk (lines 197-215) and HILOS file write loop (lines 329-348)
- **Issue**: After cleaning pass skips existing symlinks, attacker could create symlink in target directory before write loop begins, causing script to follow it and overwrite unintended file.
- **Attack Scenario**: Attackor monitors directory and immediately after cleaning walk finishes, creates symlink `seguridad.md → /root/.bashrc`. Subsequent write overwrites bashrc file.
- **Suggested Fix**: 
  - Hold directory open during entire operation (open directory with `os.opendir()` and use `os.openat` with `O_NOFOLLOW` for each file)
  - OR re-check for symlinks immediately before opening each file for writing (as in fixes above)

---

## Medium Severity Issues

### Data Integrity Issues

#### **MEDIUM: Unprotected Data Deletion in Hilo Directory Cleanup**
- **Files**: `scripts/bootstrap_hilos.py` (lines 187-215) and `scripts/integrate_hilos.py` (lines 187-215)
- **Location**: Function `clean_hilos_dir`
- **Issue**: Function deletes all `.md` files in specified `hilos_dir` (and subsequently removes empty directories). Includes safety checks to avoid system directories (`/`, `$HOME`, current directory) but does not prevent users from specifying arbitrary directories (e.g., `~/Documents`) that may contain important unrelated markdown files.
- **Impact**: Risk of accidental data loss if `hilos_dir` is misconfigured.
- **Suggested Fix**: 
  - Strengthen safety checks: disallow paths under user's home directory unless explicitly confirmed, or restrict to subdirectories of project workspace
  - OR change behavior to move files to backup directory instead of deleting (e.g., timestamped backup folder)
  - OR require explicit `--force-delete` flag

#### **MEDIUM: Overwriting User-Edited Generated Files**
- **File**: `scripts/pdftotext_actas.py`
- **Location**: `convert_document` function (lines 71-90) and main loop (lines 151-155)
- **Issue**: When `--force` is used, script reconverts all PDF/DOCX files, overwriting any existing `.md` files. If users manually edit these generated files (e.g., to fix OCR errors), those edits will be lost.
- **Impact**: Loss of manual corrections or customizations in intermediate markdown files.
- **Suggested Fix**: 
  - Add warning when `--force` is used, informing users that existing `.md` files will be overwritten
  - OR consider implementing backup mechanism (e.g., `.md.bak`) before overwriting
  - OR make non-force mode the default safe behavior (skip if `.md` exists and is newer than source)

#### **MEDIUM: Path Traversal via Filename Stem**
- **File**: `scripts/pdftotext_actas.py`
- **Location**: `convert_document()` – lines 72-73: `stem = doc_path.stem; md_path = output_dir / f"{stem}.md"`
- **Issue**: If filename in input directory contains `..` as its stem (e.g., `..pdf` or `....pdf`), resulting `md_path` will resolve outside intended output directory, allowing writing to arbitrary locations.
- **Attack Scenario**: Attacker uploads file named `..pdf` to input directory. Script writes extracted text to `output_dir/../.md` (i.e., file in parent directory), potentially overwriting sensitive files.
- **Suggested Fix**: Sanitize stem to remove path-traversal sequences. For example, reject any stem containing `..` or `.` or replace path separators; better yet, use `os.path.basename` or `Path.name` and strip extension safely.

#### **MEDIUM: Generic Signal Generation May Produce Irrelevant Suggestions**
- **File**: `scripts/generate_enrutamiento.py`
- **Location**: `_generic_signals_for` function (lines 156-167)
- **Issue**: Generates suggested signals from hilo names by splitting on spaces and filtering words; may produce irrelevant or noisy suggestions (e.g., from words like "municipal").
- **Impact**: Low-quality suggestions in generated `enrutamiento.yaml`, requiring manual cleanup.
- **Suggested Fix**: Improve filtering (e.g., exclude common Spanish stopwords, refine regex patterns) or allow manual curation of suggested signals.

### Error Handling Issues

#### **MEDIUM: Missing Input Validation on Output Directory**
- **Location**: `--output-dir` arguments in `setup_municipio.py`, `pdftotext_actas.py`, `scrape_actas.py`, etc.
- **Issue**: Scripts allow user to specify arbitrary output directory. While intended functionality, could lead to accidental overwrites if user mis-specifies a path.
- **Risk**: Low – usability issue, not security boundary violation assuming user runs script with own privileges.
- **Suggested Fix**: Add confirmation prompt when output directory contains existing files or is outside expected project scope.

#### **MEDIUM: Information Leakage via Console Output**
- **Location**: Various `print()` statements` statements` statements` that may reveal file paths or internal details
- **Issue**: Console output may reveal sensitive information
- **Risk**: Low – only relevant if logs are exposed to unauthorized parties
- **Suggested Fix**: Review and sanitize console output; consider using logging module with appropriate levels instead of print statements.

---

## Low Severity Issues

### Data Integrity Issues

#### **LOW: Potential Date Parsing Errors in Tablero Extraction**
- **File**: `scripts/extract_tablero.py`
- **Location**: `spanish_date_to_iso` function (lines 15-24)
- **Issue**: Returns empty string for unrecognized month names (e.g., misspelled months), which could lead to invalid dates in output JSON.
- **Impact**: Minor data quality issues; unlikely to break pipeline but may cause downstream confusion.
- **Suggested Fix**: Log warning when month not found and consider returning original string or placeholder date for manual review.

#### **LOW: Silent Skipping of Invalid Classifications**
- **File**: `scripts/merge_clasificaciones.py`
- **Location**: Lines 62-65
- **Issue**: Prints warning for invalid categories but continues processing, omitting invalid entry from output.
- **Impact**: Potential loss of classification data if typos exist in input JSONs; user may not notice missing entries.
- **Suggested Fix**: Add option to fail on invalid categories or include summary of skipped items in final report.

### Error Handling Issues

#### **LOW: File Handle Resource Management**
- **Location**: Various files
- **Issue**: While most files use `with open()` consistently, some may have file handles not properly closed in error conditions
- **Suggested Fix**: Ensure all file operations use context managers (`with open()`) or explicitly close handles in finally blocks.

#### **LOW: Memory Leaks from Growing Lists/Dicts**
- **Location**: Scripts that process large numbers of files
- **Issue**: Potential memory leaks from accumulating data in lists/dicts without clearing
- **Suggested Fix**: Process files in batches or clear intermediate data structures when no longer needed.

#### **LOW: Temporary Files Not Cleaned Up**
- **Location**: Scripts that create temporary files
- **Issue**: Temporary files may not be cleaned up on error or early exit
- **Suggested Fix**: Use `tempfile` module or ensure cleanup in finally blocks.

---

## Cross-Cutting Recommendations

### **Security**
1. **Principle of Least Privilege**: Run scripts with minimum required permissions; consider sandboxing (containers, userspaces) for untrusted input
2. **Input Validation**: Validate and sanitize all user inputs (filenames, directory paths, command arguments) before use
3. **Secure Defaults**: Use secure defaults (e.g., `os.O_NOFOLLOW`, `re.IGNORECASE` where appropriate)
4. **Dependency Security**: Use pinned versions, hashes, or virtual environments for dependencies; avoid blind `pip install` in production scripts

### **Data Integrity**
1. **Idempotency**: Design scripts to be safely re-runnable without corruption or data loss
2. **Backups**: Implement automatic backups before destructive operations
3. **Atomic Writes**: Use temporary files + atomic rename for critical writes to prevent partial writes
4. **Validation**: Validate data at each pipeline stage; maintain clear contracts between scripts

### **Error Handling**
1. **Comprehensive Error Handling**: Catch and handle specific exceptions rather than bare `except:`
2. **Resource Management**: Use context managers (`with` statements) for all resources (files, network connections, etc.)
3. **Logging**: Use proper logging module instead of print statements for better control and auditability
4. **Fail Fast**: Validate inputs early and fail fast with clear error messages rather than silent failures

### **Testing & Validation**
1. **Unit Tests**: Create comprehensive unit tests for all parsing and regex functions
2. **Fuzz Testing**: Implement fuzz testing for inputs that could cause ReDoS or incorrect parsing
3. **Integration Tests**: Test end-to-end pipeline with known good and bad inputs
4. **Security Testing**: Regularly run security scans and penetration tests

### **Documentation**
1. **Clarify Assumptions**: Document assumptions about input formats, character encodings, and expected data structures
2. **Maintain Consistency**: Keep SEED_HILOS, entity_index.py categories, and config.example.yaml in sync
3. **Update Documentation**: Keep `_formato-intermedio.md` and SKILL.md updated with any parser or behavior changes

---

## Next Steps for Human Validation

1. **Review each finding** in this roadmap
2. **Prioritize fixes** based on your threat model and deployment environment
3. **Validate suggested fixes** against your specific use cases
4. **Consider trade-offs** between security, usability, and functionality
5. **Implement fixes** in a controlled environment before deploying to production

**Note**: This roadmap documents issues and suggested fixes but does not implement any changes. Human review and validation is required before applying any modifications to the codebase.

---
*Generated from comprehensive security, regex/parsing, error handling, and data integrity audits of the pipeline-actas-municipal codebase.*