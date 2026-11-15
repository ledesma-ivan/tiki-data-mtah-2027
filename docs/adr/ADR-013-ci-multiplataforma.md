---
artifact: adr
version: "1.0"
created: 2026-10-30
status: superseded
---

# ADR-013: La CI corre los tests sintéticos y compara el CSV de un partido sintético en tres sistemas

## Status

Superseded by ADR-016. El protocolo vigente para cerrar el issue #54 es el
[ADR-016](ADR-016-validacion-completa-ci.md). Se conserva la propuesta original
como registro histórico:

Proposed (2026-10-30). Pasa a `Accepted` con la revisión de otra persona en el PR (`AGENTS.md`). Cierra el
issue #54. Se numera 013 porque el 010 es el de las paradas (#57), el 011 el del #55 y el 012 queda para el
ADR de la geometría del #58.

**Date:** 2026-10-30
**Deciders:** Ivan Ledesma (propone).

## Context

`SUBMISSION.md` y la respuesta del issue 11 del repo oficial piden que el CSV salga igual byte a byte en
cualquier máquina. El #6 lo resolvió en el código (distancias al cuadrado, conteos enteros, saltos de línea
LF) y lo comprobamos a mano: el `sha256` de BAR-ATH coincidió en dos máquinas, y después en cada PR que tocó
`possession.py` (#45, #57, #58).

Esa comprobación depende de que alguien se acuerde de hacerla, y solo cubre las máquinas del equipo. La única CI (`guard.yml`) corre `guard.py repo` en Ubuntu: no corre los tests, y
ninguno compara bytes entre sistemas. Un cambio que use una operación que depende de la plataforma (una media
en coma flotante que pasa por BLAS, un `hypot`, un `exp`) puede romper la reproducción sin que nadie lo vea
hasta la entrega.

## Decision

Un workflow nuevo, `.github/workflows/tests.yml`, en cada push y PR:

1. **Matriz:** Ubuntu, macOS y Windows, con Python 3.12 y 3.13 (los que admite `requirements.txt`): seis
   trabajos. Se instalan las versiones fijadas de `requirements-train.txt`, que incluye `requirements.txt`,
   para que `test_calibrate_edges.py` también corra.
2. **Scorer oficial:** solo `evaluation/possession_metrics.py` de `metrica-sports/more-than-a-hack-2027`, en
   una revisión fija (`f8f2629`), en `../mtah2027` como lo espera `bench.py`.
3. **Tests:** cada `test_*.py` con `python`, uno por uno. Algunos son `unittest` y otros scripts con `assert`;
   así corren todos con su comando real, y cualquier fallo corta el trabajo.
4. **CSV sintético:** `repro_check.py` arma un partido falso del largo de BAR-ATH (46 slots, 11 por equipo
   con datos), corre `possession.label` entero (evidencia, detector de pelota muerta, modelo de paradas, regla
   de cambio) y escribe el CSV con `possession.write_csv`. Imprime los conteos y el `sha256`.
5. **Comparación:** un trabajo final junta los seis `sha256` y falla si no son todos iguales.

El partido sintético no depende de la plataforma: enteros de PCG64, aritmética entera en centímetros y una
sola división, correctamente redondeada, para normalizar. Si los `sha256` difieren, la diferencia viene del
pipeline. Trae paradas (jugadores lentos, pelota quieta, a veces fuera de la cancha), cambios de dueño entre
equipos y huecos de pelota en un tercio de los frames, para que todas las etiquetas aparezcan.

`guard.yml` sigue igual. Nada de esto usa datos del partido ni datos abiertos.

## Cómo se mide

- **Que el chequeo ve lo que tiene que ver:** en mi máquina (Windows, numpy 2.5.1, Python 3.12) el CSV sintético
  con el pipeline de `main` después del ADR-014 (modelo de posesión) da `sha256`
  `94d98e14483b70d9d8b1328674953f6f2d53f6390860a7fbb304e63d34229de8`, y H 59304, A 59467, D 40086, X 40462.
  Con el costo de cambio del modelo (`switch`) un 10% menor da otro `sha256` (`36bb4060…`, 2 frames distintos):
  un cambio de una etiqueta se detecta. Antes del ADR-014 el `sha256` era `d184d8ad…`; la regla de cambio ya no
  decide en la entrega, así que `CHANGE_FRAMES` no sirve para esta prueba.
- **Que los tests corren sin datos:** los trece `test_*.py` pasan en una copia limpia del repo, sin `data/`, con
  solo `possession_metrics.py` del repo oficial al lado.
- **En la CI:** los seis trabajos verdes y un solo `sha256` en el trabajo final.

## Consequences

### Positive

- La reproducción byte a byte se comprueba sola en cada PR, en los tres sistemas, sin que nadie corra nada.
- Los tests corren en cada PR, también en macOS y Linux.
- Corre en menos de un minuto: el CSV sintético tarda unos 35 s, casi todo en el modelo de posesión.

### Negative

- **Hoy no corre:** GitHub Actions no inicia los trabajos por el bloqueo de pagos de la organización (el
  check del #58 lo muestra). Hasta que se arregle, el workflow es la receta, y se puede correr a mano.
- **No es BAR-ATH:** un partido sintético no recorre todos los caminos del real. Un problema que solo
  aparezca con la geometría o los huecos del ATD real lo sigue cubriendo la comparación manual del
  `sha256` de BAR-ATH en los PR que tocan `possession.py`.
- **Seis trabajos por push** consumen minutos de la organización cuando vuelvan a estar disponibles.

### Neutral

- El `sha256` sintético no está fijado en el repo: la CI compara sistemas entre sí, no contra un valor
  guardado, así que un cambio de etiquetas a propósito no obliga a actualizar nada.

## Alternatives Considered

### Fijar el `sha256` sintético en el repo

Detectaría también un cambio de etiquetas involuntario en una sola máquina, pero obliga a actualizar el valor en
cada cambio del pipeline, y eso ya lo cubren los tests de `possession` y el banco. Se puede sumar después.

### Un fixture que imite el archivo `_atd.txt`

Probaría también `load_atd`, pero un partido entero en texto pesa cientos de MB. El parser es corto y no hace
aritmética; las etiquetas se deciden después.

### Solo Ubuntu

Más barato, pero la diferencia que buscamos aparece entre sistemas y versiones de BLAS.
