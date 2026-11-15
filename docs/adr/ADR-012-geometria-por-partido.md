---
artifact: adr
version: "1.0"
created: 2026-10-29
status: accepted
---

# ADR-012: Dimensiones de cancha explícitas en el banco

## Estado

Accepted (2026-10-30), revisado por Ivan en el PR #58. Issue #52.
Complementa los ADR-006 y ADR-009, sin cambiar sus etiquetas, umbrales ni reglas de selección.

## Contexto

En `32c5d46`, el banco normaliza las posiciones con la geometría de cada fuente, pero
`owner_evidence` convierte a metros con los 105.3 × 68 m de la entrega. Metrica usa
105 × 68 m; IDSSE guarda `PitchX` y `PitchY` por partido. Además, la degradación por
aglomeración usa siempre las dimensiones de Metrica. Ambas conversiones pueden
cambiar una decisión de distancia sin que cambie la disposición física.

## Decisión

Cada loader devuelve también `pitch`, una pareja de largo y ancho en metros,
finitos y positivos. Metrica conserva la geometría declarada por su loader e IDSSE
la que usó para normalizar cada partido. Las cachés de Metrica identifican la
geometría usada para calcular velocidades; una caché anterior sin esa identificación
se vuelve a generar desde los datos abiertos.

Las funciones del banco que calculan distancias o llaman al pipeline requieren
`pitch` como argumento nombrado. También lo requieren la degradación por
aglomeración y los análisis que consumen esos loaders. Las velocidades siguen en
m/s, el radio en metros y las posiciones en coordenadas normalizadas.

`owner_evidence` acepta `pitch` y conserva como valor por defecto los 105.3 × 68 m
de la entrega. El cálculo mantiene las mismas multiplicaciones y sumas de distancia
al cuadrado. `possession.py` conserva su comando, geometría y parámetros actuales.

## Cómo se mide

- Fixtures sintéticos con la misma disposición en metros normalizada en canchas
  de distinto largo y ancho. Deben coincidir las distancias, la evidencia dentro y
  fuera del radio, y la máscara de degradación por aglomeración con semilla fija.
- Regresión contra el cálculo anterior sobre fixtures de la geometría de entrega,
  incluidos empates, pelota faltante e interpolación.
- `explore/pitch_geometry.py` compara la configuración de `32c5d46` con la geometría
  explícita. Mantiene R, N, interpolación, `max_gap`, verdad y semillas. Usa Metrica
  Games 1-3 e IDSSE abiertos, pelota original y degradada, con aglomeración 0 y 2.
  Informa `spellF1` de cada versión y el intervalo 5-95% de su diferencia mediante
  1000 remuestreos pareados de posesiones y semillas, usando `bench.compare`.
- Se registra el efecto aunque sea nulo o negativo. Las filas históricas de
  `docs/EXPERIMENTOS.md` quedan intactas y una fila nueva identifica ambas geometrías,
  fuentes, parámetros y comandos. No se recalibra ningún umbral con esta comparación.

## Consecuencias

Los consumidores del banco deben pasar la geometría explícita; omitirla produce un
error en vez de usar la cancha de otro partido. Las referencias anteriores al
issue conservan su commit y su geometría histórica. Las nuevas corridas pueden
cambiar de resultado aunque mantengan los mismos parámetros del detector.
