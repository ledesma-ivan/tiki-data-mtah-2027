# Calibración del detector de pelota muerta (ADR-002, paso 4)

Estado al 2026-10-27: se reprodujo la calibración, se amplió el reporte de falsos positivos y se auditó el tope de 60 s. Con las etiquetas del PR #14, los tramos aislados concentraban el 76.7% de los frames discrepantes y el tope no explicaba ninguno. ADR-003 (propuesto) encontró la causa de la mayoría: tres huecos de la regla B dejaban sin `D` los 11 saques de arco y el tramo de una tarjeta. Con esas etiquetas, la candidata da F1 por frame 0.967 (P 0.936, R 1.000) y 7.900 de los 10.862 frames FP quedan dentro de `D` (ver "Resultados con las etiquetas de ADR-003"). Las secciones con las etiquetas del PR #14 quedan como registro.

## Qué hay

- `calibrate_dead.py`: calibra `possession.dead_mask` sobre **Metrica Sample Game 3** (datos abiertos, otro partido). Nunca sobre los 5 minutos públicos de BAR-ATH.
- `dead_labels(events, n)`: verdad de campo `D` derivada de los eventos del Game 3 (**regla B**, ADR-003).
- `score(...)`: P/R/F1 por frame, más emparejamiento de tramos con IoU ≥ 0.5 y desfasaje mediano de los bordes en segundos.
- `fp_report(...)`: señales, ubicación respecto de las etiquetas y diez duraciones FP más largas. `fp_run_groups(...)` usa categorías exclusivas.
- `discarded_gap_report(...)`: audita el solapamiento de FP con los intervalos que la regla B descartaría por superar `MAX_DEAD_S`; no modifica las etiquetas ni las métricas.

## Cómo correrlo

