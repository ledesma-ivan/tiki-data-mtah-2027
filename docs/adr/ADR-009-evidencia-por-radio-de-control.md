---
artifact: adr
version: "1.0"
created: 2026-10-29
status: accepted
---

# ADR-009: La evidencia de dueño es el jugador a menos de R metros, y R, N y los topes se eligen juntos

## Status

Accepted (2026-10-29), revisado por Lautaro en el PR #45. Cierra el issue #33.
Depende del #31 (N mide tiempo, ya en `main`). Reemplaza la evidencia del ADR-001 y precisa su regla de racha, que con el #31 y estos valores ya no es
"el rival durante N frames seguidos" (ver Decision).

**Date:** 2026-10-29
**Deciders:** Ivan Ledesma (propone).

## Context

`owner_evidence` toma, en cada frame, el equipo del jugador seguido más cercano a la pelota, esté cerca o
no. Con la pelota viajando en un pase, el más cercano suele ser un rival lejano. Medido en Game 3 contra la
verdad del ADR-005 (issue #33): con el más cercano a menos de 1 m acierta el 95.7%, y entre 4 y 8 m el 56.0%.
Para que esos frames no partan las posesiones hay que subir N (hoy 2 s), y con un N alto se pierden las
posesiones cortas: en Game 3 el pipeline predice 266 contra 383 reales.

Si la pelota no se ve, la posición se congela en la última conocida sin límite de tiempo.

## Decision

Tres cambios en la evidencia, elegidos junto con N y `max_gap` porque se compensan entre sí:

1. **Radio de control `R`:** el equipo del jugador más cercano es evidencia solo si está a `R` metros o
   menos de la pelota. Si no, el frame no tiene evidencia (`""`).
2. **Interpolación acotada:** en un hueco de la pelota de a lo sumo `MAX_INTERP` frames entre dos
   posiciones vistas, la pelota va en línea recta de una a la otra. Un hueco más largo, o al principio o
   al final, no tiene posición y por lo tanto no tiene evidencia. El reto es post partido, así que usar
   un frame futuro está permitido.
3. **`max_gap` más largo:** como el radio deja muchos frames sin evidencia, una racha del rival tiene que
   sobrevivir a silencios más largos (#31).

Valores elegidos: `CONTROL_RADIUS` = 1.0 m, `CHANGE_FRAMES` (N) = 0.5 s, `MAX_INTERP` = 2 s,
`MAX_GAP` = 4 s. Los valores por defecto de `owner_evidence` (`radius=inf`, `max_interp=None`) reproducen
el ADR-001 exacto (3.000 casos aleatorios idénticos).

**La regla de cambio resultante.** Con estos valores ya no es "el rival durante N frames seguidos" (ADR-001): una
racha del rival empieza en su primer frame con evidencia, sobrevive a silencios de hasta `MAX_GAP` = 100 frames
(4 s) y se confirma en un frame del rival cuando pasaron `CHANGE_FRAMES` = 12 frames desde el primero. Así, dos
frames del rival separados por 11 frames o más, con silencio en el medio, bastan para confirmar un cambio, y el
cambio se fecha en el primero. El dueño actual corta la racha. Lo prueba `test_possession.py` con los valores
reales. Los datos dicen que conviene: en IDSSE, `max_gap` = 8 s todavía suma (+0.009 [+0.006, +0.013]).

## Cómo se mide

- **Métrica:** `spellF1` con `possession_metrics.evaluate`, y diferencias pareadas con 1000 remuestreos
  (`bench.py --compare`), como pide el ADR-006.
- **Datos:** Metrica Sample Games 1-3 (abiertos), pelota tal cual y degradada (45% faltante, huecos de
  1.5 s), verdad desde el inicio (ADR-005). Con el detector v2 (ADR-007, el que va en `possession.py`) y con el
  `D` verdadero (aísla la evidencia).
- **Selección** (`explore/radius_sweep.py`): Games 2 y 3, 3 semillas, `D` verdadero, 300 combinaciones de
  R ∈ {0.75, 1, 1.5, 2, ∞} m, N ∈ {0.25, 0.5, 1, 2} s, tope de interpolación ∈ {sin interpolar, 0.5, 1, 2, ∞} s (sin
  interpolar es mantener la última posición, como hoy) y `max_gap` ∈ {0.24, 0.48, 1} s. `max_gap` ganaba en el
  borde de la grilla, así que se extendió hasta 4 s y más, y la mejora se aplana desde 2 s. Se eligió a mano el
  comienzo de la zona estable (R = 1 m, N = 0.5 s, interpolación 2 s) y `max_gap` = 4 s. La tabla ordena por la
  pelota degradada, que es la que decide (ADR-006); la pelota tal cual es solo un chequeo.
- **Confirmación** (semillas 20-29, que no se usaron para elegir). Game 1 tampoco se usó para elegir; Games 2 y 3
  sí, con otras semillas, así que la columna "Games 1-3" no es independiente:

| diferencia pareada, verdad desde el inicio | Game 1 | Games 1-3 juntos |
|---|---|---|
| `radio - v2`, pelota degradada | +0.110 [+0.083, +0.139] | +0.136 [+0.121, +0.152] |
| `radio - v2`, pelota tal cual | +0.069 [+0.031, +0.108] | +0.108 [+0.088, +0.131] |
| `radio - v1`, `D` verdadero, pelota degradada | +0.130 [+0.101, +0.160] | +0.156 [+0.139, +0.173] |
| `radio - v1`, `D` verdadero, pelota tal cual | +0.080 [+0.042, +0.121] | +0.122 [+0.099, +0.146] |

La mejora está en los tres partidos y en todas las filas, y es mayor sobre el v2 que sobre el v1: el radio y
el detector de pelota muerta (#32) se suman.

- **Regla del ADR-006 completa** (medida por Lautaro en la revisión del #45, Game 1, semillas 20-29,
  `radio - v2`): la verdad desde el final da lo mismo que desde el inicio, y los seis escenarios de sensibilidad
  dan positivo con el intervalo por encima de 0.

| Escenario | Verdad desde el inicio | Verdad desde el final |
|---|---|---|
| Por defecto (45% sin pelota, huecos de 1.5 s) | +0.110 [+0.083, +0.139] | +0.109 [+0.079, +0.136] |
| `--missing 0` | +0.046 [+0.008, +0.086] | +0.050 [+0.013, +0.090] |
| `--missing 0.2` | +0.071 [+0.039, +0.104] | +0.072 [+0.041, +0.104] |
| `--gap 3` | +0.082 [+0.055, +0.108] | +0.082 [+0.055, +0.109] |
| `--crowd 2` | +0.105 [+0.078, +0.132] | +0.105 [+0.078, +0.131] |
| `--dead-missing 0.34` | +0.105 [+0.078, +0.134] | +0.104 [+0.075, +0.130] |
| `--missing 0 --dead-missing 0.34` | +0.054 [+0.019, +0.091] | +0.056 [+0.019, +0.093] |

- **Otro proveedor, IDSSE** (Lautaro, 14 mitades, no se usó para elegir): `radio - v2` = +0.073 [+0.062, +0.085]
  con la pelota degradada y +0.100 [+0.088, +0.113] tal cual, a favor en las 14 mitades.
- **Ruido de los jugadores** (Lautaro, pelota degradada por defecto, `radio - v2`): ningún intervalo toca el
  cero con ruido de posición de 0.3 a 1 m, temblor, slots perdidos o intercambios de identidad entre rivales.
  Lo que más lo achica: el ruido de posición correlacionado de 1 m por eje (+0.059 en Game 1, +0.027 en IDSSE) y
  los intercambios en el 15% de los frames (+0.057 y +0.052).
- **Zona estable en IDSSE** (Lautaro, un parámetro por vez): R = 1 m queda en el borde de abajo (0.75 m pierde
  0.034); N = 0.24 s y `max_gap` = 8 s todavía suman. No cambia la decisión: la regla del ADR-006 no deja volver
  a elegir con la confirmación. Va al #7: sumar IDSSE al barrido, bajar N, subir `max_gap` y mirar R entre 1 y
  2 m, con ruido en los jugadores.
- **Reproducción** (#6): Lautaro corrió `possession.py` sobre BAR-ATH con la cabeza del PR en su máquina y dio
  lo mismo que la nuestra: H 55470, A 35316, D 68071, X 40462 y `sha256` `9e8a0b36…`.

## Consequences

### Positive

- Sube el `spellF1` del banco entre 0.07 y 0.16 según el escenario, con intervalos que no tocan el cero.
- Permite un N de 0.5 s sin cambios falsos en los pases, y recupera posesiones cortas. Aprieta el fechado de los
  cambios de equipo: el rango intercuartil de la latencia pasa de 19 a 6 frames en Metrica y de 22 a 5 en IDSSE.

### Negative

- Cambia el CSV de la entrega (ya corrida sobre BAR-ATH, ver `docs/EXPERIMENTOS.md`).
- **Empeora el equipo que reanuda.** Cada tramo vivo arranca con el equipo de la primera evidencia, que ahora es
  el primer jugador a 1 m o menos; en un saque largo puede ser un rival. El F1 de las salidas de `D` baja de
  0.518 a 0.476 en Metrica y de 0.621 a 0.523 en IDSSE, y el "H" arbitrario (tramo sin evidencia) pasa de 0 a 97
  de 1521 tramos en Metrica. Arrancar con el jugador más cercano y seguir con el radio devuelve ese F1 pero no
  mejora el `spellF1` en Metrica; es el punto de partida del #34, con su ADR.
- Se calibró con la verdad del ADR-005, que se deriva de eventos y tiene ruido propio. Si Metrica asigna el
  dueño con otro radio, el R óptimo puede ser otro (issue #17 del repo oficial).
- En la ventana pública de BAR-ATH la latencia mediana de los cambios es -12.5 frames (el v2 ya traía -10.0) y las
  transiciones puntúan 0.29 contra 0.41 del v1: 6 de 20 emparejadas contra 9. En el banco no aparece: la latencia
  mediana de `radio` es 0 y el F1 de transiciones sube a 0.470 (`explore/edge_latency.py`), aunque ese script
  mezcla la entrada a `D`, la salida de `D` y el cambio de equipo, y los bordes de `D` los fijan `DEAD_LEAD` y
  `DEAD_TRIM`. Separado por tipo (Lautaro, `match_transitions`), ningún tipo se adelanta medio segundo ni en
  Metrica ni en IDSSE. Con 6 emparejadas la mediana de la ventana no separa una causa del ruido; si la entrega
  final lo repite, se mira en IDSSE y no en la ventana.
- La verdad del banco asigna la posesión desde el inicio del evento, y la del reto puede fecharla distinto.

### Neutral

- La interpolación es lineal. Con un hueco de pelota en el aire (cambio de frente) inventa una trayectoria
  recta; el tope de 2 s limita el error.
- `dead_mask` y el ADR-007 no cambian.

## Alternatives Considered

### Solo subir N

Con el mismo N = 2 s el radio da 0.561 y la evidencia actual 0.591 (issue #33): el radio solo rinde si
baja N. Por eso se eligen juntos.

### Evidencia blanda (peso `exp(-d/σ)` por equipo)

Más informativa, pero solo sirve con un decodificador que combine probabilidades (#35, opcional). Se retoma
si ese decodificador se hace.

### Interpolación sin tope

Probada (`interp=inf`): con R = 1 m, N = 0.5 s y `max_gap` = 1 s da lo mismo que el tope de 2 s (0.673 y 0.673
de media en la selección). Se prefiere el tope por no inventar trayectorias largas.
