---
artifact: adr
version: "1.0"
created: 2026-10-28
status: accepted
---

# ADR-007: Detector de pelota muerta v2: jugadores lentos o pelota vista fuera de la cancha

## Status

Accepted (2026-10-29), revisado por Ivan Ledesma en el PR #41. Sus cuatro preguntas quedaron
respondidas en el PR (`b9d7e2f` y `fff0fe9`, con IDSSE como confirmación independiente) y lo mergeó
(`53da7ec`). Reemplaza el **diseño** del detector del ADR-002 (su prioridad sigue en pie), que queda
`Superseded by ADR-007` en lo que hace al detector. Se mide con el banco del ADR-006 (PR #38).

**Date:** 2026-10-28
**Deciders:** Lautaro Bursese (con Claude)
**Issue:** #32, que incluye el #9

## Context

- **La pelota muerta es el cuello de botella.** Con la pelota degradada del banco, pasar de `v1` a la
  pelota muerta perfecta suma +0.240 [+0.225, +0.256] de `spellF1` (ADR-006).
- **El detector v1 depende de que falte la pelota.** Es un OR de tres señales: pelota sin datos,
  pelota fuera de 0-1 y velocidad media de los jugadores menor a 1 m/s. En el ATD la pelota falta
  por oclusiones (41% de los frames evaluados, `DATA.md`), así que "pelota sin datos" dispara con el
  juego andando: con la pelota degradada, el F1 por frame de `D` de v1 cae a 0.52-0.62.
- **Los jugadores solos separan bien** (`explore/dead_v2_features.py`; AUC de `D` contra juego vivo,
  pelota degradada, semilla 0, Games 1 / 2 / 3):

  | Señal | Game 1 | Game 2 | Game 3 |
  |---|---|---|---|
  | Fracción de jugadores a menos de 2 m/s, 2 s | 0.930 | 0.876 | 0.920 |
  | Velocidad media de los jugadores, 2 s | 0.916 | 0.854 | 0.912 |
  | Media de los 3 más rápidos, 4 s | 0.915 | 0.850 | 0.910 |
  | Cada equipo en su mitad (forma de saque inicial) | 0.514 | 0.499 | 0.559 |

  El AUC está orientado para que 1 sea separación perfecta: para las velocidades, más baja es más
  muerta. Cobertura: 100% de los frames.
- **El banco tiene dos artefactos en la pelota que restaura en las paradas** (ADR-006, paso 1: la
  interpola entre las observaciones de antes y de después):
  1. **Queda casi quieta**, así que su velocidad separa casi perfecto (AUC 0.97 con el 80% de
     cobertura). Cómo se mueve la pelota del ATD en una parada no lo sabemos.
  2. **Queda fuera de la cancha en el 27-42% de los frames `D`**. En sample-data crudo es el 0-3%, y
     en la ventana pública de BAR-ATH, el 7% (ADR-002). Infla cualquier señal de "pelota fuera de
     la cancha", también la de v1.

## Decision

`possession.dead_mask_v2(players, ball)` pasa a ser el detector de `label()`. Marca `D` donde se
cumple cualquiera de dos condiciones:

1. **Jugadores lentos.** En una ventana centrada de 5 s, la fracción de frames de jugadores seguidos
   que van a menos de 1.75 m/s:
   - una parada empieza donde esa fracción llega al 85% y sigue mientras se mantiene en el 75% o más
     (histéresis);
   - cuenta si dura al menos 3 s;
   - después su inicio se adelanta 1 s y su final, 38 frames (1.52 s): los jugadores frenan después
     del silbato y arrancan después del saque.
2. **Pelota vista fuera de la cancha.** En la mitad de una ventana de 2 s, durante al menos 1 s. Es
   la señal de v1 sola.

Una pelota que falta no cuenta nunca. Todo se cuenta con enteros y las fracciones se comparan como
`100 * cuenta >= pct * total`, así que el resultado es exacto en cualquier CPU (#6).

`dead_mask` (v1) queda en `possession.py` para `calibrate_dead.py` y como línea de base del banco. En
el banco, `v1` sigue siendo el detector del ADR-002 y `v2` es `possession.py` tal como queda con este
ADR: las próximas comparaciones van contra `v2`.

### Cómo se eligió (regla de barridos del ADR-006)

Antes de correr se fijó la partición: se elige en Games 2 y 3 con las semillas 0-9 y se confirma en
Game 1, reservado porque el ADR-003 se ajustó en Game 3. La verdad es la del banco: desde el inicio
del evento para elegir, y las dos variantes para confirmar.

1. **Barrido** (`explore/dead_v2_sweep.py`), con 3 semillas:
   - 243 combinaciones: corte de 1.5 a 2.5 m/s, ventana de 1 a 3 s, entrada del 70 al 90%,
     histéresis de 0 a 20 puntos y mínimo de 1 a 3 s;
   - 216 alrededor de la mejor zona;
   - 160 ajustes de bordes.

   Queda una meseta: decenas de combinaciones a menos de 0.004 de la mejor.
2. **Finalistas con las 10 semillas** (Games 2 y 3, diferencia pareada media contra v1):

   | Corte 1.75 m/s, ventana 5 s, 85 / 75%, mínimo 3 s | Diferencia | F1 de `D` | Bordes (inicio / fin) |
   |---|---|---|---|
   | Sin ajustar los bordes | +0.1306 | 0.803 | +1.91 / +0.69 s |
   | Inicio 1 s antes | +0.1359 | 0.817 | +1.00 / +0.68 s |
   | Inicio 1 s antes y final 1.52 s antes (**elegido**) | +0.1375 | 0.815 | +0.86 / −0.54 s |

3. **Primera confirmación, solo con jugadores** (Game 1, semillas 10-19). Pasó la condición 1
   (+0.134 [+0.110, +0.159]) y falló la 2: en los dos escenarios con `--missing 0` quedó en −0.005 y
   −0.014, dentro del ruido. En los partidos de selección pasaba lo mismo (+0.005 y −0.007), así
   que no era ruido de Game 1: con la pelota visible, v1 aprovecha su señal de pelota fuera de la
   cancha, que el banco infla. Siguiendo la regla, ese candidato no se adoptó. Se midió sobre
   `609c5f7`; los números que se repitieron con `5ac2ad2`, la verdad nueva del banco, dan igual.
4. **Segundo candidato, elegido solo en los partidos de selección**: sumarle la señal de pelota fuera
   de la cancha (`explore/dead_v2_off_pitch.py`, Games 2 y 3, semillas 0-9, diferencia contra v1):

   | Pelota restaurada en las paradas | Escenario | Solo jugadores | Jugadores + fuera de la cancha |
   |---|---|---|---|
   | Como la deja el banco | 45% faltante | +0.137 | +0.166 |
   | Como la deja el banco | `--missing 0` | +0.005 | +0.038 |
   | Metida dentro de la cancha | 45% faltante | +0.158 | +0.158 |
   | Metida dentro de la cancha | `--missing 0` | +0.053 | +0.051 |

   Suma donde la señal existe y no resta donde no. Con la pelota metida dentro de la cancha, v1 se
   cae (F1 de `D` 0.57 con `--missing 0`) y la versión solo con jugadores le gana en los dos extremos.
5. **Confirmación final**, en Game 1 con semillas nuevas (20-29): ver "Cómo se mide".

**Game 1 ya no es una reserva virgen**: se usó en la primera confirmación, y el segundo candidato se
diseñó después de verla. El cambio se eligió en los partidos de selección, y la confirmación
independiente es IDSSE (siete partidos con `BallStatus`): ver "Cómo se mide".

## Cómo se mide

Confirmación final: Game 1, semillas 20-29, `python bench.py --games 1 --seed-start 20 --compare v1 v2`
más las opciones de cada fila. Diferencia pareada `v2 − v1` con su intervalo 5-95%:

| Escenario | Verdad desde el inicio | Verdad desde el final |
|---|---|---|
| Por defecto (45% faltante, huecos de 1.5 s) | +0.163 [+0.138, +0.188] | +0.161 [+0.137, +0.184] |
| `--missing 0` | +0.033 [+0.013, +0.054] | +0.032 [+0.014, +0.052] |
| `--missing 0.2` | +0.077 [+0.058, +0.098] | +0.076 [+0.058, +0.097] |
| `--gap 3` | +0.145 [+0.122, +0.169] | +0.143 [+0.119, +0.166] |
| `--crowd 2` | +0.157 [+0.133, +0.181] | +0.155 [+0.132, +0.178] |
| `--dead-missing 0.34` | +0.144 [+0.121, +0.167] | +0.142 [+0.119, +0.164] |
| `--missing 0 --dead-missing 0.34` | +0.008 [−0.010, +0.026] | +0.007 [−0.010, +0.025] |

Por defecto, `v1` da 0.258 y `v2` 0.421 (verdad desde el inicio), con un F1 de `D` de 0.634 y 0.905.
Las dos condiciones del ADR-006 se cumplen: el intervalo por defecto queda entero por encima de 0 con
las dos verdades, y la diferencia es positiva en los seis escenarios de sensibilidad.

**Con la pelota restaurada metida dentro de la cancha** (Game 1, semillas 20-29, sin el artefacto de
la pelota fuera de la cancha): +0.156 [+0.133, +0.180] con el 45% faltante y +0.057 [+0.036, +0.079]
con `--missing 0`. El F1 de `D` de v1 cae a 0.51 y 0.65, y el de v2 queda en 0.87.

**Los tres partidos juntos** (informativo, semillas 0-9): +0.166 [+0.152, +0.180] desde el inicio y
+0.162 [+0.148, +0.175] desde el final. `v2` da 0.407, contra 0.241 de `v1` y 0.481 de la pelota
muerta perfecta: recupera el 69% de esa brecha.

**Con la pelota tal cual de sample-data** (Game 1, sin degradar): `v2 − v1` da −0.097 [−0.123, −0.073]
desde el inicio y −0.096 [−0.121, −0.071] desde el final. `v1` da 0.608, casi lo mismo que con la pelota
muerta perfecta (0.638), y `v2` da 0.511. No es un escenario del ATD: el tracking corregido de sample-data
borra la pelota en las paradas (en Game 3 falta en el 99.8% de los frames `D` y en el 2.0% de los vivos;
ADR-006), así que ahí la señal de pelota sin datos de `v1` es casi un detector perfecto. En el ATD la
pelota falta por oclusiones, aglomeraciones y pelotas en el aire (`DATA.md` del reto), y `v2` no la usa a
propósito. Por eso el ADR-006 decide con la pelota degradada.

**Robustez con los jugadores degradados** (`explore/dead_v2_players_noise.py`, Games 1-3, semillas
10-19). El banco solo degrada la pelota, así que acá también se degradan los jugadores, igual para v1
y para v2:

| Jugadores | `v2 − v1` | F1 de `D` de v2 |
|---|---|---|
| Limpios | +0.164 [+0.150, +0.178] | 0.888 |
| Ruido de 0.3 m/s en la velocidad | +0.162 [+0.148, +0.176] | 0.874 |
| Ruido de 0.6 m/s | +0.154 [+0.141, +0.169] | 0.820 |
| 10% de los slots perdidos, en ráfagas de 2 s | +0.148 [+0.135, +0.161] | 0.886 |
| 25% de los slots perdidos | +0.121 [+0.110, +0.132] | 0.884 |
| Velocidades suavizadas en 0.5 s | +0.164 [+0.150, +0.178] | 0.889 |
| Ruido de 0.3 m/s, 10% perdidos y suavizadas | +0.144 [+0.131, +0.156] | 0.873 |

La mejora baja con los slots perdidos y con el ruido fuerte, pero no se da vuelta en ningún caso.

**Según cuánto falta la pelota** (Games 1-3, semillas 0-4, verdad desde el inicio;
`python bench.py --truth start --seeds 5 --missing L --dead-missing P --compare v1 v2`). `v2 − v1`
según la pelota que falta con juego vivo (filas) y en las paradas (columnas):

| Juego vivo \ Paradas | 0 | 25% | 50% | 75% | 100% |
|---|---|---|---|---|---|
| Tal cual (2-8%) | +0.036 | +0.016 | −0.011 | −0.046 | −0.105 |
| 15% | +0.069 | +0.048 | +0.022 | −0.010 | −0.059 |
| 30% | +0.116 | +0.099 | +0.082 | +0.052 | +0.012 |
| 45% | +0.165 | +0.149 | +0.134 | +0.112 | +0.078 |
| 60% | +0.210 | +0.197 | +0.181 | +0.167 | +0.141 |

`v1` gana solo si la pelota casi no falta con juego vivo y falta mucho en las paradas, que es el patrón
de sample-data. En BAR-ATH falta en el 41% de los frames puntuados (`DATA.md`). Si las paradas son un
30-40% de esos frames, para caer en esa zona tendría que faltar en el 80-100% de los frames de parada y
en menos del 15% de los de juego vivo: lo contrario de lo que describe `DATA.md`, que la pierde por
oclusiones, aglomeraciones y pelotas en el aire.

**Transiciones en el banco** (`explore/dead_v2_transitions.py`; scorer oficial con tolerancia de 25
frames; Games 1-3, semillas 0-9, pelota degradada):

| Transición | `v1`: F1 (latencia mediana) | `v2`: F1 (latencia mediana) |
|---|---|---|
| Entra a `D` | 0.155 (−6 frames) | 0.602 (−1 frame) |
| Sale de `D` | 0.148 (+5) | 0.512 (+1) |
| Cambio de equipo | 0.275 (0) | 0.230 (−1) |

Los bordes elegidos por `spellF1` dejan las paradas a un frame de la verdad en la mediana de las
transiciones emparejadas. Los cambios de equipo pierden precisión (0.371 → 0.244), probablemente porque
v2 deja como juego vivo tramos que v1 tapaba con `D` falsos, y ahí la evidencia del jugador más cercano
usa la última posición conocida de la pelota. Queda para el #33.

**La verdad del banco sigue la convención oficial** (`explore/dead_truth_events_vs_tracking.py`).
`CHALLENGE.md` define el `D` oficial con el tracking corregido ("where the corrected tracking marks the
ball dead"), y el banco lo arma con eventos (ADR-003). En sample-data el tracking corregido borra la
pelota en las paradas, y los bordes de las dos definiciones coinciden: en los tres partidos, el inicio
se corre una mediana de +0.04 s y el final, 0.00 s.

**Confirmación independiente en IDSSE** (`explore/idsse_bench.py`: 7 partidos de la Bundesliga con
tracking de DFL, CC BY 4.0; cada mitad es un partido para el bootstrap pareado; 5 semillas). La verdad se
arma como la oficial (`CHALLENGE.md`): `D` donde `BallStatus` es 0 y, si no, el equipo de
`BallPossession`, sin eventos ni parámetros. Ningún parámetro del v2 se tocó: son los de sample-data.

| Pelota | `v1` (F1 de `D`) | `v2` (F1 de `D`) | `v2 − v1` | Mitades a favor de `v2` |
|---|---|---|---|---|
| Tal cual (DFL la sigue en todos los frames) | 0.406 (0.886) | 0.415 (0.931) | +0.009 [+0.002, +0.015] | 9 de 14 |
| Degradada (45% faltante con juego vivo, huecos de 1.5 s) | 0.220 (0.708) | 0.339 (0.932) | +0.119 [+0.108, +0.129] | 14 de 14 |

- **Con las velocidades calculadas desde las posiciones** en lugar de las del proveedor da lo mismo: +0.009 y +0.121.
- **Bordes:** los del `D` del v2 quedan a menos de 0.2 s de los de `BallStatus` (mediana por mitad: inicio −0.18 s y final +0.04 s con la pelota tal cual; −0.11 y +0.04 s degradada). Los ajustes de borde elegidos en sample-data también sirven con otro proveedor.
- **Chequeos:** `BallPossession` coincide con el jugador más cercano en el 71-82% del juego vivo (1 es el local y 2 el visitante), y la velocidad del proveedor está en km/h. En DFL el `D` ocupa el 32-59% de cada mitad, más que en sample-data.

## Consequences

### Positive

- **El `D` ya no depende de que falte la pelota**: en el banco degradado, el F1 por frame de `D` pasa
  de 0.52-0.62 a cerca de 0.9.
- **Solo señales colectivas**: sirve con los 46 slots del ATD, que no identifican a nadie.
- **Exacto en cualquier CPU**: solo enteros en las ventanas y las fracciones.
- **Pocos parámetros y con sentido físico**: un corte de velocidad, dos porcentajes, un mínimo y dos
  ajustes de borde.
- **Se confirma en otra liga y con otro proveedor** (IDSSE, sin tocar ningún parámetro): +0.119 con la
  pelota degradada en las 14 mitades, y el F1 de `D` sube de 0.71 a 0.93.

### Negative

- **El tracking de los jugadores de sample-data es limpio** y el del ATD no: hay slots que se pierden,
  se duplican o se intercambian. El banco no lo modela (ADR-006); la prueba de robustez de arriba lo
  aproxima.
- **Las velocidades no vienen igual**: en el ATD las da el proveedor por slot, y en sample-data salen
  de las posiciones, frame a frame. El corte de 1.75 m/s podría correrse.
- **El aporte de la pelota fuera de la cancha está inflado en el banco** (27-42% de los frames `D`
  contra el 7% de la ventana pública). En el ATD se espera un aporte chico, con poco riesgo: en la
  ventana pública esa señal no aparece nunca con el juego andando (ADR-002).
- **Los ajustes de borde salen de sample-data**: las demoras físicas pueden ser otras en LaLiga.
- **Fases lentas con la pelota viva** (el arquero con la pelota, una salida lenta) pueden parecer una
  parada; el 85 / 75% y el mínimo de 3 s lo acotan.
- **Game 1 se usó dos veces** (ver arriba). Por eso la confirmación independiente es IDSSE.
- **Con la pelota tal cual de sample-data gana v1** (−0.097), porque ahí la pelota que falta marca la
  parada. Con la pelota del ATD no pasa (ver "Cómo se mide").

### Neutral

- `calibrate_dead.py` sigue midiendo el detector v1. Para diagnosticar el v2 por pieza alcanza con
  `explore/dead_v2_sweep.py`, que imprime el F1 y los bordes de `D`.

## Alternatives Considered

### Quedarse con v1

Pierde contra el v2 en todos los escenarios del banco.

### v1 sin la señal de pelota sin datos

+0.140 con la pelota degradada, pero −0.002 con `--missing 0` y un F1 de `D` de 0.76, en los partidos
de selección. El v2 le gana en los dos extremos.

### Usar la velocidad de la pelota (pelota quieta en la reanudación)

Separa casi perfecto en el banco, pero por el artefacto de la pelota interpolada. Se puede revisar
cuando el banco restaure la pelota de las paradas de otra manera.

### Un clasificador con muchas señales (regresión logística o árboles)

Con tres partidos, más parámetros es más riesgo de sobreajuste, y una sola señal colectiva ya da un F1
de `D` de 0.82. Queda para cuando haya más datos (IDSSE).

### Formaciones de reanudación y Smart Tagging como pista de tiempo

Es el diseño completo del #32. Quedan para una iteración siguiente; el propio issue prevé entregar
primero las señales de jugadores y de pelota con histéresis.

## Qué sigue

- **BAR-ATH:** Lautaro lo corrió el 28/10 sobre `12e5873`, con validador OK (comentario en el #41). Se
  repite con el commit final, porque con el #28 el CSV pasó a LF. La ventana pública, solo para
  verificar (`AGENTS.md`).
- **IDSSE como banco permanente**: `explore/idsse_bench.py` arma la verdad como la oficial y no
  depende de eventos. Para que decida versiones junto al banco de sample-data hace falta un ADR que
  reemplace la parte de validación del ADR-006.
- **Banco**: restaurar la pelota de las paradas sin sacarla de la cancha (comentado en el #38).
- **#32 sigue**: formaciones de reanudación y el borde de reanudación fino.

## References

- `possession.py` (`dead_mask_v2`), `bench.py` (pipeline `v2`), `test_possession.py`
- `explore/dead_v2_features.py`, `explore/dead_v2_sweep.py`, `explore/dead_v2_off_pitch.py`,
  `explore/dead_v2_players_noise.py`, `explore/dead_v2_transitions.py`,
  `explore/dead_truth_events_vs_tracking.py`, `explore/idsse_bench.py`
- ADR-002 (detector v1), ADR-003 (etiquetas de `D`), ADR-006 (banco y regla de decisión)
- Issues #32, #9, #5 y #6
