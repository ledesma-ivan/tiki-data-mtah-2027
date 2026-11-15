---
artifact: adr
version: "1.0"
created: 2026-11-02
status: rejected
---

# ADR-023: Señales de movimiento relativo y de cambio de trayectoria para la posesión con juego vivo

## Status

Rejected (2026-11-02), por la regla que fijó el ADR-021 antes de correr. Pasó la selección con la variante `context`: +0.0133 [+0.0063, +0.0207] en Metrica y +0.0155 [+0.0101, +0.0206] en IDSSE, 12 de 12 unidades positivas. No confirmó en la reserva: 41 de 43 condiciones. Fallaron el escenario por defecto en IDSSE, +0.0047 [−0.0037, +0.0130], y los cambios de identidad entre equipos cerca de la pelota en el 5% de los frames, en IDSSE, −0.0001 [−0.0084, +0.0082].

Se escribió como `Proposed` antes de la primera medición, con el número local ADR-022: en `main` es el ADR-023, porque el 022 lo tomó el PR #93. Registro previo: `sha256` `093f25c79bd8bb2c…` a las 14:03:14 UTC del 02/11. El código, los tests y los resultados (`explore/ADR-022_*`) quedan sin mergear en la rama `exp/adr-021-toques` (`088593d`).

**Date:** 2026-11-02
**Deciders:** Matias Enrique, con Codex, gpt-6.1-sol
**Issues:** #86. Alternativa del ADR-021; confirmación según ADR-019.

## Context

El modelo del ADR-014 pierde sobre todo posesiones cortas en los datos abiertos. El diagnóstico de selección
del 31/10 atribuye la mayoría a equipo equivocado o fusión con otra posesión. `LIVE_FEATURES` ya tiene distancia
al primero y al segundo jugador, velocidad del más cercano, acercamiento del jugador a la pelota y velocidad
de la pelota. No compara el movimiento de la pelota con el del jugador, ni la trayectoria antes y después.

La hipótesis es que una pelota que cambia su velocidad o dirección cerca de un jugador aporta evidencia de
un toque, y que el movimiento conjunto ayuda a distinguir control de una pelota que pasa cerca. No se etiqueta
un toque verdadero ni se supone que cada cambio de trayectoria implique un cambio de posesión.

## Decision

### Lo que queda fijo

La referencia R se reentrena en cada pliegue con la receta del ADR-014: 63 hojas, 300 árboles, tasa 0.1,
200 filas por hoja, `random_state=0`, sin parada temprana, `lam=10`, `short_weight=1`, `short_s=5`.
Se conservan las ocho degradaciones de entrenamiento, sus filas y pesos, el decodificador entero,
`dead_mask_v2` y las paradas identidad. La candidata suma señales a las 49 de R; no modifica sus columnas.
No se usa el modelo entregado como referencia.

### Señales, versión `touch-v1`

Coordenadas redondeadas a cm con `possession._int`, antes de restar. En cada frame t se comparan los
desplazamientos t-5 a t y t a t+5. La velocidad es el desplazamiento multiplicado por 5, en cm/s.
Los 5 frames son la ventana de velocidad del ADR-014, no una ventana elegida después de ver resultados.

- **Movimiento relativo**, por equipo, respecto de su jugador más cercano en t: norma de la diferencia
  de las velocidades pelota-jugador antes y después, y coseno de sus movimientos antes y después,
  multiplicado por 1000 y con división entera. Un movimiento nulo no tiene coseno y da `UNKNOWN`.
- **Impulso**, compartido: norma de la diferencia entre la velocidad posterior y anterior de la pelota,
  diferencia de sus normas y coseno entre sus movimientos, con la misma escala entera.
- **Impulso de control**, por equipo: ese impulso si su distancia mínima es también la mínima global y
  está dentro de 100 cm, el radio del ADR-009; cero si hay posiciones pero no ese contacto. Un empate entre
  equipos da la misma evidencia a ambos. Sin jugador de ese equipo da `UNKNOWN`.
- **Contexto**, por equipo: media entera del impulso de control en los 12, 50 y 125 frames previos y siguientes.
  Son las ventanas de evidencia del ADR-014. Se usan las convenciones [t-w,t) y [t,t+w).

No hay un umbral nuevo que decida si hubo toque: el árbol calibra sus umbrales con `calibrate_touch.py`.
El radio, el máximo de velocidad de jugador de 1200 cm/s y todas las ventanas vienen de ADR-009/014.
Las únicas variantes admitidas, fijadas ahora, son estas cuatro:

| Identificador | Señales agregadas a R | Ventana de movimiento | Radio | Contexto |
|---|---|---|---|---|
| `relative` | movimiento relativo | 5 frames antes y después | no aplica | ninguno |
| `impulse` | impulso compartido e impulso de control | 5 frames antes y después | 100 cm | ninguno |
| `combined` | movimiento relativo e impulso | 5 frames antes y después | 100 cm | ninguno |
| `context` | movimiento relativo, impulso y contexto | 5 frames antes y después | 100 cm | 12, 50, 125 frames |

