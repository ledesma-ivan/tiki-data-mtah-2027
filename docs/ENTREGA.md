# Checklist de la entrega (Fase 1)

Issue #13. Fechas: documento técnico y repo público el **14/11**, entrega interna el **16/11**, cierre oficial
el **17/11** (`SUBMISSION.md`). Lo corre una persona en su máquina; ninguna IA ve los datos ni las salidas
(`AGENTS.md`). Los comandos son para `cmd` de Windows, desde la raíz del repo, salvo que diga otra cosa.

## 1. Congelar el pipeline (hasta el 14/11)

- [ ] El equipo decide qué entra. Lo que no esté mergeado en `main` ese día no va en la entrega.
- [ ] Ningún PR abierto toca lo que produce el archivo: `possession.py`, `live_model.json`, `stops_model.json`,
  `requirements.txt` (dependencias fijadas) o el código que `possession.py` importa. Los que lo tocan quedan para después.
- [ ] `main` actualizado: `git checkout main` y `git pull`.
- [ ] Tests sintéticos: la suite completa (`python ci_checks.py tests`, más `python guard.py repo` y
  `python repro_check.py`), con los comandos y las versiones exactas de Python de [`CI.md`](CI.md). Cubre
  `tests/test_*.py`, incluido el modelo de juego vivo. Las corridas locales prueban los entornos que hay en cada máquina;
  la matriz de tres sistemas en GitHub Actions no está verificada mientras la facturación de la organización la bloquee
  (`CI.md`, 30/10).

## 2. Generar y validar el CSV (16/11)

Lo corre una persona, con los datos en la carpeta de `MTAH_DATA` (`AGENTS.md`), sin escribir la ruta a mano:

```
python possession.py "%MTAH_DATA%"
```

- [ ] Anotar la línea que imprime: conteos H, A, D, X y `sha256`. Con el peso 1 (#91, opción A), la pelota muerta antes
  del saque del segundo tiempo (ADR-032, #108) y las pelotas del entrenamiento sin niveles de la verdad pública
  (ADR-033, #111) es `dab54052d5cfedf5a57fa60a7a4fb4d3c8884213e3888aa6a3ec78b58c400078` (H 52609, A 37034, D 69214,
  X 40462), con `live_model.json` `1f8b706e…`. Lo corrieron Lautaro en `ba8af70` e Ivan en `db8ba40` (#112). Antes del #112
  era `4c55c728…`, con `live_model.json` `c0a12df6…` (Lautaro e Ivan en `bfe57de`, #108). Antes del #108 era
  `a7cd94d0…` (Ivan y Lautaro en `b00e062` y otra vez en `45f99fe`). El hash experimental del peso 3 (#77, `f2460d57…`) no
  es la entrega. Si cambió, tiene que haber un PR que explique por qué.
- [ ] Una segunda persona lo corre en su máquina con el mismo commit y da el mismo `sha256`.
- [ ] Copiar `output\possession.csv` a `Tiki_Data.csv`.
- [ ] Validar **ese** archivo, el que se sube, desde `..\mtah2027`:

```
python evaluation\validate_submission.py "C:\ruta\a\Tiki_Data.csv"
```

- [ ] Opcional, como chequeo de que corre: copiarlo a `..\mtah2027\evaluation\results\` y correr
  `python evaluation\run_evaluation.py --bootstrap 1000`. La ventana pública no decide nada.

## 3. Documento técnico (14/11)

- [x] `docs/TECHNICAL.md` revisado por dos personas (#11): Lautaro en el #88 e Iván en el #116.
- [x] La tabla de resultados coincide con el `sha256` de la entrega (`dab54052…`, sección 5).
- [x] Exportar a `Tiki_Data.pdf` (o subir `Tiki_Data.md`), sin el comentario del encabezado: `docs/Tiki_Data.pdf`, del `TECHNICAL.md` congelado el 14/11.

## 4. Repo público (14/11, #12)

- [ ] Copia limpia sin el link del Drive (está en el `README.md` y en la historia de git).
- [ ] Sin datos del partido ni salidas: `python guard.py repo` da OK en la copia.
- [ ] Desde un clon nuevo de la copia, con `requirements.txt`, `possession.py` da el mismo `sha256`.
- [ ] El repo es público y el link abre sin sesión.

## 5. Formulario (16/11)

- [ ] El link del formulario llega por mail a los inscriptos. Lo sube una sola persona, con cuenta de Google.
- [ ] **Team Name:** el mismo que pusieron todos en la inscripción.
- [ ] Archivos: `Tiki_Data.csv` (validado en el paso 2), `Tiki_Data.pdf` y el link del repo público.
- [ ] Guardar la confirmación. Se puede editar hasta el cierre: vale la última respuesta.
