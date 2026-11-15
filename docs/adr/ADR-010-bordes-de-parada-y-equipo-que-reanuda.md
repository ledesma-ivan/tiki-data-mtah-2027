---
artifact: adr
version: "1.0"
created: 2026-10-29
status: proposed
---

# ADR-010: Bordes finos de las paradas y equipo que reanuda, con un modelo entrenado en datos abiertos

## Status

Proposed (2026-10-29). Lautaro lo aprobó el 29/10 con un agregado: la medición sigue el ADR-011 (el banco
decide también con IDSSE, PR #55), y la corrida que decide va cuando entren el #52 y el #53. Necesita la
revisión de otra persona en el PR para pasar a `Accepted`.

**Date:** 2026-10-29
**Deciders:** Lautaro Bursese (con Claude)
**Issues:** #32 (incluye el #9) y #34, que el propio issue permite resolver en el mismo ADR

## Context

### Dónde está lo que falta del detector

Los oráculos de `explore/oracles.py` (fila del 29/10 en `docs/EXPERIMENTOS.md`) reemplazan una pieza
del pipeline de `main` (`98479c1`: `dead_mask_v2` + la evidencia y la regla de cambio del ADR-009) por la
verdad, y miden cuánto sube `spellF1` con la pelota degradada del banco. La diferencia es pareada contra
el pipeline de `main`, con 1000 remuestreos:

| Oráculo | Metrica (3 partidos x 10 semillas) | IDSSE (14 mitades x 5 semillas) |
|---|---|---|
| Línea de base | 0.541 | 0.412 |
| `D` perfecto | +0.095 [+0.082, +0.108] | +0.071 [+0.063, +0.078] |
| Bordes de las paradas encontradas (inicio, fin y fusiones) | +0.073 [+0.062, +0.084] | +0.046 [+0.040, +0.052] |
| Solo el borde de fin / solo el de inicio | +0.041 / +0.033 | +0.022 / +0.020 |
| Paradas que faltan / paradas que sobran | +0.013 / +0.009 | +0.010 / +0.014 |
| Equipo que reanuda (el equipo verdadero al empezar cada tramo vivo) | +0.007 [+0.002, +0.012] | +0.020 [+0.015, +0.025] |

- **El v2 encuentra casi todas las paradas** (91% en Metrica y 94% en IDSSE, contando una parada como
  encontrada si el v2 cubre la mitad), pero **solo la mitad de sus bordes cae a 0.5 s o menos**. La
  mediana está cerca de 0; el 10-90% va de −2.6 a +1.8 s en el inicio y de −2.0 a +2.2 s en el fin
  (Metrica).
- **Depende del tipo de reanudación** (Metrica, bordes a 0.5 s o menos, inicio / fin):

  | Tipo | Paradas | Encontradas | Inicio | Fin | Mediana del fin |
  |---|---|---|---|---|---|
  | Lateral | 38% | 99% | 76% | 72% | +0.16 s |
  | Tiro libre | 32% | 82% | 13% | 29% | −0.56 s |
  | Saque de arco | 16% | 81% | 62% | 18% | −0.28 s |
  | Córner | 9% | 96% | 80% | 31% | −1.08 s |
  | Saque inicial | 4% | 100% | 38% | 50% | +0.20 s |

  Los ajustes del v2 (`DEAD_LEAD`, 1 s antes, y `DEAD_TRIM`, 1.52 s antes) son los mismos para todos los
  tipos. El ADR-007 ya lo anotaba como riesgo ("los ajustes de borde salen de sample-data").
- **El equipo que reanuda** sale bien en el 82% (Metrica) y el 71% (IDSSE) de las paradas con el `D` del
  v2, y en el 96% y el 82% con el `D` perfecto. Hoy cada tramo vivo arranca con "el primero que aparece
  en la evidencia", o con `"H"` si no hay ninguna (`confirm_changes`).
- **Las paradas cortas que se escapan valen poco** (+0.013 y +0.010): la idea original del #32, buscar con
  formaciones las paradas que el v2 no ve, no es donde están los puntos.

### Por qué un modelo entrenado

Lautaro pidió (29/10) el producto más preciso posible, sin escatimar esfuerzo ni entrenamiento, dentro de
las reglas y de la fecha. Un borde fino depende de cosas que una constante no ve: cómo frena y arranca el
bloque, si la pelota se ve y cómo se mueve, dónde está el que va a sacar y qué tipo de reanudación es.
Ahora hay 10 partidos abiertos con verdad (3 de Metrica y 7 de IDSSE): el ADR-007 dejaba el clasificador
"para cuando haya más datos (IDSSE)".

### Reglas que condicionan el diseño

- **Se entrena solo con otros partidos.** Nada de etiquetas ni de entrenamiento sobre BAR-ATH (issues 2,
  8 y 10 del repo oficial).
- **Ninguna IA ve los datos del partido** (`AGENTS.md`).
- **El CSV tiene que salir igual byte a byte en cualquier máquina** (#6, e issue 11 del repo oficial: el
  entrenamiento puede no ser exacto, pero la entrega sí, con los pesos publicados).
- **Se decide con el banco** (ADR-006, y el ADR-011 para IDSSE), y cada ADR dice cómo se mide.

## Decision

### Objetivos, no objetivos y antiobjetivos

- **Objetivos:** bordes de parada finos según el tipo de reanudación, y el equipo que reanuda, con una
  mejora de `spellF1` que se sostenga en Metrica y en IDSSE, y un CSV exacto en cualquier máquina.
- **No objetivos:**
  - encontrar las paradas que faltan o descartar las falsas (queda como segunda etapa, si sobra tiempo);
  - cambiar la evidencia o la regla de cambio del ADR-009;
  - la posesión con juego vivo, que es el #49;
  - el Smart Tagging (#8), el video y la homografía.
- **Antiobjetivos** (fracasa aunque "ande"):
  - un modelo que gana en el banco por los artefactos de la pelota restaurada de Metrica (ADR-007:
    queda casi quieta y fuera de la cancha en las paradas) y pierde en el ATD;
  - un parámetro elegido mirando la ventana pública;
  - un CSV que cambia de una máquina a otra;
  - una mejora que aparece en Metrica y no en IDSSE.

### El pipeline

1. **Las paradas las sigue encontrando `dead_mask_v2`**, sin cambios. Cada parada del v2 es un candidato.
2. **Un modelo por frame da la probabilidad de `D`** en una ventana alrededor de cada borde del v2: de
   unos segundos antes a unos segundos después del inicio, y lo mismo con el fin. El tamaño de las
   ventanas se elige en la selección; el 10-90% de los bordes de hoy cae entre −2.6 y +2.2 s, y en los
   saques de arco llega a ±5 s.
3. **El borde nuevo es el escalón que mejor ajusta esas probabilidades**: el frame `t` de la ventana que
   minimiza los frames que quedan del lado equivocado (marcados como `D` antes del borde de inicio, o
   como vivos después). Empates: el más temprano. Las ventanas no cruzan la parada anterior ni la
   siguiente, y una parada no queda más corta que un frame.
4. **El tipo de reanudación** de cada parada sale de un clasificador de la formación en los segundos
   previos al fin: lateral, córner, saque de arco, tiro libre, saque inicial u otro. Entra como señal al
   modelo de bordes y define dónde se espera al que saca (la línea de banda, el córner, el área chica o
   el centro).
5. **El equipo que reanuda** es el del que saca: el jugador más cercano al punto de reanudación en el
   borde de fin nuevo. `confirm_changes` recibe ese equipo como el inicial del tramo vivo siguiente (un
   parámetro nuevo, opcional). Si no hay un candidato claro, queda el comportamiento de hoy. La regla de
   cambio sigue igual: si la evidencia contradice al equipo inicial durante N, cambia.

### Las señales

Solo con lo que `possession.label` ya recibe (`players[n, k, 3]`, `ball[n, >=2]`, `team[k]`), sin
identidad de jugadores (los 46 slots del ATD no identifican a nadie) y sin Smart Tagging, video ni
homografía. Familias:

- **El movimiento del bloque:** fracción de jugadores lentos (la señal del v2), velocidad y aceleración
  colectivas en varias escalas de tiempo y su cambio.
- **La pelota cuando se ve o se interpola** (`ball_position`, ADR-009): velocidad, aceleración,
  distancia a las líneas, si está fuera de la cancha y cuánto hace que no se ve.
- **La reanudación:** el tipo previsto y el movimiento del jugador más cercano al punto de reanudación.

Todas se calculan en enteros: posiciones en centímetros, velocidades en cm/s y conteos de frames.

### El modelo y la exactitud

- **Árboles de decisión potenciados** (gradient boosting), chicos y explicables. Se entrenan con
  scikit-learn en un script aparte (`calibrate_edges.py` o parecido, como pide `AGENTS.md` para todo
  umbral), con sus dependencias fijadas en un archivo propio (`requirements-train.txt`). `possession.py`
  no las necesita.
- **El modelo entrenado se exporta** a un archivo del repo con umbrales y valores de hoja enteros.
  `possession.py` lo evalúa solo con operaciones enteras de `numpy`, así que da lo mismo en cualquier CPU.
- **Datos de entrenamiento:** los partidos de selección (ver "Cómo se mide"), con la pelota degradada por
  `bench.degrade` en varias semillas y los jugadores degradados (ver abajo). La verdad de los bordes:
  `BallStatus` en IDSSE, y los eventos (ADR-003) en Metrica. El tipo de reanudación: los `SET PIECE` y
  `GOAL KICK` de Metrica, y los eventos de reanudación de DFL en IDSSE (`idsse_dead_labels.RESTARTS`),
  llevados a frames con los tiempos de `load_ball`. El diseño pedía corregir además el desfasaje de reloj de
  cada partido (ADR-003, medición 3); la implementación no lo corrige (ver "Lo que decidió la
  implementación").
- **La degradación de los jugadores** es la de la revisión del #45: `noisy_players` y sus 10 escenarios
  (`NOISE`) del script plegado en la revisión de GitHub del 29/10 a las 12:05. Incluye intercambios de
  identidad de ~1 s entre los jugadores de `H` y de `A` más cercanos a la pelota (los dos a 5 m o menos),
  ruido gaussiano de posición suavizado en 1 s (o frame a frame, el temblor) y slots perdidos en ráfagas
  de 2 s (`explore/dead_v2_players_noise.degrade_players`). Como parte de este trabajo pasa a `explore/`,
  para que el entrenamiento y la confirmación usen exactamente la misma.

### La pelota de las paradas en el banco

En sample-data la pelota no existe en las paradas: el banco la restaura interpolando, y queda casi
quieta y fuera de la cancha en el 27-42% de los frames `D` (ADR-007). Además, el patrón del banco está
invertido respecto de la ventana pública. En el banco la pelota se ve siempre en las paradas y falta en
el 45% del juego vivo; en la ventana pública falta en el 34% de los `D` y en el 6.5% de los vivos
(ADR-006). Para que el modelo no aprenda ninguno de los dos artefactos:

- **Lo que dice la pelota se aprende solo de IDSSE**, que trae la pelota real de las paradas. En
  Metrica, la pelota se tapa en todos los frames de cada ventana, antes y después del borde. Así no queda
  ningún atajo de "pelota que falta = parada": de Metrica se aprende solo el movimiento de los jugadores.
- **En IDSSE se entrena con varios patrones de pelota faltante**, que cubren lo que no sabemos del ATD:
  con juego vivo, entre el 6.5% y el 45%, y en las paradas, entre el 0 y el 34% (`live_missing` y
  `dead_missing` de `bench.degrade`).
- **Al confirmar en Metrica**, todos los pipelines ven la pelota restaurada del banco. Además de las
  condiciones del ADR-006, que ya incluyen `--dead-missing 0.34`, la mejora tiene que sostenerse con la
  pelota de las paradas metida dentro de la cancha, como en el ADR-007.

`bench.py` no cambia: corregir cómo restaura el banco es un pendiente aparte (ADR-007) y obligaría a
volver a medir todas las líneas de base.

### Plan B y cómo se elige entre candidatos

El plan B son los ajustes de borde por tipo, como constantes: un `lead` y un `trim` por tipo de
reanudación, en lugar de los dos de hoy para todos. Usa el mismo clasificador de tipo.

- **Hay cuatro candidatos:** el plan B y el modelo, cada uno con el paso 5 (el equipo que reanuda) y sin él.
- **Se eligen en la selección**, con la regla de barridos del ADR-006: gana el de mayor diferencia
  pareada media contra `main`. Se usa validación cruzada dejando un partido afuera sobre los 7 partidos de
  selección (Metrica 2 y 3, IDSSE 1 a 5), así que tanto el modelo como las constantes del plan B se
  puntúan en partidos que no vieron.
- **La elección se fija antes de tocar la reserva**, y solo ese candidato se confirma. Si no pasa la
  confirmación, no se confirma ninguna mejora y `main` queda como está: no se vuelve a elegir con ese
  resultado (ADR-006).
- **Corte del 3/11** (lo fija el #32): compite lo que esté listo. Si el modelo no llega, el candidato es
  el plan B.

### Lo que decidió la implementación

- **Dónde vive:** en `possession.py`, en una sección propia, y no en un módulo aparte. `label` lo llama, y
  el código usa `ball_position`, `runs` y las constantes del v2; además, los `calibrate_*.py` ya importan
  de `possession.py`.
- **Señales por frame** (`FRAME_FEATURES`, 20):
  - jugadores seguidos;
  - % de lentos (< 1.75 m/s) y velocidad media, del frame y en ventanas centradas de 1 s y 3 s;
  - velocidad máxima y cantidad de rápidos (≥ 4 m/s);
  - cambio de la velocidad media entre el que viene y el anterior, en 1 s y 3 s, y del % de lentos en 1 s;
  - pelota vista y frames sin verla, con tope de 10 s;
  - posición conocida (`ball_position` con el tope de 2 s del ADR-009);
  - velocidad de la pelota en 0.2 s, si está fuera de la cancha y su distancia con signo a la línea más
    cercana;
  - distancia y velocidad del jugador más cercano a la pelota.

  El modelo de bordes suma cuatro datos de la parada: el desfasaje al borde del v2, el lado (inicio o
  fin), el largo de la parada y el tipo (`EDGE_FEATURES`). Sin dato, la señal vale `-1_000_000`.
- **Formación para el tipo** (`STOP_FEATURES`, 13), en los 2 s antes del fin del v2:
  - mínimos de distancia a la banda, al banderín, al centro y al medio del área chica;
  - jugadores dentro de las áreas;
  - % de jugadores en su propio campo y cantidad dentro del círculo central;
  - distancia entre las x medias de los equipos;
  - la pelota y sus distancias;
  - el largo de la parada.
- **Ventanas:** 3 s o 5 s a cada lado, según la selección. Para entrenar se usa uno de cada dos frames.
- **Árboles:** `HistGradientBoostingClassifier` de scikit-learn 1.9.1, sin parada temprana y con semilla 0.
  - **Bordes:** 200 iteraciones, tasa 0.1, 15 o 31 hojas (según la selección) y 200 filas por hoja como
    mínimo.
  - **Tipo:** 50 iteraciones y 8 hojas.
- **Exportación:** los umbrales se redondean con `floor`, porque las señales son enteras, y las hojas van
  en millonésimas del puntaje. Un tipo que el entrenamiento no vio nunca gana. Un test compara las
  decisiones con las de scikit-learn.
- **Pesos:** cada partido pesa lo mismo, en los bordes y en el tipo.
- **La pelota:**
  - En Metrica el modelo no la ve: se tapa en todo el partido, tanto para las señales como para la
    formación. El v2 sí la usa para encontrar las paradas, como en la inferencia.
  - En IDSSE se entrena con seis pelotas por partido: falta en el 6.5%, el 20% o el 45% del juego vivo,
    y en el 0% o el 34% de las paradas.
- **Tipo en IDSSE:** el evento de reanudación de DFL más cercano al fin de cada `D`, a 2 s o menos. Si no
  hay evento, la parada no entrena el clasificador. El penal y la pelota al árbitro van a "otro".
  - **Desvío del diseño:** no se corrige el desfasaje de reloj de cada partido. Por eso queda sin tipo el
    31% de las paradas de IDSSE (161 de 522 en la selección y 69 de 191 en la reserva).
  - Corregirlo cambia los datos de entrenamiento, así que va con el próximo candidato.
- **Jugadores para entrenar:** limpios. El ruido de `explore/player_noise.py` se usa solo en la
  confirmación (criterio 4).
  - **Desvío del texto aprobado,** que pedía entrenar también con jugadores degradados.
  - La confirmación con los 10 ruidos dio positiva en los dos bancos, así que no cambió la decisión.
  - Entrenar con ruido va con el próximo candidato.
- **Equipo que reanuda:** sin equipo, o con un radio de 2 m o de 4 m, según la selección.
- **Plan B:** por tipo previsto, la mediana del desfasaje del inicio y del fin del v2 contra la verdad.
- **Criterio 2:** la pelota restaurada se mete en la cancha como en `explore/dead_v2_off_pitch.py
  --clip-restored`.
- **Mientras no se confirme un candidato,** `stops_model.json` es el modelo identidad
  (`calibrate_edges.py --identity`): deja las paradas del v2 como están y no nombra a nadie. El CSV queda
  igual al del ADR-009.

## Cómo se mide

**Partición, fijada antes de correr nada:**

- **Selección:** Metrica Games 2 y 3 (semillas 0-9) y los partidos 1 a 5 de IDSSE, por orden de nombre de
  archivo (10 mitades, semillas 0-4). Ahí se entrena y se elige todo, con validación cruzada dejando un
  partido afuera.
- **Confirmación:** Metrica Game 1 con las semillas 20-29 y los partidos 6 y 7 de IDSSE (4 mitades,
  semillas 20-24). Nadie los mira antes de la confirmación.

**El candidato elegido se confirma si**, contra el pipeline de `main` (`radio` en `bench.py`):

1. en Metrica Game 1 cumple las dos condiciones del ADR-006: el intervalo por defecto entero por encima
   de 0 con las dos verdades, y positivo en los seis escenarios de sensibilidad;
2. en Metrica Game 1, con la pelota de las paradas metida dentro de la cancha, la diferencia sigue
   siendo positiva;
3. en las 4 mitades reservadas de IDSSE cumple las mismas dos condiciones (ADR-011): el intervalo por
   defecto entero por encima de 0 y la diferencia positiva en los seis escenarios;
4. con los jugadores degradados (los 10 escenarios de `NOISE`, en la reserva de Metrica y de IDSSE), la
   diferencia pareada media no queda en 0 o por debajo en ningún caso, como en el ADR-007. Los
   intervalos se reportan.

**Cuándo:** la corrida que decide va cuando entren el #52 (la cancha de cada partido en las distancias) y el
#53 (las velocidades en los cambios de período y de jugador), que corrigen las entradas del banco, y con el
ADR-011 aceptado. La selección y la confirmación ya corrieron con el banco de `main` (ver "Resultados"),
antes de lo aprobado. Esa confirmación fue completa, así que cuenta como la única de este candidato
(ADR-011: se confirma una sola vez). Lo que se corra después del #52 y el #53 es un candidato nuevo, con su
propia selección.

**El modelo que se entrega:** una vez confirmado, se vuelve a entrenar con la misma receta (señales,
hiperparámetros y semillas fijos) sobre los 10 partidos. Son un 30% más de datos y Lautaro pidió la
mayor precisión posible. Lo que confirma la reserva es la receta; los pesos entregados son los de ese
último entrenamiento, y el documento técnico lo dice así.

**Se reporta además:** los bordes por tipo (mediana y parte a 0.5 s o menos), el acierto del tipo de
reanudación, el acierto del equipo que reanuda por tipo, y los oráculos de `explore/oracles.py` con el
detector nuevo, para ver qué parte del techo de los bordes se capturó.

**Sobre BAR-ATH lo corre una persona,** en dos máquinas: mismo `sha256`, conteos `H/A/D/X` y validador
OK. La ventana pública, solo para verificar (`AGENTS.md`). Una fila por corrida en `EXPERIMENTOS` y una
en la tabla del README.

## Resultados (29/10, provisionales)

**Selección** (`calibrate_edges.py --select`: cada receta se entrena en 6 de los 7 partidos de selección y
se puntúa en el que queda afuera). Diferencia pareada media contra `radio`; la tabla completa está en
`EXPERIMENTOS`:

| Receta | Metrica | IDSSE | Media |
|---|---|---|---|
| Modelo de 3 s, 31 hojas, equipo a 4 m (elegido) | +0.0023 | +0.0381 | +0.0202 |
| Modelo de 5 s, 31 hojas, equipo a 4 m | −0.0031 | +0.0435 | +0.0202 |
| Plan B, equipo a 2 m | +0.0017 | +0.0158 | +0.0087 |
| Plan B | −0.0020 | +0.0072 | +0.0026 |

**Confirmación provisional** (`calibrate_edges.py --confirm`, en la reserva): **no confirma**, porque se
cumplen 41 de las 43 condiciones.

- **IDSSE 6 y 7:**
  - por defecto, +0.0458 [+0.0347, +0.0568], con las 4 mitades a favor;
  - en los seis escenarios y con los 10 ruidos de jugadores, entre +0.035 y +0.055.
- **Metrica Game 1:**
  - por defecto, +0.0085 [−0.0038, +0.0208] con la verdad desde el inicio y +0.0086 [−0.0033, +0.0205]
    desde el final. El intervalo toca el 0, y son las dos únicas condiciones que fallan;
  - los seis escenarios dan positivo. Con `--dead-missing 0.34` da +0.0256 [+0.0140, +0.0384], y con
    `--missing 0 --dead-missing 0.34`, +0.0346 [+0.0203, +0.0488];
  - con la pelota de las paradas dentro de la cancha, +0.0083; con los 10 ruidos, entre +0.0006 y +0.0070.
- **Bordes a 0.5 s o menos en la reserva (v2 → modelo):**
  - en IDSSE mejoran en todos los tipos; en los tiros libres, el inicio pasa de 19% a 73% y el fin, de 14% a
    78%;
  - en Metrica, algunos mejoran (inicio de saque de arco de 15% a 40%, inicio de córner de 64% a 82%) y
    otros empeoran (fin de lateral de 82% a 64%, fin de tiro libre de 28% a 16%).
- **Tipo de reanudación y equipo que reanuda:** el tipo acierta entre el 82% y el 100% según cuál sea, y el
  equipo, entre el 91% y el 100% de las veces que lo nombra.

**Por qué Metrica no acompaña** (medido en la selección, no en la reserva):

- **No es la pelota que inventa el banco.** Con la pelota tapada, Metrica da lo mismo, y la pelota es casi
  toda la ganancia de IDSSE.
- **Los bancos no coinciden en dónde caen los bordes del v2** respecto de su verdad
  (`explore/edge_offsets_by_kind.py`):
  - en IDSSE, la pelota real fuera de la cancha ya clava el fin del v2 al frame en laterales, saques de arco
    y córners;
  - en los tiros libres, el v2 termina 1.54 s antes en IDSSE y 0.56 s antes en Metrica, y empieza a tiempo
    en IDSSE y 0.76 s tarde en Metrica.

  El modelo aprende la corrección de IDSSE, y en Metrica se pasa.
- **Puede ser la velocidad o la convención de cada proveedor.** En IDSSE la velocidad la da el proveedor; en
  Metrica sale de las posiciones. Importa porque la verdad oficial la arma Metrica, igual que la de nuestro
  banco de Metrica.
- **El resultado depende de cuánta pelota falte en las paradas.** El escenario por defecto la pone en todas;
  en la ventana pública falta en el 34% (ADR-002), y con ese valor Metrica sí pasa. No sirve para decidir
  esta vez: cambiar el escenario por defecto después de ver este resultado sería acomodar la regla.

**Decisión:** con la regla del ADR-011 no se confirma una mejora, y no se vuelve a elegir con este
resultado. `stops_model.json` queda como el modelo identidad, así que el CSV no cambia. Esta confirmación
cuenta como la única del candidato: no se repite después del #52 y el #53. Si el equipo decide que no cuenta,
porque se corrió antes de lo aprobado, tiene que quedar escrito acá y en `EXPERIMENTOS` que la reserva ya se
miró. Los oráculos con el detector nuevo y la corrida sobre BAR-ATH quedan para cuando haya un candidato
confirmado.

**Lo que sigue** (lo decide el equipo):

1. Medir en la selección qué separa a los bancos (la velocidad del proveedor contra la de las posiciones, o
   la convención de cada uno) y entrenar los bordes con la convención de Metrica, que es la del concurso. Es
   un candidato nuevo: va con su propia selección y su confirmación. El mismo candidato puede sumar lo que
   marcó la revisión del branch:
   - el desfasaje de reloj de IDSSE para los tipos;
   - jugadores degradados al entrenar;
   - pesos que no achiquen las hojas;
   - tipos predichos fuera de pliegue;
   - tapar en IDSSE también, alguna vez, toda la pelota, para que "sin pelota" no signifique "Metrica".
2. Que una persona mida en BAR-ATH, sin pasarlo por ninguna IA, si la velocidad del ATD se parece a la de un
   proveedor o a la que sale de las posiciones. Alcanza con un agregado como el cociente que imprime
   `explore/idsse_bench.py`.
3. Si el equipo quiere revisar el escenario por defecto del banco, va en un ADR propio, que tiene que
   decidirse sin mirar este resultado.

## Consequences

### Positive

- Ataca los dos huecos del detector que más valen (los bordes y quién reanuda) con una sola pieza.
- El tipo de reanudación queda calculado: sirve para el documento técnico y, después, para la fase 2.
- La inferencia sigue exacta y con `numpy` solo.

### Negative

- **Más piezas y un archivo de modelo**: más difícil de revisar que dos constantes.
- **Sobreajuste**: 10 partidos son pocos; se acota con árboles chicos, validación por partido y la
  confirmación reservada.
- **La distancia entre el banco y el ATD**: el modelo aprende de la degradación simulada, no del ATD real.
- **Una dependencia nueva para entrenar** (scikit-learn), aunque no para correr el pipeline.
- **Los pesos que se entregan no son exactamente los que pasaron la confirmación**: se reentrenan con los
  10 partidos y lo confirmado es la receta.
- **En Metrica el modelo no aprende nada de la pelota**: depende de que IDSSE alcance para esas señales.

### Neutral

- `dead_mask_v2` no cambia: el modelo solo mueve sus bordes y nombra al que saca.

## Alternatives Considered

### Ajustes de borde por tipo, como constantes

Simple y exacto, pero no ve cada parada. Queda como plan B y como la línea a superar.

### Un detector de `D` entero aprendido, que reemplace al v2

Resolvería también las paradas que faltan y las que sobran, pero valen +0.01 cada una y el riesgo es
mayor. Queda como segunda etapa, con el mismo modelo, si sobra tiempo.

### Formaciones para encontrar paradas cortas (la idea original del #32)

Medido: +0.013 y +0.010. Las formaciones se usan, pero para el tipo y el que saca.

### Smart Tagging como pista de tiempo

No hay datos abiertos con Smart Tagging para calibrarlo (#8).

### Modelos de secuencia profundos

Con 10 partidos hay pocos datos, y la inferencia exacta es más difícil. Se puede revisar si aparece más
tracking abierto (#49).

## References

- `explore/oracles.py` y su fila del 29/10 en `docs/EXPERIMENTOS.md`
- `possession.py` (`dead_mask_v2`, `confirm_changes`), `bench.py`, `explore/idsse_bench.py`,
  `idsse_dead_labels.py`
- ADR-003 (etiquetas de `D`), ADR-006 (banco y regla de decisión), ADR-007 (detector v2), ADR-009
  (evidencia por radio de control)
- Issues #32, #9, #34, #49 y #6