Las señales nuevas usan solo tramos con pelota observada en ambos ejes en todos los frames de t-5 a t+5,
con juego vivo predicho. No usan la interpolación del ADR-009 como evidencia de toque. El jugador elegido
debe estar observado durante toda la ventana; velocidades de más de 1200 cm/s en cualquiera de sus dos
desplazamientos invalidan su movimiento. Cada período se calcula por separado. El contexto se corta también
en cada hueco de soporte y cada parada: no conecta observaciones de lados distintos de un hueco.
Lo que no se puede calcular se marca con `possession.UNKNOWN`, incluso fuera de los períodos.

Las señales son enteras y el mismo cálculo corre con cada equipo como propio. Los árboles se exportan con
`calibrate_edges.export` y se infieren con `possession.tree_scores`. El esquema se activa solo con un modelo
que declare la variante; los archivos de modelos vigentes no cambian.

## Cómo se mide

Solo selección: Metrica Games 2-3, semillas 0-9, e IDSSE 1-5, semillas 0-4. LOMO por partido, juntando las
dos mitades IDSSE. No se carga la reserva. R y las cuatro candidatas se entrenan con las mismas filas y se
puntúan sobre las mismas pelotas degradadas por defecto y los mismos jugadores limpios y máscaras.
Metrica usa la verdad desde el inicio del evento; IDSSE usa la del proveedor.

Decide la media pareada candidata menos R de `spellF1`, promediando por igual los bancos. Se reportan las
cuatro variantes, con intervalo 5-95% de 1000 remuestreos de posesiones y semillas por banco mediante
`bench.compare`, y los signos de las 12 unidades. La mejor solo queda habilitada para competir por la única
confirmación si ambos intervalos están enteros por encima de cero. Se guardan semillas, commit, tiempos y
resultados en `explore/ADR-022_selection.json`, y cada corrida en `docs/EXPERIMENTOS.md`.

Sin decidir se reporta el acierto en todos los frames verdaderamente vivos, posesiones predichas y verdaderas,
y recall por duración real [0,2), [2,5), [5,15), [15,infinito) s. El recall promedia los flags de acierto del
scorer oficial en sus umbrales IoU y las semillas, agrupados por duración verdadera.

Se prueban con datos sintéticos el cambio de trayectoria, movimiento conjunto, pelota desconocida, huecos,
saltos del jugador, límites de período, enteros, determinismo, permutación H/A y exclusión del partido retenido.
Se mide la inferencia entera de la mejor sobre 199319 frames y 46 slots sintéticos, con límite de 600 s.

Se implementa, pero este agente no ejecuta, una confirmación de la mejor con `--seed-start 80 --report RUTA`,
entrenando candidata y R en los siete partidos de selección. Reusa las 43 condiciones y la regla del ADR-019,
más la equivalencia de etiquetas de los árboles exportados y `decision_function` de los dos modelos. La única
prueba de esa ruta en esta rama usa partidos sintéticos y loaders reemplazados.

## Consequences

### Positive

- Contrasta dos fuentes de evidencia que faltan en las señales actuales, con ablaciones fuera de muestra.
- No crea un toque con interpolación ni altera el costo de cambiar o la pelota muerta.
- Los modelos actuales conservan sus señales, árboles y etiquetas.

### Negative

- El soporte estricto pierde evidencia cuando se oculta la pelota, justamente donde puede haber un toque.
- Una trayectoria puede cambiar por ruido y no por control; el movimiento cercano tampoco prueba posesión.
- La elección entre cuatro variantes tiene optimismo de selección, como advierte el ADR-021.
- Los empates del decodificador siguen la convención H del ADR-014; la antisimetría exigida corresponde al puntaje.

## Alternatives Considered

- Duplicar distancia, velocidad o acercamiento: ya están en `LIVE_FEATURES`.
- Umbral manual para detectar toques: introduce un parámetro sin calibración ni verdad de toque.
- Pelota interpolada o estimada para medir impulso: puede fabricar cambios de trayectoria en los huecos;
  la estimación de pelota es otra alternativa del ADR-021.
- Cambiar el decodificador o las paradas: son ADR-024 y ADR-025, quedan afuera de esta alternativa.
- Smart Tagging o video: no hay señales comparables en estos datos abiertos y quedan afuera del #86.

## References

- `AGENTS.md`; ADR-005, ADR-006, ADR-009, ADR-011, ADR-014, ADR-019 y ADR-021.
- `docs/EXPERIMENTOS.md`, diagnóstico de selección del 31/10; issue #86.
- `possession.py`, `calibrate_live.py`, `calibrate_edges.py`, `bench.py`.
- Metrica `metrica-sports/sample-data`; IDSSE, revisión `a715a38`, CC BY 4.0, Bassek y otros (2025).
