---
artifact: adr
version: "1.0"
created: 2026-10-30
status: accepted
---

# ADR-014: Posesión con juego vivo con un modelo por frame y un decodificador, entrenados en datos abiertos

## Status

Accepted (2026-10-30), revisado por Ivan en el PR #65: reprodujo la confirmación (43 de 43) y corrió la entrega sobre BAR-ATH.

Si confirma y se acepta, reemplaza la regla de cambio dentro de los tramos vivos: el ADR-001 y la parte de
la regla de cambio del ADR-009 (N, `max_gap`) quedan `Superseded by ADR-014`. La evidencia por radio de
control del ADR-009 sigue, ahora como señal del modelo. Si no confirma, el CSV no cambia.

**Date:** 2026-10-30
**Deciders:** Lautaro Bursese (con Claude)
**Issues:** #49, con el #35 (decodificador) adentro, como lo repartió Iván el 29/10

## Context

### Dónde está lo que falta

Los oráculos de `explore/oracles.py` (fila del 29/10 en `docs/EXPERIMENTOS.md`) reemplazan una pieza del
pipeline por la verdad y miden cuánto sube `spellF1` con la pelota degradada del banco:

| Oráculo, sobre v2 + radio | Metrica | IDSSE |
|---|---|---|
| Línea de base | 0.541 | 0.412 |
| Posesión perfecta con juego vivo (con el `D` del v2) | +0.336 [+0.314, +0.357] | +0.476 [+0.461, +0.490] |
| Pelota completa | +0.093 [+0.081, +0.105] | +0.104 [+0.095, +0.114] |
| `D` perfecto | +0.095 [+0.082, +0.108] | +0.071 [+0.063, +0.078] |

El hueco más grande es decidir quién tiene la pelota con juego vivo. Aun con la pelota completa y el `D`
perfecto, la regla de hoy (el más cercano a 1 m o menos, más la regla de cambio) llega a 0.740 en Metrica
y a 0.598 en IDSSE.

### El paso 0 (30/10)

Antes de este ADR se midió un prototipo descartable, solo con los partidos de selección (Metrica 2-3,
IDSSE 1-5): un modelo por frame con un Viterbi de dos estados, contra `radio`. La reserva no se tocó. El
script es `explore/live_possession_step0.py`, y sus corridas están en `EXPERIMENTOS` (30/10). Con λ = 20:

| Corrida | Metrica | IDSSE |
|---|---|---|
| Pliegue 1 (prueba en Metrica 3 e IDSSE 5) | 0.532 → 0.673, +0.141 [+0.113, +0.170] | 0.430 → 0.572, +0.142 [+0.111, +0.178] |
| Pliegue 2 (prueba en Metrica 2 e IDSSE 4) | 0.556 → 0.668, +0.112 [+0.086, +0.137] | 0.387 → 0.582, +0.196 [+0.167, +0.227] |
| Pliegue 1, entrenado con 3 partidos | +0.142 | +0.146 |
| Pliegue 1, entrenado solo con IDSSE | +0.144 | +0.151 |
| Pliegue 1, con ruido de jugadores al medir / también al entrenar | +0.141 / +0.152 | +0.165 / +0.183 |
| Pliegue 1 sin decodificador | −0.121 | −0.030 |

- **La ganancia es grande y se sostiene:** todas las mitades a favor y cualquier penalidad de cambio entre
  5 y 40.
- **El decodificador es indispensable:** el modelo solo, frame por frame, pierde contra `radio`.
- **No faltan datos:** con 3 partidos de entrenamiento rinde como con 5, y entrenado con un solo proveedor
  rinde igual en el otro.
- **Con la pelota completa al medir, el modelo llega a 0.756 y 0.657:** la pelota vale todavía unos +0.08
  encima del modelo.

### Reglas que condicionan el diseño

- **Se entrena solo con otros partidos**, nunca con BAR-ATH (issue 2 del repo oficial), y sin etiquetas a
  mano del partido (issues 8 y 10).
