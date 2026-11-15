---
artifact: adr
version: "1.0"
created: 2026-11-02
status: accepted
---

# ADR-020: Evaluación A/B del modelo de posesión y diagnóstico fuera de muestra en selección

## Status

Accepted (2026-11-02), revisado por Lautaro en el PR #90, con las cinco sugerencias de su revisión incorporadas.
Autoriza el protocolo: la implementación, los tests y las corridas siguen en el #85.

**Date:** 2026-11-02
**Deciders:** Emanuel Gercek (propone); revisión de Lautaro Bursese en el PR #90.
**Issue:** #85.
**Base inspeccionada:** `482327f0ae2f926e84c2b5d765c1f03c49ca5b25`.

Complementa los ADR-005, ADR-011 y ADR-014. Reutiliza el comparador del #83, que fija el ADR-019 (PR #89). La
compatibilidad se comprobó en la revisión del PR #90, antes de observar resultados:

- recetas con `calibrate_live.recipe_of` (claves `leaves`, `lam`, `short_weight` y `short_s`); el par del #77 es
  `recipe_of(["short_weight=1"])` contra `recipe_of([])`;
- entrenamiento con `calibrate_live.fit(rows, leaves, short_weight)` y `game_rows(game, short_s)`, sin globales;
- puntuación con `calibrate_live.score`, con control y candidato en la misma llamada: comparten pelotas,
  jugadores y máscaras;
- comparación con `bench.compare` (emparejado con `zip(..., strict=True)`) o `calibrate_live.paired`. Las
  predicciones de los siete pliegues se juntan en un diccionario por verdad, porque cada partido cae en uno solo;
- `conditions()` y `decide()` no se reutilizan: son las 43 condiciones de la confirmación en la reserva, y este
  diagnóstico es descriptivo.

## Context

El #62 agregó la verdad B a `bench.truth_labels`; el #82 la llevó al barrido de la regla de cambio. Sin embargo,
`calibrate_edges.load_metrica()` sigue cargando A para ambos anclajes y `calibrate_live.truth_of()` usa su anclaje
`start` al entrenar. Cambiar ese diccionario por B cambiaría también el entrenamiento, no solo la evaluación.

`explore/diagnose_changes.py`, incorporado en el #76, entrena con la selección y diagnostica en la reserva. Esa
reserva ya se examinó para explorar errores; el #77 estudió dar más peso a las posesiones cortas. Hay que registrar
esa exposición: cambiar las semillas no convierte esos partidos en una reserva nueva.

La pregunta del #85 es si las conclusiones sobre el modelo de juego vivo dependen de la referencia de control,
y cómo explorar sus errores sin seguir orientando candidatos con la reserva. No vuelve a calibrar N ni cambia
por sí mismo la entrega.

## Decision

### 1. Separar entrenamiento, predicción y evaluación

| Uso | Metrica | IDSSE |
|---|---|---|
| Entrenamiento | A, anclaje `start` | Referencia del proveedor, `status` |
| Evaluación principal | A, anclaje `start` | La misma referencia `status` |
| Sensibilidad de evaluación | A `end`, B `start` y B `end`, por separado | Sin variante B ni anclaje por eventos |

La referencia de entrenamiento se conserva explícitamente. La selección de una verdad de evaluación no puede
cambiar las filas, sus etiquetas, las duraciones usadas para ponderarlas, los pesos ni el modelo entrenado.
Las posesiones cortas de Metrica se identifican siempre con A `start`, también cuando se evalúa con B.
IDSSE conserva su entrenamiento actual. A sigue siendo el valor predeterminado de las interfaces existentes.

Por partido, semilla, escenario, receta y anclaje, las predicciones se calculan una vez y se puntúan contra A y B.
Se reutilizan la misma pelota degradada, los mismos jugadores y ruido, y el mismo modelo. B no interviene en
las señales ni en la decodificación. No se exige que `start` y `end` tengan igual cobertura entre sí: cada anclaje
conserva su evaluación separada, como hasta ahora.

