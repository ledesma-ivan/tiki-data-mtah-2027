---
artifact: adr
version: "1.0"
created: 2026-11-01
status: proposed
---

# ADR-019: Los candidatos del modelo de posesión se comparan contra la receta vigente, y `live_model.json` se exporta solo con una confirmación aprobada

## Status

Proposed (2026-11-01). Revisión pedida a Iván y a MatiasEnrique; pasa a `Accepted` con la revisión de otra persona.
Este ADR se escribe y se sube **antes** de cualquier corrida del protocolo nuevo, como pide el #83.

**Date:** 2026-11-01
**Deciders:** Lautaro Bursese (con Claude)
**Issues:** #83 y #84 (de MatiasEnrique). El #77 es el primer consumidor; después lo usan el #85 y el #86.

## Context

- **`calibrate_live.py --confirm` compara contra `radio`.** Era la referencia correcta para el ADR-014, que reemplazaba
  a `radio`. El #77 la reusó para el peso 3, que reemplaza al peso 1, y que los dos le ganen a `radio` no dice que el
  peso 3 le gane al peso 1. Contra el peso 1, el #77 midió punto a punto y sin intervalo: ganó 40 de 43 condiciones,
  con una media de +0.011 y un peor caso de −0.017 (ruido de posición de 1.0 m, Metrica; fila del 31/10 en
  `docs/EXPERIMENTOS.md`).
- **`explore/short_weight.py` distingue las recetas cambiando la global `SHORT_WEIGHT`.**
- **`--confirm` imprime un resultado negativo sin salir con error**, y la diferencia entre los árboles exportados y
  `decision_function` no entra en el resultado.
- **`--final` reentrena y sobrescribe `live_model.json`** sin mirar si la receta confirmó.

## Decision

### Las recetas

Una receta del modelo de posesión son cuatro valores, explícitos:

