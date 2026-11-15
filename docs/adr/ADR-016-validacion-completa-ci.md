---
artifact: adr
version: "1.0"
created: 2026-10-30
status: proposed
---

# ADR-016: Validar la matriz completa y registrar el entorno sintético

## Estado

Proposed. Reemplaza el ADR-013 del PR #60 para completar el issue #54.
Requiere revisión de otra persona antes de pasar a Accepted.

## Contexto

El ADR-013 compara los hashes que encuentra. Si falta un artefacto, los restantes
pueden coincidir y aprobar la comprobación. Además, las versiones menores de
Python y las dependencias transitivas permiten que el entorno cambie entre corridas.
La implementación actual también debe cubrir los tests nuevos de geometría,
continuidad de velocidades y posesión con juego vivo.

## Decisión

`ci_config.json` fija los runners Ubuntu 24.04, macOS 15 y Windows 2022, con
CPython 3.12.10 y 3.13.15. Son seis combinaciones. La matriz y el comparador leen
esa misma configuración. `requirements-ci.txt` incluye las dependencias de
entrenamiento y fija también sus dependencias transitivas. Actualizarlas exige
un cambio revisable en el repo.

Se descarga únicamente `evaluation/possession_metrics.py` del repo oficial,
en la revisión `f8f2629ff1e0985f81d7e59d8413678514ee1530`. Antes de importarlo
se verifica el SHA-256 fijado en la configuración. El directorio temporal del
scorer se pasa por `MTAH_OFFICIAL`; no se clonan datos ni otras carpetas del reto.

Cada trabajo ejecuta todos los `test_*.py` de la raíz como scripts mediante el
mismo intérprete. Esto incluye los checks del bloque principal de
`test_possession.py`. Una dependencia ausente, una versión incorrecta o un script
que falla hace fallar el trabajo. No se permite ejecutar con asserts desactivados.

Se conserva el generador sintético del ADR-013 con semilla 54, PCG64 explícito y
enteros de 64 bits. `repro_check.py` llama a `possession.label` con los modelos
versionados y a `possession.write_csv`. Incluye evidencia, pelota muerta,
refinamiento de paradas y segmentación con el modelo de juego vivo. No carga
tracking de disco. Exige las cuatro etiquetas y la cantidad completa de frames.
El CSV temporal se borra al terminar.

Cada trabajo publica un único JSON con el hash del CSV, los conteos y los
metadatos necesarios para compararlo: fixture, sistema, Python, dependencias,
scorer y hashes del código y modelos. Los hashes de archivos fuente normalizan
CRLF a LF para admitir el checkout de Windows. El hash del CSV usa los bytes
reales escritos, sin normalización.

La consolidación exige exactamente los seis artefactos, con nombres y metadatos
coherentes con cada combinación. Rechaza archivos ausentes, adicionales, vacíos,
malformados, hashes inválidos, conteos incompletos y entornos distintos de los
fijados. Solo aprueba si coincide el hash del CSV y toda la información común.
No se fija un hash esperado del CSV; los cambios deliberados de etiquetas pueden
pasar si producen los mismos bytes en todos los sistemas.

`guard.yml` conserva su check `no-match-data`. El workflow de tests también corre
`guard.py repo` antes de lanzar la matriz y exige su éxito en la consolidación.
La protección de ramas debe exigir estos checks para impedir un merge fallido;
el YAML no puede configurar esa protección por sí solo.

## Cómo se mide

- Ejecutar la suite sintética completa con ambos Python en una copia que solo
  contenga código y modelos versionados.
- Probar el comparador con una matriz completa, con un hash distinto y con
  resultados faltantes, duplicados o inválidos. Los casos inválidos deben fallar.
- Probar que una variación de la entrada sintética cambia las etiquetas y el hash
  al recorrer el pipeline. Probar también que el runner propaga un fallo de script.
- En Actions, exigir seis trabajos de tests exitosos, `guard.py repo` exitoso
  y un único SHA-256 del CSV en la consolidación.

Los comandos locales se documentan en `docs/CI.md`. No hay ajuste de parámetros,
entrenamiento con datos externos ni evaluación sobre el partido del concurso.

## Límites

La igualdad para un fixture no demuestra determinismo para todas las entradas.
No cubre el parser de ATD ni prueba la reproducción del CSV del concurso; esa
validación manual sigue pendiente de quienes ejecutan el pipeline en sus máquinas.
Los tests sintéticos adicionales cubren la regla alternativa de cambio y los
modelos de paradas que no están activos en la entrega.

Las imágenes de los runners reciben actualizaciones aunque su versión de sistema
esté fijada. El protocolo identifica Python y dependencias, y compara los bytes
en cada corrida. Los jobs necesitan que la organización tenga Actions habilitado
y presupuesto disponible; una ejecución local no sustituye la matriz remota.
