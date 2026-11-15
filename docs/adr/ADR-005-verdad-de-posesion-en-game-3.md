---
artifact: adr
version: "1.0"
created: 2026-10-28
status: accepted
---

# ADR-005: Verdad de posesión de los partidos abiertos desde el último evento con pelota

## Status

Accepted (2026-10-29), revisado por Matías y Pepi en el PR #20 y con el OK de Matías por chat, registrado en el comentario del PR #50.

**Date:** 2026-10-28
**Deciders:** Ivan Ledesma (propone). Revisión pedida a Emanuel.

## Context

El ADR-001 deja a N (frames seguidos con el rival como dueño más probable) como único parámetro y
manda calibrarlo en `metrica-sports/sample-data`, nunca en la ventana pública. Calibrar N necesita
una verdad de posesión H/A para Metrica Game 3, y esa verdad **no existe** en los datos: hay que
derivarla de los eventos.

Es una decisión de diseño (cómo se arman las etiquetas, `AGENTS.md`) con un riesgo claro:
`owner_evidence` ya usa "el equipo del jugador más cercano a la pelota". Si la verdad usara posiciones
o un criterio de confirmación en tiempo, estaríamos midiendo la regla contra sí misma.

## Decision

La posesión es del equipo del **último evento con pelota** hasta que aparece un evento con pelota del
equipo rival. Sin parámetros propios.

- **Eventos con pelota:** `PASS`, `CARRY`, `SHOT`, `RECOVERY`, `SET PIECE`. Confirmado contra Game 3
  (conteo de tipos del 2026-10-28): `CARRY` 1395, `PASS` 1121, `CHALLENGE` 335, `RECOVERY` 294,
  `BALL LOST` 288, `SET PIECE` 90, `BALL OUT` 64, `SHOT` 20, `FAULT RECEIVED` 12, `CARD` 1. No hay otros
  tipos. Cada evento trae el campo `team`.
- **Alcance:** Metrica Sample Games 1, 2 y 3. Games 1 y 2 vienen en CSV y no tienen ningún `CARRY`, así
  que en ellos la posesión cambia solo con `PASS`, `SHOT`, `RECOVERY` y `SET PIECE`. La lista no tiene
  otros tipos con pelota en ninguno de los tres.
- **No cambian la posesión:** `BALL OUT`, `BALL LOST`, `FAULT RECEIVED` y `CHALLENGE` (un duelo no dice
  quién queda con la pelota; lo dice el evento siguiente).
- **Pelota muerta:** los tramos `D` del ADR-003 (aceptado) cortan la verdad. Si otro ADR cambia las
  etiquetas de pelota muerta, lo dice ese ADR; cada fila de `docs/EXPERIMENTOS.md` anota el commit. Después de cada reanudación, la posesión arranca con el equipo del evento que reanuda.

El equipo de cada slot de tracking no es parte de la verdad: es evidencia del predictor.

## Cómo se mide

Este ADR define la verdad; no elige N. N se elige en el banco del ADR-006 contra esta verdad: diferencia
pareada de spellF1 con bootstrap, pelota degradada y confirmación en un partido reservado con semillas
nuevas. Con la pelota limpia, un solo partido y sin bootstrap no se distinguen N cercanos (0.569 con
2 s contra 0.556 con 1.5 s en Game 3 están dentro del ruido).

- **Métrica:** spellF1 (`possession_metrics.evaluate` del reto), la que usa el banco.
- **Datos:** Metrica Sample Games 1, 2 y 3 (abiertos). Nunca la ventana pública de BAR-ATH.
- **Anclaje:** el cambio va al inicio del evento con pelota (verdad principal); al final, como variante
  (`--truth start,end` en `bench.py`).
- **Chequeo de sensibilidad:** repetir en el banco la elección de N con la variante B de la verdad: el
  cambio exige 2 eventos seguidos del rival **en frames distintos**, y la cuenta se reinicia después de
  cada parada. Si el N elegido es parecido, el resultado es robusto; si cambia mucho, el N depende de
  cómo se define la verdad y se dice así en el documento técnico.
