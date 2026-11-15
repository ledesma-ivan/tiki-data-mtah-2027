---
artifact: adr
version: "1.0"
created: 2026-11-09
status: accepted
---

# ADR-033: Las pelotas del entrenamiento y los escenarios del banco, sin niveles medidos con la verdad pública

## Status

Accepted (2026-11-09), con la revisión de Iván en el PR que cambia este estado. Fue Proposed el mismo día. Cambió `live_model.json` y el CSV, y se cumplió lo pedido: BAR-ATH en dos máquinas (Lautaro en `ba8af70` e Iván en `db8ba40`) dio `dab54052d5cf…`, y una tercera (PepiGercek, sobre `b86cdd1`) dio el mismo `sha256`.
**Los organizadores no autorizaron los niveles del ADR-002.** La respuesta le llegó a Ivan por mail antes del 08/11:
repite la regla de entrenar y ajustar solo con datos externos y cierra con "todo aquello que no esté explícitamente
permitido no está permitido" (#111). Por eso este ADR entra a la entrega.

**Date:** 2026-11-09
**Deciders:** Lautaro Bursese (con Claude)
**Issues:** #111

## Context

- **La aclaración oficial del 03/11** (la pegó Emanuel en el #111): "If you need to train (or retrain), you MUST use
  only external data. If your algorithm has parameters that need to be tuned, you MUST tune them on external data,
  never on the ground-truth possession data or on the provided video."
- **`live_model.json` se entrena con datos abiertos** (Metrica e IDSSE). Pero dos de los niveles de pelota de
  `TRAIN_BALLS` salen de la tabla "Pelota sin datos" del ADR-002, que describió la ventana pública con su GT:
  - la pelota viva sin datos en el 6,5 % de los frames;
  - las paradas sin datos en el 34 %.

  Nunca se barrieron ni se eligieron por puntaje (#111), pero su origen es la GT.
- **Los mismos dos números están en `calibrate_edges.py`:**
  - en el `TRAIN_BALLS` de IDSSE, que entrena el modelo de paradas. El entregado (`stops_model.json`) es la identidad
    y no se entrena;
  - en dos de los siete `SCENARIOS` con que se confirma cada receta (`--dead-missing 0.34`).
- **Los organizadores no contestaron** la consulta del 03/11 al 09/11, y el CSV se congela el 12/11.

## Decision

1. **Los niveles se fijan antes de correr, sin mirar nada del partido ni de la ventana:**
   - **pelota viva sin datos: 0 %, 20 % y 45 %.**
     - El 0 % reemplaza al 6,5 %: no borra nada, y queda la pelota que ya falta en los datos abiertos (ADR-006). Es
       el extremo limpio.
     - El 20 % y el 45 % ya estaban (ADR-006). El 45 % sale del 41 % de los frames calificados que publica `DATA.md`,
       que es documentación oficial y no la GT;
   - **paradas sin datos: 0 % y 50 %.** El 50 %, la mitad del rango que no conocemos, reemplaza al 34 %.

   En el código:
   - `calibrate_live.TRAIN_BALLS` queda así: semilla 100, viva 0; semilla 101, viva 0.2 y paradas 0.5; semilla 102,
     viva 0.45; semilla 103, viva 0.45, huecos de 3 s y paradas 0.5;
   - en `calibrate_edges.TRAIN_BALLS` de IDSSE, viva (0, 0.2, 0.45) × paradas (0, 0.5);
   - en `calibrate_edges.SCENARIOS`, `--dead-missing 0.5` y `--missing 0 --dead-missing 0.5`.
2. **La receta se vuelve a elegir** con `calibrate_live.py --select`, que es la misma grilla de 8 recetas, LOMO sobre
   los 7 partidos de selección. La que gane es la entregada, con `short_weight` 1 (#91).
3. **La confirmación es contra `radio`, no contra otra receta.** Corre
   `calibrate_live.py --confirm --reference radio --seed-start 110`, con las mismas 43 condiciones y la misma regla
   del ADR-019.
   - **Por qué:** el ADR-019 pregunta si un cambio mejora la receta entregada. Este cambio es por cumplimiento, así que
     la pregunta es si el modelo que cumple funciona. La alternativa que cumple sin entrenar nada es `radio`
     (`calibrate_live.py --rule`, ADR-009). Si el modelo nuevo no le gana en las 43 condiciones, se entrega `--rule`.
   - **La reserva suma una mirada** (#97). Contra `radio`, con el peso 1, los márgenes fueron de +0.08 a +0.18 (#77), así que no
     decide entre alternativas parecidas.
   - **En el código**, `--reference radio` en `calibrate_live.py`.
4. **Con la confirmación, `--final`** escribe `live_model.json`, y BAR-ATH corre en dos máquinas (Lautaro e Iván).
5. **Lo que se mide y no decide:** la receta de hoy con las pelotas viejas, en la misma selección, con el mismo código
   y las mismas semillas (`--select --choice-report`). Sirve para contar cuánto cuesta el cambio y no vuelve atrás
   nada: si los organizadores no autorizan, se entrega el modelo que cumple.

## Consequences

### Positive

- Ningún valor de lo que se entrena, se elige o se confirma sale de la GT. Con la aclaración del 03/11, eso deja el
  modelo del lado seguro.

### Negative

- Cambian el modelo y el CSV: hacen falta BAR-ATH en dos máquinas y el `sha256` nuevo en el README, `TECHNICAL.md` y
  `ENTREGA.md`.
- La reserva suma una mirada.
- Puede perder algo de `spellF1`, que se mide en la selección (punto 5).

### Neutral

- `stops_model.json` sigue siendo la identidad.
- `bench.py` no cambia: su `--dead-missing` es un argumento, y por defecto vale 0.

## Cómo se mide

`spellF1` pareado contra `radio` (`bench.compare`, 1000 sorteos), en dos tramos:

- **en la selección**, con LOMO sobre Metrica Games 2 y 3 e IDSSE 1 a 5;
- **en la reserva**, sobre Metrica Game 1 (semillas 110 a 119) e IDSSE 6 y 7 (semillas 110 a 114).
