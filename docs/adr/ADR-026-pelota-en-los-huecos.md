---
artifact: adr
version: "1.0"
created: 2026-11-02
status: rejected
---

# ADR-026: Estimar la pelota en los huecos con propuestas de posición y árboles enteros

## Status

Rejected (2026-11-02), por la regla que fijó el ADR-021 antes de correr. Ninguna de las 4 variantes pasó la selección: todas cruzan 0 en los dos bancos. La mejor, `all6_features`, dio −0.0012 [−0.0074, +0.0053] en Metrica y +0.0038 [−0.0015, +0.0088] en IDSSE.

Se escribió como `Proposed` antes de la primera medición, con el número local ADR-025: en `main` es el ADR-026, porque el 022 lo tomó el PR #93. Registro previo: `sha256` `dca8a87a2326f933…` a las 14:05:01 UTC del 02/11. El código, los tests y los resultados (`explore/ADR-025_*`) quedan sin mergear en la rama `exp/adr-021-pelota` (`409cf15`).

**Date:** 2026-11-02
**Deciders:** Matias Enrique, con Codex, gpt-6.1-sol.
**Protocolo:** ADR-021. Esta rama implementa solo la alternativa 026.

## Context

`ball_position` interpola huecos de hasta 50 frames. Los más largos no aportan posición a las señales de
juego vivo ni a la evidencia de dueño. Con la pelota completa, el techo medido en abiertos ronda +0.08
en los dos bancos. No es una ganancia esperada. Los jugadores pueden ayudar a distinguir un pase de una
pelota controlada dentro de un hueco.

## Decision

La hipótesis es que elegir entre la interpolación y las posiciones de jugadores cercanos recupera información
de dueño en huecos de pelota. Un clasificador puntúa cinco propuestas por frame: la recta entre las dos
observaciones y las posiciones de los cuatro jugadores más cercanos a esa recta. La propuesta con mayor
puntaje aporta la posición; un empate conserva la primera, con la recta primero. Los jugadores se ordenan
por distancia, x, y y velocidades, sin usar equipo ni identidad. Una propuesta de jugador desconocido se
descarta. Sin dos extremos vistos en el mismo período no se estima nada.

Las posiciones y señales se cuantizan en cm antes de construir propuestas. La recta usa división entera.
Las señales incluyen la duración y fase del hueco, extremos y velocidad de la recta, posición y movimiento
de los cuatro jugadores cercanos, desplazamiento de cada propuesta respecto de la recta, sus distancias a
los extremos, su velocidad y los conteos de jugadores a 3 y 10 m. Las velocidades salen de desplazamientos
de 5 frames antes y después; un salto de más de 1200 cm/s queda UNKNOWN. No se usa quién es local.

El objetivo supervisado es la propuesta más cercana a la pelota realmente observada, por distancia cuadrada
entera. Las propuestas empatadas en la menor distancia son positivas. Se entrena solo en frames con pelota
original vista, verdad viva y hueco artificial de 1 a 150 frames. Se usa `bench.degrade` con las cuatro pelotas
y semillas 100-103 de ADR-014 y con jugadores limpios y con su ruido de entrenamiento, una muestra cada
16 frames, desplazada por variante. Cada partido pesa lo mismo. El clasificador es
`HistGradientBoostingClassifier`, 100 árboles, tasa 0.1, 31 hojas, mínimo 200 filas por hoja, semilla 0 y sin
parada temprana. Se exporta con `calibrate_edges.export`; toda elección en inferencia usa sumas de enteros.

Familia cerrada de cuatro variantes, sin cambios luego de medir:

| Nombre | Huecos estimados | Uso de la posición estimada |
|---|---|---|
| `long6_features` | 51-150 frames, inclusive | solo `live_features`; evidencia original |
| `long6_evidence` | 51-150 frames, inclusive | `live_features` y `owner_evidence` |
| `all6_features` | 1-150 frames, inclusive | solo `live_features`; evidencia original |
| `all6_evidence` | 1-150 frames, inclusive | `live_features` y `owner_evidence` |

