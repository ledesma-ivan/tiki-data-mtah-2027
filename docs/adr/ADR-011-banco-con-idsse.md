---
artifact: adr
version: "1.0"
created: 2026-10-29
status: accepted
---

# ADR-011: El banco decide también con IDSSE

## Status

Accepted (2026-10-30), revisado por Ivan en el PR #55.

Reemplaza al ADR-006 en lo que hace a IDSSE y a la regla de decisión. Lo demás del ADR-006 sigue igual: el
banco de Metrica, la pelota degradada, las dos verdades, el bootstrap pareado y los seis escenarios. Al
aceptarse, el ADR-006 queda `Superseded by ADR-011` en esa parte, como el ADR-002 con el ADR-007.

**Date:** 2026-10-29
**Deciders:** Lautaro (propone). Revisión pedida a Matías, autor del ADR-006.

## Context

El ADR-006 decide con `bench.py` sobre los tres partidos de Metrica. IDSSE queda como chequeo aparte, y el
mismo ADR pide un ADR que lo reemplace para que decida; el ADR-007 ya lo dejó anotado en "Qué sigue". Hay
cuatro razones para hacerlo ahora:

1. **IDSSE es lo más parecido a la verdad del concurso.** `CHALLENGE.md` marca `D` donde el tracking
   corregido da la pelota muerta, y el dueño es el que nombra el tracking. IDSSE trae justo eso por frame
   (`BallStatus` y `BallPossession`), sin eventos ni parámetros. En Metrica, en cambio, la verdad sale de
   los eventos (ADR-003 y ADR-005), y la pelota de las paradas la inventa el banco (ADR-007).