Antes de reutilizar predicciones entre A y B de un mismo anclaje, se comprueban longitud, orden de frames,
máscaras `X` y `D`, y los tramos válidos que usa el scorer. Una incompatibilidad produce un error explícito;
no se recorta silenciosamente la evaluación a una intersección. Los tramos de predicción se fijan con la
cobertura A del anclaje, sin usar sus etiquetas H/A como señal. No dependen de qué variante se puntúe después.

La identidad de cada resultado incluye banco, partido/mitad, partición, variante, anclaje, escenario, semilla y
receta. También se registra el grupo de partido usado para excluirlo del entrenamiento. Los resultados A y B
viven en contenedores separados o en claves que incluyan la variante; nunca se actualiza un diccionario con
claves que puedan sobrescribir otra verdad. Al adaptar al formato de `bench.compare`, cada llamada recibe
una sola referencia y valida la igualdad de verdad, semillas y cobertura entre control y candidato.
IDSSE se informa una vez como `status`, sin duplicarlo en las tablas A y B ni en sus promedios.

### 2. Diagnóstico por defecto: selección fuera del entrenamiento

Se conserva la partición de los ADR-011 y ADR-014:

| Partición | Metrica | IDSSE |
|---|---|---|
| Selección | Games 2 y 3 | Partidos 1 a 5, ambas mitades |
| Reserva | Game 1 | Partidos 6 y 7, ambas mitades |

El modo predeterminado de `explore/diagnose_changes.py` deja fuera un partido completo por pliegue (LOMO).
Cada una de las dos recetas se entrena con los otros seis partidos de selección y predice solo el excluido.
La unidad de exclusión es `Game.match`, por ejemplo `("idsse", 3)`, no el identificador de una mitad.
Todas las mitades y todas las variantes de pelota o jugadores de un partido quedan del mismo lado.
La reserva no se carga ni aporta filas, pesos, ajustes o elección de recetas en este modo.

El control también se vuelve a entrenar en cada pliegue. `live_model.json`, entrenado con selección y reserva
para entregar, no sirve como control fuera del entrenamiento: ya vio los partidos que se quieren diagnosticar.
Se pueden cachear filas por partido, pero cada ajuste debe comprobar y registrar sus grupos de entrenamiento
y el grupo evaluado, disjuntos entre sí y pertenecientes a la partición autorizada.

Las recetas se fijan antes del diagnóstico; no se busca una receta dentro de este comando. El LOMO permite
examinar predicciones de un modelo que no ajustó con ese partido, pero los partidos de selección ya se usaron
para elegir recetas. El informe lo llama diagnóstico de selección fuera del entrenamiento, no una confirmación
independiente ni una estimación libre de sesgo de selección.

### 3. Primera comparación: reconstruir el control y candidato del #77

| Parámetro | Control anterior al #77 | Candidato del #77, ya vigente |
|---|---|---|
| Hojas máximas | 63 | 63 |
| Penalidad de cambio, lambda | 10 | 10 |
| Duración considerada corta | Menos de 5 s | Menos de 5 s |
| Peso de esas filas al entrenar | 1 | 3 |

Todo lo demás se conserva igual entre las recetas: señales, muestreo, aumento de datos, clasificador,
geometría, tratamiento de paradas y decodificador. Se reconstruyen con el código de una misma revisión
registrada, no comparando un artefacto entrenado con todos los partidos contra otro entrenado solo con seis.
`radio` puede mostrarse como contexto, pero no reemplaza al control de peso 1 en la diferencia del #77.
Para candidatos futuros, la receta vigente de control se fija con el protocolo del #83; esta reconstrucción
histórica no cambia qué receta está entregada.

La primera corrida usa la degradación por defecto y jugadores limpios, con las semillas de selección actuales:
Metrica 0-9 e IDSSE 0-4; las semillas efectivas conservan `1000 * game.g + s`. El entrenamiento mantiene sus
pelotas y semillas propias 100-103 y su ruido actual. Escenario y bloques se fijan antes de correr y son iguales
para control, candidato y todas las referencias de evaluación.

