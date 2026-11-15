# Continuidad de las velocidades del banco

Issue #53, [ADR-015](adr/ADR-015-velocidad-con-continuidad.md), Proposed.
Código medido: `31e72fa`. Corrida por Matias con Codex el 30/10/2026.

## Regla del loader

Una velocidad derivada necesita dos posiciones finitas, frames consecutivos, la
misma identidad conocida y el mismo período conocido. Si falta una condición,
queda NaN. No se completa con cero ni se recorta con un límite de velocidad.

Game 3 resuelve cada PlayerChannelRef del XML a su playerId en los intervalos
inclusivos del formato. Los períodos salen de los parámetros del XML. Sin XML,
las posiciones siguen disponibles pero todas las velocidades quedan desconocidas.
El loader advierte si no queda ninguna velocidad finita, tanto en primera carga
como al reutilizar una caché.
Una referencia sin identidad deja desconocido ese slot; un período sin límites
completos deja desconocidas las velocidades de ese período. Un XML inválido o
con intervalos contradictorios produce un error.

Games 1–2 usan las columnas Player del CSV como identidades de su plantel, junto
con Period y Frame. Una columna sin identidad Player seguida de un número tiene
velocidad desconocida. Los relojes de ambos equipos deben coincidir. Los loaders
conservan el índice frame - 1 y dejan NaN donde falta una fila.

IDSSE ya separa PersonId y GameSection. Sus velocidades derivadas usan la misma
regla; las suministradas conservan S / 3.6, incluido el primer frame de cada tramo.
Las cachés de Metrica se regeneran si falta la versión del cálculo, cambia la
geometría o cambia la firma de tamaño/fecha de sus fuentes. La firma incluye el
XML opcional, por lo que agregarlo o quitarlo invalida la caché. IDSSE guarda
posiciones y velocidades del proveedor; recalcula la derivada en cada carga y
puede reutilizar su caché anterior.

## Diseño de la comparación

Antes: la diferencia por slot de `9e2a4b6`, sin cortes por identidad ni período.
Después: el loader corregido. Se comparten posiciones, geometría del #52,
etiquetas, pelota, semillas, detector y parámetros. En Metrica se comprueba que los
frames originales sean contiguos antes de reconstruir la resta histórica; en
IDSSE se usa la posición original en metros, sin normalizarla y desnormalizarla.
No se recalibran umbrales ni se reentrena el modelo de bordes.

Fuentes abiertas:

- [Metrica sample-data](https://github.com/metrica-sports/sample-data/tree/e706dd506b360d69d9d123d5b8026e7294b13996),
  Games 1–3. La fuente pide atribución y uso responsable; no declara licencia formal.
- [IDSSE](https://huggingface.co/datasets/pysport/idsse-data/tree/a715a38dfbaf5f58e431727c2b78d174101a703c),
  Bassek et al., Scientific Data 12, 195, 2025, CC BY 4.0. Los mismos siete partidos
  abiertos del #52, divididos en 14 mitades.
- Scorer oficial `f8f2629ff1e0985f81d7e59d8413678514ee1530`.
  SHA-256 de possession_metrics.py:
  `341bad48904b489d6e875397b27687f5d6a4d22a397f3dc8af3a00d48f16874d`.
- Python 3.13.15, numpy 2.5.1 y pandas 3.0.5, según requirements.txt.

Pelota original y degradada, 45% ausente en juego, huecos medios de 1.5 s,
crowd 0, dead_missing 0. Metrica usa semillas 20–29; IDSSE 0–4. v1, v2 y radio
conservan sus parámetros. La verdad de posesión es start en Metrica y BallStatus /
BallPossession en IDSSE. Se promedian primero semillas y luego partidos o mitades,
con igual peso por partido o mitad.

Los intervalos son percentiles 5–95 de 1000 remuestreos pareados de posesiones y
semillas, con la semilla del scorer. No se remuestrean partidos. Se informa tanto
el intervalo absoluto de spellF1 como el de su diferencia, después menos antes.

```bash
# MTAH_OFFICIAL apunta al repo oficial con evaluation/possession_metrics.py.
python explore/tracking_continuity.py --dataset metrica --seeds 10 --seed-start 20 --bootstrap 1000
python explore/tracking_continuity.py --dataset idsse --idsse-dir data/idsse-open --speed positions --seeds 5 --bootstrap 1000
python explore/tracking_continuity.py --dataset idsse --idsse-dir data/idsse-open --speed provider --seeds 5 --bootstrap 1000
```

## Resultados

En Metrica, 76 velocidades antes finitas pasan a desconocidas. Las velocidades
que siguen siendo válidas no cambian de valor. En IDSSE no cambia ninguna celda.
Coinciden los arrays completos de predicción antes/después: 99 en Metrica y 252
por cada modalidad de IDSSE. Son 3 pipelines por 3 partidos o 14 mitades, con una
pelota original y 10 o 5 semillas degradadas.

En las 18 comparaciones, la diferencia de F1 de D es cero y la de spellF1 es
0.000000 [0.000000, 0.000000]. La corrección elimina diferencias entre personas y
períodos; esta corrida no demuestra una mejora de las métricas del detector.

| Fuente | Pipeline | Pelota | F1 D antes → después | spellF1 antes → después | spellF1 después [5–95%] |
|---|---|---|---|---|---|
| Metrica | v1 | original | 0.937008 → 0.937008 | 0.586619 → 0.586619 | [0.559532, 0.614389] |
| Metrica | v1 | degradada | 0.575683 → 0.575683 | 0.250224 → 0.250224 | [0.237587, 0.263810] |
| Metrica | v2 | original | 0.831131 → 0.831131 | 0.490690 → 0.490690 | [0.465030, 0.516423] |
| Metrica | v2 | degradada | 0.888292 → 0.888292 | 0.404894 → 0.404894 | [0.386454, 0.424313] |
| Metrica | radio | original | 0.831131 → 0.831131 | 0.599118 → 0.599118 | [0.575510, 0.624785] |
| Metrica | radio | degradada | 0.888292 → 0.888292 | 0.541001 → 0.541001 | [0.518214, 0.566732] |
| IDSSE, posiciones | v1 | original | 0.883681 → 0.883681 | 0.407043 → 0.407043 | [0.390215, 0.422791] |
| IDSSE, posiciones | v1 | degradada | 0.705921 → 0.705921 | 0.219717 → 0.219717 | [0.210902, 0.228747] |
| IDSSE, posiciones | v2 | original | 0.929120 → 0.929120 | 0.415841 → 0.415841 | [0.398360, 0.431832] |
| IDSSE, posiciones | v2 | degradada | 0.930035 → 0.930035 | 0.340359 → 0.340359 | [0.326496, 0.353258] |
| IDSSE, posiciones | radio | original | 0.929120 → 0.929120 | 0.518798 → 0.518798 | [0.503562, 0.534383] |
| IDSSE, posiciones | radio | degradada | 0.930035 → 0.930035 | 0.415352 → 0.415352 | [0.399969, 0.431006] |
| IDSSE, proveedor | v1 | original | 0.885662 → 0.885662 | 0.407108 → 0.407108 | [0.390641, 0.422747] |
| IDSSE, proveedor | v1 | degradada | 0.707989 → 0.707989 | 0.220072 → 0.220072 | [0.211197, 0.228943] |
| IDSSE, proveedor | v2 | original | 0.931204 → 0.931204 | 0.415829 → 0.415829 | [0.398562, 0.431275] |
| IDSSE, proveedor | v2 | degradada | 0.932006 → 0.932006 | 0.339114 → 0.339114 | [0.325554, 0.352019] |
| IDSSE, proveedor | radio | original | 0.931204 → 0.931204 | 0.515120 → 0.515120 | [0.499153, 0.531049] |
| IDSSE, proveedor | radio | degradada | 0.932006 → 0.932006 | 0.412281 → 0.412281 | [0.396884, 0.426757] |

## Validación y referencias anteriores

88 tests de unittest y los scripts test_possession.py, test_stops.py y
test_player_noise.py pasan con fixtures sintéticos. Cubren sustitución sin afectar
a otro jugador, cambio de período, huecos, posiciones no finitas, falta de
metadatos, continuidad, equivalencia de caché fría/caliente y regeneración de una
caché del #52 con geometría válida. Las guardas del repo pasan.

Los resultados de ADR-007 y los análisis de #32, #49 y #54 anteriores a `31e72fa`
conservan su configuración histórica. La próxima calibración debe usar esta
versión del loader y regenerar las referencias que necesite. Este experimento
no acepta ADR-015, no elige un candidato de ADR-010 y no ejecuta datos del concurso.

La revisión adversarial de Opus 5.5 high sobre `756857a` no encontró bloqueantes.
Sus observaciones menores llevaron a agregar la advertencia de velocidades
desconocidas, validar las cabeceras Period/Frame y uniformar el error de límites
ausentes en el XML. Se ampliaron los fixtures para cubrir intercambio de slots e
invalidación por cambios del tracking. Los intervalos inclusivos que comparten un
frame se rechazan como contradictorios, y ese caso también está probado.
La firma de caché usa tamaño y mtime_ns; una edición que preserve ambos puede
requerir borrar la caché manualmente. El ADR sigue Proposed para revisión humana.