| Clave | Qué es | Vigente |
|---|---|---|
| `leaves` | hojas de cada árbol | 63 (`live_choice.json`) |
| `lam` | la penalidad de cambio, en logits | 10 (`live_choice.json`) |
| `short_weight` | cuántas veces cuentan al entrenar los frames de una posesión verdadera corta | 3 (`SHORT_WEIGHT`, #77) |
| `short_s` | el corte de "corta", en segundos | 5 (`SHORT_S`, #77) |

`fit` recibe el peso, y `game_rows` el corte, como argumentos: ninguna comparación cambia una global. Una receta con
otra clave, o con un valor fuera de rango, se rechaza.

**La normalización de pesos queda como en el #77, y es parte de la receta** (lo pide el #83): primero cada partido
suma lo mismo, y después los frames cortos se multiplican por `short_weight`. Así, un partido con más posesiones
cortas pesa más en total. Cambiar ese orden es otro candidato.

### La comparación (#83)

```
python calibrate_live.py --confirm --seed-start N [--candidate clave=valor ...] [--reference clave=valor ...] [--report RUTA]
```

- **Candidata y referencia:** las dos parten de la receta vigente y cambian solo lo que se pasa. La referencia es
  siempre una receta: `radio` no puede ser la referencia de un candidato que reemplaza a la receta vigente. Comparar
  la receta vigente contra sí misma da cero en todo y no confirma.
- **Entrenamiento:** las dos con los 7 partidos de selección y las mismas filas (si tienen el mismo corte; si no, cada
  una con las suyas). Nunca con los pesos finales, que ya vieron la reserva.
- **Evaluación:** sobre la reserva (Metrica Game 1, IDSSE 6-7), con las mismas semillas, pelotas, jugadores y máscaras
  para las dos: `score` puntúa los dos modelos sobre cada pelota degradada. `bench.compare` da la diferencia pareada,
  candidata menos referencia, con 1000 remuestreos de posesiones y semillas.
- **Decide la regla del ADR-011 contra la referencia, con las 43 condiciones del ADR-010 y del ADR-014:**
  1. el escenario por defecto: el intervalo 5-95% entero por encima de 0, en Metrica con las dos verdades y en IDSSE
     (3 condiciones);
  2. los seis escenarios de sensibilidad: la diferencia positiva (18);
  3. la pelota de las paradas dentro de la cancha, en Metrica con las dos verdades: la diferencia positiva (2);
  4. **los 10 escenarios de `NOISE`, en los dos bancos: la diferencia positiva (20).** Es el tratamiento de las
     condiciones de ruido del ADR-014 que pide fijar el #83: siguen decidiendo, como en el ADR-014, ahora contra la
     referencia;
  5. y los árboles exportados de la candidata dan los mismos frames que `decision_function` (Metrica Game 1, primera
     semilla): 0 frames distintos.

  **Confirma solo si se cumplen todas.** No se reemplaza por un conteo de condiciones ganadas, ni se cambia después de
  ver un resultado.
- **Se reporta, sin decidir:** cada modelo contra `radio` en el escenario por defecto (la referencia histórica), la
  diferencia con el `D` verdadero, el acierto por frame con juego vivo y las posesiones predichas sobre las verdaderas.
- **Semillas:** un bloque nuevo por corrida. Ya usados: 0-9 (selección), 20, 30 y 40 (ADR-014), 50 (#77) y 60
  (ADR-017 y ADR-018).
- **El informe:** `live_confirmation.json`, con el estado (`confirmed` o `rejected`), las dos recetas, las 43
  condiciones con su punto, su intervalo y si pasan, los árboles contra `decision_function`, las particiones, las
  semillas y la huella de lo que define los pesos (ver "La exportación"), más el commit, las versiones de las
  librerías y el `sha256` del scorer. Se escribe siempre, confirme o no; si no confirma, `--confirm` sale con error
  (código 1).

### El primer uso: el peso 3 del #77 contra el peso 1

```
python calibrate_live.py --confirm --reference short_weight=1 --seed-start 70
```

El peso 3 (la receta vigente) contra el peso 1, con el mismo corte de 5 s, en la reserva con las semillas 70-79
(Metrica) y 70-74 (IDSSE).

- **Es la octava confirmación sobre la reserva** (ADR-010, tres del ADR-014, el #77, el ADR-017 y el ADR-018), que
  además miró el diagnóstico del #76. No es una validación independiente nueva: semillas nuevas no hacen partidos
  nuevos.
- **No elige nada:** el peso 3 ya se eligió en la selección (#77), y no se reabre la búsqueda.
- **Qué pasa con el resultado, fijado antes de correr:**
  - si confirma, el peso 3 queda con la confirmación que le faltaba, y la entrega sigue siendo `f2460d57…`;
  - si no confirma, la propuesta es volver al peso 1 (`live_model.json` `c0a12df6…`, la entrega `a7cd94d0…`, ya
    reproducida en dos máquinas), porque el ADR-011 deja entrar solo lo que gana en los dos bancos. Lo decide el equipo
    en el PR, antes del congelamiento (14/11), sin volver a correr ni a elegir con este resultado.

### La exportación (#84)

`python calibrate_live.py --final`:

1. lee `live_confirmation.json` y arma las filas de entrenamiento de los 10 partidos;
2. **antes de entrenar, comprueba** que el informe:
   - existe, se lee y tiene todos los campos;
   - está `confirmed`, y sus 43 condiciones y la comprobación de los árboles lo sostienen: la decisión se recalcula
     con los números del informe, no se confía en el estado;
   - es de la receta vigente;
   - tiene la misma huella: el esquema de señales (`LIVE_FEATURES`), el `sha256` de las filas de entrenamiento de cada
     uno de los 10 partidos, el `sha256` del scorer oficial y las versiones de scikit-learn y numpy;
3. si algo falla, dice qué y sale con error (código 2), sin tocar `live_model.json`;
4. si pasa, entrena con los 10 partidos, escribe `live_model.json` de una vez (un archivo temporal que reemplaza al
   anterior) y anota en el informe la procedencia: los 10 partidos y el `sha256` del modelo. **Ese modelo ya vio la
   reserva:** no es una evaluación independiente (ADR-011).

**Qué cubre la huella:** lo que define los pesos exportados. Las filas resumen el código que las arma (señales,
pelotas, ruido, máscaras) y los datos abiertos, así que un cambio que no las mueve, como un comentario o un ajuste de
las paradas, no invalida la confirmación. La equivalencia vale para las entradas declaradas: no prueba que todo el
pipeline sea igual. Un cambio del decodificador o de la inferencia no cambia los pesos y se decide con su propio ADR.

**Cómo se sale de un `--final` rechazado** sin saltear la validación:

- si cambió la receta, el esquema de señales o las filas: volver al código o a la receta de la confirmación, o
  confirmar otra vez con un bloque de semillas nuevo, que es otra mirada a la reserva y se anota;
- si cambió una versión de las librerías: instalar las de `requirements-train.txt`;
- si el informe falta o está roto: recuperarlo de git (`git checkout -- live_confirmation.json`) o confirmar otra vez.

`--rule` no pide informe: escribe el modelo que no aprende nada (ADR-009 tal cual).

### Qué no cambia

- **Los pesos entregados.** `live_model.json` queda igual byte a byte, y la entrega sigue siendo `f2460d57…`.
- La selección (`--select`), sus recetas y `live_choice.json`.
- El banco, el scorer y la regla del ADR-011.

## Cómo se mide

- **El protocolo**, con tests sintéticos en `tests/test_calibrate_live.py`:
  - un modelo comparado contra sí mismo da diferencia exacta 0 en las 43 condiciones, con intervalo [0, 0], y no
    confirma (si las dos recetas no se puntuaran sobre las mismas pelotas, la diferencia no sería exacta);
  - una candidata peor que la referencia no confirma;
  - la decisión: todo en orden confirma; un intervalo que toca 0, una condición que falta o un frame distinto entre los
    árboles y `decision_function` no confirman;
  - una receta con una clave o un valor inválidos se rechaza.
- **La exportación**, con tests sintéticos de `--final`: sin informe, con el informe roto, rechazado, de otra receta,
  con otras filas o con una condición que no lo sostiene, sale con error y deja los bytes del modelo como estaban; con
  un informe válido, escribe el modelo y anota la procedencia.
- **El #77:** la tabla de diferencias e intervalos contra el peso 1, por banco, verdad y escenario, en
  `live_confirmation.json` y en una fila nueva de `docs/EXPERIMENTOS.md`, confirme o no.

## Resultados (1/11): el peso 3 no confirma contra el peso 1

`python calibrate_live.py --confirm --reference short_weight=1 --seed-start 70`, en `cea3d63`, en 1498 s. Diferencia
pareada, peso 3 menos peso 1:

| Condición | Metrica | IDSSE |
|---|---|---|
| Por defecto (intervalo 5-95%) | +0.0198 [+0.0058, +0.0352] desde el inicio; +0.0192 [+0.0049, +0.0335] desde el fin | +0.0114 [+0.0025, +0.0213] (4/4 mitades) |
| Los seis escenarios | de +0.0155 a +0.0222 | de +0.0010 a +0.0118 |
| La pelota de las paradas dentro de la cancha | +0.0195 / +0.0197 | |
| `NOISE`, los 9 escenarios sin el de 1.0 m | positivos | positivos |
| **Ruido de posición de 1.0 m** | **−0.0020 [−0.0146, +0.0101]** | **−0.0073 [−0.0169, +0.0021]** (0/4 mitades) |

- **No confirma: 41 de 43.** Los árboles exportados dan los mismos frames que `decision_function` (0 distintos).
- **Dónde gana y dónde pierde:** el peso 3 gana con intervalo en el escenario por defecto de los dos bancos y en todos
  los escenarios de la pelota, y pierde con el ruido de posición más fuerte, en los dos bancos. Es lo que el #77 había
  visto punto a punto (−0.017 con 1.0 m, en Metrica), ahora en pares y con semillas nuevas.
- **Contra `radio`, sin decidir:** el peso 1 suma +0.1290 en Metrica y +0.1519 en IDSSE, y el peso 3, +0.1487 y +0.1633.
  Los dos le ganan a `radio`, y eso no alcanza (ver "Context").
- **El informe** es `live_confirmation.json` (`rejected`). Marca `"modified": true` porque el README tenía ediciones sin
  commitear durante la corrida: el código que corrió es el de `cea3d63`.
- **Lo que sigue, como se fijó antes de correr:** la propuesta es volver al peso 1, y lo decide el equipo en el PR, antes
  del 14/11, sin volver a correr ni a elegir con este resultado. Si vuelve, no pasa por `--final` (no hay informe de este
  protocolo para el peso 1): se restauran `SHORT_WEIGHT = 1` y el `live_model.json` del peso 1 (`c0a12df6…`), el test del
  modelo entregado vuelve a fijarlo, y una persona corre BAR-ATH para comprobar que la entrega vuelve a ser `a7cd94d0…`,
  la que ya dio igual en dos máquinas (#70 y #72).

### Cambios después de la revisión del código (1/11, después de esta corrida y antes de cualquier otra)

No cambian la regla de decisión ni las 43 condiciones:

- **La huella suma el modelo de la candidata entrenado con la selección** (su `sha256`), que `--final` vuelve a entrenar
  con el código de hoy antes de entrenar con los 10 partidos, y **el orden de las filas**. Así, un cambio en el
  entrenamiento o en la exportación (hiperparámetros, la normalización de pesos, los árboles exportados, la penalidad) o
  en el orden invalida la confirmación, y un comentario no.
- Un número que llega como booleano en el informe lo invalida, y cada condición anota si se cumple (`holds`).
- `--candidate` y `--reference` acumulan los cambios aunque se repita la opción. Una candidata igual a la referencia, o
  esas opciones sin `--confirm`, son un error de uso (código 2), antes de cargar datos.
- La huella y el commit, con la lista de archivos modificados, se toman antes de puntuar la reserva, y el informe se
  escribe de una vez, como el modelo.
- `bench.compare` exige el mismo número de semillas en los dos lados (`zip(..., strict=True)`).
- Un test corre `confirm()` de punta a punta sobre partidos sintéticos con los nombres de la partición: ningún partido
  de la reserva entra al entrenamiento, el estado sale de los números y la huella es la que calcula `--final`.

El informe de esta corrida es de antes de estos cambios: además de estar `rejected`, `--final` lo rechazaría por la
huella.

## Consequences

### Positive

- Un candidato del modelo de posesión entra solo si le gana a la receta que reemplaza, con intervalo. El #85 y el #86
  lo usan tal cual.
- `--final` ya no puede exportar una receta sin confirmación, ni con filas distintas de las confirmadas.
- El informe deja lo necesario para repetir la confirmación en otra máquina y comparar.

### Negative

- La comparación entrena dos modelos y puntúa los dos: tarda más que la de antes.
- Cualquier cambio en las filas de entrenamiento obliga a confirmar otra vez, y cada confirmación es otra mirada a la
  reserva.
- La huella no cubre el decodificador: un cambio ahí se controla con su ADR y con el `sha256` de la entrega.

### Neutral

- `radio` queda en el informe como referencia histórica, sin decidir.
- `explore/short_weight.py` pasa el peso como argumento.

## Alternatives Considered

### Seguir comparando contra `radio`

Es lo que hizo el #77. Dos modelos que le ganan a `radio` pueden perder entre ellos.

### Decidir por cantidad de condiciones ganadas

El #77 ganó 40 de 43 punto a punto. Un conteo esconde dónde pierde y no tiene intervalo; el ADR-011 pide todas.

### Una huella con el `sha256` de los archivos de código

Es más simple, pero cualquier cambio, aunque sea un comentario, obligaría a confirmar otra vez y a mirar la reserva de
nuevo.

### Comparar en la selección (LOMO) en lugar de la reserva

La selección es donde se elige y se diagnostica (#85). La confirmación sigue siendo una sola corrida en la reserva,
como en el ADR-011.

## References

- ADR-006, ADR-010, ADR-011 y ADR-014; el PR #77 y su fila del 31/10 en `docs/EXPERIMENTOS.md`
- Issues #83 y #84 (MatiasEnrique), #85 y #86
- `calibrate_live.py`, `bench.compare`, `explore/short_weight.py`, `tests/test_calibrate_live.py`
