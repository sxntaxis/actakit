---
name: procesar-acta
description: >
  Convierte actas del Concejo Municipal en borradores estructurados,
  identificando episodios documentales, filtrando ruido procedimental
  y enrutando cada episodio al Hilo correspondiente de la Base Cantonal.
  Invocar cuando el usuario entrega PDFs o textos de actas.
---

# procesar-acta

Esta skill convierte actas del Concejo Municipal en borradores estructurados,
listos para revisión humana. Es la pieza de la pipeline que interpreta la
fuente (PDF, OCR, extracto `.md`); el resto de la pipeline es genérico.

## Cuándo aplica

- Hay actas del Concejo Municipal para procesar.
- El usuario pidió procesar, transcribir, preparar borradores.
- NO aplica a oficios, publicaciones, hallazgos, prensa, redes sociales,
  ni actas de otras instituciones.

## Inputs

1. Una o más rutas a archivos de acta (PDF, `.md`, `.txt`), o una carpeta.
2. Config de la skill en `config/` (rutas de fuentes, enrutamiento, inbox).
3. (Opcional) Una etiqueta de lote para el inbox.

## Outputs

1. Un archivo de borrador por acta en la ruta definida en `config/inbox.yaml`.
2. Cada borrador cumple el [formato intermedio](../_formato-intermedio.md).
3. Reporte de corrida.

Los nuevos borradores usan `version_formato: 2` y el frontmatter definido en
`../_formato-intermedio.md`. Las actas históricas sin frontmatter son formato
legado y no se migran durante el procesamiento ordinario.

## Config

Antes de ejecutarse, leer:

- `config/fuentes.yaml` — dónde están los PDFs, extractos `.md`, `.txt`.
- `config/enrutamiento.yaml` — tabla de enrutamiento Acta → Hilo,
  **específica del cantón**.
- `config/inbox.yaml` — dónde escribir el borrador.

Si la config no existe o está incompleta, detenerse y pedir al humano.

## Procedimiento

### Paso 1. Identificar el documento

Para cada acta:
1. Número de acta, tipo de sesión (Ordinaria / Extraordinaria / Solemne).
2. Fecha completa en formato `YYYY-MM-DD`.
3. Hora de inicio y cierre si constan.
4. Lugar.
5. Presidente y quórum.
6. Si es Borrador, marcar `fuente_estado: borrador`.

### Paso 2. Preparar el input

| Caso | Acción |
|---|---|
| Solo PDF | Convertir con `pdftotext -layout` y trabajar sobre el texto resultante. |
| PDF + `.md` existente | Preferir el `.md` por legibilidad, contrastar con PDF. |
| Solo `.md` sin PDF (huérfano) | Aceptar, marcar en el reporte "sin PDF de respaldo". |
| Borrador | Tratar igual que un acta firme. |

### Paso 3. Listar ARTÍCULOS e ítems

1. Listar todos los `ARTÍCULO` (o `ARTÍCULOS`/`ART`) del cuerpo.
2. Dentro de cada uno, listar los ítems numerados.
3. Un ARTÍCULO sin ítems numerados pero con cuerpo discursivo se trata
   como un solo ítem.

### Paso 4. Filtrar ruido procedimental

Descartar del Hilo (pero conservar en `## Ítems descartados por ruido
procedimental`):

- Lectura y aprobación del acta anterior (salvo rechazo u observación material).
- Minuto de silencio.
- Recesos y jornadas (salvo que el receso se discuta y documente).
- Mociones de orden puramente formales.
- "Se da por recibido" sin consecuencia.
- Saludo y cierre protocolar.

### Paso 5. Para cada ítem no descartado

#### 5.1 Clasificar con la tabla de enrutamiento

Usar `config/enrutamiento.yaml`. La tabla tiene tres componentes:

- **Tabla principal**: cada fila asocia un Hilo con señales de enrutamiento.
- **Anti-enrutamientos**: excepciones específicas.
- **Regla de oro**: si un ítem coincide con varias filas, gana la más específica.

