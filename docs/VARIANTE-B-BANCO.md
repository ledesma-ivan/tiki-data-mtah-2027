# Variante B: resultados de comprobación

La regla de referencia está definida en el [ADR-005](adr/ADR-005-verdad-de-posesion-en-game-3.md)
y documentada en `bench.truth_labels`; este archivo conserva los resultados de validación.

## Game 3: corrida del 29/10/2026

Emanuel, Windows, código incluido en el commit original `6049bd3`, antes del rebase.
Metrica Sample Game 3 abierto; una semilla (`--seed-start 0`), ambos anclajes y sin
bootstrap. Las demás opciones quedaron en sus valores predeterminados de esa versión:
45% de faltantes en juego, 0% en pelota muerta, huecos de 1.5 s y `crowd=0`.

```powershell
.\.venv\Scripts\python.exe bench.py --games 3 --seeds 1 --seed-start 0 --bootstrap 0 --truth start,end --truth-variant A
.\.venv\Scripts\python.exe bench.py --games 3 --seeds 1 --seed-start 0 --bootstrap 0 --truth start,end --truth-variant B
```

Resumen del pipeline `radio`:

| Anclaje | Pelota | Posesiones de referencia A | Posesiones de referencia B | Posesiones predichas (A y B) | spellF1 con A | spellF1 con B |
|---|---|---|---|---|---|---|
| start | as is | 383 | 234 | 317 | 0.600 | 0.634 |
| end | as is | 406 | 232 | 317 | 0.583 | 0.626 |
| start | degraded | 383 | 234 | 268 | 0.525 | 0.588 |
| end | degraded | 406 | 232 | 268 | 0.512 | 0.594 |

El banco reportó 46% de pelota faltante en juego y 0% en pelota muerta tras degradarla.
A y B usan referencias distintas: el cambio de puntaje no demuestra una mejora del
predictor. Esta corrida funcional no elige N, R ni `max_gap`.

## Comprobación tras el rebase, 30/10/2026

En Windows, Emanuel comprobó el código del commit `d407028`, tras el rebase sobre `85c60c0`:
`python -m unittest -v test_bench test_bench_variant_b` terminó con 48 pruebas OK
(28 existentes y 20 nuevas); `guard.py staged` y `git diff --cached --check` pasaron.
Las métricas de la tabla corresponden a la corrida anterior al rebase.

El [registro de experimentos](EXPERIMENTOS.md) conserva las entradas de ambas fechas.
El siguiente paso del #7 es incorporar la selección de variante al barrido para
repetir la elección de parámetros con B según el ADR-005.
