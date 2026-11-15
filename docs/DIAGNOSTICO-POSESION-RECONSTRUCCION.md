# Reconstrucción A del diagnóstico de posesión (#85)

Corrida del 2/11/2026, solo selección fuera del entrenamiento. **La reconstrucción histórica falló; B no se cargó ni evaluó. El #85 sigue pendiente.**

Se llamó a `predict_folds` con solo el escenario por defecto y jugadores limpios, y se reutilizaron `comparison` y `check_reconstruction`. Se entrenaron las dos recetas históricas por partido completo, manteniendo juntas las mitades de IDSSE. Semillas: Metrica 0-9 e IDSSE 0-4. No se consultó la reserva ni se modificaron los modelos entregados.

| Banco / referencia | Peso 1: spellF1 | Peso 3: spellF1 | Diferencia pareada (5-95%) | Diferencia histórica aproximada |
|---|---|---|---|---|
| Metrica / end | 0.653817 | 0.653369 | -0.000448 [-0.009212, +0.008562] | No fijada |
| Metrica / start | 0.672799 | 0.672072 | -0.000727 [-0.009851, +0.008576] | +0.0026 |
| IDSSE / status | 0.562600 | 0.582560 | +0.019960 [+0.013509, +0.026698] | +0.0157 |

El intervalo no reemplaza el control de reconstrucción: hay que explicar la diferencia histórica antes de mirar B. No se interpreta este diagnóstico como una confirmación independiente ni se usa para decidir #91.

## Procedencia y controles

- Python 3.12.10 en Windows, NumPy 2.5.1, scikit-learn 1.9.1 y cuatro hilos OpenMP.
- Los scorers local y fijado por CI tienen el mismo SHA-256 al normalizar finales de línea.
- Las siete huellas de filas coinciden con `live_confirmation.json` del ADR-019. No existen aquí huellas de los modelos LOMO del #77 para contrastarlas.
- La extracción por AST del `fit` histórico y el actual dio resultados idénticos en un control sintético; las agregaciones histórica y actual calculan el mismo punto por unidad y promedio.
- El informe agregado, conteos, recall, errores heurísticos, recetas y huellas están en [`live_reconstruction.json`](../live_reconstruction.json). La corrida partió de `5817e5f` con correcciones locales luego guardadas en `4c9ad10`; el campo `code` conserva esa procedencia.
- No se identificó una causa demostrada. Falta contrastar el entorno y los artefactos de la selección original.

## Control de hilos

Con las mismas filas de seis grupos de selección, excluyendo Metrica Game 2, los modelos de pesos 1 y 3 tuvieron exactamente el mismo hash con 1, 4 y 12 hilos. Hubo cero scores enteros distintos en una muestra fija. No se evaluó B ni reserva ni se seleccionó un modelo. La prueba no respalda el paralelismo como explicación en ese pliegue, sin generalizar a cualquier entrada. Detalle en [CONTROL-HILOS-85.md](CONTROL-HILOS-85.md).

## Intentos registrados

1. La corrida de un hilo se interrumpió por costo después del primer pliegue, sin evaluar B.
2. La corrida de cuatro hilos terminó los siete pliegues y las predicciones de los tres escenarios, pero falló el control A antes de B. El camino inicial de error no conservaba el resumen.
3. Se corrigió esa pérdida con un test y se ejecutó esta reconstrucción A preparatoria, guardada aunque el control falle.

El registro de `EXPERIMENTOS.md` conserva los intentos. B y el informe completo de sensibilidades siguen pendientes; este documento no los presenta como realizados.

## Comprobación independiente de Emanuel (02-03/11/2026)

Emanuel ejecutó su implementación del ADR-020 sobre `20ba28d` con cambios locales, guardada después
en `1d8af34`. En Windows con Python 3.12.14, NumPy 2.5.1, pandas 3.0.5, scikit-learn 1.9.1 y SciPy
1.18.1, pasaron sus 66 pruebas con datos inventados y los módulos de calibración. La selección con A
usó los mismos bloques de semillas y recetas históricas; no construyó B ni puntuó la reserva.

