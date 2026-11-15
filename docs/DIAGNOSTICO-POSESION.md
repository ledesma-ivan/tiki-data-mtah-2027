# Diagnóstico del modelo de posesión (ADR-020, #85)

```powershell
python explore/diagnose_changes.py --report live_diagnosis.json
```

Necesita las dependencias de `requirements-train.txt`, el scorer oficial fijado en `ci_config.json`
y los datos abiertos Metrica sample-data e IDSSE en sus ubicaciones habituales. Si el repo oficial
no está en `../mtah2027`, se indica con `MTAH_OFFICIAL`. No usa `MTAH_DATA` ni carga BAR-ATH.

El comando reconstruye el par histórico del #77: hojas 63, lambda 10, corte de 5 s y pesos 1/3.
La comparación no cambia aunque el equipo decida entregar otra receta. No busca parámetros,
no exporta modelos y no selecciona una versión de entrega.

## Particiones y referencias

- Siete pliegues de selección: Metrica Games 2-3 e IDSSE 1-5. Ambos modelos se ajustan con los
  otros seis partidos de cada pliegue; las dos mitades de un partido IDSSE se excluyen juntas.
- Entrenamiento: Metrica A/start e IDSSE/status, incluidas las duraciones usadas para ponderar.
- Predicción: misma pelota, jugadores y máscaras para ambas recetas. La cobertura de cada
  anclaje se fija con A. Las predicciones no se recalculan al cambiar de A a B.
- Evaluación: A/start principal, A/end y B/start/end como sensibilidades separadas; IDSSE/status
  aparece una sola vez. Si difieren las máscaras X/D o los tramos válidos, se rechaza la evaluación.
- Semillas: Metrica 0-9 e IDSSE 0-4. Se conserva `1000 * game.g + seed` para las pelotas y
  `10000 * game.g + seed` para el ruido de jugadores. El entrenamiento mantiene sus semillas propias.
- Tres escenarios fijados: jugadores limpios, ruido de posición de 1 m y el combinado de 0.6 m,
  10% perdidos y 5% de cambios de identidad. Los dos últimos son descriptivos.

Antes de evaluar B, A/start e IDSSE/status deben reproducir las diferencias medias de selección
del #77: aproximadamente +0.0026 y +0.0157. Se admite únicamente la incertidumbre de redondeo de
las cifras publicadas; una discrepancia detiene el comando y debe explicarse antes de continuar.
La tolerancia absoluta de la diferencia es 0.0001: cada media publicada a cuatro decimales aporta
como máximo 0.00005. Se rechazan puntos no finitos. El control conserva los objetivos del #77.
En ese caso se conserva el informe agregado A con estado `reconstruction_failed`, las diferencias
por unidad y las huellas del entrenamiento. B no se carga ni se puntúa. Así se puede investigar
la discrepancia sin perder la evidencia ni presentar un informe A/B como completo.

## Informe agregado

`live_diagnosis.json` registra las recetas, revisión y archivos modificados, scorer y versiones,
grupos de entrenamiento/evaluación, huellas de filas y modelos por pliegue, escenarios y semillas.
Contiene métricas agregadas, sin tracking ni predicciones por frame.
La CLI rechaza rutas de informe que coincidan con los modelos entregados, la receta o la confirmación
del ADR-019. Antes de ajustar, comprueba que cada partido esté completo (las dos mitades en IDSSE)
y que los identificadores de partidos/mitades sean únicos.

Para cada banco/referencia/escenario incluye `spellF1` de las dos recetas y la diferencia pareada
con 1000 remuestreos y percentiles 5-95 del comparador del ADR-019. Informa recall a IoU 0.5 en
duraciones de 0-2, 2-5, 5-15 y más de 15 s, conteos de posesiones, razón predichas/reales y
frecuencia por minuto vivo. Los conteos se promedian por semilla antes de sumar unidades:
las diez degradaciones de un partido no cuentan como diez partidos reales.