- **Ninguna IA ve los datos del partido** (`AGENTS.md`).
- **El CSV tiene que salir igual byte a byte en cualquier máquina** (#6, issue 11 del oficial): señales
  enteras, árboles exportados a enteros e inferencia solo con `numpy`, como el ADR-010. Entrenar necesita
  `requirements-train.txt`.
- **Se decide con los dos bancos** (ADR-011): selección en Metrica 2-3 e IDSSE 1-5 y una sola confirmación
  en la reserva (Metrica 1, IDSSE 6-7), con semillas nuevas.

## Decision

### Objetivos, no objetivos y antiobjetivos

- **Objetivo:** reemplazar `confirm_changes` dentro de cada tramo vivo por un modelo que da, en cada frame,
  qué equipo tiene la pelota, seguido de un decodificador que arma posesiones. Entra al CSV solo si gana
  en los dos bancos en la reserva.
- **No objetivos:**
  - el `D` no cambia: sigue `dead_mask_v2` con `refine` (ADR-007 y ADR-010);
  - el equipo que reanuda (#34) no entra al decodificador en este ADR;
  - no se reconstruye la pelota con un modelo aparte, no se usa el video (#36, en pausa) y no se suman
    datasets.
- **Antiobjetivos:**
  - nada que lea BAR-ATH para entrenar, elegir o ajustar;
  - aritmética de coma flotante en lo que decide una etiqueta;
  - un modelo que dependa de cuál equipo es local;
  - elegir con la ventana pública.

### El pipeline

`possession.label` queda así:

1. `dead_mask_v2` y `refine` dan el `D` y el equipo que reanuda, como hoy.
2. `owner_evidence` con el radio de control da la evidencia, como hoy.
3. **Nuevo:** si `live_model.json` trae un modelo, `live_features` arma las señales de cada equipo y el
   modelo da un puntaje por frame. En cada tramo vivo, `decode_live` elige la secuencia de `H` y `A`.
   - Si el archivo dice `rule`, cada tramo vivo sigue con `confirm_changes`, y el CSV es el de hoy, frame
     por frame.
   - Si el archivo falta o está roto, el pipeline se frena con su ruta, como con `stops_model.json`.
4. La salida no cambia: `H`, `A` o `D` dentro de los tiempos y `X` afuera.

### Las señales (`LIVE_FEATURES`)

Se calculan por frame y para cada equipo. El mismo cálculo se hace dos veces: una con un equipo como
"propio" y el otro como "rival", y otra al revés. Todo va en enteros: distancias en cm, velocidades en
cm/s, frames y conteos. `UNKNOWN` (−1 000 000) marca lo que no se puede calcular, como en `frame_features`.

Cada tiempo (los tramos que puntúa el scorer) se calcula por separado, así que ninguna ventana cruza el
entretiempo. En cada tiempo, el equipo cuya posición media en x es menor ataca hacia x = largo, como en
`stop_features`.

**Por equipo** (21, con prefijo `own_` y `rival_`):

- **La pelota:**
  - `nearest` y `second`: distancia del primero y del segundo jugador del equipo más cercanos a la pelota
    (la de `ball_position` con huecos de hasta 2 s);
  - `n_3m` y `n_10m`: cuántos jugadores del equipo hay a 3 m y a 10 m de la pelota;
  - `nearest_speed`: la velocidad del más cercano, la del proveedor;
  - `closing`: cuánto se acerca el más cercano a la pelota, con su velocidad de las posiciones.
- **La evidencia de `radio`:**
  - `ev_past_12`, `ev_past_50`, `ev_past_125`: frames con evidencia del equipo en los 12, 50 y 125 frames
    anteriores;
  - `ev_next_12`, `ev_next_50`, `ev_next_125`: lo mismo en los siguientes. El pipeline es offline, así que
    puede mirar hacia adelante;
  - `ev_since` y `ev_until`: frames desde la última evidencia del equipo y hasta la próxima, con tope de
    250.
- **El bloque:**
  - `tracked`: cuántos jugadores del equipo están seguidos;
  - `advance`: la posición media en x hacia el arco rival, desde la mitad de la cancha;
  - `spread_x` y `spread_y`: el desvío de las posiciones en x y en y;
  - `team_fwd`: la velocidad media hacia el arco rival, promediada en 1 s.
- **La pelota respecto del equipo:**
  - `ball_advance`: la posición de la pelota hacia el arco rival, desde la mitad;
  - `ball_fwd`: su velocidad hacia el arco rival, en 0.2 s.

**Compartidas** (7):

- `ball_seen`: si el tracking ve la pelota;
- `ball_unseen` y `ball_next_seen`: frames desde que se vio y hasta que se vuelve a ver, con tope de 250;
- `ball_known`: si `ball_position` le da una posición;
- `ball_speed`: la velocidad de la pelota, en 0.2 s;
- `live_since` y `live_until`: frames desde el inicio del tramo vivo y hasta su fin, con tope de 250.

**Las velocidades de las posiciones** salen de 0.2 s (5 frames). Si un jugador se mueve a más de 12 m/s en
ese lapso, su velocidad queda como `UNKNOWN`: cubre los saltos de un slot en los cambios de jugador y de
período (#53) sin esperar ese arreglo.

### El modelo y la exactitud

- **Clasificador:** `HistGradientBoostingClassifier` (scikit-learn 1.9.1, como en el ADR-010). Da la
  probabilidad de que el equipo propio tenga la pelota.
  - Cada frame de entrenamiento con juego vivo según la verdad da dos filas: las señales con H como propio
    (`y` = la verdad es H) y con A como propio (`y` = la verdad es A).
  - El modelo es simétrico por construcción: no sabe cuál equipo es local.
- **Exportación:** `calibrate_edges.export` lo pasa a enteros (umbrales enteros y hojas en millonésimas de
  logit), y `tree_scores` lo infiere solo con `numpy`.
- **Puntaje por frame:** `s = tree_scores(F_H) − tree_scores(F_A)`. Es antisimétrico: si se cambian los
  equipos, cambia de signo.
- **Decodificador (`decode_live`):** en cada tramo vivo, la secuencia de `H` y `A` que maximiza
  `Σ (s_t si H, −s_t si A) − switch · cambios`. Es un Viterbi de dos estados con un costo fijo por cambio.
  - `switch` = 2 · λ · 1 000 000, entero. λ es la penalidad en logits del paso 0.
  - La programación dinámica va en enteros de Python, así que es exacta.
  - En un empate, el último frame del tramo es `H`, y un cambio que empata entre varios frames va al primero
    de ellos: se fecha hacia atrás, como en `confirm_changes`.
- **Lo que se entrega:** `live_model.json` (`{"mode": "model", "switch": int, "trees": {...}}` o
  `{"mode": "rule"}`), en el repo, como `stops_model.json`.

### El entrenamiento

- **Datos:** para elegir y para confirmar, solo los partidos de selección. Para la entrega, los 10 una vez
  confirmado (ADR-011).
- **Verdad:** en Metrica, la del inicio del evento (ADR-005, la que decide en el ADR-006). En IDSSE,
  `BallPossession`.
- **Pelotas de entrenamiento:** 4 por partido, con semillas propias (100-103, que no son las de selección
  ni las de confirmación):
  - el 6.5% del juego vivo sin pelota con huecos de 1.5 s, y la pelota de las paradas completa;
  - el 20% con huecos de 1.5 s, y el 34% de las paradas sin pelota;
  - el 45% con huecos de 1.5 s, y las paradas completas;
  - el 45% con huecos de 3 s, y el 34% de las paradas sin pelota.

  Cubren lo que no sabemos del ATD, como `TRAIN_BALLS` del ADR-010. En la ventana pública del partido falta
  la pelota en el 34% de los frames de pelota muerta, y las ventanas de las señales miran unos segundos
  dentro de las paradas. En Metrica, la pelota restaurada de las paradas se deja: la condición de la pelota
  dentro de la cancha mide cuánto depende el modelo de ella.
- **Jugadores:** cada pelota va una vez con los jugadores limpios y otra con el ruido combinado de
  `explore/player_noise.py` (0.6 m, 10% de slots perdidos y cambios de identidad cerca de la pelota, para el
  5% de los frames). En el paso 0, entrenar con ruido mejoró el resultado con ruido.
- **Filas:** una cada 16 frames, corrida en cada una de las 8 variantes, de los frames que están vivos en la
  verdad y también en las paradas del propio pipeline (`dead_mask_v2` sobre esa variante). Son los únicos
  frames que el decodificador ve. Cada partido pesa lo mismo.
- **Hiperparámetros fijos:** 300 árboles, tasa 0.1, 200 filas por hoja como mínimo, `random_state` 0 y sin
  parada temprana.

### Cómo se elige y se confirma

- **Recetas:** 31 o 63 hojas, por λ de 5, 10, 20 o 40. Son 8. La penalidad no reentrena: cada tamaño se
  entrena una vez por pliegue.
- **Selección:** LOMO sobre los 7 partidos de selección. Cada receta se entrena con 6 y se puntúa en el que
  queda afuera, con la pelota degradada por defecto, los jugadores limpios y las semillas de selección
  (Metrica 0-9, IDSSE 0-4). Gana la de mayor diferencia pareada media contra `radio`, promediando por
  igual los dos bancos (ADR-011). Queda en `live_choice.json`.
- **Confirmación, una sola vez:** la receta elegida, entrenada con los 7 partidos de selección, sobre la
  reserva (Metrica Game 1 con semillas 20-29, IDSSE 6-7 con semillas 20-24). Son las mismas 43 condiciones
  del ADR-010:
  - las del ADR-011 en los dos bancos: el intervalo por defecto arriba de 0 (en Metrica, con las dos
    verdades) y la diferencia positiva en los seis escenarios;
  - la pelota de las paradas dentro de la cancha;
  - los 10 escenarios de `NOISE`.

  Confirma solo si se cumplen todas. Si no, el barrido no confirma una mejora, `live_model.json` queda en
  `rule` y no se vuelve a elegir con ese resultado.
- **Cuándo corre:** al terminar la selección, antes del #52 y el #53.
  - Los dos tocan poco lo que usa este modelo. El #52 cambia las distancias un 0.29% en x. El #53 cambia la
    velocidad de Metrica en unos pocos frames por cambio de jugador o de período, y las velocidades propias de
    este modelo ya descartan esos saltos.
  - La ganancia del paso 0 es más de 10 veces mayor que cualquier efecto que se les pueda atribuir.
  - Después de cada uno se repite `--confirm` con la misma receta, reentrenada sobre el banco nuevo, y con un
    bloque de semillas nuevo: 30 para el #52 (Metrica 30-39, IDSSE 30-34) y 40 para el #53. No se vuelve a
    elegir. Si no pasa, decide el equipo.
- **Entrega:** si confirma, la receta se reentrena con los 10 partidos (`calibrate_live.py --final`). Como
  ese modelo ya vio la reserva, cualquier comparación posterior contra él lo tiene que decir (ADR-011).
  - El CSV cambia: una persona corre BAR-ATH y pega los conteos, el `sha256` y el validador. La ventana
    pública es solo para verificar.
  - El test que vigila el modelo entregado pasa a fijar el nuevo.

## Cómo se mide

- **Métrica:** `spellF1` con las piezas del scorer oficial, en diferencia pareada contra `radio` (que hoy
  es el pipeline entregado, porque `stops_model.json` es la identidad), con `bench.compare` y 1000
  remuestreos de posesiones y semillas.
- **Decide:** la regla del ADR-011, con las condiciones de arriba.
- **Se reporta además, sin decidir:**
  - el acierto por frame con juego vivo;
  - las posesiones predichas sobre las verdaderas;
  - la diferencia con el `D` verdadero.
- **Registro:** cada corrida, con su fila en `docs/EXPERIMENTOS.md`.

## Resultados (30/10)

### Selección

`calibrate_live.py --select`, en 306 s: 539 276 filas de los 7 partidos de selección, y LOMO con las 8
recetas. Diferencia pareada media contra `radio`:

| Receta | Metrica | IDSSE | Media |
|---|---|---|---|
| **63 hojas, λ = 10** | **+0.1218** | **+0.1659** | **+0.1439** |
| 63 hojas, λ = 20 | +0.1210 | +0.1601 | +0.1406 |
| 31 hojas, λ = 10 | +0.1165 | +0.1607 | +0.1386 |
| 31 hojas, λ = 20 | +0.1200 | +0.1566 | +0.1383 |
| 63 hojas, λ = 5 | +0.1133 | +0.1602 | +0.1367 |
| 31 hojas, λ = 5 | +0.1118 | +0.1584 | +0.1351 |
| 63 hojas, λ = 40 | +0.1119 | +0.1437 | +0.1278 |
| 31 hojas, λ = 40 | +0.1022 | +0.1360 | +0.1191 |

- **Gana 63 hojas con λ = 10** (`live_choice.json`).
- **La elegida gana en los 12 partidos y mitades:** Metrica 2 da +0.110, Metrica 3 +0.134, y las 10
  mitades de IDSSE van de +0.107 a +0.219.
- **La elección no es frágil:** las 8 recetas suman entre +0.10 y +0.17 en cada banco.

### Confirmación: 43 de 43

`calibrate_live.py --confirm`, en 862 s: la elegida, entrenada con los 7 partidos de selección, sobre la
reserva (Metrica Game 1 con semillas 20-29, IDSSE 6-7 con semillas 20-24). Diferencia pareada contra
`radio`:

| Condición | Metrica (inicio / final) | IDSSE |
|---|---|---|
| **Por defecto** (decide el intervalo) | **+0.1129 [+0.0904, +0.1351] / +0.1122 [+0.0899, +0.1356]** | **+0.1522 [+0.1313, +0.1745]**, 4 de 4 mitades |
| `--missing 0` | +0.1072 / +0.1042 | +0.0949 |
| `--missing 0.2` | +0.1096 / +0.1071 | +0.1173 |
| `--gap 3` | +0.1393 / +0.1373 | +0.1555 |
| `--crowd 2` | +0.1241 / +0.1223 | +0.1471 |
| `--dead-missing 0.34` | +0.1131 / +0.1122 | +0.1448 |
| `--missing 0 --dead-missing 0.34` | +0.1007 / +0.0990 | +0.0843 |
| La pelota de las paradas dentro de la cancha | +0.1136 / +0.1133 | |
| Los 10 escenarios de `NOISE` | de +0.1127 a +0.1495 | de +0.1405 a +0.1795 |

- **Confirma con las 43 condiciones**, y cada escenario tiene además su intervalo arriba de 0.
- **No depende del detector de paradas:** con el `D` verdadero (no decide), +0.1175 en Metrica y +0.1628
  en IDSSE.
- **Aciertos y posesiones:**
  - frames con juego vivo bien etiquetados: de 0.881 a 0.927 en Metrica y de 0.849 a 0.915 en IDSSE;
  - posesiones predichas: de 257 a 319 de 353 en Metrica, y de 122 a 168 de 193 en IDSSE.
- **Lo medido es lo que se entrega:** los árboles exportados a enteros y `decision_function` dan 0 frames
  distintos en Metrica Game 1 (primera semilla).
- **Corrió antes del #52 y el #53.** Después de cada uno se repite, como dice "Cuándo corre".
- **Cada condición tiene además su intervalo arriba de 0:** el borde más bajo es +0.062.

### Control después del #52: 43 de 43

El #58 (ADR-012, la geometría de cada cancha) entró el 30/10 a las 11:45. Se mergeó `main`, se reentrenó
la misma receta sobre el banco nuevo y se repitió `--confirm --seed-start 30` (Metrica 30-39, IDSSE 30-34),
en 888 s:

- **Por defecto:** Metrica +0.1290 [+0.1044, +0.1527] desde el inicio y +0.1266 [+0.1010, +0.1535] desde
  el final; IDSSE +0.1474 [+0.1260, +0.1701], 4 de 4 mitades.
- **Escenarios:** de +0.1013 a +0.1363 en Metrica (desde el inicio) y de +0.0747 a +0.1576 en IDSSE.
- **Pelota de las paradas dentro de la cancha:** +0.1240 y +0.1231.
- **`NOISE`:** de +0.1274 a +0.1610 en Metrica y de +0.1469 a +0.1843 en IDSSE.
- **Cada condición, con el intervalo arriba de 0:** el borde más bajo es +0.052.
- **Los árboles exportados contra `decision_function`:** 0 frames distintos.

El modelo entregado se reentrenó con los 10 partidos sobre el banco nuevo. El #53 sigue pendiente.

### Lo que decidió la implementación

- **La selección y la confirmación puntúan con `decision_function` de scikit-learn**, porque `tree_scores`
  en numpy hubiera llevado unas 2 horas para la confirmación. Sobre señales enteras toma las mismas
  decisiones que los árboles exportados (0 frames distintos, arriba). `possession.py` usa los árboles
  exportados.
- **Un cambio que empata entre varios frames va al primero**, como en `confirm_changes`. Lo encontró la
  revisión de la rama, y un test lo fija.
- **Lo que la revisión dejó para después** (menores):
  - la dirección de ataque cuando empatan las medias de los dos equipos;
  - tres archivos rotos que no frenan con su ruta: un entero fuera de int64, un árbol vacío y un archivo que
    no es UTF-8;
  - que `--final` verifique que `--confirm` pasó;
  - guardar `LIVE_FEATURES` en el archivo del modelo.

## Consequences

### Positive

- Ataca el hueco más grande que midieron los oráculos, con una ganancia del orden del v2 (+0.155 y +0.119)
  y del radio (+0.136 y +0.073) en el paso 0.
- Suma el decodificador del #35 y reusa la maquinaria del ADR-010: la exportación a enteros,
  `tree_scores`, los bancos y la confirmación de 43 condiciones.
- Sigue siendo determinista: señales, árboles y decodificador en enteros.

### Negative

- **La entrega lleva un modelo entrenado:** es menos fácil de explicar que una regla, y el documento técnico
  tiene que contarlo.
- **Mezcla dos convenciones de posesión:** los eventos de Metrica y `BallPossession` de DFL. La del
  concurso la arma Metrica con su tracking. Ganar en los dos bancos es la respuesta del ADR-011, pero no
  garantiza la del concurso.
- **La degradación es una simulación del ATD.** Si el ATD real pierde la pelota o los jugadores de otra
  forma, la ganancia puede ser menor. Por eso se entrena con varias pelotas y con ruido, y se confirma con
  los escenarios y con `NOISE`.
- **La reserva se reusa:** ya confirmó el ADR-010. Es lo que prevé el ADR-011.
- **La inferencia tarda más:** 14 s en un partido sintético del tamaño de BAR-ATH (199 319 frames y 46
  slots), contra 0.2 s de la regla.

### Neutral

- El `D` y el equipo que reanuda siguen en la línea del #32 y el #34. Si un candidato nuevo del ADR-010
  mueve las paradas, el modelo de posesión se vuelve a confirmar, porque `live_since`, `live_until` y las
  filas de entrenamiento dependen de ellas. Eso es lo mismo que después del #52 y el #53: la misma receta,
  reentrenada con las paradas nuevas, y `--confirm` con semillas nuevas, sin volver a elegir.
- `bench.py` suma el pipeline `live` (el modelo entregado), que no decide: decide `calibrate_live.py`.

## Alternatives Considered

### Ajustar la regla de cambio (#7)

Barrer N, el radio y `max_gap` puede sumar algo, pero la regla tiene un techo bajo. Con la pelota completa
y el `D` perfecto llega a 0.740 y 0.598. El modelo, con la pelota degradada y el `D` verdadero, llega a
0.747 y 0.638 en el paso 0.

### Un decodificador semi-Markov o de tres estados (#35)

Un semi-Markov, con la duración de las posesiones, podría recuperar las posesiones cortas que todavía faltan
(314 de 383 en Metrica). Uno de tres estados (H, A y `D`) juntaría este ADR con el #32. Quedan como
candidatos siguientes, medidos contra este: primero el decodificador más simple que ya gana.

### Modelos de secuencia profundos

Una red recurrente o un transformer podrían aprender más contexto. Pero reproducir el CSV byte a byte con
una red en coma flotante es difícil en cualquier CPU, y los árboles exportados a enteros ya están probados
(ADR-010).

### Reconstruir la pelota con un modelo aparte

Las señales ya llevan el contexto de los huecos: lo que se vio antes y después, y cuánto falta. Una
reconstrucción aprendida desde los jugadores entra con su ADR solo si el error se concentra en los huecos
largos, y eso se mide en el banco.

### Detector de pelota desde el video (#36)

Encima del modelo, la pelota completa vale unos +0.08, que es su techo. Queda en pausa por tres razones:

- no se puede medir en los bancos, porque no hay video abierto con tracking y una licencia que lo permita;
- reproducir el CSV byte a byte con una red es muy difícil;
- hay riesgo de licencia AGPL.

### Más tracking abierto

Por ahora no, porque la curva no sube de 3 a 5 partidos. El candidato, si un modelo más rico la hace
subir, es SkillCorner Open Data:

- tiene licencia MIT;
- trae 10 partidos de la A-League 2024/25 con la posesión por frame;
- la contra: es tracking de transmisión a 10 fps, con jugadores extrapolados fuera de cámara.

### Un modelo por banco, o elegir la convención

No se sabe qué convención sigue la verdad del concurso. Por eso se entrena con las dos y se exige ganar en
las dos.

## References

- ADR-001 y ADR-009 (regla de cambio y evidencia), ADR-005 (verdad de Metrica), ADR-006 y ADR-011 (bancos y
  regla de decisión), ADR-010 (modelo de paradas, exportación a enteros y confirmación).
- Issues #49, #35, #36, #7, #52 y #53; comentario del paso 0 en el #49 (30/10).
- `explore/oracles.py` y `explore/live_possession_step0.py`, con sus filas en `docs/EXPERIMENTOS.md`.
- SkillCorner Open Data (https://github.com/SkillCorner/opendata, licencia MIT).
