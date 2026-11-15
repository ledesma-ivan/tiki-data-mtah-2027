---
artifact: adr
version: "1.0"
created: 2026-11-02
status: rejected
---

# ADR-024: Descontar el costo de cambio donde la evidencia de radio pasa de un equipo al otro

## Status

Rejected (2026-11-02), por la regla que fijó el ADR-021 antes de correr. Ninguna de las 6 variantes pasó la selección. La mejor, `w12-d5`, dio +0.0008 [−0.0004, +0.0024] en Metrica y −0.0001 [−0.0007, +0.0007] en IDSSE: el decodificador casi no cambia las posesiones predichas (320.6 → 321.2 de 351.5 en Metrica).

Se escribió como `Proposed` antes de la primera medición, con el número local ADR-023: en `main` es el ADR-024, porque el 022 lo tomó el PR #93. Registro previo: `sha256` `b7a3139f7fa5ec37…` a las 14:03:02 UTC del 02/11. El código, los tests y los resultados (`explore/ADR-023_*`) quedan sin mergear en la rama `exp/adr-021-costo-de-cambio` (`0f007a7`).

**Date:** 2026-11-02
**Deciders:** Matias Enrique (con Codex, gpt-6.1-sol)

## Context

El costo fijo del ADR-014 fusiona algunas posesiones cortas con sus vecinas. Bajarlo en todos los frames
también agrega cambios falsos. La hipótesis es que un descuento acotado donde la evidencia de radio
favorece a equipos opuestos antes y después recupera posesiones sin bajar el costo en todo el partido.

## Decision

Se cambia solo el decodificador. R se reentrena en cada pliegue con 63 hojas, `lam=10`,
`short_weight=1`, `short_s=5`. La candidata usa exactamente los mismos árboles y puntajes que R,
las mismas filas de entrenamiento, pelota degradada, jugadores, períodos y `dead_mask_v2` con paradas
identidad. No se usa `live_model.json` como referencia ni se entrena un detector adicional.

Para una frontera antes del frame `t`, se cuentan las evidencias H/A en `[t-w,t)` y `[t,t+w)`.
Son las señales existentes `ev_past_w` y `ev_next_w` de `LIVE_FEATURES`. Se recortan además al tramo
vivo actual, sin cruzar paradas ni períodos. Cada lado necesita al menos `ceil(w/4)` evidencias.
Un equipo domina si tiene al menos el 75% de las evidencias de ese lado, comparado con enteros.
La compuerta vale uno cuando dominan equipos opuestos, y cero en cualquier otro caso. Sin evidencia,
incluida la pelota desconocida sin evidencia alrededor, no hay descuento. No se interpreta `UNKNOWN`
como una observación. La compuerta es idéntica al permutar H/A.

El costo es `cost_t = max(0, 20000000 - discount * gate_t)`, en millonésimas de logit.
La programación dinámica maximiza exactamente la misma suma del ADR-014 con ese costo por frontera.
Usa enteros de Python, conserva el cambio más temprano en empates y termina en H si empatan los estados.
Este último desempate ya existe en R y es la única excepción a permutar etiquetas en un empate exacto.

La familia queda cerrada en estas seis variantes. No se amplía después de ver resultados:

| Variante | `w`, frames | Mínimo de evidencias por lado | `discount` | Costo con compuerta |
|---|---:|---:|---:|---:|
| w12-d5 | 12 | 3 | 5000000 | 15000000 |
| w12-d10 | 12 | 3 | 10000000 | 10000000 |
| w12-d15 | 12 | 3 | 15000000 | 5000000 |
| w50-d5 | 50 | 13 | 5000000 | 15000000 |
| w50-d10 | 50 | 13 | 10000000 | 10000000 |
| w50-d15 | 50 | 13 | 15000000 | 5000000 |

El camino nuevo es optativo mediante `change_cost` en el modelo. Sin esa clave, `possession.label`
y los archivos de modelos entregados quedan iguales. El código no exporta ni reemplaza esos archivos.

## Cómo se mide

Solo selección, LOMO en Metrica 2-3 e IDSSE 1-5. Las dos mitades IDSSE quedan afuera juntas.
Semillas 0-9 en Metrica y 0-4 en IDSSE, escenario por defecto y jugadores limpios. La verdad Metrica
se ancla al inicio del evento. Cada pliegue entrena R en los otros seis partidos. Las seis variantes
comparten ese ajuste. No hay parámetros aprendidos adicionales.

Se usa el scorer oficial `f8f2629` vía `bench.compare`, con 1000 remuestreos pareados de posesiones y
semillas. Se informa cada media e intervalo 5-95% por banco, las diferencias de las 12 unidades y sus
signos. Gana la mayor media de las dos medias de banco. Se reportan sin decidir el acierto de los frames
verdaderamente vivos, incluso los predichos D, las posesiones predichas/verdaderas y el recall promedio
de los umbrales IoU oficiales por duración verdadera, en 0-2, 2-5, 5-15 y más de 15 s.

Se prueba con datos sintéticos la simetría, los empates, la pelota faltante, `UNKNOWN`, los períodos,
la exactitud contra enumeración de caminos, el determinismo, la exclusión del partido retenido y la
identidad del camino vigente. Se mide inferencia sintética de 199319 frames y 46 slots. Las corridas
pesadas usan `flock /tmp/mtah-heavy.lock` y registran su tiempo de pared.

Se implementa una confirmación, pero este agente no la ejecuta. Si esta alternativa gana según ADR-021,
la persona o agente padre corre una sola vez la mejor variante, con R entrenada en los siete partidos
de selección, reserva y semillas desde 80. Reusa las 43 condiciones y la decisión del ADR-019,
compara árboles exportados con `decision_function`, y exige una ruta `--report` distinta de
`live_confirmation.json`. No tiene modo `--final`. Si el equipo cambia la referencia, el padre deberá
declararlo antes de confirmar como prevé ADR-021.

## Consequences

### Positive

- La compuerta usa señales existentes y no depende de cuál equipo es local.
- No agrega un ajuste por pliegue ni una decisión basada en la reserva.
- La inferencia del decodificador es lineal en los frames y usa costos enteros.

### Negative

- Los cambios sin evidencia de radio a ambos lados no reciben descuento.
- Una disputa con evidencias breves de equipos distintos puede agregar cambios falsos.
- La mejor de seis variantes tiene optimismo de selección. Solo la confirmación del ADR-021 permite adoptarla.

## Alternatives Considered

- Un segundo modelo de cambios. Agrega entrenamiento y otra exportación; esta familia prueba primero si
  la evidencia existente alcanza.
- Un modelo explícito de duración. Requiere elegir la forma de su distribución y cómo tratar posesiones
  cortadas por paradas. Queda fuera de esta familia para mantener una prueba acotada.
- Bajar `lam` en todos los frames. Ya perdió frente a `lam=10` en la selección del ADR-014.

## References

- ADR-005, ADR-006, ADR-011, ADR-014, ADR-019 y ADR-021.
- `possession.py`, `calibrate_live.py`, `calibrate_edges.py` y `bench.py`.
- Metrica sample-data y Bassek y otros, IDSSE, revisión `a715a38`, CC BY 4.0.
