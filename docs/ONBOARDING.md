# Onboarding

Para arrancar en el equipo. Toma ~30 min. Al terminar, pegá el `OK` de `guard.py setup` en el issue de onboarding.

## 1. Leer primero (10 min)

1. [docs/REGLAS.md](REGLAS.md): términos, privacidad y reglas del reto.
2. [AGENTS.md](../AGENTS.md): qué puede y qué no puede hacer un asistente de IA con los datos. **Una sola persona que pase datos del partido a una IA en la nube deja afuera al equipo entero.**
3. [README.md](../README.md): el reto, el enfoque y el estado.

## 2. Repos, uno al lado del otro (5 min)

```bash
git clone https://github.com/nodalsports/more-than-a-hack-2027 more-than-a-hack-2027
git clone https://github.com/metrica-sports/more-than-a-hack-2027 mtah2027     # scorer + GT público
git clone https://github.com/metrica-sports/sample-data sample-data            # datos abiertos: copiar sample-data/data/* a more-than-a-hack-2027/data/
pip install -r more-than-a-hack-2027/requirements.txt                          # versiones fijadas (#6)
```

## 3. Datos del partido: solo si vas a correr el pipeline (5 min)

Si esta semana no corrés el pipeline, **no los bajes**: trabajá con `sample-data` y la ventana pública.

1. Bajalos del Drive a mano (nunca con un asistente ni un conector) a una carpeta **fuera de todo repo y de OneDrive, Google Drive o Dropbox**, por ejemplo `C:\mtah-data\tactical\BAR-ATH_tactical_*`.
2. `setx MTAH_DATA C:\mtah-data` y reabrí la terminal.

## 4. Guardas (2 min)

```bash
cd more-than-a-hack-2027
git config core.hooksPath .githooks
python guard.py setup          # tiene que decir OK
python -m tests.test_possession # tiene que decir ok
```

En macOS, `python3` en lugar de `python` (el hook prueba los dos).

Según la herramienta de IA que uses:

- **Claude Code:** lee `AGENTS.md` y respeta los bloqueos de `.claude/settings.json`. No hace falta nada más.
- **Codex:** lee `AGENTS.md` automáticamente si lo abrís en la raíz del repo, pero no tiene rutas bloqueadas para lectura. Su protección es que los datos estén fuera del workspace: **nunca lo abras dentro de `$MTAH_DATA` ni sumes esa carpeta con `--add-dir`**, y no uses `--dangerously-bypass-approvals-and-sandbox`.
- **Cursor y Gemini:** respetan `.cursorignore` y `.aiexclude`.
- **Copilot:** pedile a quien administra el repo que lo configure en *Settings → Copilot → Content exclusion*.
- **Otra herramienta:** agregá su archivo de exclusión antes de abrirla en el repo.

## 5. Cómo trabajamos

- **Tareas:** issues del milestone "Entrega". Tomá uno, asignátelo y abrí una rama.
- **Cambios:** rama → PR → revisión de otra persona → merge. Nada directo a `main`.
- **Decisiones de diseño:** un ADR en `docs/adr/` antes de implementar.
- **Corridas:** una fila en [docs/EXPERIMENTOS.md](EXPERIMENTOS.md), también si no funcionó.
- **Con un asistente de IA:** el asistente escribe el código; los scripts sobre los datos del partido los corrés vos, y le pegás solo métricas agregadas.

## 6. Fechas

- **16/11/2026:** entrega interna. El cierre oficial es el 17/11 sin hora publicada.
- Al terminar nuestra participación se borran todas las copias de los datos (REGLAS.md).
