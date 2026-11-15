---
artifact: adr
version: "1.0"
created: 2026-10-29
status: accepted
---

# ADR-008: No se abstiene (`X`) dentro de los tiempos jugados

## Status

Accepted (2026-10-29), revisado por Lautaro en el PR #44. Cierra el issue #10.

**Date:** 2026-10-29
**Deciders:** Ivan Ledesma (propone). Cierra el issue #10.

## Context

Hoy `possession.py` solo devuelve `X` fuera de los tiempos jugados, donde no cuesta nada
(`CHALLENGE.md`). Dentro de los tiempos nunca devuelve `X`. El issue #10 pregunta si conviene abstenerse
cuando la evidencia es mala.

`EVALUATION.md` dice que el scorer trata la `X` de dos maneras:

- `macroF1` (desempate) la cuenta como un error en todo frame puntuado.
- `spellF1` (el ranking) la rellena hacia adelante con la última etiqueta que no es `X` de ese tiempo,
  antes de emparejar posesiones. Una `X` equivale a "repito mi respuesta anterior".

La regla de cambio (`confirm_changes`, ADR-001) ya sostiene la etiqueta anterior cuando falta evidencia. Si
es así, una `X` en esos frames dejaría el `spellF1` igual y solo empeoraría el `macroF1`. La primera versión
de este ADR lo midió con el detector v1 y dio eso; la revisión de Lautaro mostró que con el v2 (#41) no
es así, y por eso se midió de nuevo con los tres pipelines.

## Decision

Dentro de los tiempos jugados no se devuelve `X`: cada frame es `H`, `A` o `D`. Fuera de los tiempos
puntuados se sigue devolviendo `X`. No cambia `possession.py`.

## Cómo se mide

- **Métrica:** `spellF1` (ranking) y `macroF1` (desempate), con `possession_metrics.evaluate`, la misma
  que usa el banco del ADR-006.
- **Datos:** Metrica Sample Games 1, 2 y 3 (abiertos), pelota degradada del banco (45% faltante, huecos
  de 1.5 s), 5 semillas por partido, verdad desde el inicio del evento.
- **Políticas** (`explore/abstention_x.py --pipeline ...`), todas sobre las mismas etiquetas de cada pipeline.
  `none` es no abstenerse; `gap` es `X` donde la pelota falta 2 s o más; `edges` es `X` en el último segundo
  de cada tramo vivo.

| Pipeline | Política | `spellF1` | `macroF1` |
|---|---|---|---|
| v1 (ADR-002) | `none` | 0.242 | 0.582 |
| | `gap` | 0.242 | 0.572 |
| | `edges` | 0.243 | 0.561 |
| v2 (ADR-007, en `main`) | `none` | 0.407 | 0.798 |
| | `gap` | **0.433** | 0.721 |
| | `edges` | 0.407 | 0.796 |
| radio de control + v2 (ADR-009, en `main`) | `none` | 0.539 | 0.849 |
| | `gap` | 0.536 | 0.751 |
| | `edges` | 0.541 | 0.847 |

Las filas de v2 las midió Lautaro en la revisión del PR #44 y se reprodujeron con el mismo script. Con
bootstrap pareado (sus números, 1000 remuestreos), `gap` contra `none` en el v2: +0.026 [+0.017, +0.036] en
Metrica (3 de 3 partidos) y +0.005 [−0.000, +0.010] en IDSSE (10 de 14 mitades), con −0.08 de `macroF1` en los dos.

**Por qué cambia con el pipeline.** El v1 marcaba `D` donde la pelota faltaba mucho; el v2 ya no, y ahí la
evidencia usa la última posición de la pelota y genera cambios de equipo falsos, que la `X` tapa. El radio de
control y la interpolación acotada (ADR-009) atacan esa causa: sin nadie a 1 m no hay evidencia, y la `X` ya
no suma.

## Consequences

### Positive

- Se evita perder entre 0.00 y 0.10 de `macroF1`, que desempata. Con el pipeline del ADR-009 la `X` no
  aporta nada al ranking.
- No cambia el CSV de entrega ni el hash.

### Negative

- Con el v2 solo (sin el ADR-009), la `X` en los huecos largos sumaría +0.026 de `spellF1` en Metrica y casi
  nada en IDSSE. Si el ADR-009 se reemplaza, hay que volver a decidir.
- Las filas de IDSSE vienen de la revisión de Lautaro y no se reprodujeron aquí.

### Neutral

- La `X` en un cambio de posesión sí es peligrosa: el scorer arrastraría la etiqueta anterior a través
  del cambio (`EVALUATION.md`). Por eso la política tampoco abstiene en los bordes.

## Alternatives Considered

### Abstenerse con la pelota ausente (`gap`)

Con el v2 suma +0.026 de `spellF1` en Metrica y cuesta 0.08 de `macroF1`; con el pipeline del ADR-009 no suma
(−0.003). Se descarta porque el ADR-009 ataca la causa.

### Abstenerse al final de cada tramo vivo (`edges`)

Sin efecto en el `spellF1` en ninguno de los tres pipelines, y baja el `macroF1`.

### Sostener la posesión en los huecos largos (sin evidencia, sin `X`)

La probó Lautaro: en Metrica suma +0.021 [+0.007, +0.035] pero en IDSSE resta −0.011 [−0.019, −0.003]. No se
generaliza.

### Un score de confianza por frame

Más fiel a "declinar cuando no se sabe", pero requeriría un score calibrado que hoy no existe. Se
retoma si el decodificador del #35 produce probabilidades.

## Qué sigue

Revisar esta decisión si el ADR-009 se reemplaza o si el detector de pelota muerta cambia.
