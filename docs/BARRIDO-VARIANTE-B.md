# Variante B en el barrido del ADR-009

`explore/radius_sweep.py --truth-variant A|B` permite repetir el barrido con las
referencias del ADR-005. A es la opción predeterminada; B es el chequeo de
sensibilidad. Cada corrida usa una sola referencia y la identifica en la salida.
El anclaje sigue siendo el inicio del evento (`start`).

Con los mismos partidos y semillas, A y B usan la misma pelota degradada, los
mismos intervalos evaluados y las mismas predicciones para cada combinación de
R, N, interpolación y `max_gap`. Solo cambian las etiquetas de referencia y los
puntajes. Por eso se compara qué parámetros elige cada referencia; un puntaje
mayor con B no demuestra una mejora del predictor.

## Comprobación funcional en PowerShell

Desde la raíz del repositorio, con Metrica Sample Game 3 instalado, correr por
separado la misma grilla pequeña con A y B:

```powershell
.\.venv\Scripts\python.exe explore/radius_sweep.py --games 3 --seeds 1 --seed-start 0 --dead true --radii 1 --n 0.25,0.5,1,2 --interp 50 --gaps 100 --top 5 --truth-variant A
.\.venv\Scripts\python.exe explore/radius_sweep.py --games 3 --seeds 1 --seed-start 0 --dead true --radii 1 --n 0.25,0.5,1,2 --interp 50 --gaps 100 --top 5 --truth-variant B
```

Son cinco combinaciones: cuatro candidatas más la línea de base congelada. La
fila `current` es la regla v1 anterior al ADR-009 (R infinito, N de 2 s, última
posición de pelota y `BASE_GAP`), no el modelo de entrega del ADR-014. N se expresa
en segundos; `--interp` y `--gaps`, en frames a 25 Hz.

Estas corridas verifican el funcionamiento; no seleccionan ni confirman nuevos
parámetros. Game 3 necesita `Sample_Game_3_tracking.txt`, `Sample_Game_3_events.json`
y `Sample_Game_3_metadata.xml` en `data/Sample_Game_3`. El cargador reconstruye su
caché cuando cambian las fuentes o el cálculo de velocidades.

## Barrido y alcance

Para repetir la grilla original de 300 combinaciones del ADR-009:

```powershell
.\.venv\Scripts\python.exe explore/radius_sweep.py --games 2,3 --seeds 3 --seed-start 0 --dead true --truth-variant A
.\.venv\Scripts\python.exe explore/radius_sweep.py --games 2,3 --seeds 3 --seed-start 0 --dead true --truth-variant B
```

Fijar la misma grilla y el mismo bloque de semillas antes de correr. Ordenar por
la pelota degradada, como hace el script; la pelota tal cual es un chequeo.
Registrar cada corrida y sus opciones como filas nuevas en `EXPERIMENTOS.md`.

Este paso incorpora la referencia B al barrido de Metrica. Quedan pendientes la
selección conjunta con IDSSE y la confirmación en la reserva según el ADR-011:
Metrica 2-3 e IDSSE 1-5 para selección, Metrica 1 e IDSSE 6-7 para reserva, con
semillas nuevas y diferencias pareadas con bootstrap. El ranking del barrido no
trae esos intervalos ni equivale a esa confirmación. Los umbrales de entrega no
se modifican en este cambio; el modelo de juego vivo se rige por el ADR-014.

## Validación del 31/10/2026

Emanuel aplicó el parche sobre `2987431` y ejecutó en Windows las 55 pruebas de
`test_bench`, `test_bench_variant_b` y `test_radius_sweep`: todas aprobadas.
También completó las dos comprobaciones funcionales de Game 3 y la grilla
original de 300 combinaciones en Games 2 y 3, tres semillas (índices 0-2), `D`
verdadero y anclaje `start`. Las corridas se registran en `EXPERIMENTOS.md`.

Primer puesto por `spellF1` con la pelota degradada en la grilla de 300:

| Referencia | R (m) | N (s) | Interpolación (frames) | max_gap (frames) | Tal cual | Degradada |
|---|---|---|---|---|---|---|
| A | 1.5 | 0.5 | 50 | 25 | 0.725 | 0.627 |
| B | 1.0 | 1.0 | sin tope | 25 | 0.787 | 0.733 |

La elección conjunta cambia al cambiar la referencia: además de N, cambian R y
la interpolación. Los puntajes de A y B usan etiquetas distintas y no miden una
mejora entre predictores. En A, una combinación con N = 0.25 s llega a 0.625,
cerca del primer puesto; este ranking no aporta intervalos para distinguirlas.
Ambos primeros puestos usan `max_gap` = 25 frames (1 s), el borde superior de la
grilla original. No se eligió un nuevo umbral de entrega ni se ejecutaron IDSSE
o la reserva en esta etapa: la selección conjunta y la confirmación del ADR-011
siguen pendientes.