1. Copiar la carpeta `data/` de [metrica-sports/sample-data](https://github.com/metrica-sports/sample-data) a `data/` de este repo (está en el `.gitignore`). La ruta por defecto es `data/Sample_Game_3`.
2. `python calibrate_dead.py` (o `python calibrate_dead.py <ruta a Sample_Game_3>`).
3. La primera corrida arma `Sample_Game_3_tracking.npz` junto a los datos (caché, queda fuera de git).

Salida: tabla de las 10 mejores combinaciones de ventana, duración mínima y umbral; reporte de falsos positivos para `window 1, min 2, thr 0.5`; y auditoría de los intervalos descartados. Las pruebas del diagnóstico usan datos sintéticos: `python -m unittest test_calibrate_dead_report test_calibrate_discarded_gaps`.

## Decisión: regla B para las etiquetas (ADR-003)

D va desde el `end` del evento anterior del mismo período hasta el `start` de cada reanudación (`SET PIECE`, o cualquier evento con `GOAL KICK`). Las precisiones y sus mediciones están en ADR-003.

| | A: paradas explícitas → reanudación | B: evento anterior → reanudación (elegida) |
|---|---|---|
| Borde de fin (el que más pesa en spellF1) | start de la reanudación | start de la reanudación (igual) |
| Borde de inicio | preciso | aproximado: puede empezar antes |
| Falta una parada en los eventos | se pierde ese D | no pasa nada |
| Ley de ventaja | hay que decidirla | se resuelve sola (sin reanudación no hay D) |
| Mantenimiento | lista de paradas que cambia por proveedor | 2 tipos de reanudación |

Detalles que importan:

- "Anterior" es el **mayor `end`** entre los eventos previos del período, no `events[i-1]`: vienen ordenados por `start` y pueden solaparse. Desde ADR-003 solo cuentan los que empiezan antes de la reanudación, y nunca una `CARD`.
- `MAX_DEAD_S = 60`: un tramo más largo se **descarta** (apunta a un evento faltante, no a una parada real). Descartar y no recortar evita inventar un borde de inicio. Desde ADR-003 el tope no corre si el evento anterior para el juego por sí mismo (pelota afuera, remate afuera o gol, falta, offside, mano).
- Pasar a la regla A solo si el desfasaje del borde de inicio resulta ser el cuello de botella.

## Resultados con las etiquetas del PR #14 (Game 3, 142.698 frames, D = 24.8%)

| window_s | min_s | thr | P | R | F1 | tramos reales / predichos | matched | start_s | end_s |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 0.7 | 0.774 | 0.985 | 0.867 | 88 / 101 | 0.99 | 0.16 | -0.08 |
| 1 | 2 | 0.5 | 0.765 | 0.999 | 0.867 | 88 / 103 | 0.99 | -0.08 | 0.12 |
| 1 | 3 | 0.5 | 0.767 | 0.997 | 0.867 | 88 / 99 | 0.97 | -0.08 | 0.12 |

Las 10 mejores combinaciones tienen F1 entre 0.862 y 0.867: las diferencias observadas son pequeñas. No se midió su incertidumbre ni se demostró un empate estadístico. Se conserva `window 1, min 2, thr 0.5` como candidata para el diagnóstico; su estabilidad debe verificarse antes de fijarla.

Lectura: el recall por frame es casi 1 frente a las etiquetas derivadas. Las medianas del desfasaje de inicio y fin, calculadas sobre tramos emparejados, están dentro de ±0.2 s en estas filas. Esto no acota todos los errores de borde ni demuestra el rendimiento de spellF1.

## Diagnóstico de la precisión (0.77)

Con `window 1, min 2, thr 0.5`, los falsos positivos (detector dice D, etiqueta dice vivo):

- 10.862 frames (7.2 min) en 139 tramos; mediana 0.2 s, 88% de menos de 2 s.
- La pelota sin datos está activa en el 89% de esos frames; la señal "jugadores lentos" sola, en el 7%.
- El 89% de los tramos queda a una distancia de hasta 2 s de un D etiquetado; es una proporción de tramos, no de frames.

La hipótesis inicial atribuía las discrepancias al margen de las etiquetas. El diagnóstico ampliado no la confirma: **todavía no se determinó si predominan errores del detector o limitaciones de las etiquetas**.

### Diagnóstico ampliado por Emanuel (2026-10-27)

Cada tramo FP se asigna a una sola categoría. Se conserva la cercanía de hasta 2 s del reporte original. Se cuentan todos los frames del tramo, no solamente los que quedan dentro de esos 2 s. Si está cerca de dos D, va a `between_two` para evitar contar dos veces.

| Categoría | Tramos | Frames FP | Segundos | Porcentaje de frames FP |
|---|---:|---:|---:|---:|
| Antes del inicio (`before_start`) | 60 | 634 | 25.36 | 5.8% |
| Después del fin (`after_end`) | 59 | 1.862 | 74.48 | 17.1% |
| Entre dos D (`between_two`) | 5 | 37 | 1.48 | 0.3% |
| Aislado (`isolated`) | 15 | 8.329 | 333.16 | 76.7% |

Los 124 tramos cercanos son numerosos pero reúnen solo 2.533 frames FP (23.3%). Los 15 aislados concentran el resto. Las diez duraciones más largas fueron:

| Orden | Duración (s) | Categoría |
|---|---:|---|
| 1 | 91.04 | aislado |
| 2 | 66.56 | aislado |
| 3 | 62.44 | aislado |
| 4 | 47.84 | después del fin |
| 5 | 29.16 | aislado |
| 6 | 16.08 | aislado |
| 7 | 15.72 | aislado |
| 8 | 13.92 | antes del inicio |
| 9 | 13.72 | aislado |
| 10 | 10.36 | aislado |

Los tres mayores suman 5.501 frames, 220.04 s y el 50.6% del total de FP. La mediana pequeña de duración no describe dónde se concentra la mayor parte del tiempo discrepante. Asimismo, un fragmento FP corto puede pertenecer a una predicción larga: su duración sola no justifica aumentar la duración mínima del detector.

### Auditoría de `MAX_DEAD_S = 60`

Se cruzaron las discrepancias con los intervalos que la regla B descartaría por superar el tope, usando las mismas reanudaciones y el mayor `end` previo del mismo período.

- Intervalos descartados: **0**; unión de frames dentro de la máscara de evaluación: **0**.
- Solapamiento con todos los FP: **0 / 10.862 frames (0.0%)**.
- Solapamiento con FP aislados: **0 / 8.329 frames (0.0%)**.
- Los diez tramos FP más largos tienen solapamiento **0.0%**.

Esto descarta el tope como explicación de las discrepancias en esta corrida y con estas reglas de etiquetado. Aumentarlo no resolvería los FP observados. No demuestra que el partido carezca de interrupciones reales de más de 60 s ni identifica por sí solo la causa de los FP. Las métricas siguen siendo P 0.765, R 0.999 y F1 por frame 0.867 para la candidata.

## Resultados con las etiquetas de ADR-003 (Game 3, 142.698 frames, D = 30.4%)

Misma corrida (`python calibrate_dead.py`), en Windows con Python 3.13. Antes se reprodujo en la misma máquina la de las etiquetas del PR #14: P 0.765, R 0.999, F1 0.867, igual que arriba.

| window_s | min_s | thr | P | R | F1 | tramos reales / predichos | matched | start_s | end_s |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 0.5 | 0.939 | 0.997 | 0.967 | 99 / 99 | 0.97 | -0.08 | 0.12 |
| 1 | 2 | 0.7 | 0.948 | 0.986 | 0.967 | 99 / 101 | 0.99 | 0.14 | -0.08 |
| 1 | 2 | 0.5 | 0.936 | 1.000 | 0.967 | 99 / 103 | 0.99 | -0.08 | 0.12 |

Las 10 mejores combinaciones dan F1 entre 0.962 y 0.967. Como antes, no se midió su incertidumbre.

Falsos positivos con `window 1, min 2, thr 0.5`: 2.962 frames (2.0 min) en 141 tramos; mediana 0.2 s y 97% de menos de 2 s. El 96% de los tramos queda a una distancia de hasta 2 s de un D etiquetado (proporción de tramos, no de frames).

| Categoría | Tramos | Frames FP | Porcentaje de frames FP |
|---|---:|---:|---:|
| Antes del inicio (`before_start`) | 68 | 306 | 10.3% |
| Después del fin (`after_end`) | 61 | 795 | 26.8% |
| Entre dos D (`between_two`) | 7 | 56 | 1.9% |
| Aislado (`isolated`) | 5 | 1.805 | 60.9% |

- De los 1.805 frames aislados, 1.664 son un solo tramo de 66.56 s: un saque de arco que no está anotado como tal (ADR-003, Consequences). Los demás FP duran menos de 4 s.
- De los 10.862 frames FP con las etiquetas del PR #14, 7.900 (72.7%) quedan dentro de `D` con las nuevas; de los 8.329 aislados, 6.358 (76.3%).
- El tope no descarta ningún tramo.

## Qué falta (en orden)

1. Hecho con ADR-003 (propuesto): 7.900 de los 10.862 frames FP eran paradas que la regla B no marcaba. Quedan un saque de arco sin anotar (66.56 s) y FP cortos en los bordes (#9). Para medir las etiquetas contra una referencia independiente: el estado de la pelota del tracking de IDSSE (ADR-003, Measurement, punto 3).
2. Con el diagnóstico y la estabilidad verificados, fijar los parámetros elegidos como valores por defecto en `possession.py` (`DEAD_WINDOW`, `DEAD_MIN`, `DEAD_SCORE`).
3. Una persona verifica con agregados que "pelota sin datos" significa lo mismo en BAR-ATH que en Metrica. Esto no se tunea sobre los 5 minutos públicos.
4. Citar `metrica-sports/sample-data` en el documento técnico y registrar el resultado. Si surge una nueva decisión de diseño o de validación, documentarla mediante un nuevo ADR y revisión de otra persona, según `AGENTS.md`.

## Límites a tener presentes

- En Game 3, la ausencia de pelota está asociada tanto a detecciones D coincidentes con las etiquetas como a discrepancias; no se confirmó que equivalga siempre a pelota muerta. El 32% de frames sin pelota citado en el diagnóstico inicial es propio de ese partido y proveedor; no debe extrapolarse a BAR-ATH.
- El Game 3 tiene 10 sustituciones donde un slot cambia de jugador: cada una genera un salto falso de velocidad (marcado con `ponytail:` en `load_game3`).
- Solo se registran agregados. Nada de filas ni tiempos de eventos de BAR-ATH (`AGENTS.md`).
