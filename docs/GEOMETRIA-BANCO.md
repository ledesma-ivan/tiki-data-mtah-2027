# Geometría del banco, issue #52

Corrida de Matias con Codex, 29/10/2026, implementación `16c2ed5` sobre la base
`32c5d46`. Python 3.13.15, numpy 2.5.1 y pandas 3.0.5. Decisión en
[ADR-012](adr/ADR-012-geometria-por-partido.md), todavía Proposed.

La comparación cambia únicamente las dimensiones pasadas a la evidencia y a la
degradación por aglomeración. La configuración anterior usa 105.3 × 68 m para la
evidencia y 105 × 68 m para la degradación. La nueva usa las dimensiones del loader
en ambos casos. Los tres Metrica y los siete IDSSE de esta corrida declaran
105 × 68 m. Por eso la corrección de la degradación no cambia sus máscaras aquí;
su efecto con otras dimensiones se verifica en los fixtures sintéticos.

Los parámetros permanecen fijos. `radio` usa R = 1 m, N = 12 frames, interpolación
de hasta 50 frames y `max_gap` = 100 frames. `v1` y `v2` usan evidencia sin límite
de radio, última posición conocida, N = 50 y `max_gap` = 12 frames. No se elige ni
recalibra ningún valor con estas corridas.

## Datos y reproducción

