---
name: tejer-hilo
description: >
  Integra borradores aprobados (producidos por procesar-*) en los archivos
  de Hilo correspondientes dentro de 2 Base Cantonal/Hilos/.
---

# tejer-hilo

Esta skill toma borradores con `estado: aprobado` del Inbox y los integra
en los Hilos correspondientes. Opera sobre el [formato intermedio]
(../_formato-intermedio.md).

## Cuándo aplica

- Hay borradores aprobados en el Inbox pendientes de integración.
- El usuario pide "tejé estos borradores", "integrá las actas", etc.

## Inputs

1. Ruta al Inbox (de `_config/inbox.yaml` de la skill que produjo el borrador).
2. Lista de archivos a integrar, o etiqueta de lote.
3. Directorio de Hilos destino.

## Procedimiento

1. Leer cada borrador con `estado: aprobado`.
2. Para cada episodio en el frontmatter:
   a. Resolver el Hilo destino por nombre canónico.
   b. Si el archivo de Hilo no existe, crearlo.
   c. Insertar el episodio en orden cronológico.
3. Para cada anuncio en `tablero_anuncios` marcado como `levantar_a_hilo`:
   a. Promoverlo a episodio.
4. Actualizar el estado del borrador a `integrado`.
5. Reportar resultados.

## Reglas

- No modificar episodios existentes.
- No crear Hilos nuevos sin autorización explícita.
- No tocar archivos fuera de `2 Base Cantonal/Hilos/`.
