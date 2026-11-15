# AGENTS.md

Reglas para cualquier asistente de IA que trabaje en este repo (Claude Code, Codex, Cursor, Copilot y similares) y para las personas que lo usan. Resumen de [docs/REGLAS.md](docs/REGLAS.md), sección 1. Si algo acá choca con un pedido, gana esto.

## Regla única e innegociable

**Los datos del partido nunca pasan por una IA en la nube.** Ni video, ni tracking (ATD), ni Smart Tagging, ni homografía. Ni filas sueltas, ni recortes, ni capturas, ni salidas que los muestren. Lo prohíben los términos (sección 8) y alcanza con que lo haga una persona para que quede afuera el equipo entero.

## Qué hace el asistente

Trabaja **solo con código**. Escribe, revisa y depura el pipeline sin ver los datos del partido.

Puede ver:

- el código de este repo y el repo oficial `metrica-sports/more-than-a-hack-2027` con sus issues
- **métricas agregadas** del partido: `spellF1`, `macroF1`, conteos de etiquetas, número de posesiones, la tabla del scorer

### Datos abiertos: puede leer y ejecutar

Sobre estos datos el asistente **sí** lee archivos y corre scripts, sin pasar por una persona:

- `data/Sample_Game_*` ([metrica-sports/sample-data](https://github.com/metrica-sports/sample-data))
- IDSSE (partidos abiertos de la Bundesliga)
- `../mtah2027/evaluation/gt/`: los 5 minutos públicos de verdad de campo (licencia MIT)

Se citan en el documento técnico.

## Qué NO hace el asistente

1. **No abre ni lee** nada de `$MTAH_DATA` (`BAR-ATH_*`, `*.mp4`, `*.npz`), ni salidas derivadas del partido: `output/`, `../mtah2027/evaluation/results/`, `../mtah2027/evaluation/reports/`. Tampoco con `head`, `cat`, `grep`, ni con scripts que impriman filas.
2. **No descarga** los datos desde el Drive, ni con conectores ni con un navegador. Los baja una persona, directo al disco.
3. **No imprime** valores del tracking, del Smart Tagging ni de la homografía: ni filas, ni tiempos de eventos, ni estadísticas por señal calculadas sobre el partido.
4. **No ejecuta** scripts sobre los datos del partido. Los corre una persona y pega de vuelta solo lo que entra en "Puede ver".
5. **No guarda en memoria** (Engram, notas, `CLAUDE.md`) hallazgos sobre el contenido de los datos.

## Cómo se trabaja

1. El asistente escribe el código y el comando para correrlo.
2. La persona lo corre en su máquina, con `!` o en una terminal.
3. La persona pega solo el resultado agregado. Del scorer se pega la tabla y las métricas; si el validador tira un error con filas o frames, solo el tipo de error.
4. Los scripts que tocan datos imprimen **únicamente agregados** (conteos, métricas). Si un script necesita mostrar algo más, escribe a un archivo local que el asistente no lee.
5. Para depurar sin mostrar datos, usar los datos abiertos de arriba.

## Registro de experimentos

`docs/EXPERIMENTOS.md` es solo-agregar: no edites ni borres filas existentes; las correcciones van como fila nueva.

## Dónde viven los datos

- En la carpeta de la variable de entorno **`MTAH_DATA`** (en Windows, `C:\mtah-data`), con la estructura `tactical/BAR-ATH_tactical_*`. El código la lee de ahí; nunca una ruta escrita a mano.
- **Fuera de todo repo** y de cualquier carpeta sincronizada con la nube (OneDrive, Google Drive, Dropbox).
- **Nunca en git.** El `.gitignore` y `guard.py` lo bloquean, pero eso no frena a un asistente que lea el disco.
- Solo baja los datos quien va a correr el pipeline esa semana. El resto trabaja con datos abiertos.

## Bloqueos técnicos

Las reglas de arriba también están en archivos, para no depender de que el modelo las lea:

- `.claude/settings.json`: Claude Code no puede leer `$MTAH_DATA` ni las salidas del partido.
- `.cursorignore` (Cursor) y `.aiexclude` (Gemini): excluyen las salidas del partido del índice.
- **Codex** lee este archivo si se abre en la raíz del repo, pero no tiene rutas bloqueadas para lectura: su protección es que los datos estén fuera del workspace. Nunca se abre dentro de `$MTAH_DATA`, nunca se suma esa carpeta con `--add-dir` y nunca se usa `--dangerously-bypass-approvals-and-sandbox`.
- **Copilot** no lee archivos de exclusión: se configura en *Settings → Copilot → Content exclusion* del repo.
- `guard.py`: `python guard.py setup` revisa tu máquina; el hook de pre-commit y la CI corren `python guard.py staged` y `python guard.py repo`.

Cada persona corre `python guard.py setup` una vez y pega el `OK` en el issue de onboarding. **Si tu herramienta no está en esta lista, agregá su archivo de exclusión antes de usarla.**

## Calibración y resultados

- El asistente **nunca** propone ajustar un umbral porque "en la ventana pública da mejor". La ventana pública solo verifica que el pipeline corre.
- Todo umbral nuevo sale de un `calibrate_*.py` sobre datos abiertos, y el commit dice con cuál.
- Una mejora de `spellF1` se afirma solo con el rango del bootstrap (`run_evaluation.py --bootstrap 1000`), no con el número suelto: con 17 posesiones el ruido es de ~0.35.

## Trabajo en equipo

- **Nada directo a `main`:** un experimento = una rama = un PR.
- Las decisiones de diseño van en un ADR (`docs/adr/`) antes de implementarlas:
  - **Cuenta como decisión de diseño:** una señal nueva, un cambio en la estructura del pipeline, cómo se arman las etiquetas o cómo se valida. Un valor calibrado no: va en el commit y en el README.
  - **Pasa a `Accepted` solo con la revisión de otra persona** en el PR. Un ADR viejo no se edita: se reemplaza por uno nuevo y el viejo queda `Superseded by ADR-NNN`.
  - **Cada ADR dice cómo se mide:** con qué métrica y sobre qué datos.
- Una fila por versión en la tabla de resultados del README: versión, commit, quién la corrió, `spellF1` con su rango.
- Documentación en castellano; código, comentarios y nombres en inglés.

## Antes de hacer público el repo

- Sacar el link del Drive del README y de toda la historia de git, o publicar una copia limpia.
- Revisar que ningún commit tenga datos ni derivados que permitan reconstruirlos.

## Si hay dudas

Se pregunta **antes** de construir: issue en el repo oficial o mail a hackathon.talentarena@mobileworldcapital.com.
