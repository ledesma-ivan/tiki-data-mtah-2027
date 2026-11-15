---
artifact: adr
version: "1.0"
created: 2026-11-03
status: accepted
---

# ADR-032: La pelota muerta antes del saque de cada tiempo, con el saque oficial

## Status

Accepted (2026-11-09), con la revisión de Iván en el PR que cambia este estado. Fue Proposed el 2026-11-03. Cambia el CSV, y se cumplió lo pedido: BAR-ATH en dos máquinas (Iván y Lautaro, en `bfe57de`) dio el mismo `sha256` `4c55c728…`, que el #112 (ADR-033) cambió a `dab54052…`.

**Date:** 2026-11-03
**Deciders:** Lautaro Bursese (con Claude)
**Issues:** #105 (el chequeo que lo encontró) y #13 (la entrega). Va encima del #104.

## Context

- **La trampa que avisa el `FAQ.md` oficial:** "the second half is graded from frame 110,808 but does not kick off
  until **113,742**. Those 2,934 frames are graded and all of them are `D`". El primer tiempo se califica desde su
  saque.
- **Nuestra entrega los etiqueta mal.** Con `a7cd94d0…` (el peso 1 del #104), el conteo de nuestra salida en esos frames
  dio D 1.791, H 972 y A 171. Lo corrió Lautaro el 03/11, y son solo conteos de nuestras etiquetas, como permite
  `AGENTS.md`. El detector de paradas (ADR-007) no marca D donde no hay jugadores seguidos, y antes del saque la
  cámara del táctico recién vuelve del entretiempo.
- **Lo que cuesta en el scorer:**
  - las rachas de H y A de ese tramo son posesiones inventadas;
  - si la última se pega al saque, estira la primera posesión real del tiempo hasta dejarla sin emparejar;
  - en `macroF1`, son 1.143 frames de D que no se aciertan.
- **Ningún banco lo puede medir:** en los partidos abiertos, los tramos puntuados empiezan en el primer evento con
  pelota.

## Decision

- `possession.py` suma `KICKOFFS = (11185, 113742)`, el saque de cada tiempo según el `FAQ.md` oficial.
- `before_kickoff(dead)` marca como pelota muerta cada frame puntuado anterior al saque de su tiempo.
- `label()` lo aplica después de `refine()` y antes de decodificar, así que el primer tramo vivo del segundo tiempo
  empieza en el saque.
- **Es un metadato oficial, como `HALVES`** (los tramos puntuados de `DATA.md`), no algo visto en el video. Los
  organizadores lo publican para que nadie caiga en la trampa. Lo que las reglas prohíben es convertir lo que uno ve en
  el video en etiquetas o constantes, y esto lo dicen ellos.

## Consequences

### Positive

- Los 2.934 frames quedan como dice la verdad: las 1.143 etiquetas H y A de ese tramo pasan a D, y el primer tramo
  vivo del segundo tiempo se decodifica desde el saque.
- En `spellF1` se van las posesiones inventadas de ese tramo, y la primera posesión real del tiempo puede emparejarse.
  En `macroF1` hay 1.143 frames de D más. Se estima en unas milésimas de `spellF1` y hasta +0.008 de `macroF1`; no se
  puede medir sin la verdad del partido.

### Negative

- Cambia el CSV: hace falta BAR-ATH en dos máquinas, y el `sha256` nuevo en el README, `TECHNICAL.md` y `ENTREGA.md`.

### Neutral

- La ventana pública es del primer tiempo, así que sus números no cambian.
- No toca el modelo, los umbrales ni el banco.

## Alternatives Considered

### Detectar el saque con la etiqueta "Kick Off (Start)" del Smart Tagging

Es algorítmico, pero suma al pipeline una dependencia nueva y sus propios errores, para dos frames que publican los
organizadores.

### Detectar el saque con el tracking (la pelota en el punto central y cada equipo en su mitad)

Más código y más riesgo, para el mismo resultado.

### Dejarlo como está

Pierde seguro: el `FAQ.md` dice que los 2.934 frames son D.

## References

- `FAQ.md` y `DATA.md` del repo oficial: los tramos puntuados y el saque del segundo tiempo.
- #105, y la fila del 03/11 en `docs/EXPERIMENTOS.md` (el conteo).
- ADR-007 (el detector de paradas) y ADR-008 (sin X dentro de los tiempos).