| Banco | Peso 1 menos radio | Peso 3 menos radio | Peso 3 menos peso 1 |
|---|---|---|---|
| Metrica / start | +0.126003 | +0.125276 | -0.000727 |
| IDSSE / status | +0.163020 | +0.182980 | +0.019960 |

En un worktree de `67b8fe6`, con el mismo intérprete y datos, `explore/short_weight.py --weights 1 3`
dio +0.1260 / +0.1253 en Metrica y +0.1630 / +0.1830 en IDSSE, con el peso 3 por encima en 10/12
unidades. La coincidencia a cuatro decimales no acredita identidad de predicciones por frame.

Las siete huellas de filas de Emanuel coinciden con las del informe del ADR-019 en `20ba28d`, igual
que el scorer, las señales y las versiones registradas de NumPy y scikit-learn. Al contrastar su
`reconstruccion85.json` con `live_reconstruction.json` de esta rama, también coincidieron las 84
correspondencias de huellas por partido dentro de los dos modelos y siete pliegues. Los puntos
principal Metrica e IDSSE difieren entre implementaciones en menos de 1e-16. Son controles de las
mismas unidades abiertas; no constituyen 84 partidos ni una nueva confirmación.

Estos controles refuerzan la coincidencia entre implementaciones en el entorno observado. El informe
del ADR-019 es posterior al #77 y no reconstruye la procedencia de su selección original. Sigue
pendiente contrastar el comando, salida y entorno efectivos de aquella corrida, consultados a sus
autores en el #85. No se atribuye la discrepancia a una causa demostrada ni se habilita B con este registro.

## Continuación forense del 08/11/2026: transcripción de #77 recuperada

**Estado revisado:** la exportación reproduce exactamente el SHA-256 histórico. A incumple la tolerancia
original de **0.0001 en ambos bancos** y **B sigue bloqueado**. La reproducción actual de confirmación cubre
solo **tres condiciones por defecto por peso** (seis resultados entre pesos 1 y 3); los **43/43 completos son
resultados de los logs históricos**. La incidencia de cachés compartidas sigue siendo una hipótesis no comprobada.

**Ubicación del registro:** las seis filas del 08/11 están anexadas a `docs/EXPERIMENTOS.md` **de este worktree**
(`.audit-85-20261108/diagnostic`), no al archivo de la copia principal. El archivo
[`experiment-rows-20261108.md`](evidence/issue111/experiment-rows-20261108.md) conserva una copia exacta de las filas
anexadas; no es un registro alternativo ni debe volver a anexarse. El archivo principal de `EXPERIMENTOS.md`
y los cambios locales originales se conservaron. Para publicar se propone el registro real, sin duplicar esa copia.