Los frames vistos conservan su posición. El estado visto/no visto y la duración de los huecos siempre vienen
de la pelota degradada original. Fuera de estos huecos queda la interpolación de ADR-009, separada por período.

La referencia R se entrena por pliegue con 63 hojas, lambda 10, `short_weight=1`, `short_s=5`. La candidata
reentrena esa receta sobre las posiciones estimadas. Mantiene exactamente las mismas filas, etiquetas,
pesos, pelotas, jugadores, `dead_mask_v2`, períodos y paradas identidad que R. El estimador de cada pliegue
se entrena sin el partido retenido y se aplica a las filas de entrenamiento y al partido retenido. Este ajuste
del estimador sobre las filas de entrenamiento de la receta no es otra validación; la medición es LOMO.

La vía nueva requiere una opción explícita. Los modelos y la llamada actual a `possession.label` conservan
sus bytes y etiquetas. No se escriben `live_model.json`, `stops_model.json` ni `live_confirmation.json`.

## Cómo se mide

- Solo selección, LOMO por partido: Metrica Games 2-3, semillas 0-9; IDSSE 1-5, semillas 0-4. Las dos
  mitades IDSSE quedan afuera juntas. No se carga ni diagnostica la reserva.
- Pelota degradada por defecto y jugadores limpios. Metrica con verdad desde el inicio del evento; IDSSE
  con la verdad del proveedor. Los dos modelos reciben la misma simulación.
- `spellF1` oficial, commit f8f2629, con `bench.compare`: candidata menos R, 1000 remuestreos pareados de
  posesiones y semillas, por banco con intervalo 5-95% y signos de las 12 unidades. Gana la variante con
  mayor media de las dos medias de banco. Se reportan las cuatro, aun si pierden.
- Sin decidir: acierto en frames vivos, posesiones predichas/reales y recall de posesiones a IoU 0.5 por
  duración, 0-2, 2-5, 5-15 y más de 15 s. Se agregan por unidad y semilla, sin seleccionar con ellas.
- Tests sintéticos de simetría H/A, posiciones UNKNOWN, huecos sin extremos, períodos, exactitud entera,
  determinismo, compatibilidad de la vía actual y exclusión del partido retenido. Tiempo de inferencia
  en un fixture sintético de 199319 frames y 46 slots; máximo 600 s.
- Se implementa, pero este agente no corre, una confirmación para la mejor variante. Entrena con los 7
  partidos de selección, evalúa reserva con `--seed-start 80`, reutiliza las 43 condiciones de ADR-019 y
  comprueba árboles exportados frente a `decision_function`, tanto del estimador como de la receta.
  El informe va a `--report`, nunca al informe vigente. Solo el agente principal puede correrla si gana
  esta alternativa según ADR-021. La confirmación se prueba con un fixture sintético.
- Cada medición se agrega a `docs/EXPERIMENTOS.md`. Resultados completos, semillas, commit y tiempos
  van a `explore/ADR-025_selection.json`. Todas las cargas IDSSE, entrenamientos y mediciones de banco
  corren con `flock /tmp/mtah-heavy.lock`, de a una.

## Consequences

### Positive

Reusa jugadores, geometría y exportación existentes. No necesita video ni otra fuente. La elección de
posición es independiente del nombre de los equipos y no cruza el entretiempo.

### Negative

La pelota puede estar lejos de las cinco propuestas. Elegir un jugador puede inventar control durante
un pase. El estimador ve sus propias filas al armar el entrenamiento del modelo vivo; el pliegue retenido
queda afuera de ambos ajustes. Se suman costo de entrenamiento y árboles en inferencia.

## Alternatives Considered

- Regresión de coordenadas: puede promediar dos trayectorias posibles y poner la pelota lejos de ambas.
- Clasificar directamente el equipo: cambiaría la evidencia sin estimar una posición para las señales.
- Más variantes o calibrar confianza después de ver resultados: fuera de la familia cerrada de esta ronda.

## References

ADR-005, ADR-006, ADR-011, ADR-014, ADR-019 y ADR-021; `docs/TECHNICAL.md`, sección 6.
Metrica sample-data y IDSSE, revisión a715a38, son los únicos datos usados.
