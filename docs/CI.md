# Tests sintéticos y reproducción entre sistemas

El workflow `tests` ejecuta cada `tests/test_*.py` con su propio comando,
incluido `python -m tests.test_possession`. Después genera un fixture sintético,
calcula sus etiquetas con `possession.label` y escribe el CSV con `write_csv`.
La consolidación exige los seis resultados y compara sus SHA-256.

La configuración está en `ci_config.json`: Ubuntu 24.04, macOS 15 y Windows 2022,
con CPython 3.12.10 y 3.13.15. `requirements-ci.txt` fija las dependencias de
tests y entrenamiento, incluidas las transitivas. La instalación exige wheels
con `--only-binary=:all:`; si falta uno, falla en vez de compilar desde fuentes.
El scorer es únicamente
`evaluation/possession_metrics.py` de la revisión
`f8f2629ff1e0985f81d7e59d8413678514ee1530` del repo oficial. Su SHA-256 se
verifica antes de importarlo.

## Reproducir localmente

Desde la raíz del repo, usar una de las dos versiones exactas de Python.
Estos comandos no requieren datos abiertos ni datos del concurso.

En macOS o Linux, con Python 3.13.15 instalado:

```bash
MTAH_CI_TMP="$(mktemp -d)"
python3.13 -m venv "$MTAH_CI_TMP/venv"
source "$MTAH_CI_TMP/venv/bin/activate"
python -m pip install --only-binary=:all: -r requirements-ci.txt
export MTAH_OFFICIAL="$MTAH_CI_TMP/official-scorer"
python ci_checks.py scorer "$MTAH_OFFICIAL"
python guard.py repo
python ci_checks.py tests
python repro_check.py
```

En PowerShell, con Python 3.13.15 instalado:

```powershell
$mtahCiTmp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
py -3.13 -m venv "$mtahCiTmp/venv"
$mtahCiPython = "$mtahCiTmp/venv/Scripts/python.exe"
& $mtahCiPython -m pip install --only-binary=:all: -r requirements-ci.txt
$env:MTAH_OFFICIAL = "$mtahCiTmp/official-scorer"
& $mtahCiPython ci_checks.py scorer $env:MTAH_OFFICIAL
& $mtahCiPython guard.py repo
& $mtahCiPython ci_checks.py tests
& $mtahCiPython repro_check.py
```

Repetir con Python 3.12.10 en un segundo entorno. El runner rechaza una versión
distinta, dependencias faltantes o asserts desactivados con `-O` o
`PYTHONOPTIMIZE`. Ejecuta los scripts en orden y termina con error ante el primer
fallo. Los tests de loaders crean sus archivos sintéticos en directorios temporales.

`python repro_check.py` imprime conteos y SHA-256, y borra el CSV temporal.
Para conservarlo, se puede pasar una ruta explícita fuera de `output/`:
`python repro_check.py /ruta/temporal/synthetic.csv`.
El comando rechaza destinos de CSV o metadatos dentro de `output/`, incluidos
enlaces simbólicos que apuntan allí, antes de calcular etiquetas o escribir archivos.

## Metadatos y consolidación

El workflow publica solamente `synthetic.json`. Contiene el hash del CSV, los
conteos, la configuración del fixture, el sistema, Python, las dependencias,
la revisión del scorer y los hashes del código y modelos. No publica el CSV,
arrays, cachés, logs ni filas. Los hashes del código normalizan CRLF a LF; el
hash del CSV siempre usa los bytes reales.

Para generar el mismo JSON localmente, usar el entorno anterior y el identificador
del sistema correspondiente: `macos-15`, `ubuntu-24.04` o `windows-2022`.
En macOS con Python 3.13.15:

```bash
python repro_check.py --metadata "$MTAH_CI_TMP/hash-macos-15-3.13.15/synthetic.json" --runner macos-15
```

El identificador nombra la combinación de CI. En una ejecución local no prueba
que se esté usando la misma imagen de GitHub; el script verifica la familia de
sistema y la versión exacta de Python.

Descargar los seis artefactos del mismo run en una carpeta, conservando sus nombres:

```text
hashes/
  hash-ubuntu-24.04-3.12.10/synthetic.json
  hash-ubuntu-24.04-3.13.15/synthetic.json
  hash-macos-15-3.12.10/synthetic.json
  hash-macos-15-3.13.15/synthetic.json
  hash-windows-2022-3.12.10/synthetic.json
  hash-windows-2022-3.13.15/synthetic.json
```

Con el mismo commit del run: `python ci_checks.py compare hashes`.
Este comando solo necesita la biblioteca estándar. Falla si falta una combinación,
hay archivos adicionales o inválidos, cambió el código o el entorno declarado,
los conteos no cubren los frames o los hashes difieren. No alcanza con que
coincidan los archivos que sí llegaron.

## Checks y límites

`guard.yml` mantiene `no-match-data`. El workflow `tests` también ejecuta
`guard.py repo` en `prepare` y solo lanza la matriz si pasa. `same-bytes`
falla si `prepare` o cualquier trabajo de la matriz falla o se cancela.
Para bloquear merges, la protección de `main` debe exigir `no-match-data` y
`same-bytes`; cambiar el YAML no modifica esa configuración de GitHub.

El fixture recorre el pipeline de etiquetas y escritura, con los modelos
versionados. La suite también cubre la regla alternativa de cambio, modelos de
paradas, geometría y continuidad de velocidades. No llama a `load_atd`, ni lee
`MTAH_DATA`, `output/` o resultados del concurso. No se ajustan umbrales.

Un fixture no prueba determinismo para todas las entradas. La reproducción manual
del CSV del concurso sigue siendo parte de la entrega y la realiza una persona.
El hash sintético se compara entre sistemas, sin fijar un valor esperado en el repo.

El 30/10/2026, GitHub Actions no inicia los jobs por el bloqueo de facturación de
la organización, según las anotaciones del PR #60. Hasta resolverlo, las corridas
locales verifican los entornos disponibles, pero no prueban la matriz remota.
La decisión y cómo se mide están en el [ADR-016](adr/ADR-016-validacion-completa-ci.md).