El comentario de [Iván en #111](https://github.com/nodalsports/more-than-a-hack-2027/issues/111#issuecomment-6727829010)
publica los cuatro logs como bloques de texto, no como adjuntos descargables. Se guardaron en
[`evidence/issue111/`](evidence/issue111/source.json), junto con fuente, fecha y hashes. Los hashes siguientes
identifican la extracción UTF-8 de los bloques; **no acreditan los bytes de los archivos originales**.
`sw1.txt` está incompleto al principio. Los logs equivalentes de Lautaro siguen pendientes.

| Log recuperado | SHA-256 de la extracción |
|---|---|
| `sw1.txt` | `636ba19240592fa29911350b6b8e752321135d569ba28a8a23336759d6b155f2` |
| `conf_w1.txt` | `09748ce0479400250b2bf8727003e7aba517f2ab3a2873a538c82ba224d498db` |
| `conf_w3.txt` | `1c08743579a722d087687bd4e3ea5aee0d21dfe3f97df930305ced480b603ea4` |
| `final3.txt` | `509d146bf2ae072f58430aa42b627d0bf46d761ccc74c80227575845b06c0ea2` |

### Comandos recuperados y alcance

Iván identifica el commit `67b8fe6`, Windows y `.venv-repro`, con las demás opciones por defecto:

```powershell
python explore/short_weight.py --weights 1 3 5
python explore/short_weight.py --confirm 1 --seed-start 50
python explore/short_weight.py --confirm 3 --seed-start 50
python calibrate_live.py --final
```

Las dos confirmaciones corrieron como procesos separados simultáneos. No hubo `--reference` ni ADR-019,
posterior al experimento. Se resuelve así la duda del comando y del tipo de comparación, pero **siguen SIN
CONFIRMAR las versiones históricas del entorno, la revisión de los datos externos y el estado de sus cachés**.
Las versiones actuales de Iván comunicadas por el equipo son Python 3.12.10, NumPy 2.5.1, scikit-learn 1.9.1
y SciPy 1.18.1; no se presentan como prueba de las instaladas el 31/10.

### Selección, confirmaciones y exportación son comprobaciones diferentes

| Etapa | Histórico recuperado | Reconstrucción previa comprobada en esta rama | Interpretación |
|---|---|---|---|
| Selección, peso 1 contra radio | Metrica +0.1224; IDSSE +0.1646 | Metrica +0.126003; IDSSE +0.163020 | Las cifras originales quedan respaldadas por el log; la discrepancia permanece. |
| Selección, peso 3 contra radio | Metrica +0.1250; IDSSE +0.1803 | Metrica +0.125276; IDSSE +0.182980 | No se confunde esta comparación con peso 3 menos peso 1. |
| Selección, peso 5 contra radio | Metrica +0.0970; IDSSE +0.1800 | No estaba documentada en la reconstrucción previa | Es una receta fija de la transcripción, no un nuevo candidato elegido aquí. |
| Confirmación peso 1 contra radio | 43/43; por defecto Metrica start +0.1176 [0.0937, 0.1420], end +0.1162 [0.0925, 0.1416]; IDSSE +0.1440 [0.1204, 0.1657] | El ADR-019 posterior no reproduce este protocolo | Semillas 50–59 y 50–54, 1000 remuestreos. |
| Confirmación peso 3 contra radio | 43/43; por defecto Metrica start +0.1368 [0.1075, 0.1647], end +0.1346 [0.1050, 0.1631]; IDSSE +0.1538 [0.1287, 0.1784] | ADR-019 dio 41/43 contra peso 1 con otro bloque de semillas | No hay contradicción lógica entre ambos resultados: cambian control y semillas. No es una causa demostrada de la discrepancia de selección. |
| Exportación | 593518 bytes; SHA-256 `1e0579ad8232de7579ac3df6a4d49768fa6702e374e20c57ee9cec2bcb2a8ddf` | Se reproduce por separado; no se deduce de 43/43 | Que el artefacto coincida no demuestra por sí solo que se reprodujo A fuera del entrenamiento. |

No se restan los extremos de los intervalos de las dos confirmaciones para fabricar un intervalo peso 3−peso 1.
En el ruido de posición de 1 m, los puntos publicados frente a radio son +0.1526/+0.1633 para peso 1 y
+0.1356/+0.1581 para peso 3 (Metrica/IDSSE). Ambos aprueban contra radio aunque peso 3 reporte menos ventaja:
43/43 individuales no demuestra superioridad frente al peso 1. Son puntos de los logs, no un nuevo contraste pareado.
No se repitieron las confirmaciones completas: los logs recuperados acreditan qué se informó y el código explica
el cambio de comparador. Tras reproducir el export se repitió solo el bloque por defecto de cada peso, con las
semillas históricas, para localizar la diferencia por etapa. Es una reproducción forense fijada de una reserva ya
expuesta, no otra selección ni una confirmación independiente. No resuelve por sí sola la procedencia histórica.

### Valores por defecto y estado compartido: lectura de `67b8fe6`

- `explore/short_weight.py:27–43`: sin `--weights` se usa `[1, 3]`; el comando recuperado agrega explícitamente
  el 5. En selección se cambia `CL.SHORT_WEIGHT` antes de cada ajuste; se usan siempre hojas/lambda de
  `live_choice.json`. Ese script no escribe la receta ni el modelo.
- `calibrate_live.py:46–50,92–103`: corte estricto de menos de 5 s, peso comprometido 3, filas vivas muestreadas
  cada 16 frames; cada partido se equilibra **antes** de ponderar sus posesiones cortas. Los pesos finales
  se normalizan a media 1. Clasificador de 300 iteraciones, tasa 0.1, 63 hojas según la receta, mínimo 200 filas
  por hoja, semilla 0 y sin parada temprana.
- `explore/short_weight.py:30–33` y `calibrate_live.py:209–260`: `--confirm W` sustituye el global solo en ese
  proceso, entrena con selección y compara contra radio en la reserva. Las dos confirmaciones leen
  `live_choice.json`; no escriben ese archivo ni `live_model.json`.
- `calibrate_live.py:280–284`: un proceso nuevo con `--final` usa el peso comprometido 3 y hojas 63/lambda 10
  del archivo de receta; ajusta con los diez partidos externos de selección y reserva. No hereda el último
  peso 5 de otro proceso ni el peso 1 de una confirmación concurrente. El exportador histórico no exige un
  informe de confirmación: esa guarda apareció con ADR-019.
- **Cachés compartidas:** `bench.py:63–102`, `calibrate_dead.py:39–62`, `explore/idsse_bench.py:83–90` y
  `calibrate_edges.py:72–85` pueden escribir `tracking.npz`, `positions.xml.npz` y `positions.xml.restarts.json`.
  No hay bloqueo ni reemplazo atómico de esos archivos. Las cachés de Metrica verifican firmas de fuentes;
  las de IDSSE no verifican el checksum del XML original. Existe un riesgo condicionado a cachés frías,
  incompletas o antiguas. **Que ocurriera en #77 o explique sus métricas es NO COMPROBADO.** Ambos logs terminan
  correctamente; eso no reconstruye el estado original de las cachés. No se modificó su implementación.

El detalle de configuración y los hashes de los archivos de código están en
[`static-audit.json`](evidence/issue111/static-audit.json). Los controles anteriores de 1/4/12 hilos no demostraron
una causa en el pliegue probado; tampoco permiten descartar toda diferencia de entorno en cualquier ajuste.

### Reproducciones actuales y procedencia

El trabajo está aislado en dos worktrees: histórico `67b8fe6` y diagnóstico `056d1bd`. Se copiaron exclusivamente
Metrica sample-data e IDSSE; los comandos no cargan datos del desafío. Los cambios locales originales se conservan.

- Intérprete actual: Windows, Python 3.12.14; NumPy 2.5.1, pandas 3.0.5, scikit-learn 1.9.1, SciPy 1.18.1,
  `threadpoolctl` 3.7.0. Se fijaron `OMP_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`.
  Es un entorno actual controlado, no una reconstrucción confirmada de `.venv-repro` el 31/10.
- [`current-inputs.json`](evidence/issue111/current-inputs.json): 42 archivos copiados, incluidos 21 XML crudos
  de IDSSE, con tamaños, fechas y SHA-256. Se conservó este manifiesto inicial para mantener su hash en las
  invocaciones. Su nota genérica sobre ausencia de revisiones se corrige con
  [`current-revisions.json`](evidence/issue111/current-revisions.json): el contenido de los nueve archivos Metrica,
  normalizando explícitamente CRLF a LF, coincide con blobs del commit
  `e706dd506b360d69d9d123d5b8026e7294b13996` de `metrica-sports/sample-data`;
  los 21 XML de IDSSE coinciden con ETags de la revisión `a715a38dfbaf5f58e431727c2b78d174101a703c`
  declarada en sus metadatos locales de Hugging Face. Los hashes de las cachés derivadas se registran aparte;
  esa procedencia actual no prueba qué revisión ni qué cachés se usaron el 31/10, que siguen **SIN CONFIRMAR**.
- [`selection-input-verification.json`](evidence/issue111/selection-input-verification.json): 84/84 correspondencias
  de huellas de filas coinciden con la reconstrucción previa; también coinciden esquema, orden, scorer y versiones
  registradas. Los cuerpos de `fit`, `game_rows`, `score`, `per_game`, `bench_means` y `degraded` son iguales al
  código histórico tras hacer explícitos los parámetros globales de peso/corte. No se ajustó ningún modelo en
  este control. Las huellas completas de los insumos de evaluación de aquella corrida no se habían guardado;
  este resultado se limita a las filas de entrenamiento y los campos comprobados.
- Scorer normalizado: `341bad48904b489d6e875397b27687f5d6a4d22a397f3dc8af3a00d48f16874d`.
  Se reutilizan las métricas y el bootstrap anteriores como antecedentes identificados. Para registrar ahora
  los tres pesos con un manifiesto de insumos se ejecuta una sola selección histórica completa, sin barrer
  recetas nuevas. La exportación se comprueba aparte.

La selección histórica completa actual terminó con salida 0, en 490.7 s. El comando invocado fue
`python explore/short_weight.py --weights 1 3 5` dentro del worktree `67b8fe6`. El manifiesto y el entorno
son los anteriores. No cambió `live_choice.json` ni se exportó un modelo durante esta selección.

| Peso | Histórico Metrica | Actual Metrica | Diferencia actual−histórico | Histórico IDSSE | Actual IDSSE | Diferencia actual−histórico |
|---|---|---|---|---|---|---|
| 1 | +0.1224 | +0.1260 | +0.0036 | +0.1646 | +0.1630 | −0.0016 |
| 3 | +0.1250 | +0.1253 | +0.0003 | +0.1803 | +0.1830 | +0.0027 |
| 5 | +0.0970 | +0.1046 | +0.0076 | +0.1800 | +0.1818 | +0.0018 |

Las diferencias de esta tabla son aritmética de los puntos redondeados, no intervalos de mejora. Los conteos
de unidades por encima del control vuelven a ser 10/12 para peso 3 y 9/12 para peso 5; ni esos conteos ni
conservar el ganador por media reproducen los valores exigidos por el control A. El comando histórico y el
diagnóstico coinciden en el entorno/insumos actuales para los pesos 1 y 3; no respalda atribuir exclusivamente
al refactor del #85 la discrepancia histórica. No demuestra una causa alternativa.

Los registros de invocación y resultado están en `selection-current-invocation.json`,
`selection-current-result.json` y `selection-current.txt` dentro del directorio de evidencia.
Las 33 pruebas de `tests.test_diagnose_changes` y `tests.test_bench_variant_b` pasaron con fixtures inventadas;
el resultado con código de salida 0 y hash del log está en `synthetic-checks-result.json`. No se puntuó B real.

**Exportación actual:** `python calibrate_live.py --final` en `67b8fe6`, salida 0 y 141.9 s, produjo 593518 bytes
con SHA-256 **`1e0579ad8232de7579ac3df6a4d49768fa6702e374e20c57ee9cec2bcb2a8ddf`**, idéntico al histórico
esperado y a `final3.txt`. `live_choice.json` no cambió. Evidencia: `final-current-invocation.json`,
`final-current-result.json` y `final-current.txt`. La reproducción solo escribe en el worktree histórico;
no reemplaza modelos de la copia de trabajo original ni se usa como control fuera del entrenamiento.

El archivo inicial del checkout Windows tenía 593519 bytes y SHA-256 `b383df17…` por CRLF. Se comprobó por
separado que el blob Git tiene LF y el SHA histórico, y que convertir sus saltos a CRLF reproduce aquel hash
inicial. El hash **del export nuevo se comparó sin normalizarlo** y coincide exactamente; véase
`model-line-endings.json`. Esta diferencia de serialización inicial no explica las diferencias numéricas de
`spellF1`. Los insumos de Metrica también conservan sus hashes de bytes crudos y la comprobación de su contenido
con LF se identifica expresamente: no se confunde un hash normalizado con el de un archivo original.

**Confirmación actual parcial:** `audit_77_default_confirmation.py` reutilizó las funciones históricas de
`67b8fe6`, con entrenamiento solo en selección y evaluación de Metrica Game 1 e IDSSE 6–7, semillas 50–59/50–54.
Usó peso 1 y peso 3, hojas 63, lambda 10 y 1000 remuestreos. No usó el modelo ajustado con los diez partidos.
Los dos pesos se ejecutaron sucesivamente en un proceso forense; no se recreó la concurrencia histórica.
Terminó en 325.5 s; no modificó código, receta ni modelo histórico. Se verificaron únicamente las tres condiciones
por defecto de cada peso: todas conservan el intervalo por encima de 0, **3/3 por peso**. No se afirma 43/43 actual.

| Peso / banco / anclaje | Histórico, contra radio | Actual, contra radio | Actual−histórico (puntos redondeados) |
|---|---|---|---|
| 1 / Metrica / end | +0.1162 | +0.1129 | −0.0033 |
| 1 / Metrica / start | +0.1176 | +0.1149 | −0.0027 |
| 1 / IDSSE / status | +0.1440 | +0.1447 | +0.0007 |
| 3 / Metrica / end | +0.1346 | +0.1345 | −0.0001 |
| 3 / Metrica / start | +0.1368 | +0.1372 | +0.0004 |
| 3 / IDSSE / status | +0.1538 | +0.1511 | −0.0027 |

Los puntos completos y sus intervalos están en `confirmation-default-current.json`; las diferencias de la tabla
no son intervalos de efecto. La selección y el bloque por defecto no reproducen las cifras históricas; la
exportación sí reproduce el artefacto. Esa identidad del modelo ajustado con diez partidos no demuestra que
todos los modelos de seis o siete partidos, los insumos de evaluación o el entorno histórico fueran idénticos.

[`comparison-summary.json`](evidence/issue111/comparison-summary.json) reúne las tres etapas y sus hashes.
Se verificó que los 42 archivos copiados originales no cambiaron. La exportación creó cinco cachés derivadas de
datos abiertos, registradas con sus hashes; no hubo escrituras concurrentes sobre cachés frías en esta reproducción.
El scorer actual corresponde al repo oficial `f8f2629ff1e0985f81d7e59d8413678514ee1530`, con el SHA normalizado
ya fijado en `67b8fe6:ci_config.json`; el checksum del módulo efectivamente cargado el 31/10 no figura en los logs.

### Criterios completos antes de declarar reproducida A

La revisión del control anterior evalúa **los dos bancos**, sin detener el informe en el primer fallo:

| Banco | Diferencia histórica peso 3−peso 1 | Reconstrucción previa | Error absoluto | Tolerancia | Estado |
|---|---|---|---|---|---|
| Metrica A/start | +0.0026 | −0.000726770188243242 | 0.003326770188243242 | 0.0001 | No cumple |
| IDSSE/status | +0.0157 | +0.01996000210585714 | 0.004260002105857141 | 0.0001 | No cumple |

Se mantienen los objetivos y la tolerancia del ADR-020; no se cambian para aceptar la discrepancia. Para completar
el #85 también se exigen exclusión del partido completo, entrenamiento A/start inalterado, semillas y cobertura
pareadas, métricas del scorer, categorías/recall por duración y sensibilidades previstas. Las pruebas de B con
fixtures inventadas no son una evaluación de B en los partidos abiertos. El informe completo A/B, ambos anclajes
y sensibilidades no queda acreditado por recuperar los logs ni por verificar un hash de exportación.

| Criterio del ADR-020 / PR #107 | Evidencia actual | Estado |
|---|---|---|
| Par histórico fijo, referencias de entrenamiento A/start e IDSSE/status, hojas 63/lambda 10/corte 5 s/pesos 1 y 3 | Comandos recuperados, cabecera del log y código `67b8fe6`; equivalencia de los cuerpos y 84 huellas | Comprobado para los campos revisados; entorno/insumos históricos completos siguen pendientes |
| Exclusión del partido completo, dos mitades IDSSE juntas, sin reserva en selección | Siete pliegues del comando histórico, huellas por grupo y pruebas sintéticas de exclusión/carga | Cumple en la ejecución y el código revisados |
| Escenario por defecto, jugadores limpios y semillas Metrica 0–9 / IDSSE 0–4 | Valores por defecto preservados y manifiestos de invocación | Cumple para la selección actual |
| Reconstrucción de la diferencia en **ambos** bancos dentro del redondeo | Tabla de los dos errores, log histórico y selección actual | **No cumple en ambos bancos** |
| Referencias/semillas/cobertura compatibles; B no cambia entrenamiento ni predicciones | 33 pruebas con fixtures, incluidas cobertura, identidad de predicciones y conservación del fallo A | Cumple en fixtures; comprobación B con partidos reales pendiente y bloqueada |
| Scorer oficial y métricas/recall/categorías/bootstrap del informe completo | SHA del scorer y pruebas; existen agregados del intento anterior | Scorer comprobado; no se presenta la selección actual como informe completo de diagnóstico |
| Dos sensibilidades con ruido, A/B y ambos anclajes, datos abiertos y fila nueva de experimentos | Protocolo conservado; no se ejecuta B real al fallar A | Pendiente del control de reconstrucción y de explicar la discrepancia |
| Exportación final o mismo ganador por media | SHA del export reproducido exactamente; mismo ganador por media | No sustituye el control A ni habilita B |

La causa de la discrepancia de selección sigue sin demostrarse. Entorno, revisión de datos externos y cachés
históricas son hipótesis pendientes de evidencia. **B permanece bloqueado y #85 no se declara completado.**

### Resuelto y pendiente

- **Comprobado:** comandos/protocolo recuperados; ambas confirmaciones históricas fueron contra radio y
  reportaron 43/43; peso de exportación 3 por proceso nuevo; ausencia de escrituras directas de confirmación sobre
  receta/modelo; selección histórica nueva coincide con la reconstrucción previa; exportación actual idéntica al
  SHA histórico; 33 pruebas sintéticas aprobadas; revisiones actuales de los datos externos documentadas.
- **No comprobado:** causa de las diferencias de selección y del bloque por defecto; versiones históricas de
  `.venv-repro`, revisión e identidad de los insumos/cachés por etapa, checksum del scorer efectivamente importado
  y cualquier efecto de la simultaneidad de las confirmaciones sobre cachés o cómputo. Los logs de Lautaro faltan.
- **Estado del #85:** A no reproducida; B real y el informe completo de sensibilidades siguen pendientes.
  No se modifica el algoritmo, la tolerancia ni el criterio de aceptación para dar por buena la discrepancia.

**Conservación y validación final de la ejecución:** se agregaron seis filas a `docs/EXPERIMENTOS.md` del worktree
de diagnóstico, conservando exactamente
el prefijo anterior de 100389 bytes y SHA-256 `12c8341c8efc5b19978dc403919b54ccd7ace9edbc579430bb7a3c3e73d3447d`
(`append-only-check.json`). Pasan `git diff --check`, los enlaces locales y `guard.py repo`; las 33 pruebas
sintéticas tienen salida 0. Los dos archivos modificados originalmente por el usuario conservan sus hashes;
también permanecen intactos el código y la receta históricos. Los controles están en `final-integrity-check.json`.
Todo queda en los worktrees aislados, sin staging, commit ni push; no se tocaron datos protegidos ni modelos
de la copia de trabajo original.

**Revisión posterior:** se revisaron íntegramente los cinco archivos preparados y el anexo real de
`EXPERIMENTOS.md`, comparándolos con la copia principal y los resultados guardados. Se aclaró la ubicación de las
filas y el alcance por peso de las tres condiciones reproducidas; los scripts y resultados de ejecución no se
modificaron. Las comprobaciones de integridad, pruebas y guarda citadas arriba son las ya registradas, no controles
nuevos. Esta revisión no ejecutó PowerShell, Git, Python, pruebas ni evaluaciones. La propuesta de archivos está en
[`PUBLICACION-PROPUESTA.md`](evidence/issue111/PUBLICACION-PROPUESTA.md) y el comentario local, sin publicar, en
[`COMENTARIO-85-BORRADOR.md`](evidence/issue111/COMENTARIO-85-BORRADOR.md).
