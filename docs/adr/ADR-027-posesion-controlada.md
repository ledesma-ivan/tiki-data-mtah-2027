---
artifact: adr
version: "1.0"
created: 2026-11-02
status: proposed
---

# ADR-027: Separar la verdad de entrenamiento de la de evaluación para probar posesión controlada

## Status

Proposed (2026-11-02). Issue #94. Lo escribe Matias con Codex, gpt-6.1-sol, antes de medir.
Pasa a `Accepted` solo con la revisión de otra persona en el PR. No cambia la entrega.

## Context

El concurso pide posesión controlada. Un toque sin control, un desvío que no intercepta o un duelo
 aéreo sin control posterior no alcanzan para cambiarla. A cuenta cada evento rival con pelota;
B exige dos eventos consecutivos del rival en frames distintos y fecha el cambio al primero.
B es una aproximación por eventos, no la verdad del concurso. IDSSE trae el dueño del proveedor.
El ADR-020 separa B como sensibilidad, pero conserva A al entrenar y decidir. El #94 pregunta si
entrenar con B reduce la dependencia de los toques que cuenta A.

El equipo eligió la opción A del #91. R es la receta del ADR-014 con 63 hojas, `lam=10`,
`short_weight=1`, `short_s=5`, `dead_mask_v2` y paradas identidad. Se entrena de cero en cada
pliegue. `live_model.json` todavía tiene peso 3 y no es una referencia válida.

## Decision

### Familia cerrada antes de medir

| Variante | Verdad de entrenamiento en Metrica | Anclaje | Posesiones cortas |
|---|---|---|---|
| `A-start` (R) | A | start | A start, duración menor que 5 s |
| `B-start` | B | start | B start, duración menor que 5 s |

IDSSE conserva `status` para etiquetas y duraciones en las dos variantes. Solo cambia la verdad
que arma `y` y la duración que identifica las posesiones cortas. Con peso 1, esa identificación
no altera los pesos. Las filas se muestrean igual porque A y B deben tener idénticas máscaras X/D.
No se cambian señales, degradaciones, ruido de entrenamiento, hiperparámetros, normalización,
árboles exportados ni decodificador. No se exploran otros anclajes de entrenamiento ni pesos.

`calibrate_live.py` permite elegir la verdad de entrenamiento y la de evaluación por separado,
con A como valor predeterminado. Las posesiones cortas usan la verdad de entrenamiento elegida.
Una opción de evaluación nunca cambia filas ni modelos. Las predicciones se calculan una sola vez
por anclaje y se reutilizan para A/B después de verificar longitud, máscaras X/D y tramos válidos.
Se mantienen los anclajes de evaluación start y end separados. IDSSE no inventa una variante B.
Los modos históricos de confirmación/exportación no habilitan estas opciones nuevas, porque
su protocolo y sus huellas todavía son los del ADR-019. Este trabajo no los ejecuta.

### Regla de decisión

Se compara `B-start` menos R con 1000 remuestreos pareados de posesiones y semillas de
`bench.compare`, por banco. B start en Metrica y status en IDSSE son la evaluación principal.
La candidata pasa la selección solo si:

1. El límite 5% es estrictamente mayor que 0 en Metrica B start y en IDSSE status.
2. El límite 5% de Metrica A start es mayor o igual que −0.0100, margen de no inferioridad
   fijado en un punto de spellF1 absoluto para limitar el costo bajo la convención anterior.
3. Las comprobaciones sintéticas de simetría, enteros, períodos, pelota desconocida y exclusión
   del partido retenido pasan. La inferencia no cambia.

Se reportan A end y B end, pero no deciden. La media da igual peso a Metrica B start e IDSSE;
se cuentan las unidades positivas en esa evaluación principal, sobre 12. Con una sola candidata
no hay desempate ni búsqueda posterior. Si no pasa, no se propone adoptar ninguna variante.

## Cómo se mide