Si después de aplicar la tabla el ítem no encaja en ningún Hilo existente,
ir a 5.4.

#### 5.2 Construir el episodio

Para cada ítem enrutado, redactar según la plantilla narrativa:

- **Título**: `#### YYYY-MM-DD — <Sujeto> <verbo> <objeto>`.
- **Cuerpo**: 2–5 párrafos, orden: contexto, qué ocurrió, quién intervino,
  qué preocupación apareció, qué dato se aportó, qué acuerdo se tomó.
- **Cita canónica**: `> Fuente: Acta N° X, DD de mes del YYYY, ...`.
- **Datos estructurados**: agregar `episodio_id`, `tipo: evidencia` y los
  localizadores `archivo`, `articulo`, `item` y `pagina` en el frontmatter.

#### 5.3 Anuncios sin acuerdo formal

Si la fuente registra un anuncio con datos verificables pero no hay acuerdo,
va a la sección `## Tablero de anuncios`. El humano decide si lo levanta a Hilo.

#### 5.4 Si el ítem no encaja en ningún Hilo

NO crear archivo nuevo. Registrar en `## Propuestas de Hilo nuevo`.

### Paso 6. Resolver episodios multi-Hilo

- El episodio principal va al Hilo donde el Concejo votó el acuerdo.
- Desde ese Hilo, se enlazan los Hilos secundarios con cross-ref.
- En el borrador, documentar la decisión en una nota para el revisor.

### Paso 7. Resolver colisiones de fecha

- Si en el Hilo destino ya existe un episodio con la misma fecha,
  este ítem se incorpora como sub-bloque en **negrita**.

### Paso 8. Verificación final

- [x] Cada episodio lleva cita canónica.
- [x] No duplica Hilos.
- [x] No contiene datos personales innecesarios.
- [x] No editorializa.
- [x] No convierte acuerdos del Concejo en tareas.
- [x] Solo se escribe Evidencia o Inferencia explícita.

### Paso 9. Escribir el borrador

Estructura del archivo:
- Frontmatter YAML con metadatos.
- Cuerpo Markdown con todas las secciones.

### Paso 10. Reporte

Producir reporte de corrida con resultados.

## Modo Bootstrap

Cuando se ejecuta en contexto de bootstrap (generación inicial de taxonomía),
se aplican estas variantes al procedimiento estándar:

1. **Enrutamiento mínimo**: si no existe `config/enrutamiento.yaml`, usar
   la taxonomía semilla embebida en `scripts/bootstrap_hilos.py` (24 hilos
   universales) como tabla de enrutamiento de respaldo.

2. **Propuestas forzadas**: en lugar de registrar en `## Propuestas de Hilo
   nuevo`, el episodio sin clasificar se marca con `**Hilo:** _Sin clasificar_`
   y se incluye en el cuerpo del borrador con metadatos de entidades extraídas:
   ```
   **Entidades detectadas:** institución=_sigla_, lugar=_nombre_, ...
   ```

3. **Salida dual**: además del borrador normal, escribir un archivo
   `_episodios_raw.json` con todos los episodios (clasificados y no) para
   que `bootstrap_hilos.py` los consuma.

4. **No bloquear por falta de config**: si `config/enrutamiento.yaml` no
   existe, continuar con la semilla interna y marcar en el reporte
   `"bootstrap: enrutamiento semilla"`.

## Reglas duras

- **Una sola edición por episodio.**
- **No crear archivos nuevos** en `2 Base Cantonal/Hilos/` durante la corrida.
- **No duplicar episodios entre Hilos.**
- **No escribir** en `5 Archivo/`, `4 Salidas/`, ni `1 Operaciones/` (excepto flag).
- **No convertir acuerdos del Concejo en tareas.**
- **No inventar** intervenciones, cifras o citas.
- **No editorializar.**