- Cada corrida va como fila nueva en `docs/EXPERIMENTOS.md`.

## Consequences

### Positive

- La verdad sale de eventos, no de posiciones ni de tiempos: no mide `owner_evidence` contra sí misma.
- Cero parámetros propios; se explica en una línea en el documento técnico.
- Se puede refinar sin tocar el pipeline de entrega.

### Negative

- Un rebote o un duelo aéreo cuenta como cambio de posesión. Empuja a elegir un N más bajo, que en un
  partido real dejaría pasar cambios falsos. Se mitiga con el chequeo de sensibilidad.
- La lista de eventos con pelota depende del proveedor y hay que confirmarla.
- La verdad tiene ruido propio, así que un spellF1 alto sobre Game 3 no garantiza el mismo valor en BAR-ATH.

### Neutral

- No cambia `possession.py` ni N. La verdad vive en `truth_labels` de `bench.py` (ADR-006).

## Alternatives Considered

### Variante B: 2 eventos seguidos del rival

Se parece más a "control" (`CHALLENGE.md`), pero mete un segundo criterio de confirmación en la
verdad: un N implícito. Calibrar N contra eso sería circular. Queda solo como chequeo de sensibilidad.

Contada en cualquier frame, B no sirve como chequeo en Game 3. 348 de los 363 cambios de equipo entre
eventos con pelota ya traen un segundo evento del nuevo equipo en el mismo frame (casi siempre
`RECOVERY` + `CARRY`), así que B coincide con A por cómo se anotan los eventos y no por robustez. En
Games 1 y 2, sin `CARRY`, eso pasa solo en el 33% y el 40% de los cambios (conteos de la revisión del
PR #20; con las reanudaciones del ADR-003 dentro de la lista dan 351, 34% y 41%). Por eso B exige
frames distintos.

**Desde qué evento cuenta la posesión en B.** Desde el primero de los dos eventos del rival, igual que en A. El
segundo solo confirma que el cambio existe; no mueve su fecha. Así, cuando A y B coinciden en que hubo un
cambio, la posesión dura lo mismo en las dos, y la única diferencia es que B puede descartar tramos cortos que A
cuenta.

**Ejemplo: intercepción con pase de primera** (tiempos ilustrativos, no salen de un partido). El local tiene la
pelota y el visitante la intercepta:

| Secuencia de eventos | Verdad A | Verdad B |
|---|---|---|
| `RECOVERY` del visitante en t = 0, y `PASS` del visitante a los 0.3 s | cambia a visitante en t = 0 | cambia a visitante en t = 0, confirmado a los 0.3 s |
| `RECOVERY` del visitante en t = 0 y el local lo recupera a los 0.2 s, sin otro evento del visitante | visitante durante 0.2 s | no hay cambio: el local sigue |
| `RECOVERY` y `CARRY` del visitante en el mismo frame, y el local lo recupera a los 0.2 s | visitante durante 0.2 s | no hay cambio: el `CARRY` del mismo frame no cuenta como segundo evento |

Qué esperamos: en el primer caso las dos verdades dan la misma posesión, y el tramo es de control aunque dure
poco. En el segundo, A registra una posesión de 0.2 s que la definición oficial puede no contar (un toque sin
control o un desvío), y B la descarta; ahí está la diferencia entre A y B. El tercero muestra por qué B exige
frames distintos: si el `CARRY` del mismo frame contara, B confirmaría ese cambio y volvería a coincidir con A
por cómo se anotan los eventos, no por robustez.

### Verdad desde posiciones (jugador más cercano)

Es exactamente `owner_evidence`. Medir la regla contra su propia evidencia no valida nada.

### Anotar a mano un fragmento de Game 3

Más fiel, pero no escala ni se reproduce, y el plazo (entrega 17/11/2026) no lo permite.