2. **Los dos bancos ya dieron resultados distintos:**
   - sostener la posesión en los huecos de pelota suma en Metrica (+0.021 [+0.007, +0.035]) y resta en
     IDSSE (−0.011 [−0.019, −0.003]) (ADR-008);
   - con ruido en los jugadores, IDSSE pide un radio de control de 1.5 m y Metrica no (revisión del #45).

   Con la regla de hoy, una versión que gana en Metrica y pierde en IDSSE puede entrar.
3. **Tres issues lo necesitan:**
   - el #32: el ADR-010 entrena con IDSSE y elige con sus partidos;
   - el #49: un modelo de posesión entrenado con `BallPossession`;
   - el #7: el barrido de N, R y `max_gap`, con IDSSE en la selección.
4. **IDSSE ya funcionó como banco:**
   - v2 sobre v1: +0.119 [+0.108, +0.129], con las 14 mitades a favor (ADR-007);
   - el radio de control sobre v2: +0.073 [+0.062, +0.085], también 14 de 14 (ADR-009).

## Decision

Toda decisión que cambie el CSV de entrega se toma con los dos bancos, y **una versión entra solo si gana en
los dos**.

### Metrica (sin cambios)

`bench.py`, con las dos condiciones del ADR-006: el intervalo 5-95% de la diferencia pareada entero por
encima de 0 con las dos verdades, y la diferencia positiva en los seis escenarios de sensibilidad.

### IDSSE

`explore/idsse_bench.py --compare A B`:

- **Partidos:** los 7 de IDSSE (revisión `a715a38`), numerados del 1 al 7 por orden de nombre de archivo.
  Cada mitad cuenta como un partido para el bootstrap pareado: son 14.
- **Verdad:** `D` donde `BallStatus` es 0; si no, el equipo de `BallPossession`. Es una sola verdad: como
  no sale de eventos, no tiene variante de anclaje.
- **Pelota degradada:** `bench.degrade`, con los mismos valores por defecto y las mismas opciones que en
  Metrica (`--missing`, `--dead-missing`, `--gap` y `--crowd`). DFL sigue la pelota en todos los frames,
  también con la pelota muerta, así que el primer paso de la degradación (devolver la pelota en las
  paradas) acá no cambia nada.
- **Velocidades:** las del proveedor (`S`), como `possession.py` lee las del ATD.
- **Semillas:** 5 por mitad (`1000 * partido + s`), con `--seed-start` para usar un bloque nuevo.

B le gana a A en IDSSE si se cumplen las mismas dos condiciones del ADR-006:

1. **Ruido:** el intervalo 5-95% de la diferencia pareada, con la pelota degradada por defecto, queda
   entero por encima de 0.
2. **Sensibilidad:** la diferencia es positiva con `--missing 0`, `--missing 0.2`, `--gap 3`,
   `--crowd 2`, `--dead-missing 0.34` y `--missing 0 --dead-missing 0.34`.

### Barridos de parámetros

Como en el ADR-006, la partición y los bloques de semillas se fijan antes de correr, se elige en la
selección y se confirma una sola vez en la reserva.

- **Partición por defecto:**
  - en Metrica, selección en los Games 2 y 3 y reserva en el Game 1 (ADR-006);
  - en IDSSE, selección en los partidos 1 a 5 y reserva en el 6 y el 7.

  Un ADR puede fijar otra antes de correr.
- **Selección:** gana el candidato con mayor diferencia pareada media contra la versión actual,
  promediando por igual los dos bancos. Cada banco aporta su media sobre los partidos de selección y las
  semillas; en Metrica, con la verdad desde el inicio del evento (ADR-006).
- **Confirmación:** en la reserva, con semillas nuevas, las dos condiciones en los dos bancos. Si no pasa
  en alguno, el barrido no confirma una mejora, y no se vuelve a elegir con ese resultado.
- **Entrenamiento** (revisión de Iván en el PR #55):
  - todo lo que se entrene o se ajuste usa solo los partidos de selección;
  - la reserva no entra al entrenamiento antes de la confirmación, así que la confirmación no sale inflada;
  - si después de confirmar se reentrena con todos los partidos para la entrega, como prevé el ADR-010, ese
    modelo ya vio la reserva, y lo tiene que decir cualquier comparación que se haga después contra él.

La fila "pelota tal cual" se reporta en los dos bancos y no decide.

### Qué no cambia

- `bench.py` no cambia.
- Las decisiones ya tomadas (ADR-007 a ADR-009) no se vuelven a decidir: la regla vale para lo que entre
  desde ahora.
- La ventana pública sigue sin servir para elegir (`RULES.md`).

## Cómo se mide

Como el ADR-006, esta decisión se valida con su propia línea de base en datos abiertos (fila del 29/10 en
`docs/EXPERIMENTOS.md`): los 7 partidos de IDSSE, 14 mitades y 5 semillas por mitad (0-4).

**Control.** Sin opciones, `explore/idsse_bench.py` compara `v1` con `v2` como antes de este ADR, y da lo
mismo que en el ADR-007: +0.119 [+0.108, +0.129] con la pelota degradada (14 de 14 mitades) y +0.009
[+0.002, +0.015] tal cual.

**El banco ve lo que tiene que ver.** Como en el ADR-006, la pelota muerta perfecta tiene que sumar en todos
los escenarios, y más cuanto más falta la pelota. Todas las corridas son
`python explore/idsse_bench.py --compare radio "radio, true D"`, más las opciones de cada fila; entre
corchetes, el intervalo de la diferencia pareada con 1000 remuestreos de posesiones y semillas:

| Escenario | `radio` | `radio, true D` | Diferencia pareada | Mitades a favor |
|---|---|---|---|---|
| Pelota tal cual (no decide) | 0.515 | 0.598 | +0.083 [+0.075, +0.091] | 14/14 |
| Degradada, por defecto (45%, huecos de 1.5 s) | 0.412 | 0.483 | +0.071 [+0.063, +0.078] | 14/14 |
| `--missing 0` | 0.515 | 0.598 | +0.083 [+0.075, +0.091] | 14/14 |
| `--missing 0.2` | 0.474 | 0.553 | +0.079 [+0.071, +0.086] | 14/14 |
| `--gap 3` | 0.391 | 0.459 | +0.068 [+0.061, +0.075] | 14/14 |
| `--crowd 2` | 0.405 | 0.476 | +0.071 [+0.064, +0.079] | 14/14 |
| `--dead-missing 0.34` | 0.388 | 0.483 | +0.095 [+0.087, +0.102] | 14/14 |
| `--missing 0 --dead-missing 0.34` | 0.490 | 0.598 | +0.108 [+0.100, +0.115] | 14/14 |

Se logra el 45% de frames vivos sin pelota (44% con `--gap 3` y `--crowd 2`), y el 34-35% de frames muertos
con `--dead-missing 0.34`.

- **La pelota muerta perfecta suma en los siete escenarios y en las 14 mitades**, entre +0.068 y +0.108.
- **Con `--missing 0`, la pelota degradada es igual a la tal cual:** DFL la sigue en todos los frames,
  también en las paradas. En IDSSE no existe el atajo de la pelota que desaparece en las paradas.
- **Crece cuando la pelota falta en las paradas** (+0.095 y +0.108), porque el detector pierde la pelota
  vista fuera de la cancha: su F1 de `D` baja de 0.93 a 0.91 y el fin de las paradas se adelanta casi
  medio segundo.

## Consequences

### Positive

- **Se decide con la verdad más parecida a la del concurso**, y con dos proveedores, dos ligas y dos
  maneras de armar la verdad. Lo que gana solo por un artefacto de un banco, como la pelota inventada de
  Metrica en las paradas o la verdad por eventos, ya no alcanza.
- **IDSSE suma 14 mitades** a los 3 partidos de Metrica.
- **Una sola regla para el #32, el #49 y el #7.**

### Negative

- **Es más exigente:** alguna mejora chica que hoy entraría ya no va a entrar. Es lo que se busca: si una
  mejora es real, tiene que aparecer en los dos bancos.
- **Cada decisión tarda más:** una corrida de IDSSE tarda unos 27 s en esta máquina, contra 11-12 s de
  Metrica. Una decisión completa (el escenario por defecto y los seis de sensibilidad, en los dos bancos)
  lleva unos 5 minutos en serie.
- **La reserva se reusa:** el Game 1 y los partidos 6 y 7 de IDSSE confirman todos los barridos. Con 10
  partidos abiertos no hay una reserva nueva para cada uno, y por eso la reserva nunca se usa para elegir.
- **IDSSE es un solo proveedor y una sola liga**, y su verdad no tiene variante de sensibilidad.

### Neutral

- `explore/idsse_bench.py` suma las opciones de `bench.py`: `--compare`, `--matches`, `--seed-start` y
  los escenarios. Sin opciones compara `v1` con `v2`, como antes.

## Alternatives Considered

### Dejar IDSSE como chequeo aparte (ADR-006)

No obliga a nada: una versión que pierde en IDSSE podría entrar igual. El caso del ADR-008 lo muestra.

### Un solo intervalo con los dos bancos juntos

Una ganancia grande en un banco taparía una pérdida en el otro, que es justo lo que se quiere ver.

### Solo IDSSE

Se pierden los tres partidos de Metrica, sus dos verdades y la comparación con todo lo medido hasta ahora.

## References

- ADR-006 (banco de Metrica y regla de decisión), ADR-007 (v2 confirmado en IDSSE), ADR-008 y ADR-009
  (resultados distintos entre los bancos), ADR-010 (#32 y #34, en la rama `feat/bordes-parada-32`)
- `bench.py`, `explore/idsse_bench.py`
- Issues #7, #30, #32 y #49; issue 16 del repo oficial (uso de IDSSE aprobado)
- IDSSE: Bassek y otros, *Scientific Data* 12, 195 (2025), CC BY 4.0
