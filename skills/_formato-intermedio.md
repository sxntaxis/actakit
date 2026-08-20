# Formato intermedio

Este es el **contrato v2** entre las skills de extracción (`procesar-*`)
y la skill de integración (`tejer-hilo`). Toda skill `procesar-*` produce
un archivo que cumple este formato; `tejer-hilo` lo consume sin negociar.

El formato combina:

- **Frontmatter YAML** con metadatos machine-readable.
- **Cuerpo Markdown** con el contenido narrativo del borrador.

## Estructura general del archivo

```markdown
---
version_formato: 2
fuente_tipo: actas | prensa | redes | actas_institucionales | oficio | ...
fuente_id: <identificador canónico>
fecha_fuente: YYYY-MM-DD
fecha_extraccion: YYYY-MM-DD
estado: borrador | aprobado | integrado | descartado
hilos_destino:
  - <Hilo canónico 1>
  - <Hilo canónico 2>
episodios:
  - episodio_id: <fuente-id>-<locator>-<slug>
    titulo: <texto>
    fecha: YYYY-MM-DD
    hilo_destino: <Hilo canónico>
    tipo: evidencia | inferencia
    cuerpo: <markdown>
    cita: <texto canónico>
    fuente:
      archivo: <ruta local o URL canónica>
      articulo: <número o null>
      item: <número o null>
      pagina: <número o null>
  - ...
tablero_anuncios:
  - cita: <texto>
    descripcion: <una línea>
notas_extraccion:
  - <texto libre para el revisor>
---

# <Título de la fuente>

## Hilos afectados

- `Bloque/Hilo` — N episodio(s)

## Tablero de anuncios

- *<texto>*

## Ítems descartados por ruido

- *<texto>*

## Episodios

### → Hilo: `Bloque/Hilo`

#### YYYY-MM-DD — <Título del episodio>

<cuerpo>

> Fuente: <cita canónica>

## Propuestas de Hilo nuevo

- [propuesta_hilo_nuevo] ...

## Verificación final

- [x] ...
```

## Campos del frontmatter

### `version_formato`
Usar `2` para nuevos borradores. Los archivos Markdown históricos sin
frontmatter se aceptan como formato legado v1 y no deben migrarse en masa.

### `fuente_tipo`
Tipo de fuente. Valores: `actas`, `actas_institucionales`, `prensa`,
`redes`, `oficio`, `hallazgo`, `otro`.

### `fuente_id`
Identificador canónico. Ej: `Acta N° 156`.

### `fecha_fuente`
Fecha del documento en `YYYY-MM-DD`.

### `fecha_extraccion`
Fecha en que la skill produjo el borrador.

### `estado`
Ciclo de vida: `borrador` → `aprobado` → `integrado` → `descartado`.

### `hilos_destino`
Lista de Hilos canónicos a los que apunta el borrador.

### `episodios`
Lista estructurada con `titulo`, `fecha`, `hilo_destino`, `cuerpo`, `cita`.
Los nuevos episodios incluyen `episodio_id`, `tipo` y el objeto `fuente` para
que la cita pública tenga un localizador verificable. `tipo` es `evidencia` por
defecto; usar `inferencia` solo cuando la conclusión se declare como tal.

### `tablero_anuncios`
Lista de anuncios materiales sin acuerdo formal.

### `notas_extraccion`
Observaciones para el revisor humano.

## Compatibilidad entre versiones

- **Nuevos campos opcionales**: se aceptan sin cambios.
- **Campos renombrados**: se mantienen alias durante una versión.
- **Cambios incompatibles**: se incrementa `version_formato`.

## Versionado

Campo opcional `version_formato: 1`. Ausente → se asume `1`.
