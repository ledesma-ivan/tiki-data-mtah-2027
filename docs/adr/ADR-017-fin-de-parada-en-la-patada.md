---
artifact: adr
version: "1.0"
created: 2026-10-31
status: rejected
---

# ADR-017: El fin de cada parada en la patada que reanuda el juego, con una regla física

## Status

Rejected (2026-10-31). Lautaro pidió arrancar el #32 el 30/10 ("Arrancá, si!") y dio el OK para la confirmación
el 31/10 ("OK te confirmo"). **Confirmó 43 de 43 en la reserva, pero en BAR-ATH la regla no mueve ninguna parada**
(revisión de Iván en el PR #80; ver "La entrega y BAR-ATH"), así que no entra a la entrega. Lautaro aceptó la
propuesta de Iván el 31/10 ("Dale ok si"). `stops_model.json` sigue siendo la identidad, y el ADR-010 sigue como
estaba.

**Date:** 2026-10-31
**Deciders:** Lautaro Bursese (con Claude)
**Issues:** #32; responde además el #34

## Context

### Lo que queda del `D`, encima del modelo de posesión

`explore/oracles_live.py` (fila del 30/10 en `docs/EXPERIMENTOS.md`) mide los oráculos sobre el pipeline de `main`
(el v2, las paradas identidad y el modelo de posesión del ADR-014 con su Viterbi). El modelo de posesión es la receta
de `live_choice.json`, entrenada en los 6 partidos de selección que no se puntúan (LOMO). Cada fila arregla un error
del `D` con la verdad. Diferencia pareada contra `main`:

| Oráculo | Metrica (Games 2-3) | IDSSE (1-5) |
|---|---|---|
| Línea de base (v2 + modelo de posesión) | 0.673 | 0.563 |
| Paradas que faltan / que sobran | +0.015 / +0.011 | +0.009 / +0.012 |
| Borde de inicio / de fin | +0.036 / +0.039 | +0.026 / +0.021 |
| **Los dos bordes** | **+0.071 [+0.059, +0.083]** | **+0.052 [+0.045, +0.059]** |
| `D` perfecto | +0.100 [+0.085, +0.115] | +0.075 [+0.067, +0.082] |
| Equipo que reanuda verdadero (#34) | −0.003 | −0.002 |

- **Los bordes son casi todo lo que queda del `D`:** el 71% en Metrica y el 69% en IDSSE. El inicio y el fin pesan
  parecido.
- **El equipo que reanuda ya no suma:** el modelo de posesión acierta solo quién arranca cada tramo vivo.

### Un modelo de bordes aprendido no pasa los dos bancos (paso 0)

`explore/edges_on_live.py` toma la receta elegida del ADR-010 (modelo de 3 s, 31 hojas), sin el equipo que reanuda,
y le suma de a uno los arreglos que dejó su revisión. Encima del modelo de posesión, contra `main`, LOMO:

| Variante | Metrica | IDSSE |
|---|---|---|
| La receta del ADR-010 | −0.0043 [−0.0132, +0.0044] | +0.0316 [+0.0261, +0.0371] |
| + pesos normalizados (con los de hoy, las hojas se achican) | −0.0079 | +0.0320 |
| + cada banco pesa lo mismo (hoy IDSSE pesa 5 contra 2) | −0.0087 | +0.0314 |
| + tiros libres de IDSSE desde la infracción, tipos en el reloj corregido | −0.0141 [−0.0231, −0.0054] | +0.0310 |
| + jugadores con ruido al entrenar | −0.0175 | +0.0311 |
| + tipos fuera de pliegue y una pelota de IDSSE tapada | −0.0173 | +0.0306 |
| Plan B (constantes por tipo) | −0.0040 | +0.0038 |

Ningún arreglo destraba Metrica. La ganancia de IDSSE sale de la pelota real de sus paradas, que el banco de
Metrica no tiene: en Metrica el modelo no la ve al entrenar, y lo que aprende de los jugadores no pasa de un banco
al otro. En Metrica casi todos los bordes empeoran: el fin del tiro libre a 0.5 s o menos pasa de 24% a 5-7%.

### La física es la misma en los tres lados

- **Las dos verdades marcan el fin de la parada en la patada** (`explore/edge_clock.py`, repetida después del #53):
  IDSSE 0.04 s después y Metrica entre 0.04 s antes y la patada misma.
- **La pelota cerca de la reanudación es real** en IDSSE y en el ATD. En sample-data, que no trae la pelota en las
  paradas, reaparece con la reanudación.
- **Una reanudación es una pelota quieta que se patea.** Sin esa condición, cuando la patada no se ve (en el banco
  falta la pelota en el 45% del juego vivo) la regla toma el pase siguiente y rompe los fines que el v2 ya tenía bien.

`explore/kick_snap.py` mueve el fin de cada parada del v2 a la patada más cercana, sin entrenar nada. Encima del
modelo de posesión, contra `main`, LOMO:

| Regla | Metrica | IDSSE |
|---|---|---|
| Cualquier patada (4 m/s), de 2 s antes a 3 s después del fin | +0.0029 [−0.0028, +0.0087] | −0.0027 [−0.0067, +0.0008] |
| Pelota quieta 0.5 s, la misma ventana | +0.0053 [+0.0017, +0.0091] | +0.0058 [+0.0039, +0.0080] |
| Pelota quieta 1 s, la misma ventana | +0.0072 [+0.0043, +0.0104] | +0.0060 [+0.0041, +0.0081] |
| Pelota quieta 1 s, de 3 s antes a 5 s después | +0.0080 [+0.0031, +0.0124] | +0.0070 [+0.0049, +0.0094] |

- **Con la pelota quieta gana en los dos bancos,** con el intervalo arriba de 0, en los 2 partidos de Metrica y en
  las 10 mitades de IDSSE.
- **Arregla los tiros libres sin romper lo que estaba bien.** Fines a 0.5 s o menos con la última regla: tiros
  libres de 22% a 46% en IDSSE y de 24% a 42% en Metrica, saques de arco de Metrica de 15% a 41%, córners de Metrica
  de 47% a 73%; laterales, saques de arco y córners de IDSSE suben de 77-86% a 84-89%.

### El modelo de posesión no se reentrena

El ADR-014 (Neutral) preveía reentrenar el modelo de posesión si las paradas cambian, porque `live_since`,
`live_until` y sus filas dependen de ellas. Medido en el paso 0 (`explore/kick_snap.py --retrain`), con la última
regla de la tabla:

| Modelo de posesión | Metrica | IDSSE |
|---|---|---|
| El de hoy, entrenado con las paradas del v2 | +0.0080 [+0.0031, +0.0124], 2 de 2 | +0.0070 [+0.0049, +0.0094], 10 de 10 |
| Reentrenado con las paradas nuevas | +0.0007 [−0.0069, +0.0079], 1 de 2 | +0.0079 [+0.0035, +0.0123], 9 de 10 |

Reentrenado pierde la ganancia de Metrica, así que el modelo de posesión sigue como está.

### Reglas que condicionan el diseño

- **Se elige solo en otros partidos**, nunca en BAR-ATH ni en la ventana pública (issues 2, 8 y 10 del repo oficial),
  y **ninguna IA ve los datos del partido** (`AGENTS.md`).
- **El CSV tiene que salir igual byte a byte en cualquier máquina** (#6): todo en enteros.
- **Se decide con los dos bancos** (ADR-011): selección en Metrica 2-3 e IDSSE 1-5 y una sola confirmación en la
  reserva (Metrica 1, IDSSE 6-7), con semillas nuevas.

## Decision

### Objetivos, no objetivos y antiobjetivos

- **Objetivo:** el fin de cada parada del v2 en la patada que reanuda el juego, cuando se ve, con una mejora de
  `spellF1` en los dos bancos encima del modelo de posesión.
- **No objetivos:**
  - el inicio de las paradas: el del tiro libre es la infracción, que no se ve en el tracking;
  - las paradas que faltan o que sobran (~+0.01 cada una);
  - el equipo que reanuda (#34), que no suma;
  - reentrenar el modelo de posesión.
- **Antiobjetivos:**
  - elegir con BAR-ATH o con la ventana pública;
  - coma flotante en lo que decide una etiqueta;
  - una regla que gane en un banco y pierda en el otro.

### La regla

`stops_model.json` en modo `kick` (`{"mode": "kick", "before", "after", "kick_cms", "rest", "rest_cms"}`, enteros),
que `refine` aplica con `possession.snap_ends`:

1. `dead_mask_v2` encuentra las paradas, como hoy.
2. **La patada** (`kick_onsets`) es un frame `t` desde el que la pelota se mueve a `kick_cms` cm/s o más durante
   `KICK_RUN` = 3 pasos seguidos, después de `rest` pasos más lentos que `rest_cms`. Un paso desde o hacia una pelota
   que falta no es rápido ni quieto.
3. **El fin de cada parada pasa a la patada más cercana** dentro de `[fin − before, fin + after)`. En un empate, la más
   temprana. Sin patada, el fin queda.
   - Un fin nunca pasa antes del segundo frame de su parada, ni llega a la parada siguiente, ni sale de su tiempo.
4. El inicio no cambia, y no se nombra al equipo que reanuda.
5. **Todo en enteros:** las posiciones en cm (redondeadas como en `frame_features`) y las velocidades al cuadrado,
   comparadas como enteros.

`kick_cms` = 400 (4 m/s, la patada de `explore/edge_clock.py`) y `rest_cms` = 200 (2 m/s: quieta, sostenida o
llevada) quedan fijos. `before`, `after` y `rest` se eligen.

### Cómo se elige y se confirma

- **Recetas:** la pelota quieta 0.5, 1 o 1.5 s; la patada buscada desde 2 o 3 s antes del fin hasta 3, 5 u 8 s
  después. Son 18, fijadas después del paso 0 y antes de `--select`.
- **Selección** (`calibrate_kick.py --select`): LOMO sobre los 7 partidos de selección.
  - En cada pliegue, el modelo de posesión de la receta del ADR-014 (63 hojas, λ = 10) se entrena con los otros 6.
  - Cada receta se puntúa en el partido que queda afuera contra `main` (las paradas del v2 con el mismo modelo), con
    la pelota degradada por defecto, los jugadores limpios y las semillas de selección (Metrica 0-9, IDSSE 0-4).
  - Gana la de mayor diferencia pareada media, promediando por igual los dos bancos (ADR-011). Queda en
    `kick_choice.json`.
- **Confirmación, una sola vez** (`calibrate_kick.py --confirm`): la elegida contra `main`, con el modelo de posesión
  entrenado en los 7 partidos de selección, sobre la reserva con un bloque de semillas nuevo (Metrica Game 1 con
  60-69, IDSSE 6-7 con 60-64; el ADR-010 usó el 20, el ADR-014 el 20, el 30 y el 40, y el #77 el 50). Son las 43
  condiciones del ADR-010:
  - las del ADR-011 en los dos bancos: el intervalo por defecto arriba de 0 (en Metrica, con las dos verdades) y la
    diferencia positiva en los seis escenarios;
  - la pelota de las paradas dentro de la cancha;
  - los 10 escenarios de `NOISE`.

  Confirma solo si se cumplen todas. Si no, `stops_model.json` queda en la identidad y no se vuelve a elegir con ese
  resultado.
- **Entrega:** si confirma, `calibrate_kick.py --final` escribe `stops_model.json` con la receta. No hay nada que
  entrenar, y `live_model.json` no cambia (`c0a12df6…`).
  - El CSV cambia: una persona corre BAR-ATH en dos máquinas y pega los conteos, el `sha256` y el validador. La
    ventana pública es solo para verificar.
  - El test que vigila `stops_model.json` pasa a fijar la regla.

## Cómo se mide

- **Métrica:** `spellF1` con las piezas del scorer oficial, en diferencia pareada contra `main`, con `bench.compare`
  y 1000 remuestreos de posesiones y semillas.
- **Decide:** la regla del ADR-011, con las condiciones de arriba.
- **Se reporta además, sin decidir:**
  - los fines a 0.5 s o menos, por tipo de reanudación, del v2 y de la regla;
  - el acierto por frame con juego vivo y las posesiones predichas;
  - los árboles exportados del modelo de posesión contra `decision_function`.
- **Registro:** cada corrida, con su fila en `docs/EXPERIMENTOS.md`.

## Resultados (31/10)

**La base es el modelo de posesión del #77**, con las posesiones de menos de 5 s contando 3 veces al entrenar. Entró
a `main` el 31/10 a las 15:54, antes de la confirmación, y es el que se entrega. La selección corrió encima de su
código en una rama local, y la confirmación, también: el código del pipeline de esa rama y el de `main` son
idénticos.

### Selección

`calibrate_kick.py --select`, en 1498 s. Diferencia pareada contra `main`, LOMO:

| Receta | Metrica | IDSSE | Media |
|---|---|---|---|
| **Quieta 1.5 s, de −3 s a +8 s** | **+0.0088 [+0.0043, +0.0133]** | **+0.0072 [+0.0052, +0.0094]** | **+0.0080** |
| Quieta 1.5 s, de −3 s a +5 s | +0.0089 [+0.0046, +0.0133] | +0.0066 [+0.0047, +0.0086] | +0.0077 |
| Quieta 1.5 s, de −3 s a +3 s | +0.0084 | +0.0062 | +0.0073 |
| Quieta 1 s, de −3 s a +3 s | +0.0085 | +0.0060 | +0.0072 |
| Quieta 1.5 s, de −2 s a +8 s | +0.0074 | +0.0069 | +0.0071 |
| Quieta 0.5 s, de −2 s a +8 s (la última) | −0.0002 | +0.0025 | +0.0011 |

- **Gana quieta 1.5 s, de 3 s antes a 8 s después** (`kick_choice.json`), en los 12 partidos y mitades (de +0.002 a
  +0.015).
- **La elección no es frágil:** 16 de las 18 recetas ganan en los dos bancos. La elegida está en el borde de la
  grilla, pero las primeras se separan por menos de 0.001, y no se vuelve a elegir.
- **Fines a 0.5 s o menos** (primera semilla): tiros libres de 22% a 49% en IDSSE y de 24% a 46% en Metrica; saques
  de arco de Metrica de 15% a 41%; córners de Metrica de 47% a 73%. Ningún tipo empeora.

### Confirmación: 43 de 43

`calibrate_kick.py --confirm`, en 1518 s: la elegida, con el modelo de posesión entrenado en los 7 partidos de
selección, sobre la reserva (Metrica Game 1 con semillas 60-69, IDSSE 6-7 con semillas 60-64). Diferencia pareada
contra `main`:

| Condición | Metrica (inicio / final) | IDSSE |
|---|---|---|
| **Por defecto** (decide el intervalo) | **+0.0093 [+0.0041, +0.0151] / +0.0093 [+0.0041, +0.0151]** | **+0.0094 [+0.0057, +0.0137]**, 4 de 4 mitades |
| `--missing 0` | +0.0182 / +0.0180 | +0.0160 |
| `--missing 0.2` | +0.0132 / +0.0130 | +0.0126 |
| `--gap 3` | +0.0090 / +0.0089 | +0.0102 |
| `--crowd 2` | +0.0090 / +0.0089 | +0.0109 |
| `--dead-missing 0.34` | +0.0039 / +0.0039 | +0.0037 |
| `--missing 0 --dead-missing 0.34` | +0.0068 / +0.0067 | +0.0041, 3 de 4 mitades |
| La pelota de las paradas dentro de la cancha | +0.0087 / +0.0087 | |
| Los 10 escenarios de `NOISE` | de +0.0065 a +0.0095 | de +0.0082 a +0.0108 |

- **Confirma con las 43 condiciones.** El borde más bajo de los intervalos que deciden es +0.0041.
- **Gana más cuanto más pelota se ve en el juego vivo** (+0.018 y +0.016 sin pelota faltante) y menos cuando falta en
  las paradas (+0.004 con `--dead-missing 0.34`): la regla necesita ver la pelota quieta y la patada. En la ventana
  pública falta en el 6.5% del juego vivo y en el 34% de las paradas.
- **Fines a 0.5 s o menos en la reserva** (primera semilla): tiros libres de 14% a 51% en IDSSE y de 28% a 44% en
  Metrica; saques de arco de 50% a 69% en IDSSE y de 15% a 40% en Metrica; córners de Metrica de 9% a 36%.
- **El acierto con juego vivo y las posesiones predichas no cambian** (0.929 y 0.911; 347 de 353 y 185 de 193): la
  regla solo mueve fines.
- **Los árboles exportados contra `decision_function`:** 0 frames distintos.

### La entrega y BAR-ATH: no actúa

- `calibrate_kick.py --final` escribió `stops_model.json` con la regla
  (`{"mode":"kick","before":75,"after":200,"kick_cms":400,"rest":37,"rest_cms":200}`, `sha256` `c9a10c49…`). Con
  ella, el CSV sintético de la CI pasaba de `df8eac60…` a `d16c2a26…`.
- **En BAR-ATH no mueve ninguna parada.** Iván corrió `possession.py` en `80131ca`, la cabeza del PR #80, y obtuvo H
  53405, A 37381, D 68071, X 40462, `sha256` `f2460d57…`: el mismo archivo que sin la regla (#77). Lo repitió
  desde cero, confirmó que el pipeline leía el modo `kick` y, con la identidad, el `sha256` es el mismo.
- **La sospecha** (Iván, sin mirar datos): en el ATD, la pelota de las paradas falta o tiembla, y la condición de
  pelota quieta (37 pasos seguidos bajo 2 m/s) no se cumple nunca. En los bancos, la pelota quieta es lisa: en
  sample-data la restaurada es una interpolación, y en IDSSE el proveedor la suaviza. El banco simula los huecos de
  la pelota, pero no ese temblor.
- **No se mide ni se elige otra receta.** Contar patadas por parada en BAR-ATH sería una estadística por señal sobre
  el partido (`AGENTS.md`, punto 3). Elegir otra receta porque esta no actúa sería elegir con el partido.
- **Decisión:** `Rejected`. `stops_model.json` vuelve a la identidad, vuelve el test que la fija, y la entrega sigue
  siendo `f2460d57…`. El código (`kick_onsets`, `snap_ends`, el modo `kick` y `calibrate_kick.py`) queda en el repo
  sin efecto, como el del ADR-010.
- **Lo aprendido:** una condición sobre la pelota que el banco no degrada, como el temblor, puede no darse en el ATD.
  Un candidato que dependa de la pelota quieta necesita antes un banco que la haga temblar, en un rango elegido sin
  mirar BAR-ATH.

## Consequences

Escritas antes de la corrida sobre BAR-ATH, donde la regla no actúa (ver "La entrega y BAR-ATH").

### Positive

- **Física, sin entrenar:** lo mismo en los dos bancos y en el ATD, y cinco enteros en un archivo. Es fácil de
  explicar en el documento técnico.
- **Arregla el tipo de parada que peor estaba,** el tiro libre, sin romper los bordes que el v2 ya tenía bien.
- Sigue siendo exacta en cualquier CPU.

### Negative

- **La ganancia es chica frente al techo:** +0.007 y +0.008 contra +0.071 y +0.052 de los dos bordes perfectos.
  Mueve solo el fin, y solo cuando se ve la patada.
- **El banco ve menos patadas que el ATD:** en el banco falta la pelota en el 45% del juego vivo, y en la ventana
  pública, en el 6.5%. La regla debería ver más patadas en el ATD, pero eso no se puede medir.
- **El modelo de posesión se entrenó con las paradas del v2 y se usa con las nuevas.** Es una diferencia entre el
  entrenamiento y la inferencia, medida: reentrenarlo con las paradas nuevas perdía la ganancia de Metrica.
- **La reserva se reusa**, con otro bloque de semillas, como prevé el ADR-011.

### Neutral

- `dead_mask_v2` no cambia: la regla solo mueve los fines de sus paradas.
- `refine` suma el modo `kick`. `calibrate_edges.py` queda como estaba, con sus corridas del ADR-010.

## Alternatives Considered

### El modelo de bordes del ADR-010, con sus arreglos

Medido en el paso 0: gana en IDSSE y pierde en Metrica con cualquiera de los arreglos.

### La patada sin la pelota quieta

Medido en el paso 0: sin la condición, toma el pase siguiente cuando la patada no se ve, y pierde en IDSSE.

### Reentrenar el modelo de posesión con las paradas nuevas

Medido en el paso 0: pierde la ganancia de Metrica.

### El inicio de las paradas

El inicio del tiro libre es la infracción (Metrica) o el silbato (DFL, unos 0.5 s después), y ninguno se ve en el
tracking. Las constantes por tipo (el plan B del ADR-010) no ganaron.

### Un decodificador de tres estados (H, A y `D`)

Juntaría las paradas y la posesión en un solo Viterbi, y podría tocar también las paradas que faltan y las que
sobran. Es un cambio más grande: el #35 lo dejó para un issue nuevo.

### El equipo que reanuda (#34)

Su oráculo, encima del modelo de posesión, da −0.003 y −0.002.

## References

- `explore/oracles_live.py`, `explore/edges_on_live.py`, `explore/kick_snap.py` y `explore/edge_clock.py`, con sus
  filas en `docs/EXPERIMENTOS.md`.
- ADR-006 y ADR-011 (bancos y regla de decisión), ADR-010 (`refine`, `stops_model.json` y las 43 condiciones), ADR-014
  (el modelo de posesión).
- Issues #32, #34 y #35.