- Selección exclusivamente: Metrica Games 2-3 con semillas 0-9 e IDSSE 1-5 con 0-4.
  LOMO por partido; las dos mitades de IDSSE salen juntas del entrenamiento.
- Pelota degradada por defecto: 45% faltante en vivo, huecos de 1.5 s, jugadores limpios al evaluar.
  Entrenamiento y normalización del ADR-014, con las mismas filas X para las dos variantes.
- Scorer oficial local de `MTAH_OFFICIAL=/home/matias/open-data/mtah2027`, revisión f8f2629.
  Intervalos 5-95% por banco, sin remuestrear partidos, como `bench.compare`.
- Diagnósticos de R y candidata, por evaluación: acierto sobre todos los frames verdaderamente
  vivos, posesiones predichas/verdaderas medias por unidad y semilla, recall por duración verdadera
  0-2, 2-5, 5-15 y más de 15 s. Para evitar ambigüedad de bordes, los cortes son [0,2), [2,5),
  [5,15] y (15,infinito). Recall es la media de los aciertos del scorer sobre sus umbrales de IoU.
- Resultados y tiempos en `explore/ADR-027_selection.json`; una fila por corrida, incluso fallida,
  en `docs/EXPERIMENTOS.md`. El hash de este ADR y la hora UTC se guardan antes de medir en
  `explore/ADR-027_preregistration.log`. Los resultados posteriores van en otro documento para
  conservar verificable este hash.
- No se usa la reserva cerrada: ni Game 1 ni IDSSE 6-7. No se abre la ventana pública. No se
  usan semillas 70-89. No hay red, instalaciones, commits ni cambios a modelos entregados.

### Confirmación futura sobre el banco del #97, sin ejecutar

Solo si pasa esta selección y el equipo lo decide, fijar en un nuevo protocolo los partidos nuevos
del #97, su partición, sus semillas todavía no usadas y la adaptación de las 43 condiciones.
Entrenar R con A y la candidata con B sobre los siete partidos de selección, sin incorporar los
partidos nuevos. Aplicar sin ajustes las dos recetas y la regla principal B/proveedor con el
mismo margen A. Medir también anclaje end, sensibilidades de pelota, ruido de jugadores y
árboles enteros contra `decision_function`. La verdad del proveedor nuevo debe definirse antes
de mirar números, y una persona debe revisar si permite un control A comparable. Si no lo
permite, el equipo debe resolver esa limitación antes de confirmar. Una sola confirmación de
la candidata, sin volver a elegir con su resultado. La reserva vieja sigue cerrada.

## Consequences

### Positive

La convención que entrena queda explícita y separada de la que mide. Se puede probar B sin
cambiar inferencia ni la entrega. R se reconstruye con la receta elegida por el equipo.

### Negative

Dos partidos de Metrica son pocos y las anotaciones difieren entre Games 2 y 3. B también
impone un criterio artificial de confirmación y puede borrar control real de un solo evento.
La selección ya se usó para otras decisiones. Pasar esta regla no confirma transferencia.

## Alternatives Considered

- Mantener B solo como sensibilidad, como ADR-020. Sigue siendo el comportamiento por defecto.
- Entrenar con end o mezclar A/B. Agregaría variantes y otra pregunta a una comparación que
  puede aislar el efecto de B con dos recetas.
- Cambiar el peso de cortas o la penalidad. El #91 ya eligió peso 1 y lam 10; acá se fijan.
- Confirmar en la reserva histórica o con la ventana pública. Prohibido para esta tarea.

## References

- ADR-005, ADR-006, ADR-011, ADR-014, ADR-019, ADR-020 y ADR-021.
- Issues #91, #94 y #97; PR #92, diagnóstico con B, y PR #98, registro de la ronda anterior.
- `bench.truth_labels`, `bench.compare`, `calibrate_live.py`, `calibrate_edges.export` y
  `possession.tree_scores`.
- Metrica sample-data y IDSSE, revisión a715a38, citados en `docs/TECHNICAL.md`.
