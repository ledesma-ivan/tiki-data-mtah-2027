# Reglas del juego

Todo lo que aceptamos al anotarnos y lo que los organizadores aclararon después, resumido para el equipo al 26/10/2026. Si algo cambia, manda el documento original (links al final). Si una regla no está clara o lo que vamos a hacer queda cerca del límite, **se pregunta antes de construir**: issue en el repo oficial o mail a hackathon.talentarena@mobileworldcapital.com.

---

## 1. LOS DATOS DEL PARTIDO NUNCA PASAN POR UNA IA EN LA NUBE

> [!CAUTION]
> **Ni el video, ni el tracking, ni el Smart Tagging, ni la homografía. Ni filas sueltas, ni recortes, ni capturas, ni salidas de notebooks o logs que los muestren.** Vale para cualquier IA alojada en la nube: Claude, ChatGPT, Gemini, Copilot, Cursor y similares. Alcanza con que lo haga uno para que puedan excluir al equipo entero (T&C 19).

Qué dicen los términos (sección 8): se pueden usar modelos de lenguaje, comerciales o abiertos, en la nube o locales, pero no se puede subir, divulgar ni poner a disposición de ningún LLM de terceros alojado en la nube ningún video, dataset, información confidencial ni material restringido de la competencia, ni extractos, salvo autorización escrita. El repo oficial lo repite en `FAQ.md` y en `OVERVIEW.md`.

En la práctica:

- **Los asistentes de código trabajan solo con código.** La carpeta de datos va fuera de la carpeta del repo y de cualquier carpeta que el asistente pueda leer, para que no la abra ni por accidente.
- **Nada de pegar** filas, tablas, gráficos, capturas de frames ni mensajes de error que muestren datos en un chat con una IA en la nube.
- **Lo que sí puede ver una IA en la nube**: el código, el repo oficial y sus issues, los 5 minutos públicos de verdad de campo (licencia MIT), métricas agregadas (por ejemplo, el `spellF1` de una corrida) y los datos abiertos de **otros** partidos.
- Si algo necesita mirar los datos con IA: un modelo que corra en la máquina, sin pasar por la nube.

---

## 2. Qué se puede hacer con los datos

- **Solo para el desafío.** Prohibido reproducirlos, publicarlos, redistribuirlos o explotarlos comercialmente sin autorización escrita de BIHUB y Metrica (T&C 8). El link del Drive es para inscriptos: no sale del equipo.
- **Nunca en un repo**, tampoco en este: el `.gitignore` bloquea `data/`, `BAR-ATH_*` y `*.mp4`. Tampoco derivados que permitan reconstruirlos: exportaciones de tracking por frame, recortes de video y similares (`RULES.md`).
- **Dónde guardarlos**: fuera del repo y fuera de carpetas que se sincronizan con la nube (OneDrive, Google Drive, Dropbox).
- **Al terminar nuestra participación, se borra todo**: todas las copias, locales o en la nube, incluidos extractos, datasets derivados, embeddings y pesos de modelos que los contengan o permitan reconstruirlos. Se quedan solo el código, la documentación y los entregables propios que no permitan reconstruirlos. Vale también si quedamos afuera en la fase 1 (T&C 8).

---

## 3. Qué se puede y qué no en el reto

Fuente: `RULES.md` del repo oficial y las respuestas de los organizadores en sus issues (el número entre paréntesis).

**Se permite cualquier método**, con dos condiciones: que los organizadores puedan acceder a él y revisarlo, y que el documento técnico lo explique. Cualquier lenguaje, modelos preentrenados, LLM, datos externos de **otros** partidos, detección o tracking propios. Mejorar o reemplazar los datos que dan está bien si lo hace un algoritmo. **Lo único que se descarta es un modelo privado o un dataset interno que no se pueda compartir.**

**Prohibido:**

