---
artifact: adr
version: "1.0"
created: 2026-10-26
status: superseded
---

# ADR-001: Regla de cambio de posesión por retención temporal

## Status

Superseded by ADR-009 (2026-10-29) en lo que hace a la **evidencia de dueño** y a la regla de racha (radio de
control, interpolación acotada, N y `max_gap` elegidos juntos). El principio sigue: el cambio se confirma con
retención temporal y se fecha en el primer frame de la racha. Es la cuarta palanca en impacto: la prioridad 1 es
el detector de pelota muerta (ADR-007).

**Date:** 2026-10-26
**Deciders:** Ivan Ledesma

## Context

El reto (More than a Hack 2027, Fase 1) pide etiquetar cada frame del video tactical de BAR-ATH
como `H`, `A`, `D` o `X`. El ranking usa `spellF1`: cada posesión se evalúa como un objeto entero,
emparejado por IoU temporal. Cada cambio falso parte una posesión y suma un falso positivo, y un
cambio detectado tarde también cuesta: 1 s de retraso baja el spellF1 de 1.0 a 0.65.

`CHALLENGE.md` dice que una posesión cambia cuando el rival logra un control **controlado** de la
pelota, y deja el criterio abierto. Sugiere dos aproximaciones: "la retiene unos segundos" o
"completa más de dos pases seguidos".

Fuerzas en juego:

- **La pelota falta en el 43% de los frames del partido** (41% de los evaluados). El tracking solo
  trae x, y y velocidad de 46 slots, cada uno con equipo fijo, más la pelota. No hay campo de dueño
  ni de pelota viva.
- **Procesamos el partido completo, no en vivo.** Un cambio se puede confirmar mirando hacia
  adelante y fecharse hacia atrás.
- **No se puede calibrar contra la ventana pública** (5 min, 17 posesiones; ver `RULES.md`). Cada
  parámetro se calibra en otros partidos (`metrica-sports/sample-data`), así que cuantos menos
  parámetros, mejor.
- Hay 22 días hasta la entrega (17/11/2026), y el documento técnico tiene que justificar las reglas
  de posesión.

## Decision

Vamos a confirmar un cambio de posesión cuando **el equipo rival es el dueño más probable de la
pelota durante N frames seguidos**, y vamos a **fechar el cambio en el primer frame** de esa racha,
no en el frame en que se confirma.

- El "dueño más probable" en un frame es el equipo del jugador más cercano a la pelota. Si la pelota
  falta, se usa su última posición conocida.
- Los tramos de pelota muerta (`D`) cortan la secuencia. Después de cada reanudación, la posesión
  arranca de cero.
- N es el único parámetro. Se calibra en partidos de `sample-data`, nunca en la ventana pública.
- Fuera de esta decisión: detectar la pelota muerta (ADR-002) y la evidencia del Smart Tagging
  (entra con un ADR posterior, si migramos a Viterbi).

Ejemplo: Barça tiene la pelota, Athletic roba en el seg 3 y la pelota no se ve del seg 4 al 6. Con
N = 2 s, Athletic es el más cercano del seg 3 al 5. El cambio se confirma en el seg 5 y queda
fechado en el seg 3.

## Consequences

### Positive

- Aguanta los huecos de la pelota: usa la última posición conocida, no hace falta ver pases.
- Sin retraso en el cambio, gracias al fechado hacia atrás.
- Un solo parámetro: se calibra rápido y es difícil de sobreajustar.
- Fácil de explicar en el documento técnico: la regla entra en una línea.
- Deja armada la estructura del pipeline (evidencia → cortes por pelota muerta → CSV), que Viterbi
  reutiliza.

### Negative

- No detecta posesiones más cortas que N. Un robo seguido de una pérdida inmediata se absorbe en la
  posesión anterior.
- "El jugador más cercano" no es lo mismo que "tiene control": en duelos y rebotes puede marcar un
  dueño falso. Una N más alta lo compensa, pero pierde más posesiones cortas.
- Ignora el Smart Tagging, que es evidencia útil sobre qué equipo tiene la pelota.

### Neutral

- La elección de N define el balance entre posesiones cortas perdidas y cambios falsos. Es la
  decisión que más mueve el spellF1 y se documenta junto con la calibración.

## Alternatives Considered

### Dos o más pases seguidos

Pide ver la pelota salir de un jugador y llegar a un compañero. Con la pelota faltando el 43% del
partido, falla justo en los huecos. Además tiene 2-3 parámetros: radio de control, tiempo mínimo de
pase. Lo descartamos como regla principal. Podría volver como evidencia extra si mejora la
detección de la pelota.

### Híbrido (N segundos O 2 pases)

Cubre más casos que cualquiera de las dos solas, pero tiene 3-4 parámetros con pocos datos para
calibrarlos. Lo descartamos por ahora: más complejidad que la que podemos validar.

### Viterbi/HMM con penalización por cambio

Encuentra la secuencia H/A que mejor explica toda la evidencia junta, con un costo por cada cambio.
El resultado sale fechado de forma óptima y el Smart Tagging entra como evidencia extra. Es la
evolución natural de esta decisión, no un rival: la penalización equivale a un N implícito. Lo
dejamos para un ADR posterior, una vez que el pipeline funcione de punta a punta, porque cuesta más
entender por qué falla.

### Modelo aprendido con datos de otros partidos

Es el más flexible, pero hay riesgo de que no transfiera (otra cámara, otro tracking). Además es
poco explicable y tarda más de 3 días. Lo descartamos por el plazo.

## References

- `metrica-sports/more-than-a-hack-2027`: `CHALLENGE.md` (definición de posesión controlada),
  `EVALUATION.md` (spellF1 y costo del retraso), `RULES.md` (prohibición de calibrar en la ventana
  pública)
- `explore/dead_ball.py`: análisis descriptivo de las señales de pelota muerta
- `metrica-sports/sample-data`: partidos con eventos para calibrar N