Se conservan las categorías heurísticas del diagnóstico anterior: equipo incorrecto, pelota
muerta predicha, división, fusión y bordes. No son atribuciones causales demostradas. A y B no se
promedian ni se comparan como si fueran dos predictores distintos.

Los partidos de selección ya se usaron para elegir recetas. El LOMO diagnostica fuera del
entrenamiento, pero no constituye una confirmación independiente ni recupera una reserva intacta.
La decisión del #91 sigue su propio protocolo y no espera ni depende de este informe.

## Modo explícito de reserva

La primera corrida del #85 usa solamente selección. El modo `--reserve` existe para una receta
fijada previamente y exige todas sus claves, revisión de código y bloque de semillas (desde 90).
El ADR-020 registró 80 como próximo bloque en su fecha; el #97 informa que el ADR-021 ya lo consumió.
Rechaza modificaciones locales de código o dependencias respecto de esa revisión. La CLI no puede
comprobar por sí sola que la revisión se registró antes ni que nadie usó ya el bloque: eso se
registra antes de correr y se controla en la revisión humana.

```powershell
python explore/diagnose_changes.py --reserve --revision COMMIT_REGISTRADO --seed-start 90 --reference leaves=63 lam=10 short_s=5 short_weight=1 --candidate leaves=63 lam=10 short_s=5 short_weight=3 --report live_diagnosis_reserve.json
```

Entrena con selección y comprueba en Metrica Game 1 e IDSSE 6-7. Es otra mirada a una reserva ya
examinada, no una búsqueda ni una nueva validación independiente. No ejecutarlo para explorar.

## Pruebas

```powershell
python -m tests.test_diagnose_changes
python ci_checks.py tests
```

Los tests nuevos verifican reutilización de predicciones, entrenamiento A inalterado, carga B con
eventos inventados, rechazo de cobertura y semillas no pareadas, exclusión de ambas mitades,
ausencia de carga de reserva, conteos por semilla, equivalencia de recetas y guardas de reserva.
Los eventos de recuperación, pase de primera, mismo frame, reinicio y período se cubren además
con `tests/test_bench_variant_b.py`.

## Continuación forense del #77 (08/11/2026)

La [reconstrucción documentada](DIAGNOSTICO-POSESION-RECONSTRUCCION.md#continuación-forense-del-08112026-transcripción-de-77-recuperada)
incorpora los cuatro logs recuperados de #111, comandos originales y comprobaciones aisladas sobre datos externos.
La selección con pesos 1/3/5 reproduce los resultados de la reconstrucción previa, pero no los históricos.
La exportación de `67b8fe6` sí reproduce exactamente el SHA del modelo histórico. Se comprobaron por separado
solo las **tres condiciones por defecto de cada peso** con semillas 50, sin repetir las 43 condiciones ni seleccionar
recetas. Los 43/43 completos corresponden únicamente a los logs históricos recuperados.

Esa coincidencia del export no satisface el control A fuera del entrenamiento: **los dos bancos** incumplen la
tolerancia original de **0.0001**.
Se mantiene B real bloqueado y #85 pendiente. Los hashes, entornos, revisiones actuales de datos y métricas
agregadas están en `docs/evidence/issue111/`; sus revisiones y versiones históricas siguen sin confirmar.
Los scripts `explore/audit_77_reproduction.py` y `explore/audit_77_default_confirmation.py` son instrumentos de
auditoría aislada. El segundo es una comprobación forense parcial de una reserva ya expuesta, no un comando
para volver a explorarla ni una confirmación nueva de entrega.

Las seis filas de experimentos están en `docs/EXPERIMENTOS.md` del worktree de diagnóstico. El archivo
`docs/evidence/issue111/experiment-rows-20261108.md` es una copia de las mismas filas, conservada localmente;
no debe agregarse de nuevo al registro ni confundirse con un cambio en la copia principal.
