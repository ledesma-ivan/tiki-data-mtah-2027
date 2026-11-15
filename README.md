# more-than-a-hack-2027

> [!CAUTION]
> **NUNCA LE PASES LOS DATOS DEL PARTIDO A UNA IA EN LA NUBE.** Ni video, ni tracking, ni Smart Tagging, ni homografía, ni recortes, capturas o salidas que los muestren: ni a Claude, ni a ChatGPT, ni a Gemini, ni a Copilot, ni a ninguna. Lo prohíben los términos (sección 8) y alcanza con que lo haga uno para que quede afuera el equipo entero.
>
> **Antes de tocar los datos, leé [docs/REGLAS.md](docs/REGLAS.md)**: términos y condiciones, privacidad, reglas del reto y aclaraciones de los organizadores.

More Than a Hack (TalentArena 2027): hackathon de analítica de fútbol organizada por Mobile World Capital Barcelona, Barça Innovation Hub y Metrica Sports, con datos reales de partidos del FC Barcelona.

- **Competencia:** https://landing.mobileworldcapital.com/more-than-a-hack-2027
- **Repo oficial del reto:** https://github.com/metrica-sports/more-than-a-hack-2027
- **Data del partido:** la comparten los organizadores solo con los participantes inscriptos; no se publica ni se enlaza acá.

> [!NOTE]
> **Copia pública del equipo Tiki Data.** Es el árbol de `main` congelado el 14/11/2026 (commit `9a8c51a` del repo privado), en un solo commit y sin la historia. Los commits, issues y PR que citan los ADR, `docs/EXPERIMENTOS.md` y este README pertenecen al repo privado y no están acá. En `docs/adr/ADR-002-detector-pelota-muerta.md` se omitieron las estadísticas por señal calculadas sobre el partido.

## El reto (Fase 1: posesión de la pelota)

Para cada frame del FC Barcelona vs Athletic Club (LaLiga 2024-25, fecha 2), decir quién tiene la pelota: `H` local, `A` visitante, `D` pelota muerta o `X` sin respuesta. Se entrega un CSV de 199,319 filas indexado al video tactical.

- **Ranking por `spellF1`:** cada posesión se empareja como un objeto entero por IoU temporal (0.3 a 0.7). `macroF1` es el desempate.
- **Baseline a superar:** `spellF1` 0.2433 en el partido completo.
- **Entrega:** 17 de noviembre de 2026.

### Fases (landing y `docs/REGLAS.md`)

| Fase | Fechas | Quién |
|---|---|---|
| Fase 1, posesión por frame (este repo) | hasta el 17/11/2026; resultados antes del 26/11 | todos los inscriptos, ranking automático por `spellF1` |
| Fase 2, reto de innovación | 26/11/2026 al 14/01/2027 | los 20 mejores, con 10 partidos profesionales y mentoría; preguntas analíticas o tácticas libres |
| Presentación final | 22/02/2027 | los 5 mejores de la fase 2 |
| Final presencial | 02/03/2027, Talent Arena (Barcelona) | jurado profesional |

## Enfoque

Tratamos la posesión como un problema de segmentación, no de clasificación frame por frame. Las palancas, en el orden de impacto que esperamos:

1. **Detectar la pelota muerta.** Cuando reanuda el mismo equipo (`H D H`), el `D` es lo único que separa las dos posesiones, y el baseline detecta muy pocos. [ADR-002](docs/adr/ADR-002-detector-pelota-muerta.md) (prioridad) y [ADR-007](docs/adr/ADR-007-detector-pelota-muerta-v2.md) (detector v2: jugadores lentos o pelota vista fuera de la cancha)
2. **El Smart Tagging como señal de equipo.** Las fases tácticas dicen qué equipo tiene la pelota.
3. **Bordes precisos.** Llegar 1 s tarde baja el `spellF1` de 1.0 a 0.65.
4. **Regla de cambio de posesión.** Una racha del rival se confirma cuando pasaron N frames desde su primer frame, y el cambio se fecha en ese primer frame. Los silencios de hasta `MAX_GAP` frames no la cortan; la corta el dueño actual o un silencio más largo (#31, ADR-009). [ADR-001](docs/adr/ADR-001-regla-cambio-posesion.md) La evidencia es el jugador a menos de `CONTROL_RADIUS` = 1 m de la pelota, que se interpola hasta `MAX_INTERP` = 2 s; N = 0.5 s y `MAX_GAP` = 4 s (elegidos juntos en el banco, [ADR-009](docs/adr/ADR-009-evidencia-por-radio-de-control.md)).

Todos los umbrales se calibran en otros partidos ([metrica-sports/sample-data](https://github.com/metrica-sports/sample-data)), nunca en el ground truth público de 5 minutos, como piden las reglas del reto.

## Estado

- [x] El scorer oficial corre en local y los baselines se reproducen
- [x] Carga de datos con mapeo de slot a equipo (`explore/dead_ball.py`)
- [x] Análisis descriptivo de las señales de pelota muerta
- [x] Esqueleto del pipeline: evidencia, cortes por pelota muerta, CSV (`possession.py`)
- [x] Detector de pelota muerta v2 (ADR-007): en el banco, +0.166 de `spellF1` sobre el v1 y un F1 de `D` de 0.9 con la pelota degradada
- [x] Confirmación del v2 con IDSSE, otro proveedor (`explore/idsse_bench.py`): +0.119 de `spellF1` con la pelota degradada en 14 de 14 mitades
- [x] Radio de control, interpolación acotada y N calibrados juntos en el banco (ADR-009, PR #45): +0.136 de `spellF1` sobre el v2 con la pelota degradada; en la ventana pública 0.5714, dentro del ruido
- [x] Bordes de las paradas y equipo que reanuda (ADR-010, #57): mejora IDSSE pero no confirma en Metrica, así que la entrega usa el modelo identidad
- [x] Fin de las paradas en la patada (ADR-017, #32, `Rejected`): mueve el fin de cada parada a la patada de una pelota quieta. Confirmó en los bancos abiertos (43 de 43, +0.009 en Metrica y en IDSSE), pero en BAR-ATH no mueve ninguna parada (el mismo `sha256`), así que no entra a la entrega
- [x] Bordes de las paradas y equipo que reanuda con la convención de Metrica, sobre el modelo de posesión (ADR-018, #32 y #34, `Rejected`): el elegido gana en IDSSE (+0.033 [+0.024, +0.043]) y pierde en Metrica (−0.018 [−0.032, −0.005]). No confirma (21 de 43), así que no entra a la entrega. Lo que separa a los bancos no es la velocidad ni la convención; la pelota que el banco de Metrica inventa en las paradas queda como hipótesis, sin aislar. El código queda sin mergear en la rama `feat/bordes-convencion-metrica-32-34-codigo`
- [x] Posesión con juego vivo (ADR-014, #49 y #35): un modelo por frame con un decodificador de Viterbi, entrenado en datos abiertos. Confirmó en la reserva con 43 de 43 condiciones: +0.113 de `spellF1` en Metrica y +0.152 en IDSSE contra el pipeline anterior. Después del #52 y del #53 volvió a confirmar, cada vez con semillas nuevas: +0.129 y +0.147, y +0.132 y +0.146. En la ventana pública, 0.5946 y, con el modelo reentrenado después del #53, 0.5622: los dos dentro del ruido
- [x] Protocolo del modelo de posesión (ADR-019, #83 y #84): la candidata contra la receta vigente, en pares y con las 43 condiciones, y `calibrate_live.py --final` solo con una confirmación aprobada. Primer uso: el peso 3 del #77 **no confirma contra el peso 1** (41 de 43: gana por defecto en los dos bancos y pierde con 1.0 m de ruido de posición en los dos). La propuesta, fijada antes de correr, era volver al peso 1, y el equipo la eligió en el #91 (opción A, por unanimidad): la entrega vuelve al peso 1
- [x] Pelotas del entrenamiento sin niveles de la verdad pública (ADR-033, #111, `Accepted` en el #115): el 6,5 % y el 34 % del ADR-002 salían de la GT de la ventana, y la aclaración oficial del 03/11 pide entrenar y ajustar solo con datos externos. Con niveles fijados antes de correr (viva 0, 20 y 45 %; paradas 0 y 50 %), la selección elige la misma receta, cuesta −0.0014 de media contra las pelotas viejas y confirma 43 de 43 contra el radio. Los organizadores no autorizaron los niveles del ADR-002 ("todo aquello que no esté explícitamente permitido no está permitido"), así que entra a la entrega
- [x] Reproducción byte a byte (#6): versiones fijadas y cuentas exactas; el modelo de posesión dio el mismo `sha256` en dos máquinas antes del reentrenamiento del #53 (`3a2e8ac5…`) y después (`a7cd94d0…`), con las posesiones cortas al triple (`f2460d57…`) con la pelota muerta antes del saque del segundo tiempo (`4c55c728…`) y con las pelotas del entrenamiento sin niveles de la verdad pública (`dab54052…`, la entrega), como antes el radio de control (`9e8a0b36…`)
- [x] Banco de prueba en datos abiertos con ruido de ATD simulado (`bench.py`, ADR-006)
- [ ] CI sintética en tres sistemas (ADR-016, #54): el workflow está en `main` y corrió el 01/11 y el 02/11; desde el 02/11 está frenado por la facturación (los minutos de noviembre se agotaron) y no se paga (decisión de Lautaro, 09/11): vuelve gratis cuando el repo sea público, y hasta entonces valen los tests y `guard.py` locales
- [x] Documento técnico (`docs/TECHNICAL.md`): revisado por dos personas (#88 y #116), congelado el 14/11 y exportado a `docs/Tiki_Data.pdf` (#11)
- [ ] Entrega final (`docs/ENTREGA.md`, #13) y repo público (#12)

### Resultados (ventana pública de 5 min: verifica el pipeline, no es un ranking)

| Versión | spellF1 | macroF1 | Nota |
|---|---|---|---|
| baseline_smooth125 | 0.4242 | 0.5812 | mejor baseline público |
| v0 | 0.4727 | 0.5365 | regla ADR-001 sin calibrar; recall de `D` = 0 |
| v1 | 0.5294 | 0.7543 | score de pelota muerta con OR de señales; recall de `D` = 0.59 |
| v2 | 0.4941 [0.32, 0.67] | 0.8726 [0.73, 0.91] | jugadores lentos o pelota vista fuera de la cancha (ADR-007); recall de `D` = 0.83; `12e5873`, la corrió Lautaro |
| radio | 0.5714 [0.41, 0.72] | 0.8617 [0.73, 0.90] | radio de control, interpolación acotada, N = 0.5 s y `max_gap` = 4 s sobre el v2 (ADR-009); recall de `D` = 0.83; `b6c6912`, la corrió Ivan; `sha256` `9e8a0b36…` |
| modelo de posesión | 0.5946 [0.43, 0.75] | 0.8889 [0.76, 0.93] | modelo por frame y decodificador de Viterbi sobre el radio (ADR-014); recall de `D` = 0.83; `9a4e457`, la corrió Ivan; `sha256` `3a2e8ac5…`; dentro del ruido de la ventana (17 posesiones) |
| modelo de posesión reentrenado tras el #53 | 0.5622 [0.40, 0.70] | 0.8894 [0.75, 0.93] | la misma receta con las velocidades corregidas (ADR-015); `b00e062`, la corrieron Ivan y Lautaro; `sha256` `a7cd94d0…`, igual en las dos máquinas; dentro del ruido de la ventana (17 posesiones) |
| pelotas del entrenamiento sin niveles de la verdad pública (entrega) | 0.5939 [0.41, 0.78] | 0.8970 [0.76, 0.94] | la misma receta, reentrenada con pelotas de niveles fijados sin la GT: viva 0, 20 y 45 % y paradas 0 y 50 % (ADR-033, #111); confirmó 43 de 43 contra el radio en la reserva con semillas nuevas, y en la selección cuesta −0.0014 de media contra las pelotas viejas; `ba8af70` y `db8ba40`, la corrieron Lautaro e Ivan; `sha256` `dab54052…`, igual en las dos máquinas, con 372 posesiones; la ventana no decide nada (17 posesiones) |
| pelota muerta antes del saque del segundo tiempo | 0.5622 [0.40, 0.70] | 0.8894 [0.75, 0.93] | el peso 1 con los 2.934 frames puntuados antes del saque del segundo tiempo en D, como dice el `FAQ.md` oficial (ADR-032, #108): cambian solo esos 1.143 frames, y hay 372 posesiones contra 381; `bfe57de`, la corrieron Lautaro e Ivan; `sha256` `4c55c728…`, igual en las dos máquinas; la ventana es del primer tiempo y no cambia |
| posesiones cortas al triple al entrenar | 0.6526 [0.49, 0.78] | 0.8882 [0.76, 0.93] | la misma receta, con los frames de posesiones reales de menos de 5 s contando 3 veces (#77); confirmó 43 de 43 en la reserva con semillas nuevas y gana al control en 40, con +0.011 de media; contra el peso 1, en pares (ADR-019), no confirma: 41 de 43, así que no queda en la entrega (#91); `67b8fe6`, la corrieron Ivan y Lautaro; `sha256` `f2460d57…`, igual en las dos máquinas; la subida de 0.09 en la ventana está dentro del ruido (17 posesiones) y no decide nada |

La versión con el modelo de posesión (ADR-014) dio `3a2e8ac577d6c0f8ee43bf9defb6139cf27370143516e9151c987043a38d4385` (H 53974, A 36812, D 68071, X 40462; pasa `validate_submission.py`), igual en dos máquinas: la de Ivan, en `9a4e457`, y la de Lautaro, en `8a14e52`, con el mismo código. Después del #53, el ADR-014 reentrena el modelo con las velocidades corregidas (`live_model.json` `c0a12df6…`), y la entrega pasa a ser `a7cd94d0a6ad74f7b82cb905bda152265a5b6652de3bfec9ea694e25af810c56` (H 54147, A 36639, D 68071, X 40462; pasa `validate_submission.py`), igual en dos máquinas: la de Ivan y la de Lautaro, las dos en `b00e062`. Con las posesiones de menos de 5 s contando 3 veces al entrenar (#77), `live_model.json` pasó a `1e0579ad…` y la entrega, a `f2460d577cb96df59c02bbb6b91bb44bcc91ebd05f139355962a7764969fa528` (H 53405, A 37381, D 68071, X 40462; pasa `validate_submission.py`), igual en dos máquinas: la de Ivan en `67b8fe6` y la de Lautaro en `8a91843`, con el mismo código. Como ese peso 3 no confirma contra el peso 1 (ADR-019), el equipo eligió volver al peso 1 en el #91 (opción A). `SHORT_WEIGHT` vuelve a 1 y `live_model.json` vuelve a ser el `c0a12df6…` de `b00e062`, recuperado de git byte a byte y sin pasar por `--final`, porque no hay informe del ADR-019 para el peso 1. La entrega volvió a ser `a7cd94d0…`, igual en dos máquinas sobre ese código: la de Lautaro y la de Ivan, las dos en `45f99fe` (#104). Con la pelota muerta antes del saque del segundo tiempo (ADR-032, #108), la entrega pasa a `4c55c72812aad022de7e1b2c7d3980d72cf2d97cea929afca6bc6d6507aeca6a` (H 53175, A 36468, D 69214, X 40462; pasa `validate_submission.py`), igual en dos máquinas: la de Lautaro y la de Ivan, las dos en `bfe57de`. Cambian solo los 1.143 frames puntuados antes del saque del segundo tiempo, que pasan a D. Con las pelotas del entrenamiento sin niveles medidos con la verdad pública (ADR-033, #111), la selección eligió la misma receta, `live_model.json` pasa a `1f8b706e…` y la entrega, a `dab54052d5cfedf5a57fa60a7a4fb4d3c8884213e3888aa6a3ec78b58c400078` (H 52609, A 37034, D 69214, X 40462; pasa `validate_submission.py`), igual en dos máquinas: la de Lautaro en `ba8af70` y la de Ivan en `db8ba40` (entre los dos commits cambió solo documentación). Los `sha256` `3a2e8ac5…`, `a7cd94d0…`, `f2460d57…`, `4c55c728…` y `9e8a0b36…` ya no son el de la entrega.

## Instalación

```bash
# 1. Repo oficial del reto al lado de este (scorer + ground truth público)
git clone https://github.com/metrica-sports/more-than-a-hack-2027 ../mtah2027
pip install -r requirements.txt          # Python 3.12 o 3.13; versiones fijadas (#6)

# 2. Data del partido (requiere inscripción, ver el link del Drive arriba), FUERA de todo repo:
#    C:\mtah-data\tactical\BAR-ATH_tactical_{atd.txt,atd.xml,homography.csv,smart_tagging.xml}
setx MTAH_DATA C:\mtah-data              # Windows; reabrir la terminal

# 3. Guardas (AGENTS.md): hook de pre-commit y chequeo de la máquina
git config core.hooksPath .githooks
python guard.py setup                    # tiene que decir OK

# 4. Generar la entrega y puntuarla
python -m tests.test_possession          # chequeos de la regla de cambio y del detector v2
python -m tests.test_bench               # chequeos del banco, con datos sintéticos
python -m tests.test_geometry            # geometría por partido, cachés y compatibilidad de entrega
python -m tests.test_tracking_speed      # continuidad de jugador/período y cachés de los loaders abiertos
python bench.py                          # comparar versiones en datos abiertos (ADR-006; data/Sample_Game_*)
python possession.py                     # -> output/possession.csv, e imprime su sha256
cp output/possession.csv ../mtah2027/evaluation/results/possession_v0.csv
cd ../mtah2027 && python evaluation/validate_submission.py evaluation/results/possession_v0.csv
python evaluation/run_evaluation.py
```

La primera corrida parsea el tracking (~20 s) y lo guarda como `.npz` junto a la data. Si esa carpeta no se puede escribir, sigue sin caché.

### Reproducir la entrega

`python possession.py` está hecho para regenerar el mismo archivo, byte a byte, con las versiones de `requirements.txt`, como pide `SUBMISSION.md` del repo oficial (#6). Lo comprobado es la entrega vigente (`dab54052…`) en cuatro máquinas: Lautaro (Windows, `ba8af70`), Ivan (`db8ba40`), Emanuel (Windows, Python 3.12.14, `b86cdd1`) y Matias (macOS, CPython 3.13.15, `e274882`). No equivale a la matriz completa de la CI, que vuelve con el repo público:

- No hay pasos aleatorios. Los pesos entrenados están en el repo, con umbrales y hojas enteros, y la entrega solo los lee:
  - `live_model.json` (ADR-014): el modelo de posesión con juego vivo, que se entrena en datos abiertos con `calibrate_live.py`. Su decodificador también cuenta en enteros;
  - `stops_model.json` (ADR-010), que se entrena con `calibrate_edges.py`. Mientras el ADR-010 no confirme un candidato, es el modelo identidad, que no cambia nada.
- El CSV sale con `\n` en todos los sistemas operativos. pandas escribe `\r\n` en Windows.
- Las cuentas que deciden una etiqueta son exactas. El jugador más cercano se busca con la distancia al cuadrado, porque `np.hypot` depende de la librería matemática de cada plataforma. La ventana de pelota muerta cuenta frames con enteros, porque un promedio en flotante pasa por BLAS y su redondeo en el umbral cambia según la CPU.

Para comparar dos corridas alcanza con el `sha256` que imprime al final. La entrega es ese archivo renombrado a `Tiki_Data.csv`, y renombrarlo no cambia el hash.

### CI sintética multiplataforma

El workflow `tests` corre todos los `test_*.py` como scripts en Ubuntu, macOS y
Windows, con Python 3.12.10 y 3.13.15. Calcula las etiquetas de un fixture
sintético con el pipeline completo, escribe su CSV y exige el mismo SHA-256 en
las seis combinaciones. Publica solo hashes y metadatos. `guard.py repo` debe
pasar antes de la matriz; el check `no-match-data` también se conserva.

Los entornos y el scorer oficial están fijados en `ci_config.json` y
`requirements-ci.txt`. [CI.md](docs/CI.md) explica cómo correr los tests y comparar
los resultados localmente. Un fixture sintético no demuestra determinismo para
todas las entradas ni reemplaza la reproducción manual de la entrega.

### Geometría del banco

Desde el #52, los loaders devuelven `pitch`, el largo y ancho de su cancha en metros.
`bench.load_game` devuelve cinco valores y `explore.idsse_bench.load` agrega `pitch`
al final de cada mitad. Los pipelines, `bench.owner_evidence`, `radio_evidence` y
`degrade` requieren `pitch=...`. Los análisis llaman a `bench.owner_evidence`;
`possession.owner_evidence` conserva su valor por defecto para las llamadas de entrega.
Metrica usa 105 × 68 m; IDSSE conserva `PitchX` y `PitchY` del partido.
Las cachés de Metrica sin geometría se regeneran desde los archivos originales.

`possession.py` mantiene los 105.3 × 68 m de la entrega y los mismos parámetros.
El cambio de geometría del banco no recalibra R, N, interpolación ni `max_gap`.
Los resultados anteriores al #52 usaban 105.3 × 68 m para la evidencia y
105 × 68 m para la degradación por aglomeración. Sus commits y registros conservan
esa configuración histórica; [el experimento del #52](docs/GEOMETRIA-BANCO.md)
registra el efecto de corregirla y cómo reproducirlo.

Resultados del banco con pelota degradada y `crowd=0`. Los intervalos son de la
diferencia pareada contra `32c5d46`, con 1000 remuestreos; no corresponden a la ventana pública.

| Versión | Commit | Quién corrió | Metrica, spellF1 y diferencia [5–95%] | IDSSE, spellF1 y diferencia [5–95%] |
|---|---|---|---|---|
| radio, geometría por partido | `16c2ed5` | Matias con Codex | 0.541001; +0.000087 [−0.000059, +0.000422] | 0.412281; −0.000046 [−0.000307, +0.000133] |

Desde el #53, una velocidad derivada requiere dos posiciones válidas del mismo
jugador, en frames consecutivos del mismo período. En otro caso queda `NaN`.
Game 3 obtiene identidades y períodos de su XML; sin esos metadatos conserva las
posiciones y deja las velocidades desconocidas. Games 1–2 usan las cabeceras
Player y las columnas Period/Frame. El loader advierte si Game 3 queda sin
velocidades finitas, incluso al leer una caché. IDSSE conserva sus velocidades
del proveedor.
Las cachés de Metrica anteriores al cálculo versionado se regeneran.
La regla, la comparación completa y los comandos están en
[VELOCIDADES-BANCO.md](docs/VELOCIDADES-BANCO.md) y el [ADR-015](docs/adr/ADR-015-velocidad-con-continuidad.md).

Con radio fijo, pelota degradada y crowd 0, la corrección de velocidades conserva
las predicciones. Esta tabla usa intervalos absolutos de spellF1; la diferencia
pareada contra `9e2a4b6` es 0 [0, 0] en las tres modalidades, con 1000 remuestreos.

| Versión | Commit | Quién corrió | Metrica, spellF1 [5–95%] | IDSSE proveedor, spellF1 [5–95%] | IDSSE posiciones, spellF1 [5–95%] |
|---|---|---|---|---|---|
| radio, continuidad de velocidad | `31e72fa` | Matias con Codex | 0.541001 [0.518214, 0.566732] | 0.412281 [0.396884, 0.426757] | 0.415352 [0.399969, 0.431006] |

## Estructura

```
possession.py        pipeline: tracking -> evidencia -> cortes por pelota muerta -> bordes de las paradas y equipo que reanuda (ADR-010) -> posesión con juego vivo (ADR-014) -> CSV
tests/test_possession.py casos de la regla de cambio (ADR-001), del detector de pelota muerta v2 (ADR-007) y de la reproducción byte a byte (#6)
tests/test_stops.py casos de los bordes de las paradas, el tipo de reanudación y el equipo que reanuda (ADR-010), y de la patada (ADR-017)
tests/test_live.py casos de las señales enteras, el decodificador y live_model.json (ADR-014)
stops_model.json     modelo de las paradas que lee possession.py (ADR-010); sin él no corre
live_model.json      modelo de posesión con juego vivo que lee possession.py (ADR-014), o "rule" (la regla de cambio); sin él no corre
calibrate_edges.py   entrena, elige y confirma el modelo de las paradas en datos abiertos (ADR-010), y su tests/test_calibrate_edges.py
calibrate_live.py    entrena, elige y confirma el modelo de posesión en datos abiertos (ADR-014): la candidata contra la receta vigente, y --final solo con una confirmación aprobada (ADR-019), y su tests/test_calibrate_live.py
live_confirmation.json  informe de la última confirmación del modelo de posesión (ADR-019): recetas, las 43 condiciones y la huella de las filas de entrenamiento
explore/diagnose_changes.py  diagnóstico LOMO A/B en selección (ADR-020, #85), con las recetas históricas de peso 1/3; instrucciones en docs/DIAGNOSTICO-POSESION.md
calibrate_kick.py    elige y confirma la regla de la patada en datos abiertos (ADR-017, Rejected: no entra a la entrega), y su tests/test_calibrate_kick.py
requirements.txt     versiones fijadas para reproducir el CSV byte a byte (#6)
requirements-train.txt  scikit-learn y sus dependencias, solo para calibrate_edges.py, calibrate_live.py y calibrate_kick.py
bench.py             banco de datos abiertos: pipeline completo en sample-data con ruido de ATD (ADR-006)
tests/test_bench.py casos del banco con datos sintéticos
ci_checks.py         validaciones de la CI: entorno fijado, scorer oficial y comparación de hashes (ADR-016), y su tests/test_ci_checks.py
ci_config.json      matriz de sistemas y versiones de la CI, y el scorer oficial fijado
repro_check.py       CSV sintético de la CI: mismo `sha256` en cada sistema (#54), y su tests/test_repro_check.py
requirements-ci.txt  versiones fijadas de los tests y el entrenamiento en la CI
.github/workflows/  guard.yml (regla de datos) y tests.yml (tests y reproducción)
calibrate_dead.py    calibración de la pelota muerta con etiquetas de eventos (ADR-003), y sus test_calibrate_*.py
idsse_dead_labels.py etiquetas de pelota muerta desde IDSSE (BallStatus), y su tests/test_idsse_dead_labels.py
guard.py             guardas de la regla de datos: máquina, pre-commit y CI (AGENTS.md)
.githooks/           hook de pre-commit que corre guard.py
AGENTS.md            reglas para asistentes de IA y para el equipo: leer primero
docs/REGLAS.md       términos, privacidad y reglas del reto: leer antes de tocar los datos
docs/ONBOARDING.md   cómo arrancar en el equipo (30 min)
docs/EXPERIMENTOS.md registro solo-agregar de cada corrida: datos, resultado y commit
docs/TECHNICAL.md    documento técnico de la entrega, en inglés; se exporta a Tiki_Data.pdf
docs/ENTREGA.md      checklist de la entrega final: CSV, documento, repo público y formulario
docs/CI.md           cómo correr los tests sintéticos y comparar los hashes entre sistemas
docs/GEOMETRIA-BANCO.md y docs/VELOCIDADES-BANCO.md  experimentos del banco: cancha de cada partido (ADR-012) y velocidades con continuidad (ADR-015)
docs/adr/            registros de decisiones de arquitectura
explore/             análisis descriptivo y barridos sobre datos abiertos, no es parte del pipeline de entrega
```

## Decisiones (`docs/adr/`)

| ADR | Tema | Estado |
|---|---|---|
| 001 | regla de cambio de posesión | Superseded by ADR-009 (evidencia y regla de racha) |
| 002 | detector de pelota muerta (la prioridad; su diseño lo reemplaza el 007) | Superseded by ADR-007 |
| 003 | etiquetas de pelota muerta | Accepted |
| 005 | verdad de posesión de los partidos abiertos | Accepted |
| 006 | banco de datos abiertos (el 011 lo reemplaza en la parte de IDSSE) | Accepted |
| 007 | detector de pelota muerta v2 | Accepted |
| 008 | sin `X` dentro de los tiempos jugados | Accepted |
| 009 | evidencia por radio de control e interpolación acotada | Accepted |
| 010 | bordes de las paradas y equipo que reanuda (la entrega usa el modelo identidad) | Proposed |
| 011 | el banco decide también con IDSSE (reemplaza al 006 en esa parte) | Accepted |
| 012 | dimensiones de cancha explícitas en el banco | Accepted |
| 013 | CI sintética multiplataforma | Superseded by ADR-016 |
| 014 | posesión con juego vivo: modelo por frame y decodificador de Viterbi (#49, #35) | Accepted |
| 015 | velocidades derivadas con continuidad de jugador y período (#53) | Accepted |
| 016 | matriz completa, entorno fijado y comparación de hashes sintéticos (#54) | Proposed |
| 017 | fin de cada parada en la patada que reanuda (#32): confirma en datos abiertos y en BAR-ATH no actúa | Rejected |
| 018 | bordes de las paradas y equipo que reanuda con la convención de Metrica, sobre el modelo de posesión (#32, #34): no confirma | Rejected |
| 019 | los candidatos del modelo de posesión contra la receta vigente, y `live_model.json` solo con una confirmación aprobada (#83, #84) | Proposed |
| 020 | evaluación del modelo de posesión con las verdades A y B, y diagnóstico fuera de muestra en la selección (#85) | Accepted |
| 021 | ronda de cuatro alternativas: se eligen en la selección y solo la ganadora va a la reserva, una vez; ninguna confirmó | Proposed |
| 023 | señales de toque para el modelo de posesión (#86): pasa la selección y no confirma (41 de 43) | Rejected |
| 024 | costo de cambio según el contexto en el decodificador: no pasa la selección | Rejected |
| 025 | detector de paradas entrenado por frame: empeora en la selección | Rejected |
| 026 | pelota estimada en los huecos: no pasa la selección | Rejected |
| 032 | la pelota muerta antes del saque de cada tiempo, con el saque oficial (`FAQ.md`): los 2.934 frames antes del saque del segundo tiempo pasan a D | Accepted |
| 033 | las pelotas del entrenamiento y los escenarios del banco sin niveles medidos con la verdad pública (#111): viva 0, 20 y 45 % y paradas 0 y 50 %; la misma receta, confirmada 43 de 43 contra el radio (`--confirm --reference radio`) | Accepted |

Un ADR pasa a `Accepted` solo con la revisión de otra persona.

## Data

La data del partido no se puede redistribuir y no está en este repo. El `.gitignore` bloquea `data/`, `BAR-ATH_*` y `*.mp4`.