**Control de reconstrucción, antes de mirar B.** Con A `start`, IDSSE `status`, jugadores limpios y estas
semillas, la primera corrida repite la selección del #77 (`explore/short_weight.py`), y el camino del modelo de
posesión no cambió desde `67b8fe6`. La diferencia peso 3 menos peso 1 tiene que dar las medias de la fila del
31/10 del #77 en `docs/EXPERIMENTOS.md`: unos +0.0026 en Metrica (+0.1250 − 0.1224) y +0.0157 en IDSSE
(+0.1803 − 0.1646), que están redondeadas a 4 decimales. Si no dan, se explica la diferencia antes de seguir.

**Sensibilidad con ruido de jugadores, descriptiva.** La misma comparación se repite, con las mismas semillas, con
dos entradas de `NOISE`: `position noise 1.0 m per axis (1 s correlated)` y `noise 0.6 m + 10% lost + swaps 5%`.
En la reserva, el peso 3 perdió contra el peso 1 con la primera, en los dos bancos (ADR-019). Se informa sin
decidir y sirve para diseñar las señales del #86.

El informe utiliza el comparador del #83 (ADR-019, ver Status), con 1000 remuestreos pareados y
percentiles 5-95 de la diferencia `spellF1(candidato) - spellF1(control)`. Se reutilizan sus comprobaciones,
su agregación y su pareado de posesiones y semillas; no se implementa un segundo bootstrap dentro del diagnóstico.
Los detalles compartidos con el ADR-019 quedaron registrados en el Status antes de observar resultados. No se
ajusta el protocolo después de conocer A o B.

Se informa cada banco y referencia por separado. El promedio por semillas y unidades de evaluación conserva
la regla de los ADR-011/014 y del comparador; las mitades de IDSSE siguen juntas para entrenar aunque el scorer
informe cada mitad. No se mezclan A y B en una media ni se resta su score absoluto como si fueran dos modelos.
Los intervalos describen los partidos y pliegues medidos; no convierten el diagnóstico en una reserva nueva.

### 4. Métricas y categorías explicativas

Para cada banco, referencia y receta se reportan:

- `spellF1`, diferencia pareada entre recetas y su intervalo; A y B tienen comparaciones independientes.
- Recall de posesiones con IoU 0.5 en duraciones `[0, 2)`, `[2, 5)`, `[5, 15)` y `[15, infinito)` segundos.
- Posesiones predichas y reales, su razón y su frecuencia por minuto vivo; se explicita el promedio por semillas
  para no presentar varias realizaciones de un mismo partido como posesiones reales distintas.
- Conteos y proporciones de errores: equipo incorrecto, pelota muerta predicha, división, fusión y bordes.

Las posesiones, el tratamiento de abstenciones y los emparejamientos usan las funciones del scorer oficial
que ya emplea el diagnóstico. Se conserva el orden y las reglas de sus categorías; estas son descripciones
heurísticas de las predicciones, no causas demostradas del error ni una justificación para ajustar con la reserva.
La salida compartida contiene agregados; los tests usan eventos y tracking inventados.

### 5. Reserva y tratamiento de los resultados

El modo de reserva requiere una opción explícita y una receta identificada y fijada previamente, junto con su
revisión, partición de entrenamiento, escenario y bloque de semillas registrados antes de ejecutar. Entrena solo
con la selección y comprueba en la reserva, sin elegir otra receta con su resultado. No se usa el modelo final
entrenado con los diez partidos. El encabezado advierte que la reserva ya se examinó en el #76 y se reutilizó
después: una corrida posterior no recupera su condición de datos nunca observados. Si se usa, es una mirada más
a la reserva, que al 01/11 lleva ocho confirmaciones, además del diagnóstico del #76, y va con un bloque de
semillas nuevo: el próximo libre es el 80 (ADR-019).