- [Metrica sample-data](https://github.com/metrica-sports/sample-data/tree/e706dd506b360d69d9d123d5b8026e7294b13996),
  Games 1–3, revisión `e706dd5`. Verdad desde el inicio del evento, ADR-003 y ADR-005.
  Semillas 20–29 por partido, semilla efectiva `1000 * game + índice`.
- [IDSSE](https://huggingface.co/datasets/pysport/idsse-data/tree/a715a38dfbaf5f58e431727c2b78d174101a703c),
  siete partidos de Bundesliga, revisión `a715a38`, CC BY 4.0. Verdad de
  `BallStatus` y `BallPossession`; cada una de las 14 mitades cuenta como un caso.
  Semillas 0–4, misma fórmula. Se comprueban velocidades del proveedor y desde posiciones.
- [Scorer oficial](https://github.com/metrica-sports/more-than-a-hack-2027/blob/f8f2629ff1e0985f81d7e59d8413678514ee1530/evaluation/possession_metrics.py),
  revisión `f8f2629`. `spellF1` usa sus funciones y `bench.compare` calcula la
  diferencia con 1000 remuestreos pareados de posesiones y semillas. Intervalo
  percentil 5–95%, misma semilla de bootstrap que el scorer. Los casos tienen igual peso.

Pelota tal cual y degradada con 45% faltante en juego vivo, huecos medios de 1.5 s
y 0% faltante en paradas después de restaurarla. Se repite con `crowd=0` y `crowd=2`.

```bash
python -m unittest discover
python test_possession.py
python guard.py repo

# MTAH_OFFICIAL apunta al repo oficial con evaluation/possession_metrics.py.
# Metrica se guarda en data/Sample_Game_{1,2,3}.
python explore/pitch_geometry.py --dataset metrica --seeds 10 --seed-start 20 --bootstrap 1000
python explore/pitch_geometry.py --dataset idsse --idsse-dir ../idsse-data --seeds 5 --bootstrap 1000
python explore/pitch_geometry.py --dataset idsse --idsse-dir ../idsse-data --speed positions --seeds 5 --bootstrap 1000
```

El script imprime solo agregados. Su salida incluye geometrías, parámetros y
semillas. Para conservar el control histórico del experimento, usar el commit
`16c2ed5`; futuras modificaciones del detector pueden cambiar ambas columnas.

## Verificación

Pasaron los 67 tests de `unittest`, incluidos diez nuevos de geometría, más los
chequeos de `test_possession.py` y `guard.py repo`. Se probaron ambos ejes, distancias
dentro y fuera del radio, selección del equipo más cercano, interpolación,
degradación con aglomeración, propagación por todos los pipelines y cachés frías,
válidas y anteriores al cambio. La misma disposición en metros se mantiene en
canchas de largo y ancho distintos.

El pipeline de entrega produce las mismas etiquetas que la implementación
anterior sobre fixtures sintéticos, incluidos empates y pelota faltante. No se
ejecutó sobre datos del concurso. La variante histórica del experimento también
se contrastó con el código extraído de `32c5d46`, sin cambiar sus cuentas.
Coincidieron exactamente 54 arrays de predicción en Metrica y 168 en IDSSE,
con los tres pipelines y ambos valores de `crowd`.

Ese chequeo de paridad usó menos semillas que la medición de `spellF1`. Los 54
arrays de Metrica son 3 partidos × 3 pipelines × 2 valores de crowd × 3 pelotas,
una original y dos degradadas con semillas 20 y 21. Los 168 de IDSSE son 14
mitades × 3 pipelines × 2 valores de crowd × 2 pelotas, una original y una
degradada con semilla 0. Son arrays completos, no claves del diccionario ni
remuestreos de bootstrap.

El chequeo quedó versionado después de la revisión adversarial. Requiere el
commit `32c5d46` disponible en la historia local y ejecuta únicamente su código
sobre los datos abiertos cargados por el banco:

```bash
python explore/verify_pitch_geometry.py --dataset metrica --seeds 2 --seed-start 20
python explore/verify_pitch_geometry.py --dataset idsse --idsse-dir ../idsse-data --seeds 1
```

Las correcciones posteriores a la revisión agregan `bench.owner_evidence`, que
exige `pitch`, y migran allí las llamadas del banco y sus análisis. La función de
entrega mantiene su compatibilidad. También se conserva la aritmética de entradas
`float32` y `float64` usando escalares de Python para las dimensiones. Pasaron los
69 tests, incluidos los dos nuevos de estas regresiones, y se repitió la paridad
de 54 y 168 arrays con el script versionado. El ADR-012 sigue Proposed.

### Integración con main, 30/10/2026

La rama se rebasó sobre `85c60c0`. El ADR de geometría pasa a ser el ADR-012:
main ya contiene el ADR-010 de bordes y el ADR-011 de IDSSE. Las referencias en
filas anteriores de `EXPERIMENTOS.md` se aclaran con una fila nueva, sin editarlas.

Los consumidores incorporados por main también reciben la geometría del loader:
`stops`, los ejemplos y candidatos de `calibrate_edges.py`, los oráculos, el ruido
de posición y los intercambios de identidad, y el reloj de la pelota. No se
reentrenó el modelo ni se modificaron sus parámetros.

Pasaron 76 tests de `unittest`, incluidos 16 de geometría, y los scripts de prueba
`test_possession.py`, `test_stops.py`, `test_player_noise.py` y
`test_calibrate_edges.py`. Se repitió la paridad histórica: 54 arrays idénticos en
Metrica y 168 en IDSSE. La CLI de IDSSE conserva los controles agregados por main:
la corrida siguiente terminó correctamente y `stops` dio las mismas métricas
que `radio` con el modelo identidad.

```bash
python explore/idsse_bench.py --dir data/idsse-open --matches 1 --compare radio stops \
  --seeds 1 --seed-start 20 --missing .2 --dead-missing .34 --gap 3 --crowd 2 --bootstrap 1000
```

Iván informó una corrida humana de BAR-ATH sobre la rama anterior al rebase:
H 55470, A 35316, D 68071, X 40462 y prefijo SHA-256 `9e8a0b36…`, igual a main.
Esa verificación no cubre la rama rebasada: debe repetirse sobre su commit final
antes de mergear. El asistente no ejecutó esa corrida ni accedió a esos datos.

## Resultados

Cada celda muestra la media de `spellF1` por caso y semilla. La diferencia es
geometría por partido menos geometría histórica. La pelota original se muestra
una vez porque `crowd` solo afecta a la degradada.

### Metrica, velocidades desde posiciones

| Pelota | crowd | Pipeline | Anterior | Por partido | Diferencia [5–95%] |
|---|---:|---|---:|---:|---:|
| original | — | v1 | 0.586619 | 0.586619 | +0.000000 [+0.000000, +0.000000] |
| degradada | 0 | v1 | 0.250263 | 0.250224 | -0.000039 [-0.000287, +0.000150] |
| original | — | v2 | 0.490690 | 0.490690 | +0.000000 [+0.000000, +0.000000] |
| degradada | 0 | v2 | 0.405098 | 0.404894 | -0.000204 [-0.000530, +0.000057] |
| original | — | radio | 0.599118 | 0.599118 | +0.000000 [+0.000000, +0.000000] |
| degradada | 0 | radio | 0.540915 | 0.541001 | +0.000087 [-0.000059, +0.000422] |
| degradada | 2 | v1 | 0.249246 | 0.249263 | +0.000017 [-0.000138, +0.000179] |
| degradada | 2 | v2 | 0.406111 | 0.405833 | -0.000278 [-0.000638, -0.000001] |
| degradada | 2 | radio | 0.529784 | 0.529784 | +0.000000 [+0.000000, +0.000000] |

### IDSSE, velocidades del proveedor

| Pelota | crowd | Pipeline | Anterior | Por partido | Diferencia [5–95%] |
|---|---:|---|---:|---:|---:|
| original | — | v1 | 0.406357 | 0.407108 | +0.000751 [+0.000078, +0.001556] |
| degradada | 0 | v1 | 0.219961 | 0.220072 | +0.000111 [-0.000082, +0.000363] |
| original | — | v2 | 0.415156 | 0.415829 | +0.000672 [+0.000011, +0.001497] |
| degradada | 0 | v2 | 0.339040 | 0.339114 | +0.000074 [-0.000246, +0.000414] |
| original | — | radio | 0.515120 | 0.515120 | +0.000000 [+0.000000, +0.000000] |
| degradada | 0 | radio | 0.412327 | 0.412281 | -0.000046 [-0.000307, +0.000133] |
| degradada | 2 | v1 | 0.225153 | 0.225281 | +0.000128 [-0.000070, +0.000390] |
| degradada | 2 | v2 | 0.343842 | 0.343696 | -0.000147 [-0.000625, +0.000251] |
| degradada | 2 | radio | 0.404898 | 0.404913 | +0.000014 [-0.000029, +0.000089] |

### IDSSE, velocidades desde posiciones

| Pelota | crowd | Pipeline | Anterior | Por partido | Diferencia [5–95%] |
|---|---:|---|---:|---:|---:|
| original | — | v1 | 0.406296 | 0.407043 | +0.000747 [+0.000072, +0.001549] |
| degradada | 0 | v1 | 0.219607 | 0.219717 | +0.000111 [-0.000082, +0.000362] |
| original | — | v2 | 0.415172 | 0.415841 | +0.000669 [+0.000013, +0.001485] |
| degradada | 0 | v2 | 0.340222 | 0.340359 | +0.000137 [-0.000192, +0.000499] |
| original | — | radio | 0.518798 | 0.518798 | +0.000000 [+0.000000, +0.000000] |
| degradada | 0 | radio | 0.415397 | 0.415352 | -0.000045 [-0.000305, +0.000133] |
| degradada | 2 | v1 | 0.224667 | 0.224795 | +0.000128 [-0.000070, +0.000389] |
| degradada | 2 | v2 | 0.345067 | 0.344920 | -0.000147 [-0.000623, +0.000251] |
| degradada | 2 | radio | 0.408157 | 0.408241 | +0.000084 [-0.000030, +0.000303] |

En `radio`, todos los intervalos de la diferencia contienen cero. El cambio corrige
las unidades; estas corridas no sostienen una mejora de `spellF1` de la versión de
entrega. `v1` y `v2` suben levemente en IDSSE con pelota original. En Metrica, `v2`
con `crowd=2` baja 0.000278, con el extremo superior del intervalo apenas por debajo
de cero. Se registra ese efecto sin usarlo para ajustar parámetros.
