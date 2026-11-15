---
artifact: adr
version: "1.0"
created: 2026-10-28
status: accepted
---

# ADR-006: Las versiones se comparan en un banco de datos abiertos con ruido de ATD simulado

## Status

Accepted (2026-10-29), revisado por Ivan en el PR #51. Depende del ADR-005 (verdad de posesión de
Game 3, PR #20), que extiende a los tres partidos.

**Date:** 2026-10-28
**Deciders:** Matias Enrique

## Context

Para elegir entre dos versiones del pipeline, o entre dos valores de un parámetro, hace falta medir el
`spellF1` de punta a punta en algún lado. Hoy no hay dónde:

- **La ventana pública no sirve para elegir.** Tiene 17 posesiones, el ruido del bootstrap ronda
  ±0.35 y `RULES.md` prohíbe usarla para elegir entre versiones. `EVALUATION.md` muestra que con un
  solo parámetro ya elige la versión equivocada.
- **Las calibraciones actuales miden piezas sueltas** con métricas por frame: F1 de `D` en
  `calibrate_dead.py` y un barrido de N en `calibrate_n.py` (PR #21), solo en Game 3.
- **El tracking de sample-data es limpio y BAR-ATH no.** En Game 3 la pelota falta en el 99.8% de
  los frames muertos y en el 2.0% de los vivos: el tracking corregido la borra durante las paradas.
  "Pelota sin datos" como único detector da F1 por frame de 0.976. En BAR-ATH la pelota falta en el
  41% de los frames evaluados, por oclusiones (`DATA.md`). Calibrar sobre sample-data tal cual
  premia ese atajo, que en el partido no existe. Lo encontró el análisis del 28/10 y lo confirmó una
  revisión independiente (`explore/oracles_2810.py`, issue #30).

## Decision

Toda decisión que cambie el CSV de entrega se toma con `bench.py`: el pipeline completo sobre los tres
partidos de Metrica sample-data, con la pelota degradada al estilo ATD, puntuado con el scorer oficial.

### Qué corre

- **Partidos:** Sample Games 1, 2 y 3 (`data/Sample_Game_*`): unos 95 minutos y entre 320 y 406
  posesiones cada uno.
- **Verdad de campo:**
  - posesión: equipo del último evento con pelota (ADR-005, opción A), contado desde el **inicio**
    del evento;
  - variante de sensibilidad: contado desde el **final** del evento;
  - una reanudación (ADR-003: `SET PIECE` o subtipo `GOAL KICK`, aunque venga como `BALL LOST`)
    le da la pelota a su equipo desde su inicio, con las dos variantes;
  - pelota muerta: etiquetas del ADR-003.
- **Pelota degradada** (`bench.degrade`):
  1. en los frames muertos sin pelota, la pelota vuelve, interpolada entre las observaciones más
     cercanas. Las observaciones reales dentro de una parada se conservan;
  2. en los frames vivos de los tiempos se borra en huecos de largo exponencial, hasta que, en
     esperanza, falte en `--missing` de los frames vivos, **contando la que ya faltaba**. Si ya falta
     más, no se agrega nada. Los arranques son de Poisson, con la tasa que da en esperanza la
     fracción buscada (`1 - exp(-rL) = p`, superposiciones incluidas);
  3. en los frames muertos de los tiempos se aplica el mismo modelo de huecos, con objetivo
     `--dead-missing`, contado después de devolver la pelota. Por defecto es 0;
  4. opcionalmente, los huecos son más probables cuando hay 3 o más jugadores a menos de 3 m de la
     pelota (`--crowd`).

  Valores por defecto: 45% de frames vivos sin pelota, 0% de muertos, huecos de 1.5 s y 10 semillas.
  La tabla muestra los porcentajes logrados en cada partido (`miss` y `D miss`). `--seed-start`
  cambia el inicio del bloque de semillas, por defecto 0, para confirmar con simulaciones nuevas.
- **Pipelines:**
  - `v1`: `possession.py` tal cual;
  - `v1, true D`: el mismo pipeline con la pelota muerta perfecta, como diagnóstico para aislar la
    evidencia de equipo.

  Para comparar una versión nueva se suma al diccionario `PIPELINES`, usando las funciones de
  `possession.py` sin copiar su lógica.
- **Métricas:** las de `possession_metrics.evaluate`, la función que usa el scorer oficial. Incluye
  `spellF1` con las abstenciones rellenadas como lo hace el scorer, su bootstrap 5-95% (1000
  remuestreos) y `macroF1`. Se suman las posesiones predichas contra las reales y el F1 por frame
  de `D`.

### Cómo se decide

`python bench.py --compare A B` calcula un **bootstrap pareado de la diferencia** `spellF1(B) − spellF1(A)`:

- En cada partido, cada remuestreo elige las posesiones reales una vez y puntúa sobre ellas a las dos
  versiones y a todas las semillas de la pelota degradada. Es el remuestreo del bootstrap oficial
  (`bootstrap_spell_f1`), armado con sus propias piezas para que A y B compartan los sorteos
  (`spell_draws`).
- Además, cada remuestreo elige con reposición tantas semillas como se corrieron en ese partido.
  A y B comparten esa elección. Se promedian las diferencias de las semillas elegidas y después
  las de los partidos elegidos con `--games`. El intervalo 5-95% incluye así el ruido de las
  posesiones y el de la pelota simulada. Los partidos no se remuestrean.

B le gana a A si se cumplen las dos condiciones:

1. **Ruido:** el intervalo 5-95% de la diferencia combinada, con la pelota degradada por defecto,
   queda **entero por encima de 0**, con las **dos** variantes de verdad.
2. **Sensibilidad:** la diferencia combinada es positiva con `--missing 0`, `--missing 0.2`,
   `--gap 3`, `--crowd 2`, `--dead-missing 0.34` y `--missing 0 --dead-missing 0.34`.

   No conocemos bien cuánta pelota falta con el juego andando en BAR-ATH: `DATA.md` da el 41% de
   todos los frames evaluados, y la ventana pública (ADR-002), el 6.5% de los frames vivos. La
   decisión tiene que sostenerse en todo ese rango. `--missing 0` no borra nada: solo devuelve la
   pelota en las paradas, y deja la que ya falta en sample-data con el juego andando (2%, 4% y 8% en
   Games 3, 1 y 2). Es el extremo más bajo al que se puede llegar con estos datos.

   En esa ventana también falta la pelota en el 34% de los frames muertos (ADR-002). Los dos
   escenarios con `--dead-missing 0.34` comprueban que el resultado se sostiene cuando la pelota
   puede faltar tanto en juego como en las paradas.

### Barridos de parámetros

Para barrer N, R o `max_gap` (#7 y #33), se reserva un partido antes de empezar. Se elige el
candidato con mayor diferencia pareada media sobre los partidos de selección, con la verdad desde
el inicio del evento. Después se lo confirma contra la versión actual en el partido reservado,
con semillas nuevas, aplicando las dos condiciones de arriba y las dos variantes de verdad. No se
vuelve a elegir con ese resultado; si no pasa, el barrido no confirma una mejora.

Por ejemplo, selección con `--games 2,3 --seed-start 0` y confirmación con `--games 1 --seed-start 10`,
ambas con 10 semillas. Se fijan la partición y los bloques de semillas antes de correr. Se reserva
Game 1 o 2 cuando la selección depende de las etiquetas de `D`, porque ADR-003 se ajustó en Game 3.

La fila "pelota tal cual" se reporta, pero **no decide**: mide el escenario que favorece el atajo de
sample-data.

### Qué no se hace

- **Ajustar el simulador mirando BAR-ATH desde una IA** (`AGENTS.md`). Si una persona quiere acercar
  los parámetros al partido, calcula la distribución de huecos en su máquina y la guarda en un
  archivo local. Ese archivo no va al repo ni se le muestra a ninguna IA.
- **Usar el banco para afirmar cuánto va a dar en BAR-ATH.** Compara versiones; no predice el
  ranking.

## Cómo se mide

Esta decisión se valida con su propia línea de base, en datos abiertos (fila del 28/10 en
`docs/EXPERIMENTOS.md`). Media de los 3 partidos y de las 10 semillas, índices 0-9 por partido,
verdad desde el inicio del evento; entre corchetes, el intervalo de la diferencia pareada con
1000 remuestreos de posesiones y semillas. Todas las corridas son
`python bench.py --compare v1 "v1, true D"`, más las opciones de cada fila:

| Escenario | `v1` | `v1, true D` | Diferencia pareada |
|---|---|---|---|
| Pelota tal cual (no decide) | 0.587 | 0.619 | +0.032 [+0.022, +0.042] |
| Degradada, por defecto (45%, huecos de 1.5 s) | 0.241 | 0.481 | +0.240 [+0.225, +0.256] |
| Ídem, verdad desde el final del evento | 0.237 | 0.472 | +0.234 [+0.219, +0.251] |
| `--missing 0` (2-8%, solo la pelota en las paradas) | 0.495 | 0.619 | +0.124 [+0.110, +0.138] |
| `--missing 0.2` | 0.407 | 0.571 | +0.163 [+0.150, +0.177] |
| `--gap 3` | 0.252 | 0.459 | +0.206 [+0.192, +0.221] |
| `--crowd 2` | 0.246 | 0.481 | +0.234 [+0.219, +0.249] |
| `--dead-missing 0.34` | 0.248 | 0.480 | +0.232 [+0.217, +0.248] |
| `--missing 0 --dead-missing 0.34` | 0.506 | 0.619 | +0.113 [+0.101, +0.125] |

Las corridas de sensibilidad también usan las dos variantes de verdad. Con `--dead-missing 0.34`
se logra un 34-35% de frames muertos sin pelota por partido, promediando las semillas.

- Con la pelota tal cual, la pelota muerta perfecta suma apenas 0.03, porque el detector `v1` ya la
  "ve" por el atajo (F1 de `D` entre 0.91 y 0.96).
- Con solo devolver la pelota en las paradas (`--missing 0`), `v1` cae de 0.587 a 0.495 y la pelota
  muerta perfecta pasa a sumar 0.12.
- Con la pelota degradada por defecto, suma 0.24, y el F1 de `D` de `v1` cae a 0.54-0.62 en la
  primera semilla. Aun borrando el 34% de la pelota en las paradas, suma 0.23; con `--missing 0`, 0.11.

El banco reproduce ese hallazgo en los 3 partidos y en todas las variantes. Es la señal de que el
banco mide lo que tiene que medir.

También se reprodujo el ejemplo de la revisión con N = 1.5 s, redondeado a 38 frames. Con 45% de
faltantes y las semillas 6-8, la diferencia es −0.0059: el intervalo anterior era [−0.0111, −0.0003]
y al remuestrear semillas queda [−0.0130, +0.0014], dentro del ruido. Con 10 semillas queda
−0.0037 [−0.0090, +0.0014]; con `--missing 0.2`, −0.0030 [−0.0123, +0.0071]. Fue un control del
intervalo, sin agregar esa variante a `PIPELINES` ni cambiar N.

## Consequences

### Positive

- **Cada decisión tiene detrás cientos de posesiones** (unas 1,050 entre los 3 partidos), en lugar
  de 17.
- **El atajo de sample-data queda neutralizado.** Un detector que depende de que la pelota
  desaparezca en las paradas deja de verse bien.
- **La regla mira la diferencia entre versiones, no cada versión por separado.** Una mejora chica,
  con mucha dispersión entre posesiones, no pasa por mejora.
- **Es rápido:** unos 11-12 segundos por corrida en esta máquina, con 10 semillas, las dos verdades,
  bootstrap y comparación incluidos. Antes eran unos 5 segundos con 3 semillas. Se puede correr en
  cada PR.
- **El documento técnico gana una validación** que se puede explicar y reproducir.

### Negative

- **La verdad sale de eventos y la del concurso, del tracking corregido** (`CHALLENGE.md`). Las dos
  variantes de verdad acotan, pero no eliminan, la diferencia: entre ellas cambia el 0.8% de los
  frames vivos, pero el total de posesiones pasa de 383 a 406 en Game 3.
- **El simulador es una suposición.** No modela el ruido de los jugadores (slots que se pierden o se
  intercambian) ni oclusiones atadas a la jugada, salvo la aproximación de `--crowd`.
- **Los 3 partidos son del mismo proveedor y la misma época.** No prueban que el resultado se
  transfiera a otra liga u otra cámara.
- **ADR-003 se ajustó en Game 3** mirando dónde el detector no coincidía. En lo que dependa de las
  etiquetas de `D`, los Games 1 y 2 son la validación más limpia.
- **El bootstrap pareado vuelve a armar el bucle de sorteos del oficial** con sus piezas. Un test
  verifica que con los mismos sorteos da exactamente el mismo intervalo que `bootstrap_spell_f1`.

### Neutral

- `calibrate_dead.py` sigue sirviendo como diagnóstico de la pelota muerta. La decisión final pasa por
  el banco. El `calibrate_n.py` del PR #21 no llegó a `main`: el barrido de N lo hace el banco.

## Alternatives Considered

### La ventana pública

Prohibida para elegir (`RULES.md`). Además, el ruido es 4 veces mayor que las diferencias que
buscamos.

### Sample-data sin degradar

Premia el atajo de la pelota sin datos. Con esa pelota, `v1` queda a 0.03 de la pelota muerta
perfecta, y con la degradada, a 0.24: elegir ahí el detector de `D` lleva a calibrar el atajo.

### Comparar B contra el intervalo de A, sin parear

Era la primera versión de este ADR. La revisión adversarial del PR #38 mostró un contraejemplo:

- A tiene IoU 0.55 en las 100 posesiones (0.600, sin dispersión);
- B acierta 61 y se equivoca de equipo en 39 (0.610).

B queda por encima del intervalo de A, pero la diferencia pareada va de −0.07 a +0.09. El caso quedó
como test (`test_a_tiny_gain_with_a_wide_spread_is_inside_the_noise`).

### IDSSE (Bundesliga, CC BY 4.0, aprobado en el #16 del repo oficial)

Es la fuente más cercana a la verdad del concurso: su tracking DFL trae el estado de la pelota y el
dueño por frame. Se usa como **chequeo aparte**, no como parte de la regla de decisión
(`explore/idsse_bench.py`; resultados en el ADR-009). Si pasa a decidir, entra con un ADR que reemplace
a este.

## References

- `bench.py`, `test_bench.py`
- `explore/oracles_2810.py`, `explore/control_radius_2810.py`: el análisis del 28/10 que motiva este
  ADR, con su degradación vieja
- Issues #30 (este banco), #31-#36 (lo que se mide con él); revisión adversarial en el PR #38
- ADR-003 (etiquetas de `D`), ADR-005 (verdad de posesión, PR #20)
- `metrica-sports/more-than-a-hack-2027`: `EVALUATION.md`, `RULES.md`, `DATA.md`,
  `evaluation/possession_metrics.py`
- `metrica-sports/sample-data`: Sample Games 1, 2 y 3 (citar en el documento técnico)
