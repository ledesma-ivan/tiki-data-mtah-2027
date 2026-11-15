---
artifact: adr
version: "1.0"
created: 2026-10-30
status: accepted
---

# ADR-015: Velocidad derivada con continuidad de jugador y período

## Estado

Accepted (2026-10-30), revisado por Ivan en el PR #67. Issue #53. Era el ADR-013; se renumera al 015 porque el 013 es el de la CI (#60) y el 014 el del modelo de posesión (#65).
Complementa los ADR-006, ADR-007, ADR-011 y ADR-012.

## Contexto

Game 3 reutiliza slots al sustituir jugadores. Restar posiciones consecutivas del
slot genera desplazamientos entre personas distintas. Los períodos también pueden
ser contiguos en el archivo, aunque entre ellos no haya movimiento observable.
Games 1 y 2 usan columnas por jugador; IDSSE separa cada PersonId y GameSection.

## Decisión

Los loaders abiertos comparten una diferencia hacia atrás. La velocidad en el frame
actual es la distancia en metros por 25 Hz solo si ambas posiciones son finitas,
los números de frame son consecutivos y las dos observaciones tienen la misma
identidad conocida dentro del mismo período conocido. El primer frame, un cambio
de identidad o período, un hueco y una identidad o período desconocidos dan NaN.
La observación posterior a una posición ausente también da NaN. No se interpolan
jugadores ni se recortan velocidades con un umbral.

Game 3 resuelve PlayerChannelRef a PlayerChannel.playerId para cada pareja x/y,
en cada intervalo inclusivo startFrame/endFrame de DataFormatSpecification. Los
períodos salen de los parámetros first_half y second_half del XML, incluidos los
períodos extra si están presentes. Las filas se alinean por frameCount, dejando NaN
en frames omitidos. Sin metadatos no se supone que un slot conserve jugador ni que
pertenezca a un período: sus velocidades quedan desconocidas.

Games 1 y 2 toman la identidad de las cabeceras Player de sus columnas y el período
y número de frame del CSV. Una columna sin identidad conocida produce velocidad
desconocida. Se exige que los relojes de ambos equipos coincidan.

IDSSE conserva una columna por PersonId y una matriz por GameSection. Los huecos
se representan con posiciones NaN. Usa la misma diferencia en modo positions;
el modo provider conserva S / 3.6, también en el primer frame.

Las cachés de Metrica llevan versión del cálculo y firma de sus fuentes. Una caché
anterior o una fuente modificada obliga a regenerar. IDSSE guarda posiciones y
velocidad del proveedor, no la derivada, y recalcula esta última al cargar; esa
caché no contiene el defecto de Metrica y puede conservarse.

## Cómo se mide

- Fixtures sintéticos de sustitución, cambio de período, posiciones no finitas,
  frames omitidos, metadatos ausentes y movimiento continuo. El cambio en un slot
  no debe alterar la velocidad válida de otro jugador.
- Primera carga, recarga y caché anterior con geometría válida deben dar los
  mismos arrays, incluidos los NaN. Un cambio de metadatos invalida la caché.
- Comparación antes/después en Metrica Games 1–3 e IDSSE con detector, geometría,
  etiquetas, parámetros y semillas fijos. F1 de D, spellF1 y diferencia pareada de
  spellF1 con 1000 remuestreos de posesiones y semillas, según ADR-006/011.
  El antes reproduce la resta por slot sin cortes de la versión 9e2a4b6.
- Registrar fuente, commit, configuración y resultados en docs/EXPERIMENTOS.md.
  Se acepta la corrección aunque la diferencia de métricas sea nula o negativa.

No se recalibran umbrales ni se reentrena el modelo de bordes. Las referencias de
evaluación anteriores conservan sus commits; nuevas calibraciones de #32, #49 y
#54 deben identificar esta versión del loader. No se ejecuta sobre BAR-ATH.