1. **Etiquetar a mano el partido dado (BAR-ATH), en cualquier cantidad**: ni para la entrega, ni para entrenar, ni para validar, ni para elegir los valores de los parámetros, aunque esas etiquetas nunca entren al pipeline (#8, #10). Tampoco corregir a mano el tracking.
2. **Usar la verdad de campo privada** o cualquier dato producido por personas sobre ese partido: eventos de Opta, StatsBomb, Wyscout o LaLiga, tracking corregido, anotaciones.
3. **Entregar un archivo que el repo no regenere byte a byte.**

**Los 5 minutos públicos** sirven para verificar que el pipeline está bien: frames alineados, archivo bien formado, etiquetas que significan lo que creemos. **No son para entrenar, ni para ajustar, ni para elegir entre dos versiones** (#16; `EVALUATION.md` muestra que eligen mal).

**Sí se puede:**

- **Mirar el video** para entender y depurar, y convertir observaciones generales en reglas del código. Lo que no: convertir lo visto en etiquetas, correcciones o reglas y constantes atadas a frames concretos del partido (#14).
- **Etiquetar a mano otros partidos, sin límite**, elegir los parámetros ahí y aplicarlos sin cambios a BAR-ATH. Hay que compartir con los organizadores el video y las anotaciones (si tenemos derechos sobre ellos) y explicar en el documento qué se etiquetó, cómo, quién y cuánto (#8, #10).
- **Usar datos abiertos de otros partidos**, citándolos en el documento y en el README. Aprobado como ejemplo: IDSSE, de la Bundesliga, con licencia CC BY 4.0 (#16). `metrica-sports/sample-data` no tiene licencia formal: pide usarla con responsabilidad y citar la fuente.
- **Usar frames futuros**: la tarea es post partido (#15).
- **Usar GPU y tardar lo que haga falta** para reproducir (#2).
- **Commitear la salida de una etapa** junto con el script, la versión del modelo y los ajustes que la regeneran, siempre que no permita reconstruir los datos (#14).

**Reproducción (#11)**: el entrenamiento no tiene que dar exactamente igual (alcanza con publicar su código); la entrega sí: pesos commiteados, inferencia en CPU, dependencias fijadas y semillas fijas.

> [!WARNING]
> **Zona gris, preguntar antes**: entrenar algo sobre BAR-ATH con etiquetas que genera un algoritmo. El 22/10 rechazaron un detector de pelota entrenado sobre el video del partido con el tracking dado como etiquetas (#2), pero el `RULES.md` del 23/10 permite pseudo-etiquetas producidas por un algoritmo sobre ese partido.

---

## 4. Fechas

Barcelona va 4 horas adelante de Argentina (CET, UTC+1, desde el 25/10/2026).

| Etapa | Fecha | Hora argentina |
|---|---|---|
| Inscripción | hasta el **10/11/2026** | sin hora publicada |
| Entrega de la fase 1 | **17/11/2026** | **sin hora publicada**: planificar para el 16/11. Si cierra al empezar el 17/11 en Barcelona, son las 20:00 del 16/11 acá |
| Resultados de la fase 1 | antes del 26/11/2026 | |
| Fase 2, reto de innovación (top 20) | 26/11/2026 al **14/01/2027, 11:00 CET** | 07:00 del 14/01 |
| Presentación final (top 5) | **22/02/2027, 11:00 CET** | 07:00 del 22/02 |
| Final presencial | **02/03/2027**, Talent Arena, Fira Barcelona (Montjuïc) | |

---

## 5. Equipo e inscripción (T&C 4 y 5)

- De **3 a 5 integrantes**, con al menos **3 perfiles técnicos** (datos, IA, software, estadística o afines). Un equipo con menos de 3 inscriptos no vale, sin importar su puntaje.
- Cada integrante: mayor de edad, con formación técnica o profesional en datos, IA, software, estadística, análisis táctico o afines, y con documento válido según la ley española (DNI/NIF, pasaporte o NIE: para nosotros, el pasaporte).
- **Cada uno se anota por su cuenta**, con:
  - **la cuenta de Gmail con la que va a abrir el Drive de los datos** (#5). Quien usó otro mail se vuelve a anotar;
  - **el mismo nombre de equipo, escrito idéntico** (letras, espacios y mayúsculas), para que nos agrupen.
- El acceso a los datos llega dentro de las 72 horas.

---

## 6. La entrega de la fase 1 (`SUBMISSION.md`)

Un único Google Form. El link llega por mail a los inscriptos, hace falta cuenta de Google, va una respuesta por equipo (editable) y vale la última antes del cierre; lo tardío no cuenta.

1. **El CSV** `frame,label`, 199.319 filas, llamado `<equipo>.csv`. Validarlo antes con `evaluation/validate_submission.py` del repo oficial, sobre el archivo exacto que se sube.
2. **Este repo, público**, que regenere exactamente el mismo archivo: fuente, dependencias fijadas, instrucciones y el comando.
3. **Un documento técnico corto** (`<equipo>.pdf` o `.md`): el enfoque y por qué, qué datos se usaron y cuáles se descartaron, los datos de entrenamiento etiquetados (fuente, quién, cuánto: nada del partido dado), las reglas de posesión, las limitaciones y cómo reproducirlo.

No hay leaderboard ni devolución antes del cierre. Pueden volver a correr el repo ganador para confirmar que reproduce el archivo.

### El día que hacemos público el repo

- [ ] Sacar el link del Drive del README y de **toda la historia** de git, o publicar una copia limpia del repo.
- [ ] Revisar que ningún commit tenga datos, derivados que permitan reconstruirlos ni salidas que los muestren.
- [ ] Revisar que las dependencias estén fijadas y que el comando regenere el CSV byte a byte.

---

## 7. Propiedad intelectual (T&C 16)

> [!IMPORTANT]
> **Todo lo que desarrollemos durante el desafío, Metrica Sports lo puede usar comercialmente, gratis y para siempre.**

- Lo que presentamos sigue siendo nuestro, pero MWCapital, BIHUB y Metrica reciben una licencia limitada, no exclusiva, mundial y gratuita para usarlo y mostrarlo, solo para promocionar y desarrollar la competencia y futuras ediciones.
- **Además, Metrica Sports recibe una licencia no exclusiva, mundial, gratuita, irrevocable y perpetua** para usar, modificar, integrar y explotar comercialmente los "resultados" en sus productos y servicios. "Resultados" son las ideas, enfoques, metodologías, marcos analíticos, conceptos y estrategias desarrollados durante el desafío, **estén o no en código**.
- No tienen que justificar trabajo previo ni desarrollos paralelos, y participar no nos da exclusividad ni derecho a frenarlos si hacen algo parecido, antes, durante o después.
- Garantizamos que no infringimos derechos de terceros: hay que respetar la licencia de cada dataset, modelo y librería que usemos.
- **En la práctica: no traer código, modelos ni ideas de otros proyectos propios que no queramos ceder.** Ante la duda, consultarlo con el equipo antes.

---

## 8. Confidencialidad, imagen y cambios (T&C 3, 14 y 17 a 21)

- **Confidencialidad (18)**: todo lo que comparten los organizadores es confidencial, no se usa ni se comparte con terceros sin autorización escrita, y dura **24 meses** después del final de la competencia.
- **Imagen (17)**: nos pueden filmar y fotografiar, y usar nombre e imagen para promoción, en todo el mundo y sin pago. Se revoca por escrito, hacia adelante.
- **Cambios (19)**: pueden modificar, extender o cancelar la competencia, y avisan por mail o en el sitio de Talent Arena. Quien no acepta un cambio avisa por escrito en 72 horas y queda afuera. **Pueden excluir** por uso indebido de recursos, problemas de seguridad, no devolver materiales o violar los términos.
- **Participar (3)**: es gratis y anotarse implica aceptar todo. Información falsa o incompleta: rechazo en cualquier momento.
- **Responsabilidad (14)**: cada uno cuida su seguridad y su equipo, y tiene su propio seguro.
- **Fraude (20) y ley (21)**: ley española, tribunales de Barcelona.

---

## 9. Privacidad (T&C 15 y política de MWCapital)

- **Qué datos nuestros tratan**: los del formulario (nombre, documento, mail, teléfono, LinkedIn, GitHub, perfil y equipo). Los usan para gestionar la competencia y pueden compartirlos con BIHUB, Metrica y proveedores.
- **No incorporar ni procesar datos personales que no sean los provistos.**
- **Política general de MWCapital** ("Latest update: April 2026"): el responsable es la Fundació Barcelona Mobile World Capital Foundation (Pl. Pau Vila 1, Sector 2C, Palau de Mar, 08039 Barcelona). La inscripción a eventos se trata por contrato y se guarda "un período razonable"; fotos, videos y comunicaciones comerciales, con consentimiento; algunos proveedores pueden estar fuera de la UE, con garantías.
- **Derechos** (acceso, rectificación, supresión, limitación, oposición, portabilidad y retirar el consentimiento): dpo@mobileworldcapital.com. Reclamos ante la AEPD.

---

## 10. Premios (T&C 12)

- **Sin efectivo.** A los 5 finalistas les cubren viaje y alojamiento a Barcelona, con límites que avisan antes.
- **1.er puesto**, cada integrante: camiseta oficial del FC Barcelona, 50 % de descuento en el Postgrado en Sports Analytics, entrada al MWC Barcelona 2028, entrada XPro a Talent Arena 2028 y licencia anual de Metrica Nexus Elite.
- **2.º**: 15 % de descuento en el posgrado, entrada XPro a Talent Arena 2028 y licencia anual de Metrica Nexus Pro. **3.º**: entrada XPro a Talent Arena 2028 y licencia anual de Metrica Nexus Prime.
- Todos los finalistas: merchandising de BIHUB y una experiencia exclusiva del FC Barcelona. Los impuestos corren por cuenta del ganador y los premios no se canjean.

---

## Fuentes

- Términos y condiciones v2 (PDF de 11 páginas): https://25499644.fs1.hubspotusercontent-eu1.net/hubfs/25499644/More%20Than%20A%20Hack%202027%20-%20Terms%20and%20Conditions%20v2.pdf
- Política de privacidad de MWCapital: https://mobileworldcapital.com/en/privacy-policy/
- Repo oficial: https://github.com/metrica-sports/more-than-a-hack-2027 (`RULES.md`, `FAQ.md`, `SUBMISSION.md`, `EVALUATION.md`) y sus issues: https://github.com/metrica-sports/more-than-a-hack-2027/issues?q=is%3Aissue
- Landing e inscripción: https://landing.mobileworldcapital.com/more-than-a-hack-2027
- Contacto de los organizadores: hackathon.talentarena@mobileworldcapital.com
