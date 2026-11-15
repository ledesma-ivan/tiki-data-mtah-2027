---
artifact: adr
version: "1.0"
created: 2026-10-26
status: superseded
---

# ADR-002: Detector de pelota muerta como prioridad 1, con reglas sobre varias señales

## Status

Superseded by ADR-007 (2026-10-29) en lo que hace al **diseño** del detector. La **prioridad** sigue
aceptada (2026-10-26): la pelota muerta es la palanca más grande.

**Date:** 2026-10-26
**Deciders:** Ivan Ledesma

## Context

`spellF1` cuenta posesiones, no frames, y una posesión es una racha máxima de `H` o de `A` con la
pelota viva. Un tramo `D` la corta: `H H D D H H` son dos posesiones. Si no ves un `D`, las dos
posesiones reales se fusionan en una larga. Lo mismo pasa con un cambio de equipo no detectado, y
el costo por error es parecido: en un ejemplo de 10 s + 5 s + 10 s, el `D` no visto deja un spellF1
de ~0.27 y el cambio no visto, ~0.40. El `D` cuesta algo más porque la pelota muerta suma tiempo al
IoU.

Lo que hace al `D` prioritario es otra cosa:

- **Cuando reanuda el mismo equipo** (`H D H`), la evidencia de equipo dice lo mismo de los dos
  lados. No hay cambio que detectar, así que ninguna regla de cambio (ADR-001) puede separar esas
  posesiones: solo el `D` lo hace.
- **Frecuencia:** el baseline acierta el equipo el 88.5% de las veces con la pelota viva, pero
  detecta muy pocos frames muertos.

Hoy el detector es la parte más floja. En la ventana pública el baseline tiene un recall de `D` de
0.08 a 0.34: `smooth125` marca como `H` casi todos los frames muertos. El ground truth se
construye de forma mecánica, a partir del tracking corregido: `D` donde ese tracking marca la pelota
muerta. El tracking que recibimos no trae ese campo, así que hay que inferirlo.

Lo que se vio en la ventana pública (`explore/dead_ball.py`) solo describe y no se usó para calibrar
nada. En esta copia pública se omiten las estadísticas por señal calculadas sobre el partido (la
tabla de P(señal | muerta) y P(señal | viva), la cantidad y la duración de los tramos muertos y los
conteos del Smart Tagging), por la regla de los organizadores de no divulgar datos del partido. Se
conservan en el repo privado. La conclusión que sí se usó: ninguna señal sola alcanza para detectar
la pelota muerta, así que el detector combina varias.

## Decision

Vamos a poner el esfuerzo principal en detectar la pelota muerta, antes de pulir la regla de cambio
(ADR-001).

Primera versión, basada en reglas:

1. **Score por frame.** Combina las señales independientes: pelota sin datos, pelota fuera de la
   cancha, jugadores lentos y frames dentro de una ventana de `SET PIECES`.
2. **Suavizado y duración mínima.** Un tramo es `D` solo si el score se mantiene alto durante un
   mínimo de segundos. Así se descartan los huecos cortos de tracking con la pelota viva.
3. **Ubicar los bordes.** La reanudación se ubica en el primer movimiento rápido de la pelota (o en
   la suba de velocidad de los jugadores) después del tramo. Es el borde que más pesa en el IoU.
4. Los umbrales y la duración mínima se calibran en partidos de `metrica-sports/sample-data`, nunca
   en la ventana pública.

Fuera de esta decisión: qué equipo reanuda (el reto no lo pide: con la pelota muerta la respuesta es
`D`) y detectar la pelota en el video.

## Consequences

### Positive

- Ataca la palanca más grande del spellF1: separa las posesiones que ninguna regla de cambio puede
  separar (`H D H` del mismo equipo).
- Las reglas se explican en el documento técnico, y las señales tienen sentido futbolístico.
- La salida (tramos `D`) es la entrada que ADR-001 necesita para cortar la secuencia.

### Negative

- Pausas que no detienen el juego (un equipo que hace circular la pelota lento, o un hueco largo de
  tracking) pueden quedar marcadas como `D` y partir posesiones reales.
- Los `SET PIECES` tienen margen en sus ventanas, así que no sirven para ubicar el borde exacto.
- Varios umbrales para calibrar; dependemos de que `sample-data` se parezca lo suficiente a este
  tracking.

### Neutral

- Si las reglas se quedan cortas, el mismo conjunto de señales se convierte en las features de un
  clasificador entrenado en `sample-data`, o en la evidencia de Viterbi (en un ADR posterior).

## Alternatives Considered

### Una sola señal (pelota sin datos)

Es lo que hace en la práctica el baseline. Cubre un tercio de los frames muertos y además dispara
con la pelota viva cuando el tracking la pierde. Descartado: es el error que tenemos que corregir.

### Clasificador entrenado desde el arranque

Puede combinar las señales mejor que las reglas, pero requiere armar etiquetas en `sample-data` y
cuesta más explicarlo. Queda como el paso siguiente si las reglas no alcanzan.

### Detectar la pelota en el video

Cubriría los huecos de la pelota en la raíz, pero exige procesar 5 GB de video. Mucho esfuerzo para
la etapa en que estamos. Descartado por ahora.

## References

- ADR-001: regla de cambio de posesión (consume los tramos `D`)
- `explore/dead_ball.py`: análisis descriptivo de las señales
- `metrica-sports/more-than-a-hack-2027`: `CHALLENGE.md` (definición de `D`), `EVALUATION.md`
  (spellF1)
