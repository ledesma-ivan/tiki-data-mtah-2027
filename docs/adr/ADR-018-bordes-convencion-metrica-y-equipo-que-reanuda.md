---
artifact: adr
version: "1.0"
created: 2026-10-31
status: rejected
---

# ADR-018: Bordes de las paradas y equipo que reanuda con la convención de Metrica, sobre el modelo de posesión

## Status

Rejected (2026-11-01). Es el candidato nuevo que pide el paso 1 de "Lo que sigue" del ADR-010. **No confirmó** (21 de
43 condiciones, ver "Resultados"): `stops_model.json` sigue siendo el modelo identidad y el CSV no cambia. Ivan lo
revisó en el PR #81 el 31/10. Reprodujo los tests y corrió BAR-ATH: el mismo `sha256` de la entrega, `f2460d57…`.
Pidió tres cosas: que quede `Rejected`; que se renumere, porque el ADR-017 es el del #80, y Lautaro pidió el 018; y
que no entre código a `main` a una semana y media del congelamiento. El ADR-010 sigue como estaba. Lautaro lo aprobó
en el PR #81 el 1/11, con la decisión sobre lo que sigue (ver "Lo que sigue").

**El código no está en `main`.** El código de este ADR queda en la rama `feat/bordes-convencion-metrica-32-34-codigo`
(`ac041b7`), sin mergear: `possession.py`, `calibrate_edges.py`, `edges_choice.json` con la elección, los tests y
`explore/edge_transfer.py`. En `main` entran solo este ADR, sus filas de `EXPERIMENTOS`, `explore/edge_transfer.py`
(que corre sobre esa rama) y el README. En esa rama, el código y los mensajes de los commits todavía dicen ADR-017: es
este ADR antes de renumerarlo. Los commits que cita este ADR (`6ec956b`, `c8ae6a5`, `6544a04`) están en las dos ramas.

**Date:** 2026-10-31
**Deciders:** Matías (con Claude); revisión de Ivan y de Lautaro en el PR #81
**Issues:** #32 (incluye el #9) y #34

## Context

### Qué quedó del ADR-010

- **No confirmó** (41 de 43 condiciones, contra `radio`): en Metrica Game 1, el intervalo por defecto tocó el 0
  (+0.0085 [−0.0038, +0.0208]). `stops_model.json` quedó como el modelo identidad y el CSV no cambió.
- **Su confirmación fue la única de aquel candidato.** La reserva (Metrica Game 1, IDSSE 6 y 7) ya se miró para el
  ADR-010, con las semillas 20-29 y 20-24, y después tres veces para el ADR-014 (semillas 20, 30 y 40).
- **Dejó escrito el paso siguiente:** medir en la selección qué separa a los dos bancos (la velocidad del proveedor
  contra la que sale de las posiciones, o la convención de cada uno) y entrenar los bordes con la convención de
  Metrica, que es la del concurso. Con eso, cinco puntos de la revisión de su rama:
  1. el desfasaje de reloj de IDSSE para los tipos;
  2. jugadores degradados al entrenar;
  3. pesos que no achiquen las hojas;
  4. tipos predichos fuera de pliegue;
  5. tapar en IDSSE también, alguna vez, toda la pelota, para que "sin pelota" no signifique "Metrica".

### Qué cambió desde entonces

- **El pipeline que se entrega es otro** (ADR-014 y ADR-015, aceptados): dentro de cada tramo vivo decide un modelo
  por frame con un decodificador de Viterbi (`live_model.json`), no la regla de cambio. `refine` sigue en el
  pipeline, con el modelo identidad, y **el equipo que reanuda no entra al decodificador** (ADR-014, no objetivos).
  Este ADR se compara contra ese pipeline, no contra `radio`.
- **ADR-014, Neutral:** si un candidato mueve las paradas, el modelo de posesión ve otras (`live_since` y
  `live_until` dependen de ellas). Acá se mide la composición entera contra `main` (ver "Cómo se mide").

### Paso 0: qué separa a los bancos (medido en la selección)

Solo con los partidos de selección (Metrica 2 y 3, IDSSE 1 a 5); la reserva no se tocó. Dos mediciones, las dos en
`docs/EXPERIMENTOS.md` (31/10; la segunda, corregida el 1/11):

**1. Los bordes en el reloj de la pelota** (`explore/edge_clock.py --seeds 3`, sobre `main` de hoy). Repite la fila
del 30/10 con las velocidades del #53, y da lo mismo salvo centésimas en Metrica:

| Borde (mediana [25%, 75%], s, + = después) | IDSSE | Metrica |
|---|---|---|
| Fin de la verdad − patada, todos los tipos | +0.04 | entre −0.04 y 0.00 |
| Inicio de la verdad − salida de la pelota (lateral, saque de arco, córner) | +0.08 a +0.16 | +0.08 a +0.12 |
| Inicio del tiro libre, verdad − infracción | **+0.48 [−0.48, +1.20]** | **0.00** (por construcción) |
| Fin del tiro libre, v2 − patada (velocidad del proveedor / de las posiciones) | −1.60 / −1.72 | −0.60 |
| Fin del córner, v2 − patada | +0.08 | −0.70 |

