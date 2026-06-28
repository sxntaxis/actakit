# Política de Seguridad — actakit

## Reporte de vulnerabilidades

Si descubrís una vulnerabilidad de seguridad, **no uses GitHub Issues**.
En su lugar:

1. **No incluyas información sensible** en ningún commit ni en Issues públicos.
2. Contactá directamente al mantenedor a través de GitHub.

## Vulnerabilidades conocidas y mitigaciones

actakit procesa documentos gubernamentales y archivos del sistema local.
Las siguientes mitigaciones están implementadas:

### Command injection

**Estado:** Mitigado.

Todos los scripts usan `subprocess.run` con listas de argumentos (no strings
de shell). Los argumentos derivados de usuario se sanitizan antes de usar.

```python
# BIEN — lista de argumentos
subprocess.run(["pdftotext", str(path), "-"], ...)

# MAL — string shell (NO se usa en este proyecto)
# subprocess.run(f"pdftotext {path} -", shell=True, ...)
```

### Path traversal

**Estado:** Mitigado.

Los nombres de archivo se sanitizan y las rutas se construyen con `pathlib`.
Los scripts rechazan paths que contain `..`.

```python
# Sanitización en setup_municipio.py
basename = re.sub(r'[^\w\-]+', '_', raw.lower())
```

### Symlink attacks

**Estado:** Mitigado.

Todas las operaciones de escritura usan `os.open` con `O_NOFOLLOW` o verifican
`os.path.islink()` antes de abrir. Esto impide escribir a través de symlinks.

### TOCTOU race conditions

**Estado:** Mitigado en operaciones de descarga.

Los archivos se crean atómicamente con `os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW`
antes de recibir contenido de la red.

### Deserialization attacks

**Estado:** Mitigado.

Todos los archivos JSON se leen con `json.load()` y YAML con
`yaml.safe_load()`. No se usa `pickle` ni `eval`.

## Configuración segura

- **No ejecutar como root** — el pipeline está diseñado para ejecutarse
  con permisos de usuario regulares.
- **Vault en directorio local** — no en `/tmp` ni en rutas compartidas.
- **Backups automáticos** — `aplicar_graduacion.py` crea backups antes de
  modificar actas.
- **Permisos de archivo** — archivos creados con `0o644`, directorios con
  `0o755` por defecto.

## Actualizaciones

Mantener el proyecto actualizado. Revisar el changelog para cambios de
seguridad en cada release.

---

_Last reviewed: 2026-06-28_