El primer informe del #85 se hace con LOMO en selección; no necesita volver a explorar la reserva. Si después
se ejecuta su modo explícito, sus resultados se registran aparte como comprobación de receta fijada. Un cambio
de criterio o de receta que use lo observado necesita un protocolo previo y reconocer esa exposición.

A sigue siendo la referencia principal. B es sensibilidad descriptiva: se publica aunque contradiga A y
no se elige la verdad que dé más puntaje. Este estudio no añade B como condición retroactiva de adopción ni
redecide automáticamente el #77. La decisión de volver o no al peso 1 sigue la regla que el ADR-019 fijó antes de
su confirmación: el peso 3 no confirma contra el peso 1 (41 de 43), y lo decide el equipo (#89). Este diagnóstico
no se usa para sostener ni revertir esa decisión, ni para esperar a tomarla. La adopción de futuras recetas sigue
el protocolo vigente revisado; cualquier cambio de criterio debe acordarse antes de ver sus resultados.

## Cómo se valida

- Reutilizar los casos inventados del #62: recuperación aislada, pase de primera, eventos del mismo frame,
  reinicio tras `D` y cambio de período, con ambos anclajes cuando corresponda.
- Comprobar que pedir B no cambia filas, etiquetas, duraciones ni pesos de entrenamiento; tampoco el modelo,
  pelota, jugadores, señales o predicciones de cada anclaje. A mantiene el comportamiento predeterminado.
- Rechazar coberturas incompatibles, variantes inválidas, claves que mezclen referencias, verdades distintas
  entre recetas y semillas o grupos de evaluación que no estén pareados.
- Espiar los grupos que llegan al ajuste en todos los pliegues: no aparece el partido evaluado, sus dos
  mitades de IDSSE se excluyen juntas y ningún partido de reserva se carga en el diagnóstico predeterminado.
- Verificar que las métricas y el recall reproducen el scorer oficial, y que una comparación de recetas
  idénticas tiene diferencia exactamente cero en cada referencia. La identidad de predicciones se comprueba
  antes de puntuar, no se deduce de la igualdad de un score redondeado.
- Antes de mirar B, el control de reconstrucción de la sección 3: con A `start` e IDSSE `status`, la diferencia
  peso 3 menos peso 1 reproduce las medias de la selección del #77.
- Informar aparte, sin decidir, la sensibilidad con ruido de jugadores de la sección 3.
- Ejecutar el informe de las dos recetas fijadas en datos abiertos, con A/B y ambos anclajes en Metrica,
  IDSSE `status`, bootstrap pareado del #83 y fila nueva en `docs/EXPERIMENTOS.md`. Registrar revisión,
  versiones, recetas, grupos de entrenamiento/evaluación, semillas, escenarios y métricas agregadas.

La aceptación de este ADR autoriza el protocolo; no afirma que esos tests o corridas ya se hayan realizado.

## Consequences

Se puede evaluar la sensibilidad A/B sin alterar el entrenamiento ni confundir etiquetas con predicciones.
El diagnóstico habitual deja de consultar la reserva y añade ajustes por pliegue, con mayor costo de cómputo.
Persisten el ruido de las etiquetas por eventos, el tamaño pequeño de los bancos y la exposición previa de
selección y reserva; se informan como límites del estudio.

La implementación no modifica `live_model.json`, otros modelos entregados ni las etiquetas de entrega.
No lee ni ejecuta BAR-ATH ni sus derivados. El registro de experimentos sigue siendo solo-agregar.

## References

- Issue #85; PR #62 (verdad B), #76 (diagnóstico en reserva), #77 (peso 3) y #82 (barrido A/B).
- Issue #83 y ADR-019 (comparador, PR #89; compatibilidad comprobada en la revisión del PR #90), con la
  confirmación del peso 3 contra el peso 1 en la reserva.
- ADR-005 (referencia principal y sensibilidad B), ADR-011 (bancos y particiones), ADR-014 (modelo de juego vivo).
- `bench.py`, `calibrate_edges.py`, `calibrate_live.py`, `explore/short_weight.py`, `explore/diagnose_changes.py`.
