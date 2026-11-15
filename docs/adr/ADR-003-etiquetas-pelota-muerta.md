---
artifact: adr
version: "1.0"
created: 2026-10-27
status: accepted
---

# ADR-003: Etiquetas de pelota muerta en sample-data, del evento anterior a la reanudación

## Status

Accepted (2026-10-28), revisado por Ivan Ledesma en el PR #25. Formaliza la regla B que `calibrate_dead.py` usa desde el PR #14 y le agrega tres precisiones
medidas en los eventos del Game 3. Cubre el caso del ADR-004 (PR #19) con otro mecanismo; la
comparación está en Alternatives Considered. El ADR-004 (PR #19) quedó
cerrado a favor de este.

**Date:** 2026-10-27
**Deciders:** Ivan Ledesma (regla B, PR #14), Lautaro Bursese (precisiones)

## Context

El detector de pelota muerta (ADR-002) se calibra en partidos de `metrica-sports/sample-data`, nunca
en la ventana pública. Para calibrar hacen falta etiquetas `D` por frame, y el tracking del Sample
Game 3 no trae el estado de la pelota: hay que derivarlas de los eventos. El ground truth oficial, en
cambio, sale de un campo del tracking corregido (ADR-002). Las etiquetas son una aproximación a esa
definición, y esta regla decide qué cuenta como pelota muerta al calibrar.

El Game 3 tiene 3,620 eventos en dos tiempos y 101 reanudaciones: 90 `SET PIECE` (50 laterales, 28
tiros libres, 8 córners y 4 saques del medio) y 11 saques de arco. Metrica anota el saque de arco como
`PASS | GOAL KICK`, o como `BALL LOST | GOAL KICK` cuando pierde la pelota (3 de los 11).

El issue #4 pedía elegir entre dos reglas:

- **A: parada explícita → reanudación.** `D` desde un evento que para el juego (pelota afuera,
  falta, offside) hasta la reanudación.
- **B: evento anterior → reanudación.** Toda reanudación implica que antes la pelota estuvo muerta:
  `D` desde el `end` del evento anterior del mismo período hasta el `start` de la reanudación.

El PR #14 implementó la B con un tope de 60 s. Con esas etiquetas el detector da F1 por frame 0.867
(P 0.765, R 0.999), y el diagnóstico del 27/10 dejó una pregunta abierta: 15 tramos aislados reúnen el
76.7% de los frames FP, y el tope no explica ninguno (`docs/CALIBRACION-PELOTA-MUERTA.md`).

Al medir la B del PR #14 sobre los eventos del Game 3 aparecen tres huecos:

1. **Los 11 saques de arco quedan sin `D`.** En los 8 anotados como `PASS`, Metrica pone un
   `RECOVERY` del arquero en el mismo frame del saque. Por el orden de los eventos cuenta como
   "anterior", y el tramo dura 0 s. Los 3 anotados como `BALL LOST` no figuran como reanudación.
2. **La tarjeta corre el inicio.** Se muestra con la pelota ya muerta, pero cuenta como evento
   anterior. En el único caso del Game 3, el tramo pierde los 14.0 s que van de la falta a la tarjeta.
3. **El tope descarta paradas reales.** Con los saques de arco corregidos, los dos más largos (60.5 y
   89.1 s) superan los 60 s, y los dos empiezan con la pelota afuera.

Esos tramos explican la mayor parte de los falsos positivos del diagnóstico. Medido frame a frame
(Measurement, punto 2), 7,900 de sus 10,862 frames FP (72.7%) quedan dentro de `D` con las etiquetas
de este ADR, y de los 10 FP más largos, 9 quedan cubiertos entre el 94% y el 100%. El décimo (66.6 s)
es un saque de arco que no está anotado como tal (ver Consequences). El PR #18 llegó al mismo síntoma
por otro camino, con los tipos de evento en los bordes de los 3 FP más largos, y el ADR-004 (PR #19)
propone arrancar el `D` en la última salida de la pelota.

## Decision

Las etiquetas `D` de los partidos de calibración salen de la **regla B**, con cuatro definiciones
precisas (`restart_gaps`, `stops_play` y `dead_labels` en `calibrate_dead.py`):

1. **Reanudación:** un `SET PIECE` o cualquier evento con subtipo `GOAL KICK`.
2. **Evento anterior:** el de mayor `end` entre los eventos del período que **empiezan antes** de la
   reanudación, sin contar las `CARD`.
3. **`D`:** desde el `end` del evento anterior hasta el `start` de la reanudación. Sin reanudación no
   hay `D`, así que la ley de ventaja se resuelve sola.
4. **Tope:** un tramo de más de 60 s (`MAX_DEAD_S`) se descarta, salvo que el evento anterior pare el
   juego por sí mismo: pelota afuera, remate afuera o gol, falta, offside o mano. El tope cubre los
   eventos que faltan durante el juego; después de una salida de la pelota, un tramo largo es una
   parada real. La lista solo levanta el tope: si le falta un caso, el tope sigue valiendo.

Fuera de esta decisión: el detector (ADR-002) y las etiquetas de otros proveedores. IDSSE, por
ejemplo, necesita su propia lista de reanudaciones.

## Measurement

Tres mediciones, de la más directa a la más independiente.

**1. Qué etiqueta la regla.** Solo eventos del Game 3, hecha para este ADR:

| | B del PR #14 | Este ADR |
|---|---|---|
| Reanudaciones reconocidas | 98 | 101 |
| Con `D` | 88 | 99 |
| Sin `D` (tramo de 0 s) | 8 | 0 |
| Descartadas por el tope | 0 | 0 |
| Frames `D` en los dos tiempos | 35,443 (24.8%) | 43,344 (30.4%) |

Los dos saques del medio que abren cada tiempo no tienen evento anterior. Los 7,901 frames nuevos
(316 s) son los 11 saques de arco (302 s) y la tarjeta (14 s).

**2. Acuerdo del detector con las etiquetas.** `python calibrate_dead.py` sobre el Game 3, con las
métricas que ya usa: P/R/F1 por frame de `D`, tramos emparejados con IoU ≥ 0.5, desfasaje mediano de
los bordes y reporte de FP por ubicación. Con la candidata `window 1, min 2, thr 0.5` (la corrida con
las etiquetas del PR #14 reproduce lo documentado):

| | Etiquetas del PR #14 | Este ADR |
|---|---|---|
| P / R / F1 por frame | 0.765 / 0.999 / 0.867 | 0.936 / 1.000 / 0.967 |
| Tramos reales / predichos (emparejados) | 88 / 103 (0.99) | 99 / 103 (0.99) |
| Frames FP | 10,862 en 139 tramos | 2,962 en 141 tramos |
| FP aislados | 8,329 frames en 15 tramos | 1,805 frames en 5 tramos |

De los 7,901 frames que agrega este ADR, el detector ya marcaba como `D` todos menos uno. De los FP que
quedan, 1,664 frames son el saque de arco sin anotar, y el resto son tramos de menos de 4 s, casi todos
pegados al borde de un `D` (#9). Las 10 mejores combinaciones del barrido dan F1 entre 0.962 y 0.967,
y las tres mejores son de nuevo con ventana de 1 s. No es una validación: las etiquetas y el detector
se miran entre sí, y un acuerdo alto no dice que alguno de los dos se parezca al ground truth oficial.

**3. Contra una referencia independiente (pendiente).** El tracking de IDSSE trae el estado de la
pelota por frame (`BallStatus`, que kloppy lee como viva o muerta), la misma clase de definición que el
ground truth oficial. Derivar `D` con esta regla desde los eventos de IDSSE y compararla con ese estado
mide la regla misma: P/R/F1 por frame y desfasaje mediano de los bordes de inicio y de fin. Es la
medición que decide si el borde de inicio, el punto débil de la B, es el cuello de botella. Si lo es,
se evalúa la regla A para ese borde en un ADR nuevo.

## Consequences

### Positive

- Explica la mayor parte de los falsos positivos del diagnóstico del 27/10: 6,358 de los 8,329 frames
  FP aislados (76.3%) caen en paradas que las etiquetas del PR #14 no marcaban.
- Los 11 saques de arco tienen `D` (antes, ninguno), y el tope deja de descartar las dos paradas más
  largas del partido.
- Conserva lo que la B hace mejor que la A, medido en el Game 3. Cuando una falta o un offside se
  cobran después de una jugada, la A marcaría como `D` entre 0.1 y 3.7 s de juego (5 casos). Y en 3
  reanudaciones sin parada anotada, todas después de un `BALL LOST | FORCED`, la A no tiene de dónde
  arrancar.
- Las tres precisiones tienen pruebas sintéticas (`test_calibrate_dead_labels.py`) que fallan con el
  código anterior.

### Negative

- Dos listas cortas dependen de la taxonomía de Metrica: qué es una reanudación y qué para el juego
  (esta última, solo para el tope). Otro proveedor necesita su propio mapeo.
- El borde de inicio sigue siendo aproximado cuando hay eventos con la pelota muerta que no son una
  tarjeta ni el `RECOVERY` del saque de arco: la regla arranca más tarde que la parada real.
- Un saque de arco sin anotar como tal sigue como pelota viva. En el Game 3 hay uno: 66.6 s después de
  un remate afuera, que terminan en un `RECOVERY` y un `BALL LOST | FORCED`. Ninguna regla basada en
  estas etiquetas lo ve.
- Siguen siendo una aproximación: el ground truth oficial sale del tracking, no de los eventos.
- Las tres precisiones salieron de mirar dónde discrepaba el detector (observación de la revisión, PR
  #25). Las etiquetas quedan más fieles a los eventos, pero el F1 de 0.967 no prueba que el detector
  sea mejor. Lo que mide la regla sin pasar por el detector es el chequeo de pases dentro de `D` y,
  pendiente, la referencia independiente (Measurement, punto 3).

### Neutral

- `D` pasa del 24.8% al 30.4% de los frames del Game 3, y el F1 por frame de la candidata, de 0.867 a
  0.967. Elegir los parámetros del detector sigue en el #5, con la estabilidad verificada.

## Alternatives Considered

### Regla A: parada explícita → reanudación

Contra la B del PR #14, en las 96 reanudaciones con evento anterior: arranca igual en 79, antes en 14
(mediana 6.5 s) y no tiene parada de la cual arrancar en 3. De esos 14, 8 son los saques de arco que
la B dejaba en 0 s (ahí acierta la A); en 5 de los otros 6, la falta o el offside se cobraron después
de una jugada, y la A marca como `D` juego que siguió. Contra la regla de este ADR, en 99
reanudaciones: arranca igual en 89, antes en 6 (mediana 1.6 s, máximo 3.7 s), después en 1 (la
tarjeta) y sin parada en 3. Depende de una lista de paradas por proveedor y pierde el `D` cuando falta
la parada. Se descarta como regla base; su punto fuerte, arrancar en una parada explícita, entra solo
para levantar el tope.

### Arrancar en la última salida de la pelota (ADR-004, PR #19 y #23)

`D` desde el `end` de la última `BALL OUT` o `SHOT` con `OUT` o `GOAL` posterior a la reanudación
anterior; si no hay, la regla B. Mismas reanudaciones; el tope no corre para los tramos que arrancan en
una de esas paradas. Medida con la implementación del PR #23 (reproduce lo que informa el #19), el
mismo detector y la misma candidata:

| Etiquetas | `D` | P | R | F1 | Frames FN | Pases o conducciones dentro de `D` |
|---|---|---|---|---|---|---|
| B del PR #14 | 24.8% | 0.765 | 0.999 | 0.867 | 18 | 0 |
| ADR-004 (#23) | 31.1% | 0.924 | 0.965 | 0.944 | 1,562 | 48, en 2 tramos |
| Este ADR | 30.4% | 0.936 | 1.000 | 0.967 | 19 | 0 |

La baja de recall del ADR-004 no es pelota muerta que el detector no ve: 1,546 de sus 1,562 frames FN
están en dos tramos con juego adentro. Cuando falta una reanudación anotada, "la última parada" cruza
juego vivo. Uno es de 81.1 s, desde una `BALL OUT` hasta un tiro libre, con 21 pases y 26
conducciones, y el detector marca `D` solo en el 33%. El otro es de 96.9 s, desde un remate afuera:
incluye el saque de arco sin anotar (66.6 s de pelota muerta, que este ADR no ve) y el juego que sigue
hasta el tiro libre. Este ADR toma el evento inmediatamente anterior a cada reanudación, así que, por
construcción, un `D` nunca contiene pases ni conducciones. Cubre además los saques de arco anotados
como `BALL LOST` y la tarjeta, que el ADR-004 deja para un ADR posterior. Descartada.

### La B del PR #14, sin cambios

Deja sin `D` los 11 saques de arco (302 s) y corre el inicio después de una tarjeta. Descartada por
esos huecos.

### Estado de la pelota de IDSSE como etiquetas, en lugar de los eventos

Es la referencia más parecida a la definición oficial, pero es otro proveedor y otro tracking: antes
hay que medir si la señal principal del detector (pelota sin datos) se comporta igual. Por ahora sirve
para medir la regla (Measurement, punto 3), no para reemplazar al Game 3.

### Marcar como `D` todo tramo sin eventos de más de T segundos

Cubriría el saque de arco sin anotar, pero suma un parámetro sin referencia para calibrarlo y marcaría
como `D` los huecos de anotación con la pelota viva. Descartada.

## References

- `calibrate_dead.py`: `restart_gaps`, `stops_play`, `dead_labels`; pruebas en
  `test_calibrate_dead_labels.py`
- `docs/CALIBRACION-PELOTA-MUERTA.md`: tabla A/B, resultados con las etiquetas del PR #14 y diagnóstico
  de FP
- `docs/EXPERIMENTOS.md`: corridas del 27/10
- ADR-002: detector de pelota muerta (paso 4, calibración en `sample-data`)
- `metrica-sports/sample-data`: eventos del Sample Game 3 (datos abiertos; citar en el documento
  técnico)
- IDSSE: Bassek y otros, *Scientific Data* 12, 195 (2025); kloppy, `sportec.load_open_tracking_data`
  (`BallStatus` → `BallState.ALIVE` o `BallState.DEAD`)
- Issue #4