- **Las dos verdades marcan igual casi todo:** el fin en la patada y el inicio a 0.1-0.2 s de la salida de la pelota.
- **Difieren en el inicio del tiro libre:** DFL pone `BallStatus` en 0 medio segundo después de la infracción, y
  Metrica empieza la parada en la infracción.
- **La velocidad de las posiciones no acerca IDSSE a Metrica.** El cociente entre la del proveedor y la de las
  posiciones es 0.996-0.997 en las 10 mitades.

**2. ¿Qué hace que un modelo entrenado en IDSSE transfiera?** (`explore/edge_transfer.py --seeds 3`, nuevo). El
modelo de bordes de este ADR (la receta fija de abajo) se entrena solo con IDSSE 1 a 5, de tres maneras, y se puntúa en
los bordes de Metrica 2 y 3, que no vio.

**Corrección (1/11, review del PR #81).** La primera versión del script sacaba del denominador de cada modelo las
paradas que ese modelo ya no cubría por la mitad, así que un modelo que perdía las paradas difíciles podía salir
mejor. Esos números están en la fila del 31/10 de `EXPERIMENTOS`, y la fila del 1/11 tiene los nuevos. Ahora todos se
puntúan sobre las mismas 573 paradas verdaderas con tipo (3 semillas), y una parada que el modelo no cubre cuenta como
fallo. Con la versión de `ac041b7`, estas son las paradas que cubre cada modelo y los bordes a 0.5 s o menos de la
verdad, con todos los tipos:

| Modelo | Cubre | Inicio | Fin | Cubre, sin pelota | Inicio, sin pelota | Fin, sin pelota |
|---|---|---|---|---|---|---|
| v2, sin mover (referencia) | 91% | 55% | 45% | 91% | 55% | 45% |
| IDSSE, velocidad del proveedor | 79% | 56% | 34% | 87% | 43% | 40% |
| IDSSE, velocidad de las posiciones | 79% | 54% | 33% | 89% | 47% | 38% |
| IDSSE, convención de Metrica | 78% | 56% | 33% | 88% | 43% | 38% |
| Metrica, el otro partido de selección | 87% | 42% | 27% | 87% | 42% | 27% |

- **Ni la velocidad ni la convención cambian la transferencia:** las tres versiones de IDSSE quedan a cuatro puntos o
  menos entre sí, viendo la pelota y sin ella.
- **Ninguna mejora al v2 en Metrica.** Viendo la pelota, el inicio queda igual (54-56% contra 55%) y el fin baja (33-34%
  contra 45%). Sin la pelota, bajan los dos. La primera versión mostraba una mejora en el inicio (71% contra 61%) que
  venía del denominador.
- **Viendo la pelota, el modelo de IDSSE deja de cubrir paradas:** el 79%, contra el 91% del v2, sobre todo en los
  tiros libres (53% contra 80%).
  - En los 90 tiros libres que cubren todos, adelanta el fin a −2.48 s (el v2 queda en −0.22 s).
  - Solo el 6% de los tiros libres termina a 0.5 s o menos, contra el 24% del v2.
  - Con la pelota tapada, cubre el 71% de los tiros libres; en los 120 que cubren todos, el fin queda en −0.06 s, y el
    27% de los tiros libres cae a 0.5 s o menos.
- **Hipótesis, sin aislar:** lo que no transfiere es lo que el modelo lee de la pelota que el banco inventa en las
  paradas de Metrica. En esas paradas la pelota no existe: el banco la inventa interpolando entre la última observación
  de antes y la primera de después (ADR-007), y se mueve despacio durante toda la parada. En IDSSE, y en el ATD, la
  pelota de una parada es real. Pero tapar la pelota saca de todo el partido tanto la real como la inventada, y cambia
  además lo que lee el clasificador de tipo (review del PR #81). La medición es compatible con la hipótesis, pero no la
  aísla. Para aislarla haría falta un control en la selección que conserve los tipos y separe la pelota inventada de
  la observada.
- **Sin pelota, el modelo pierde los inicios** (56% → 43%): ahí la pelota ayuda.
- **Dos partidos de Metrica no alcanzan** para entrenar solos (42% y 27%).

**Consecuencia para este candidato:**

- La convención de Metrica entra como se pidió, porque es la del concurso y no cuesta en la transferencia. No se
  elige: en IDSSE puede costar algo en el inicio de los tiros libres, porque el banco puntúa con la verdad de DFL, y
  la confirmación lo exige igual.
- La velocidad sigue siendo la del proveedor, como la del ATD que lee `possession.py`.
- Se suma una variante del modelo de bordes que no lee la pelota (solo los jugadores). En Metrica cubre más paradas y
  acierta más fines (40% contra 34%, con los números corregidos), aunque pierde inicios y lo que la pelota real aporta
  en IDSSE y en el ATD. Entre las dos decide la selección. La decisión se tomó con la primera versión del paso 0, y con
  los números corregidos se sostiene.

### Lo que queda abierto del #34

- El acierto de quién reanuda por tipo, contra el respaldo ("primer equipo de la evidencia").
- Tests sintéticos: un lateral con un rival más cerca de la pelota que el que saca (arranca el que saca) y un tramo
  sin evidencia (respaldo, sin la `"H"` arbitraria si hay otra fuente).
- La `"H"` arbitraria de `confirm_changes`, documentada o reemplazada.
- El PR #57 ya resolvió `restart_team`, el `initial` de `confirm_changes` y el test con la regla de cambio. Desde el
  ADR-014 la regla de cambio no corre en la entrega, así que el `initial` no llega al CSV.

## Decision

Todo lo que sigue describe el código de la rama `feat/bordes-convencion-metrica-32-34-codigo`; `main` no lo tiene
(ver "Status").

### Objetivos, no objetivos y antiobjetivos

- **Objetivo:** un candidato nuevo para los bordes de las paradas y el equipo que reanuda, entrenado con la convención
  de Metrica, que entra al CSV solo si le gana en los dos bancos al pipeline que se entrega hoy (ADR-011).
- **No objetivos:**
  - encontrar las paradas que faltan o descartar las falsas: `dead_mask_v2` sigue igual;
  - cambiar el modelo de posesión del ADR-014 o su receta: `live_model.json` no cambia;
  - el Smart Tagging (#8), el video y la homografía;
  - cambiar el escenario por defecto del banco (ADR-010, "Lo que sigue", paso 3).
- **Antiobjetivos:**
  - nada que lea BAR-ATH para entrenar, elegir o ajustar, ni la ventana pública para elegir;
  - aritmética de coma flotante en lo que decide una etiqueta;
  - volver a elegir después de ver la confirmación.

### El pipeline

`possession.label` no cambia de forma: `dead_mask_v2` → `refine` con `stops_model.json` → el modelo de posesión en
cada tramo vivo. Cambian dos cosas:

1. **El equipo que reanuda entra al decodificador.** `decode_live(score, switch, initial)` toma al equipo que reanuda
   como el estado de antes del tramo: arrancar con el otro equipo cuesta un cambio (`switch`, el mismo λ = 10 del
   ADR-014). Es la regla de cambio del #34 en el idioma del decodificador: si las señales del tramo contradicen al
   equipo inicial por más de lo que cuesta un cambio, cambia; si no, arranca con el que reanuda. No suma parámetros.
   Con el modelo identidad (`team_radius_cm` = 0) no hay equipo inicial y el CSV es el de hoy, frame por frame.
2. **El que saca es el más cercano a su lugar, no a la pelota.** `restart_team` busca a los jugadores a
   `team_radius_cm` o menos del punto de reanudación (la pelota si se conoce; si no, el jugador más cercano al lugar
   del tipo, como en el ADR-010) y, entre ellos, toma al más cercano a la banda (lateral), al banderín (córner), al
   medio del área chica (saque de arco) o al centro (saque inicial). Las reglas del juego dejan a los rivales a 2 m
   de un lateral y a 9.15 m de las otras reanudaciones: el que marca puede quedar más cerca de la pelota que el que
   saca, pero no más cerca de la línea. En un tiro libre o en "otro" sigue el más cercano a la pelota. Es el test
   que pide el #34.

### El modelo de las paradas: la receta nueva

La maquinaria es la del ADR-010: las mismas señales (`FRAME_FEATURES`, `EDGE_FEATURES`, `STOP_FEATURES`), árboles
potenciados exportados a enteros, el escalón que mejor ajusta las probabilidades y el clasificador de tipo. Lo que
cambia es con qué se entrena:

- **La verdad de los bordes, con la convención de Metrica** (`calibrate_edges.dfl_clock`). La parada de un tiro libre
  de IDSSE empieza en la infracción (el evento `Foul` u `Offside` de DFL a 3 s o menos del inicio, en el reloj del
  tracking), donde la empieza la verdad de Metrica (ADR-003: desde el fin del evento anterior). Los demás bordes ya
  coinciden en las dos convenciones (paso 0). La verdad de IDSSE con la que se puntúa no cambia: sigue siendo
  `BallStatus` (ADR-011).
- **Los tipos de IDSSE en el reloj del tracking** (punto 1 de la revisión): cada mitad se corre por la mediana de
  evento de reanudación menos patada, como en `explore/edge_clock.py`, y cada parada toma el evento más cercano a
  su patada a 2 s o menos.
- **Jugadores degradados al entrenar** (punto 2): cada pelota de entrenamiento va una vez con los jugadores limpios
  y otra con el ruido combinado de `explore/player_noise.py` (`noise 0.6 m + 10% lost + swaps 5%`, el del ADR-014).
  Para no duplicar las filas, se toma un frame de cada 4 de cada ventana, corrido 2 en la variante con ruido: la
  densidad por pelota del ADR-010.
- **Pesos que promedian 1** (punto 3): cada partido sigue pesando lo mismo, pero los pesos se escalan a media 1.
  Con pesos de 1 / filas, la suma de hessianos de un nodo queda cerca del `min_hessian_to_split` de scikit-learn
  (1e-3) y el nodo no se parte.
- **Tipos fuera de pliegue** (punto 4): el modelo de bordes y el plan B aprenden con el tipo que predice un
  clasificador entrenado con los otros partidos, tan errado como el que van a ver al inferir. El clasificador que se
  exporta se entrena con todos.
- **Una pelota tapada en IDSSE** (punto 5): a las seis pelotas de entrenamiento de IDSSE se suma una que el modelo no
  ve, como en Metrica. `dead_mask_v2` sí la ve degradada por defecto, como en Metrica.
- **Fijo, del ADR-010:** ventanas de 3 s, 31 hojas, 200 iteraciones, tasa 0.1, 200 filas por hoja como mínimo,
  semilla 0; el clasificador de tipo con 50 iteraciones y 8 hojas. La velocidad de IDSSE es la del proveedor, como
  `possession.py` lee la del ATD.

### Los candidatos

Nueve recetas, todas con la convención de Metrica, cada una sin equipo que reanuda o con un radio de 2 o de 4 m:

- **el modelo de bordes con la pelota** (como el ADR-010, con la receta nueva);
- **el modelo de bordes sin la pelota:** sus señales por frame se calculan sin pelota, al entrenar y al inferir
  (`"ball": false` en `stops_model.json`). El tipo y el que saca la siguen viendo;
- **el plan B:** un `lead` y un `trim` por tipo, la mediana de los desfasajes del v2 contra la verdad.

### El modelo de posesión en la comparación

`live_model.json` se entrenó con los 10 partidos, así que vio la selección y la reserva (ADR-011). Para comparar, la
receta elegida del ADR-014 (63 hojas, λ = 10, `live_choice.json`) se vuelve a entrenar sin los partidos que se
puntúan: con 6 de los 7 de selección en cada pliegue, y con los 7 para la confirmación. Las dos ramas de cada
comparación (`main` y el candidato) usan el mismo modelo de posesión.

- **No se reentrena con las paradas nuevas** (desvío del ADR-014, Neutral). Sus filas de entrenamiento son los frames
  vivos en la verdad y en `dead_mask_v2`, que no cambia; reentrenarlo pediría un modelo por receta de paradas y por
  pliegue (ver "Alternatives").
- **Lo que se confirma es la composición:** las paradas nuevas, el modelo de posesión con la receta del ADR-014 y el
  equipo que reanuda en el decodificador, contra `main`. Si confirma, `live_model.json` queda como está, porque su
  receta es la misma que se midió.

## Cómo se mide

**Métrica:** `spellF1` con las piezas del scorer oficial, en diferencia pareada contra `main` (las paradas del v2 sin
mover y el modelo de posesión, entrenado como se dice arriba), con `bench.compare` y 1000 remuestreos de posesiones y
semillas.

**Partición, fijada antes de correr nada** (la del ADR-010 y el ADR-011):

- **Selección:** Metrica Games 2 y 3 (semillas 0-9, verdad desde el inicio del evento) y los partidos 1 a 5 de IDSSE
  (10 mitades, semillas 0-4). Ahí se entrena y se elige todo, con validación cruzada dejando un partido afuera: cada
  receta y el modelo de posesión se entrenan con 6 partidos y se puntúan en el que queda afuera, con la pelota
  degradada por defecto y los jugadores limpios.
- **Regla de selección** (ADR-011): gana la receta con mayor diferencia pareada media contra `main`, promediando por
  igual los dos bancos. Queda en `edges_choice.json`, antes de tocar la reserva.
- **Confirmación, una sola vez:** la receta elegida, entrenada con los 7 partidos de selección, en la reserva: Metrica
  Game 1 con las semillas 50-59 e IDSSE 6 y 7 (4 mitades) con las semillas 50-54. Este texto decía: "Cuando se
  fijaron no las había usado nadie; el mismo día las usó también el #77, en paralelo". **Corrección (1/11, review
  del PR #81):** cuando se fijaron (`a903761`, 31/10 a las 16:01, hora de Argentina), ya estaban usadas. El #77 había
  registrado su confirmación con las semillas desde 50 en su rama a las 10:39 (`67b8fe6`), y se mergeó a `main` a las
  15:54. Este ADR no lo vio porque partía de `2987431`. **La reserva no es virgen:** la miraron el ADR-010 (semillas 20-29 y 20-24) y el ADR-014 (20, 30 y
  40). Nunca se usó para elegir, y acá tampoco: con lo que dé no se vuelve a elegir.

**Comandos** (en la rama `feat/bordes-convencion-metrica-32-34-codigo`): `python calibrate_edges.py --select` y
`python calibrate_edges.py --confirm` (semillas desde 50 por defecto). Los dos leen solo datos abiertos.

**Condiciones de confirmación**, fijadas antes de correrla (las 43 del ADR-010 y del ADR-014). El candidato confirma
solo si se cumplen todas:

1. En Metrica Game 1, con la pelota degradada por defecto, el intervalo 5-95% de la diferencia queda entero por encima
   de 0 con las dos verdades (inicio y final del evento): 2 condiciones.
2. En Metrica Game 1, la diferencia es positiva en los seis escenarios de sensibilidad (`--missing 0`,
   `--missing 0.2`, `--gap 3`, `--crowd 2`, `--dead-missing 0.34` y `--missing 0 --dead-missing 0.34`), con las dos
   verdades: 12.
3. En IDSSE 6 y 7, el intervalo por defecto queda entero por encima de 0 y la diferencia es positiva en los seis
   escenarios: 7.
4. En Metrica Game 1, con la pelota restaurada de las paradas metida dentro de la cancha, la diferencia es positiva
   con las dos verdades: 2.
5. Con los jugadores degradados (los 10 escenarios de `NOISE`), la diferencia es positiva en cada banco: 20.

**Si confirma:** `calibrate_edges.py --final` entrena la receta con los 10 partidos y escribe `stops_model.json`. Ese
modelo ya vio la reserva, y cualquier comparación posterior contra él lo tiene que decir (ADR-011). `live_model.json`
no cambia. El CSV cambia: una persona corre `possession.py` sobre BAR-ATH en dos máquinas y pega solo los conteos de
`H/A/D/X` y el `sha256` (`AGENTS.md`). La ventana pública, solo para verificar.

**Si no confirma:** `stops_model.json` queda como el modelo identidad y el CSV no cambia. El código nuevo
(`decode_live` con el equipo inicial y el que saca en `restart_team`) no cambia nada con ese modelo: lo vigilan los
tests y el `sha256` sintético de `repro_check.py`, que tiene que ser el de `main`.

**Se reporta además, sin decidir:**

- los bordes por tipo a 0.5 s o menos (v2 contra el candidato) y el acierto del tipo;
- el acierto de quién reanuda por tipo, contra el respaldo del #34 (el primer equipo de la evidencia, la que leía
  `confirm_changes`) y contra la primera etiqueta del tramo en `main` y en el candidato;
- cuántos frames vivos caen en tramos sin equipo que reanuda y sin evidencia: los que la regla de cambio llenaría con
  la `"H"` de respaldo.

## Resultados (31/10): no confirma, el CSV no cambia

### Selección

`calibrate_edges.py --select`, en 659 s: 631 242 filas de bordes y 539 240 del modelo de posesión, de los 7 partidos
de selección; LOMO con las 9 recetas. Diferencia pareada media contra `main`:

| Receta | Metrica | IDSSE | Media |
|---|---|---|---|
| **Modelo con la pelota** (elegido) | **−0.0161** | **+0.0316** | **+0.0077** |
| Modelo con la pelota, equipo a 2 m | −0.0162 | +0.0316 | +0.0077 |
| Modelo con la pelota, equipo a 4 m | −0.0162 | +0.0316 | +0.0077 |
| Modelo sin la pelota | +0.0011 | +0.0091 | +0.0051 |
| Modelo sin la pelota, equipo a 2 m | +0.0000 | +0.0091 | +0.0046 |
| Modelo sin la pelota, equipo a 4 m | +0.0000 | +0.0089 | +0.0045 |
| Plan B, equipo a 2 m | −0.0065 | +0.0033 | −0.0016 |
| Plan B, equipo a 4 m | −0.0064 | +0.0030 | −0.0017 |
| Plan B | −0.0065 | +0.0030 | −0.0017 |

- **Gana el modelo con la pelota, sin equipo que reanuda** (`edges_choice.json`), por la regla del ADR-011.
- **Pierde en los dos partidos de Metrica** (Game 2 −0.020, Game 3 −0.012) y gana en las 10 mitades de IDSSE (de
  +0.021 a +0.043). Es compatible con el paso 0 y con la hipótesis de que, en Metrica, el modelo lee la pelota que inventa el banco. La regla
  no pide ganar en los dos bancos en la selección, y se aplica como se fijó: no se cambia la elección por esto.
- **El modelo sin la pelota es el único positivo en los dos bancos**, pero chico (+0.0011 y +0.0091), y el plan B
  pierde en Metrica.
- **El equipo que reanuda cambia poco el `spellF1`, y no se midió cuánto.** Este texto decía que las tres variantes
  de cada modo eran iguales a cuatro decimales. **Corrección (1/11, review del PR #81):** no lo son. Diferencias
  entre variantes del mismo modo:
  - con el modelo sin la pelota, en Metrica, +0.0011 sin equipo contra +0.0000 con él: el equipo empeora un poco;
  - en IDSSE, hasta 0.0003 (plan B: +0.0033 con 2 m contra +0.0030 sin equipo);
  - con el elegido, −0.0161 contra −0.0162.

  Son chicas, pero no se midió la diferencia pareada entre variantes ni su intervalo. No alcanza para decir que el
  equipo que reanuda no cambia nada ni que no empeora en ningún partido. El modelo de posesión ya arranca bien casi
  todos los tramos (ver abajo).

**Bordes y equipo que reanuda del elegido** (primera semilla de cada partido que quedó afuera; el detalle por tipo
está en `EXPERIMENTOS`):

- **IDSSE:** los bordes a 0.5 s o menos suben en todos los tipos. En los tiros libres, el inicio pasa de 28% a 61% y el
  fin, de 24% a 83%.
- **Metrica:** bajan. En los tiros libres, el inicio pasa de 14% a 8% y el fin, de 24% a 5%; en los saques de arco, el
  fin de 15% a 4%.
- **Quién reanuda, por tipo** (con el equipo a 4 m, que es la receta del mismo modo que más nombra). **No es una
  comparación pareada** (review del PR #81): cada fuente se mide en las reanudaciones en las que nombra un equipo, y
  esas no son las mismas. Falta el acierto del respaldo en las reanudaciones en las que `restart_team` nombra equipo, y
  el de `restart_team` completado con el respaldo cuando no nombra:
  - el equipo que nombra `restart_team` acierta entre el 86% y el 100% en Metrica y entre el 93% y el 100% en IDSSE
    ("otro" aparte, 67% de 3); nombra entre el 68% y el 100% de las reanudaciones;
  - el respaldo del #34 (el primer equipo de la evidencia) acierta entre el 85% y el 100% en Metrica y entre el 74% y
    el 91% en IDSSE;
  - la primera etiqueta del modelo de posesión ya acierta en `main` entre el 89% y el 100% en Metrica y entre el 93%
    y el 100% en IDSSE ("otro" aparte).
- **Tramos sin equipo que reanuda y sin evidencia** (donde la regla de cambio pondría la `"H"`): el 0.99% de los frames
  vivos en Metrica y el 0.43% en IDSSE sin equipo, y el 0.67% y el 0.14% con el equipo a 4 m.

La elección se fijó en git (`c8ae6a5`) antes de tocar la reserva.

### Confirmación: no confirma, 21 de 43

`calibrate_edges.py --confirm`, en 1901 s, sobre `c8ae6a5`: el modelo con la pelota, entrenado con los 7 partidos de
selección, contra `main` con el modelo de posesión entrenado con los mismos 7, en la reserva (Metrica Game 1 con las
semillas 50-59, IDSSE 6 y 7 con las semillas 50-54). Diferencia pareada y su intervalo 5-95%:

| Condición | Metrica (inicio / final) | IDSSE |
|---|---|---|
| **Por defecto** (decide el intervalo) | **−0.0180 [−0.0319, −0.0046] / −0.0185 [−0.0323, −0.0048]** | **+0.0327 [+0.0236, +0.0425]**, 4 de 4 mitades |
| `--missing 0` | −0.0112 / −0.0120 | +0.0395 |
| `--missing 0.2` | −0.0120 / −0.0125 | +0.0414 |
| `--gap 3` | −0.0192 / −0.0190 | +0.0369 |
| `--crowd 2` | −0.0173 / −0.0172 | +0.0348 |
| `--dead-missing 0.34` | +0.0108 / +0.0104 | +0.0496 |
| `--missing 0 --dead-missing 0.34` | +0.0231 [+0.0086, +0.0386] / +0.0220 | +0.0602 |
| La pelota de las paradas dentro de la cancha | −0.0207 / −0.0205 | |
| Los 10 escenarios de `NOISE` | de −0.0237 a −0.0142 | de +0.0312 a +0.0384 |

- **IDSSE cumple sus 17 condiciones**, cada una con el intervalo arriba de 0 (el borde más bajo, +0.0229).
- **Metrica cumple 4 de 26:** solo los dos escenarios con la pelota faltante en el 34% de las paradas, las dos
  verdades. Por defecto el intervalo queda entero por debajo de 0, y lo mismo con la pelota dentro de la cancha y con
  los diez ruidos.
- **Bordes a 0.5 s o menos en la reserva** (primera semilla, v2 → modelo):
  - en IDSSE suben en todos los tipos: tiro libre, inicio 17% → 71% y fin 17% → 80%; córner, fin 75% → 100%;
  - en Metrica bajan en los tiros libres (inicio 6% → 3%, fin 28% → 3%), en el fin de los saques de arco (15% → 0%) y
    en el fin de los laterales (82% → 75%), y suben en el inicio de los saques de arco (15% → 30%) y de los laterales
    (75% → 89%).
- **Quién reanuda en la reserva:** la receta elegida no nombra equipo. El respaldo del #34 (el primer equipo de la
  evidencia) acierta entre el 89% y el 100% en Metrica y entre el 58% (córners) y el 100% en IDSSE; la primera
  etiqueta del modelo de posesión, entre el 93% y el 100%, y entre el 88% y el 100%.
- **Tramos sin equipo que reanuda y sin evidencia:** el 1.69% de los frames vivos en Metrica y el 0.60% en IDSSE.

**Por qué (hipótesis, compatible con el paso 0 pero sin aislar):** el modelo aprende de la pelota real de IDSSE dónde
termina una parada, y en Metrica ve la pelota que el banco inventa: se mueve despacio durante toda la parada, así que el modelo da la
parada por terminada antes (el fin de los tiros libres cae del 28% al 3%). Cuando el banco deja sin pelota un tercio
de las paradas (`--dead-missing 0.34`, como en la ventana pública), el modelo ve menos pelota inventada y Metrica pasa
a favor. No sirve para decidir: cambiar el escenario por defecto después de ver esto sería acomodar la regla (ADR-010).

**Decisión:** con la regla del ADR-011 no se confirma una mejora y no se vuelve a elegir con este resultado.
`stops_model.json` queda como el modelo identidad y el CSV no cambia; `live_model.json` tampoco. No hay nada que
correr sobre BAR-ATH para este ADR. Igual Ivan lo corrió en `9ce867a` y dio el `sha256` de la entrega. El código
nuevo no entra a `main` (ver "Status"). Con el modelo identidad no cambia ninguna etiqueta: el `sha256` sintético de
`repro_check.py` es el de `main`. En su rama quedan listos, para un candidato futuro, el equipo que reanuda en el
decodificador y el modelo sin pelota.

**Lo que cambió en `main`.** Este texto decía que el #77 entró "mientras corría" la confirmación.

**Corrección (1/11, review del PR #81):** el historial dice otra cosa (31/10, hora de Argentina):
- el #77 se mergeó a `main` a las 15:54;
- el primer commit de este ADR es de las 16:01 (`a903761`), la elección de las 16:16 (`c8ae6a5`) y el resultado de
  las 16:50 (`6544a04`).

Esta rama partía de `2987431` y no integró `main` hasta después de la confirmación (`f29a884`, 16:54). El #77
reentrena el modelo de posesión con las posesiones de menos de 5 s contando 3 veces y pasa la entrega a `f2460d57…`.
Su confirmación, sobre otro candidato, usó las mismas semillas de la reserva (50 en adelante) y quedó registrada en su
rama a las 10:39 (`67b8fe6`), antes de que este ADR las fijara. Git registra el orden de los commits, no el momento
en que corrió cada cosa. Por eso:

- **Esta comparación es contra el `main` de `2987431`**, con la receta del ADR-014 sin ese peso. Con `main` integrado,
  `calibrate_edges.py` entrena el modelo de posesión con el peso nuevo, porque usa `calibrate_live.fit`.
- **No se repite la confirmación contra el `main` nuevo.** El ADR-011 confirma una sola vez, y un candidato que no
  confirmó no se vuelve a probar con la misma receta. Lo que falla está en los bordes de las paradas de Metrica, que el
  modelo de posesión no mueve.
- **Las dos confirmaciones vieron la reserva con las mismas semillas**, y ninguna eligió con ella. El ADR-017 (#80)
  la miró otra vez, con las semillas 60-69 y 60-64. Para el próximo candidato, la reserva lleva siete miradas:
  ADR-010, tres del ADR-014, el #77, el ADR-017 y esta. No es una validación independiente nueva.

### El #34, criterio por criterio

- **Acierto de quién reanuda por tipo, contra el respaldo:** en `EXPERIMENTOS` (selección y reserva). Cuando
  `restart_team` nombra un equipo, acierta entre el 93% y el 100% en IDSSE y entre el 86% y el 100% en Metrica. El
  primer equipo de la evidencia acierta entre el 74% y el 91%, y entre el 85% y el 100%. Pero `restart_team` nombra
  solo entre el 68% y el 100% de las reanudaciones, y cada acierto se mide sobre un subconjunto distinto. No demuestra
  que `restart_team` sea mejor que el respaldo en las mismas reanudaciones (ver "Selección").
- **El `spellF1` no empeora en ningún partido y mejora en la media:** no se cumple. Las variantes con y sin equipo
  difieren poco en la selección, pero no se midió la diferencia pareada por partido ni su intervalo. Con el modelo sin
  la pelota, en Metrica, el equipo baja la media de +0.0011 a +0.0000. El modelo de posesión ya acierta la primera
  etiqueta del tramo en el 89-100% de las reanudaciones. Este texto decía que el equipo "no mueve el `spellF1`" y
  "tampoco empeora"; las dos afirmaciones se retiran (review del PR #81).
- **Tests sintéticos**, en la rama `feat/bordes-convencion-metrica-32-34-codigo`: `tests/test_stops.py` (un lateral con el que marca más cerca de la pelota que el que saca, y un
  córner), `tests/test_possession.py` (un tramo sin evidencia arranca con el que reanuda) y `tests/test_live.py` (el
  decodificador desde el equipo que reanuda, contra la fuerza bruta).
- **La `"H"` arbitraria:** documentada acá. El comentario en `confirm_changes` quedó en la rama del código. Solo existe en el modo `rule`, que no se entrega, y en un
  tramo sin equipo que reanuda y sin evidencia: el 0.4-1.7% de los frames vivos en los bancos. En el decodificador
  del ADR-014 la `"H"` solo resuelve un empate exacto de sumas enteras, y con equipo que reanuda gana ese equipo.

### Lo que sigue (lo decidió Lautaro en el PR #81, el 1/11)

1. **El banco de Metrica y la pelota de las paradas: nada antes del congelamiento (14/11).** Es la hipótesis que
   queda de lo que separa a los bancos para cualquier modelo que lea la pelota. Aislarla no cambia la entrega, y
   arreglar el banco necesita su propio ADR, volver a medir las líneas de base y un candidato que después transfiera a
   la pelota del ATD en las paradas, que no se puede medir (`AGENTS.md`): es lo que le pasó al ADR-017. Queda para
   después de la fase 1. Si se retoma, primero se aísla en la selección (ver el paso 0), y cambiar cómo el banco la
   restaura (por ejemplo, dejarla faltar donde sample-data no la trae) va en un ADR propio, que vuelve a medir las
   líneas de base y se decide sin mirar este resultado.
2. **El modelo sin la pelota: no se abre como candidato.** Fue el único positivo en los dos bancos en la selección
   (+0.0011 y +0.0091), pero +0.0011 en Metrica es una media sin intervalo, que no alcanza para afirmar una mejora
   (`AGENTS.md`, "Calibración y resultados"), y es unas ocho veces menos que lo que ganó el ADR-017 en Metrica en su
   confirmación (+0.0093). Con la reserva en siete miradas, no se gasta una octava en él: el tiempo hasta el
   congelamiento va al protocolo del modelo de posesión (#83 a #86).
3. **El equipo que reanuda: el #34 se cerró el 31/10 como no planificado** (y el #32, como completado). Con el
   modelo de posesión no se mostró que aporte: las diferencias fueron chicas y sin intervalo, y el acierto contra el
   respaldo no está pareado. Por eso el cierre del #34 se apoya solo en el oráculo del PR #80 (arrancar cada tramo
   vivo con su primer equipo verdadero da −0.003 en Metrica y −0.002 en IDSSE), no en el equipo predicho de este ADR.
   Una señal nueva del modelo de posesión, medida en pares y con bootstrap, va por el #86, con el protocolo del #83
   (ADR-019).

## Consequences

### Positive

- **Cierra lo que dejó abierto el ADR-010:** su paso 1 y los cinco puntos de la revisión, medido contra el pipeline
  que se entrega hoy.
- **El equipo que reanuda llega al CSV por primera vez**, si confirma: hasta ahora solo lo leía la regla de cambio,
  que desde el ADR-014 no corre en la entrega.
- **El paso 0 responde la mitad de la pregunta del ADR-010** con datos de la selección: no es la velocidad ni la
  convención. La pelota que inventa el banco de Metrica es la hipótesis que queda, sin aislar.
- **Sigue exacto:** el decodificador suma un costo entero al primer frame, y el modelo sin pelota usa las mismas
  señales enteras.

### Negative

- **La reserva se reusa otra vez:** el ADR-010; la confirmación y los dos controles del ADR-014; el #77, que antes
  había usado las mismas semillas, desde la 50; y el ADR-017 (#80), con las semillas desde 60. Sin elegir con ella,
  es lo que prevé el ADR-011, pero no es una reserva virgen.
- **El banco de Metrica castiga lo que el modelo aprende de una pelota real.** Si gana el modelo sin pelota, la
  entrega deja de usar una señal que en el ATD sí existe.
- **El modelo de posesión no se reentrena con las paradas nuevas:** en la entrega ve paradas que no vio al entrenar.
- **La convención de Metrica puede costar en IDSSE**, cuya verdad es la de DFL, en el inicio de los tiros libres.

### Neutral

- `dead_mask_v2` y `live_model.json` no cambian.
- Con el modelo identidad, el CSV es el de hoy, frame por frame: el equipo inicial solo existe si `team_radius_cm` es
  mayor que 0.

## Alternatives Considered

### Reentrenar el modelo de posesión con las paradas nuevas (ADR-014, Neutral)

Es lo más fiel al pipeline, pero hace falta un modelo de posesión por receta de paradas y por pliegue, con sus filas
recalculadas sobre las paradas movidas de cada variante. Las filas del ADR-014 salen de `dead_mask_v2`, que no
cambia, y la confirmación mide la composición con la receta que se entrega. Queda para cuando un candidato confirme,
si el equipo lo pide.

### El equipo que reanuda como estado forzado

Arrancar siempre con el que reanuda, sin costo para salir, o forzar sus primeros frames. Una reanudación mal nombrada
dejaría una posesión corta falsa, que es justo lo que el #34 quiere evitar. Con el costo de un cambio, el
decodificador sale del equipo inicial solo si las señales lo justifican.

### Un indicador de banco como señal

Una señal que diga "IDSSE" o "Metrica" dejaría que los árboles aprendan cada convención por separado. Al inferir habría
que ponerla en "Metrica", y la rama de Metrica solo vio dos partidos de selección, sin pelota. Además absorbe toda
diferencia entre bancos, no solo la convención.

### Entrenar los bordes solo con Metrica

Es la convención del concurso sin traducir nada, pero son dos partidos de selección y el modelo no vería nunca la
pelota. El paso 0 lo mide como referencia.

### La velocidad de las posiciones en IDSSE

La que el banco de Metrica calcula. El paso 0 muestra que no acerca los bancos (cociente 0.996-0.997, y los mismos
bordes en Metrica), y el ATD trae la velocidad del proveedor, que es la que lee `possession.py`.

### La convención como opción de la selección

Entrenar también con la convención de cada banco, como control. El paso 0 muestra que no cambia la transferencia, y
el ADR-010 pide la de Metrica porque es la del concurso. Sumarla duplicaría las recetas sin una pregunta nueva.

### Corregir cómo el banco restaura la pelota de las paradas

Es la causa probable según el paso 0 (sin aislar), y queda pendiente desde el ADR-007. Cambiarlo obliga a volver a medir todas las
líneas de base del banco de Metrica y va en un ADR propio, que tiene que decidirse sin mirar este resultado. Queda
para después de la fase 1 (ver "Lo que sigue").

### Más recetas (ventanas de 5 s, 15 hojas)

En el ADR-010 empataron (+0.0202 las dos de 31 hojas). Fijar la receta deja nueve candidatos en lugar de treinta y
seis, y menos caminos para elegir por ruido.

## References

- ADR-007, ADR-010, ADR-011, ADR-014 y ADR-015. ADR-017 (PR #80, `Rejected`): otro candidato para el fin de las
  paradas, la patada, que confirmó en los bancos abiertos y no actúa en BAR-ATH.
- `calibrate_edges.py`, `calibrate_live.py`, `possession.py` (`refine`, `restart_team`, `decode_live`),
  `explore/edge_clock.py`, `explore/edge_transfer.py`, `explore/edge_offsets_by_kind.py`.
- Issues #32, #34, #83 y #86; PR #57 (ADR-010), #65 (ADR-014) y #81 (este ADR, con la revisión de Ivan, la aprobación
  de Lautaro y el review automático).
- El código, sin mergear: rama `feat/bordes-convencion-metrica-32-34-codigo` (`ac041b7`).
