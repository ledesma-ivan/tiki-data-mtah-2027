---
artifact: adr
version: "1.0"
created: 2026-11-02
status: rejected
---

# ADR-025: Detectar las paradas por frame con el movimiento y la formación de los jugadores

## Status

Rejected (2026-11-02), por la regla que fijó el ADR-021 antes de correr. Ninguna de las 3 variantes pasó la selección: las tres empeoran, con el intervalo entero bajo 0 en los dos bancos. La mejor, `d40`, dio −0.0337 [−0.0480, −0.0185] en Metrica y −0.0191 [−0.0278, −0.0103] en IDSSE. Su signo cambia según cómo se simula la pelota de las paradas (sensibilidad, no decide): con esa pelota dentro de la cancha, Metrica +0.0143 [−0.0006, +0.0282]; con el 34% de esa pelota faltante, IDSSE +0.0181 [+0.0098, +0.0262].

Se escribió como `Proposed` antes de la primera medición, con el número local ADR-024: en `main` es el ADR-025, porque el 022 lo tomó el PR #93. Registro previo: `sha256` `ed034979c7b13b5b…` a las 14:04:16 UTC del 02/11. El código, los tests y los resultados (`explore/ADR-024_*`) quedan sin mergear en la rama `exp/adr-021-paradas` (`85811c8`).

**Date:** 2026-11-02
**Deciders:** Matias Enrique, con Codex gpt-6.1-sol.

## Context

El oráculo de D del 30/10 deja un techo de +0.100 en Metrica y +0.075 en IDSSE sobre el modelo vivo. Un techo no es una ganancia esperada. El ADR-010 movía los bordes de paradas ya encontradas y no confirmó en Metrica. El ADR-017 confirmó en datos abiertos, pero su condición de pelota quieta no actuó en la entrega. El ADR-018 tampoco confirmó, según el resumen de esta ronda.

La hipótesis es que un clasificador por frame, seguido de un Viterbi, pueda corregir bordes y paradas ausentes o falsas con el movimiento colectivo y la formación. Se excluyen las señales de pelota del detector en ambos bancos. Así no puede aprender ni la pelota interpolada quieta ni su posición fuera de la cancha durante las paradas de Metrica. El modelo vivo sigue viendo la misma pelota degradada de R. Los eventos de Metrica y BallStatus de IDSSE tienen convenciones distintas; se reportan por separado.

## Decision

Se agrega una ruta opcional, sin cambiar los modelos entregados ni las etiquetas por defecto.

El detector usa enteros en cm, cm/s, porcentajes y frames. Parte de las primeras 12 señales de FRAME_FEATURES, las de jugadores. Agrega distribuciones de velocidad, porcentajes bajo 0.5, 1, 1.75, 3 y 4 m/s en ventanas centradas de 1, 3, 5 y 10 s, medias y cambios entre pasado y futuro en esas ventanas; y formación agrupada sin distinguir equipos: dispersión en x e y, distancia mínima a banda, esquina y centro, y cantidades en áreas y cerca del círculo central. Las ventanas se calculan por período. Una posición o velocidad desconocida usa UNKNOWN y no cuenta como observada. El detector no recibe el nombre del equipo ni la pelota.

Se entrena un HistGradientBoostingClassifier de 200 iteraciones, tasa 0.1, 31 hojas, mínimo 200 filas por hoja, random_state 0 y sin parada temprana. Cada partido suma el mismo peso, sin reponderar D. Se toma una fila cada 16 frames válidos, con el desplazamiento de la variante de entrenamiento. Se usan las cuatro degradaciones de TRAIN_BALLS del ADR-014, semillas 100-103, cada una con jugadores limpios y con TRAIN_NOISE. Aunque el detector no ve la pelota, el ruido de jugadores y el modelo vivo sí usan esas degradaciones.

Los árboles se exportan con calibrate_edges.export. Un Viterbi de dos estados maximiza la suma del puntaje si D y su negativo si vivo, menos un costo entero por cambio. Un empate final prefiere vivo, y los empates de transición conservan el estado. Se eliminan después las paradas de menos de 25 frames, sin extenderlas. No se mueven bordes con constantes, no se predice equipo de reanudación y no se usa un decodificador de tres estados.

La familia queda cerrada en estas tres variantes. El único cambio entre ellas es lambda de D; el costo entero es 2 * lambda * 1 000 000.

