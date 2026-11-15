# ADR-027: resultados de selección

Protocolo en [ADR-027](adr/ADR-027-posesion-controlada.md). Sigue Proposed y no cambia la entrega.

Preregistro: `82e959bf6dacc813429658c22a735f75e8b4e889f25c9435bd59518d4d9ff512`, `2026-11-02T18:05:03Z`. Primera medición: `2026-11-02T18:23:14.967461+00:00`.

## Implementación

`calibrate_live.game_rows(..., training_truth="A"|"B")` elige las etiquetas y las duraciones cortas de Metrica. `score(..., evaluation_truth="A"|"B")` elige solo la evaluación. `reevaluate` reutiliza los mismos arrays de predicción y rechaza coberturas X/D distintas. IDSSE conserva siempre el proveedor. A es el valor predeterminado.

La interfaz histórica `--select` también acepta `--training-truth` y `--evaluation-truth`. Con una verdad distinta de A exige `--choice-report` separado de `live_choice.json`. Ese modo conserva el barrido histórico del ADR-014; no es la corrida de este ADR. La familia cerrada de este ADR se reproduce exclusivamente con:

```bash
export MTAH_OFFICIAL=/home/matias/open-data/mtah2027
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 flock /tmp/mtah-heavy.lock \
  /home/matias/open-data/venv/bin/python explore/controlled_truth.py
```

## Diferencias contra R

R y candidata se entrenaron de cero en cada uno de los siete pliegues. Las dos mitades de cada IDSSE quedaron juntas fuera del ajuste. Solo se usaron Metrica 2-3 e IDSSE 1-5, con semillas 0-9 y 0-4 respectivamente. Las matrices X y el muestreo fueron idénticos. Todas las predicciones se calcularon con los árboles enteros exportados. El recorrido compilado conserva exactamente cada umbral y hoja; convierte cada hoja a int64 antes de sumar. Los primeros arrays H/A de cada modelo y pliegue se compararon score por score con possession.tree_scores.

Diferencia pareada B-start menos A-start, 1000 remuestreos, intervalo 5-95%. R contra sí misma tiene diferencia e intervalo exactos 0 en todas las evaluaciones.

| Banco | Evaluación | Diferencia | Unidades positivas |
|---|---|---|---|
| Metrica | A end | -0.0265 [-0.0366, -0.0162] | 0/2 |
| Metrica | A start | -0.0275 [-0.0376, -0.0170] | 0/2 |
| IDSSE | provider status | -0.0237 [-0.0295, -0.0177] | 0/10 |
| Metrica | B end | +0.0206 [+0.0129, +0.0277] | 2/2 |
| Metrica | B start | +0.0203 [+0.0129, +0.0275] | 2/2 |

Media con igual peso de Metrica B start e IDSSE: -0.001710; 2 de 12 unidades positivas.

No pasa la regla de selección. No se propone adoptar B-start.

| Condición fijada antes de medir | Cumple |
|---|---|
| Metrica_B_lo_above_0 | sí |
| IDSSE_lo_above_0 | no |
| Metrica_A_noninferiority | no |

Tiempo de pared de la corrida completa: 1076.2 s, sin contar la espera por el lock. Hubo una corrida previa interrumpida manualmente por costo del recorrido interpretado, sin scores de selección. El último tiempo registrado fue 620.5 s, cota inferior del total de esa corrida. Está en explore/ADR-027_interrupted.json y en una fila separada del registro. La familia y la regla no cambiaron.

## Diagnósticos

Acierto sobre todos los frames verdaderamente vivos, incluidas como errores las predicciones D/X. Posesiones como media por unidad y semilla. Recall agregado sobre posesiones/semillas, promediado en los umbrales IoU del scorer, no solo IoU 0.5. Cortes [0,2), [2,5), [5,15] y (15,infinito) segundos.

| Banco y evaluación | Modelo | spellF1 | Acierto vivo | Predichas / verdaderas | Recall 0-2 | 2-5 | 5-15 | >15 |
|---|---|---|---|---|---|---|---|---|
| IDSSE proveedor status | A-start | 0.5626 | 0.8523 | 168.1 / 229.0 | 0.1847 | 0.4427 | 0.7425 | 0.8751 |
| IDSSE proveedor status | B-start | 0.5389 | 0.8488 | 156.7 / 229.0 | 0.1478 | 0.3984 | 0.7171 | 0.8588 |
| Metrica A end | A-start | 0.6538 | 0.8669 | 320.6 / 368.0 | 0.2598 | 0.5124 | 0.8014 | 0.8830 |
| Metrica A end | B-start | 0.6273 | 0.8624 | 297.3 / 368.0 | 0.1867 | 0.4280 | 0.7804 | 0.8812 |
| Metrica A start | A-start | 0.6728 | 0.8705 | 320.6 / 351.5 | 0.3167 | 0.5229 | 0.7991 | 0.8920 |
| Metrica A start | B-start | 0.6453 | 0.8657 | 297.3 / 351.5 | 0.2248 | 0.4382 | 0.7786 | 0.8898 |
| Metrica B end | A-start | 0.5979 | 0.8489 | 320.6 / 204.5 | 0.4253 | 0.5737 | 0.8028 | 0.8530 |
| Metrica B end | B-start | 0.6185 | 0.8535 | 297.3 / 204.5 | 0.3505 | 0.5257 | 0.7966 | 0.8615 |
| Metrica B start | A-start | 0.6033 | 0.8536 | 320.6 / 205.5 | 0.4253 | 0.5766 | 0.8058 | 0.8626 |
| Metrica B start | B-start | 0.6236 | 0.8579 | 297.3 / 205.5 | 0.3505 | 0.5294 | 0.7982 | 0.8708 |

## Comprobaciones y límites

Pasaron los 19 módulos sintéticos del repo con el entorno fijado. El módulo nuevo también comprueba que un modelo B exportado se repite byte a byte y que su score cambia de signo al intercambiar H/A. Se prueban pelota desconocida, límites de períodos, máscaras incompatibles, reutilización de predicciones y exclusión de todo el partido retenido.

La comprobación sintética contra `de97105` dio filas, modelo y predicciones por defecto idénticos. `possession.py`, `live_model.json`, `stops_model.json` y `live_confirmation.json` conservaron sus bytes. No cambió la inferencia y no se corrió un benchmark nuevo de 199.319 frames. El test nuevo también compara el recorrido compilado con tree_scores en los umbrales y en sus dos enteros adyacentes. No se midió en otras máquinas. El desempate H heredado del decodificador sigue igual.

Los números describen selección ya reutilizada, no una confirmación independiente. B es una convención por eventos y no prueba equivalencia con la posesión controlada del concurso. No se usaron la reserva histórica, la ventana pública ni datos del partido del concurso.

La confirmación futura del #97 está descrita en el ADR y no se implementó ni se ejecutó. Requiere banco nuevo, protocolo previo y decisión del equipo. No se vuelve a elegir con la reserva vieja.

Los agregados completos, las huellas de filas, las versiones, los hashes de modelos por pliegue y los tiempos están en `explore/ADR-027_selection.json`. La compatibilidad con la base queda en `explore/ADR-027_checks.json`.
