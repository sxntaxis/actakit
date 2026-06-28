---
name: procesar-prensa
description: >
  Convierte notas de prensa, artículos y comunicados en borradores
  estructurados para integración en Hilos.
---

# procesar-prensa

Análoga a `procesar-acta` pero para fuentes de prensa escrita o digital.
Sigue el mismo [formato intermedio](../_formato-intermedio.md) y los mismos
[principios](../_principios-compartidos.md).

## Diferencias con procesar-acta

- La fuente no es un PDF de acta sino un artículo, nota o comunicado.
- El enrutamiento prioriza el tema del artículo sobre la institución que lo emite.
- Los datos atribuibles a periodistas o medios se marcan como `percepción` por defecto.
- No hay sección de ruido procedimental; entra directamente a Episodios.

## Inputs

1. Texto del artículo o enlace.
2. Medio, fecha, autor si corresponde.
3. `_config/` con enrutamiento específico de prensa.

## Outputs

1. Borrador en formato intermedio.
2. Reporte de corrida.