| Variante | Lambda de D | Mínimo D |
|---|---:|---:|
| d10 | 10 | 25 frames |
| d40 | 40 | 25 frames |
| d160 | 160 | 25 frames |

En cada pliegue se entrena el detector sin el partido excluido. Con ese detector se arman las paradas de los partidos de entrenamiento y del excluido. Cada candidata reentrena el modelo vivo con sus propias paradas, filas y live_since/live_until. Esto usa predicciones del detector dentro del entrenamiento del modelo vivo, nunca etiquetas de D del partido excluido. R se entrena con dead_mask_v2 y la identidad. La receta viva de ambos queda fija en 63 hojas, lambda 10, short_weight 1 y short_s 5. Se conserva exactamente el muestreo de filas vivas del ADR-014, después de filtrar los frames vivos en la verdad y en cada detector.

Para ahorrar memoria se pueden guardar señales enteras en cachés locales ignorados por git. La puntuación compilada de selección puede usar los mismos árboles con umbrales y hojas enteros representados exactamente en float64, con suma absoluta menor que 2**53, y se verifica contra tree_scores. La inferencia entregable usa tree_scores. Además se reportan las etiquetas de los árboles exportados contra decision_function original, como exige el ADR-019.

## Cómo se mide

Rige el ADR-021. Solo selección LOMO: Metrica 2-3 con semillas 0-9 e IDSSE 1-5 con semillas 0-4, ambas mitades juntas al excluir un partido. Candidata y R reciben la misma pelota y los mismos jugadores. Decide spellF1 del scorer oficial f8f2629 mediante bench.compare, con 1000 remuestreos pareados de posesiones y semillas. Se informa media e intervalo 5-95% por banco, los signos de las 12 unidades y también Metrica con ancla al fin del evento. Se elige por el promedio simple de las medias de los dos bancos, con ancla al inicio para Metrica.

Se informa, sin decidir, acierto en todos los frames verdaderamente vivos, acierto condicionado a predecir H/A, posesiones predichas y verdaderas, y recall a IoU 0.5 por duración verdadera: [0,2), [2,5), [5,15) y [15,infinito) segundos. Para la mejor se repiten los escenarios de pelota de las paradas dentro de la cancha y dead_missing 0.34 con las mismas semillas de selección. Todos los resultados van en explore/ADR-024_selection.json y cada corrida agrega una fila a EXPERIMENTOS.

La reserva no se carga ni se usa en esta tarea. Queda implementado, con tests sintéticos, un comando de confirmación para que el padre lo corra solo si esta alternativa gana. Entrena con los siete partidos de selección y aplica las 43 condiciones del ADR-019 en Metrica 1 e IDSSE 6-7, semillas desde 80; exige también igualdad de etiquetas entre árboles exportados y decision_function, para D y para la salida final. Escribe al --report indicado y nunca a live_confirmation.json. No se implementa adopción automática ni --final en esta alternativa.

## Consequences

### Positive

Puede crear y quitar paradas además de mover sus bordes. El detector no aprende los artefactos de pelota del banco. Los árboles y el decodificador tienen inferencia exacta y simétrica entre equipos.

### Negative

El detector no ve la salida de la pelota ni la patada de reanudación. Las formaciones y velocidades pueden variar por proveedor. Reentrenar el modelo vivo por cada variante y pliegue cuesta más tiempo y memoria. La mejor variante sobre la selección tiene sesgo de selección; solo puede adoptarse si gana la ronda y confirma.

## Alternatives Considered

- Repetir el ajuste de bordes del ADR-010 o la patada del ADR-017: ya se probaron y no resuelven la hipótesis de esta ronda.
- Usar la pelota de Metrica para entrenar D: expone el detector a los artefactos del banco.
- Aprender señales de pelota solo de IDSSE: agrega una diferencia entre entrenamiento e inferencia; queda fuera de esta familia acotada.
- Decodificación conjunta H/A/D: cambia dos piezas a la vez y agrega parámetros; queda fuera de esta familia.

## References

- ADR-003, ADR-006, ADR-010, ADR-011, ADR-014, ADR-017, ADR-019 y ADR-021.
- Metrica sample-data; IDSSE revisión a715a38, CC BY 4.0.
- explore/oracles_live.py y su fila del 30/10 en docs/EXPERIMENTOS.md.
