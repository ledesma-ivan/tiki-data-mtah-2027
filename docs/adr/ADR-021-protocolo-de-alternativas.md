---
artifact: adr
version: "1.0"
created: 2026-11-02
status: proposed
---

# ADR-021: Cuatro alternativas para mejorar la entrega se eligen en la selección con un protocolo fijado antes de correr, y solo la ganadora va a la reserva

## Status

Proposed (2026-11-02). Se subió **antes** de cualquier corrida de las alternativas, en `80b0850` (está en las ramas `exp/adr-021-*`). Pasa a `Accepted` con la revisión de otra persona en el PR.

**Resultado:** ninguna alternativa confirmó y la entrega no cambia (ver "Resultados").

**Date:** 2026-11-02
**Deciders:** Matias Enrique (con Claude). Cada alternativa la implementa un agente (Codex, gpt-6.1-sol) en su propia
rama, solo con datos abiertos (`AGENTS.md`).
**Issues:** #86 (señales de toque). Usa el protocolo del ADR-019 (#83, #84, PR #89).

## Context

- **Dónde se pierde hoy** (datos abiertos, fila del 31/10 en `docs/EXPERIMENTOS.md`, `explore/diagnose_changes.py`):
  las posesiones que la receta del ADR-014 no acierta son casi todas cortas (cerca del 87% duran menos de 5 s en
  Metrica). Las causas: equipo equivocado (43% en Metrica y 41% en IDSSE), fusionada con otra (37% y 36%), predicha
  muerta (11% y 13%), bordes (7% y 6%) y partida (2% y 4%). La receta predice 10-15% menos cambios que los reales.
- **Los techos** (oráculos encima del modelo de juego vivo, fila del 30/10): el `D` perfecto suma +0.100 en Metrica y
  +0.075 en IDSSE, y los bordes de las paradas son cerca del 70% de eso. La pelota completa, unos +0.08
  (`docs/TECHNICAL.md`). Un techo no es una ganancia esperada.
- **La reserva está gastada:** el ADR-019 fue su octava mirada. Probar varias alternativas en la reserva y quedarse con
  la mejor sería elegir con la reserva.
- **La referencia:** el ADR-019 midió que el peso 3 del #77 no confirma contra el peso 1 (41 de 43) y fijó antes de
  correr que, en ese caso, la propuesta es volver al peso 1.
- **El plazo:** el pipeline se congela el 14/11 (`docs/ENTREGA.md`).

## Decision

### La referencia

La receta del ADR-014 con `short_weight` = 1 (`leaves` 63, `lam` 10, `short_s` 5), con el `D` de `dead_mask_v2` y
`stops_model.json` identidad: lo que propone el ADR-019 si el peso 3 no confirma. Si el equipo decide mantener el
peso 3, la selección no se repite, y la confirmación usa como referencia la receta que quede vigente y como candidata
esa receta más el cambio.

### Las cuatro alternativas

Cada una va en su rama, con su propio ADR escrito antes de su primera corrida. En las ramas se numeraron del 022 al 025; en `main` son del 023 al 026, porque el 022 lo tomó el PR #93:

| ADR | Alternativa | Qué error ataca | Qué cambia |
|---|---|---|---|
| 023 | Señales de toque (#86) | equipo equivocado y fusión en posesiones cortas | señales nuevas del modelo de juego vivo; el decodificador y las paradas no cambian |
| 024 | Costo de cambio según el contexto o la duración | posesiones cortas fusionadas | el decodificador; los árboles de juego vivo no cambian |
| 025 | Paradas con un modelo entrenado | bordes de las paradas, paradas que faltan o sobran | el detector de `D`; el modelo de juego vivo se reentrena con la misma receta sobre las paradas nuevas |
| 026 | Pelota estimada en los huecos | la pelota que falta | la posición de la pelota en los huecos; el modelo de juego vivo se reentrena con la misma receta |

El Smart Tagging (#8) queda afuera: ningún dato abierto lo trae, así que no se puede elegir ni confirmar con este
protocolo.

### La selección, en cada alternativa

- **Solo los partidos de selección:** Metrica Games 2-3 (semillas 0-9) e IDSSE 1-5 (semillas 0-4). La reserva
  (Metrica Game 1, IDSSE 6-7) no se usa para nada: ni para entrenar, ni para evaluar, ni para diagnosticar.
- **Fuera de muestra (LOMO):** cada partido de selección (en IDSSE, sus dos mitades juntas) se predice con modelos
  entrenados sin él, como en el ADR-014. La candidata y la referencia se entrenan con las mismas filas, salvo que el
  cambio las mueva, y se puntúan con las mismas pelotas, jugadores y máscaras.
- **Escenario:** la pelota degradada por defecto del banco (45%, huecos de 1.5 s) y jugadores limpios. La verdad es la
  del inicio del evento en Metrica (ADR-005) y la del proveedor en IDSSE.
- **Variantes:** cada ADR declara antes de correr una familia de a lo sumo 6 variantes. Se elige la variante con la
  mayor diferencia pareada media contra la referencia, promediando por igual los dos bancos (ADR-011), y se reportan
  todas.
- **Medida:** `spellF1` con el scorer oficial (`f8f2629`). Es la diferencia pareada candidata − referencia con 1000
  remuestreos de posesiones y semillas (`bench.compare`), por banco y con su intervalo 5-95%, más cuántos de los 12
  partidos y mitades (2 de Metrica, 10 de IDSSE) dan positivo.
- **Quedan descalificadas** las variantes en que una etiqueta dependa de aritmética no reproducible (fuera de enteros o
  de operaciones IEEE exactas), en que el modelo dependa de cuál equipo es local, o con una inferencia de más de
  10 minutos en un partido del tamaño de BAR-ATH.

### La ganadora

Entre las alternativas cuya variante elegida tiene el intervalo 5-95% entero por encima de 0 **en los dos bancos**,
gana la de mayor diferencia media (el promedio de los dos bancos). Si ninguna lo cumple, no se corre ninguna
confirmación y la entrega no cambia.

### La confirmación: una sola vez, solo la ganadora

- La variante ganadora, sin cambios después de ver la selección, contra la referencia. Las dos se entrenan con los 7
  partidos de selección y se evalúan sobre la reserva: Metrica Game 1 con las semillas 80-89 e IDSSE 6-7 con las
  80-84. Es la novena mirada a la reserva.
- Decide la regla del ADR-019: las 43 condiciones contra la referencia y, si hay árboles nuevos, los exportados iguales
  a `decision_function`. Confirma solo si se cumplen todas.
- Si no confirma, ninguna otra alternativa va a la reserva en esta ronda, y la entrega no cambia.

### La adopción

Si confirma, se corre `--final` con los 10 partidos y se abre un PR con este ADR, el de la alternativa y sus filas de
`docs/EXPERIMENTOS.md`. Una persona corre BAR-ATH en dos máquinas y pega los conteos, el `sha256` y el validador antes
de que sea la entrega (`AGENTS.md`). Todo antes del congelamiento del 14/11.

## Cómo se mide

`spellF1` con el scorer oficial, en diferencia pareada contra la referencia con 1000 remuestreos. Selección: Metrica
2-3 e IDSSE 1-5, fuera de muestra. Confirmación: Metrica 1 e IDSSE 6-7, semillas 80 en adelante. Solo datos abiertos.

## Resultados (02/11)

### Selección

Fuera de muestra, contra R (peso 1), en diferencia pareada con 1000 remuestreos, intervalo 5-95%. La unidad es cada
partido de Metrica y cada mitad de IDSSE (12 en total).

| ADR | Alternativa | Variantes | Elegida | Metrica | IDSSE | Unidades positivas | ¿Pasa? |
|---|---|---|---|---|---|---|---|
| 023 | Señales de toque | 4 | `context` | +0.0133 [+0.0063, +0.0207] | +0.0155 [+0.0101, +0.0206] | 12 de 12 | sí |
| 024 | Costo de cambio según el contexto | 6 | `w12-d5` | +0.0008 [−0.0004, +0.0024] | −0.0001 [−0.0007, +0.0007] | 6 de 12 | no |
| 025 | Paradas entrenadas | 3 | `d40` | −0.0337 [−0.0480, −0.0185] | −0.0191 [−0.0278, −0.0103] | 3 de 12 | no |
| 026 | Pelota estimada en los huecos | 4 | `all6_features` | −0.0012 [−0.0074, +0.0053] | +0.0038 [−0.0015, +0.0088] | 7 de 12 | no |

Todas las variantes de cada alternativa, con sus semillas y tiempos, están en su ADR y en `explore/ADR-0NN_selection.json`
de su rama.

### Confirmación: no confirma (41 de 43)

La única que pasó, el ADR-023 con `context`, se confirmó una vez contra R en la reserva: Metrica Game 1 con las
semillas 80-89 e IDSSE 6-7 con las 80-84. Fue la novena mirada a la reserva. Fallaron dos condiciones:

- el escenario por defecto en IDSSE: +0.0047 [−0.0037, +0.0130], con 3 de 4 mitades a favor;
- los cambios de identidad entre equipos cerca de la pelota, en el 5% de los frames, en IDSSE: −0.0001
  [−0.0084, +0.0082].

En Metrica, el escenario por defecto dio +0.0143 [+0.0035, +0.0253] desde el inicio y +0.0145 [+0.0032, +0.0260]
desde el fin. Las otras 41 condiciones se cumplieron, y los árboles exportados dieron 0 frames distintos de
`decision_function`. El informe es `explore/ADR-022_confirmation.json`, en `exp/adr-021-toques` (`088593d`).

**Según este ADR, la entrega no cambia y ninguna otra alternativa va a la reserva en esta ronda.** Las semillas 80 ya
están usadas en la reserva: la próxima confirmación ahí tendría que arrancar en 90.

### Lo que deja la ronda

- **Lo que persigue posesiones cortas depende de la convención.** Las señales de toque ganan en Metrica, que decide
  con la verdad A, y no se distinguen del ruido en la reserva de IDSSE. Va en la misma dirección que el peso 3 con la
  verdad B (#92). Sigue en el #94.
- **Las candidatas caen con jugadores mal seguidos**: el peso 3 con 1.0 m de ruido (ADR-019) y los toques con cambios
  de identidad. Sigue en el #95.
- **El decodificador no es el cuello de botella** con jugadores limpios y la verdad A (ADR-024). **Estimar la pelota
  desde los jugadores no suma** (ADR-026).
- **Las paradas siguen siendo el techo más alto**, pero el detector entrenado depende de cómo se simula la pelota de
  las paradas (ADR-025). Sigue en el #96.
- **La reserva está gastada:** nueve miradas. Sigue en el #97.

## Consequences

### Positive

- Se elige entre cuatro alternativas sin mirar la reserva, y la reserva se mira una sola vez.
- Cada alternativa queda registrada, aunque pierda.

### Negative

- **La ganancia de la ganadora en la selección es optimista:** es la mejor de varias variantes y alternativas sobre
  los mismos partidos. La confirmación lo corrige, pero no hace partidos nuevos.
- Los partidos de selección son los mismos de las decisiones anteriores.
- Si el equipo mantiene el peso 3, la confirmación cambia de referencia.

## Alternatives Considered

- **Confirmar las cuatro en la reserva y quedarse con la mejor:** elige con la reserva. Descartada.
- **Un dataset abierto nuevo como segunda reserva** (SkillCorner, ADR-014): tiene otro formato y 10 fps, y no llega
  al 14/11.
- **Una alternativa por vez:** no llega al 14/11.

## References

- ADR-005, ADR-006, ADR-011, ADR-014 y ADR-019 (PR #89)
- `docs/EXPERIMENTOS.md`: filas del 30/10 (`explore/oracles_live.py`) y del 31/10 (`explore/diagnose_changes.py`)
- Issues #8, #85 y #86; los que abre la ronda: #94, #95, #96 y #97
- Ramas de la ronda, sin mergear: `exp/adr-021-toques`, `exp/adr-021-costo-de-cambio`, `exp/adr-021-paradas` y `exp/adr-021-pelota`
