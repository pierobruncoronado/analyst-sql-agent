# Reglas del proyecto — Analyst (leer siempre)

## Contexto
- Proyecto: agente SQL conversacional que responde preguntas en lenguaje natural (ES/EN) sobre una base de datos de negocio, generando y ejecutando SQL **solo-lectura**, con un **loop de autocorrección orquestado en LangGraph**. La spec completa está en `docs/spec.md` — es la fuente de verdad. Ante ambigüedad, consultarla; si no resuelve, PREGUNTARME antes de asumir.
- **Razón de existir del proyecto:** cerrar el gap de frameworks (LangGraph / agéntico multi-paso). El loop de autocorrección ES el punto; todo lo demás es soporte de ese punto.
- Idioma del producto: el agente entiende ES y EN. Idioma del código, comentarios, README, case study y Loom: **EN**.

## Flujo de trabajo (obligatorio en cada sesión)
1. Antes de codear: enumerar el plan en pasos y esperar mi OK.
2. Después de implementar: CORRER el código y mostrar el output real. Nada es "listo" sin ejecución visible.
3. Si algo que pido contradice la spec o agranda el alcance v1: avisar y NO implementar sin confirmación.
4. Cerrar cada sesión con:
   (a) verificación contra los criterios de aceptación de la spec (sección 8);
   (b) actualizar `docs/DECISIONS.md` con la fase trabajada — qué / por qué / cómo, input→output, gotchas (solo decisiones, no narración línea por línea);
   (c) commit descriptivo + verificar `.gitignore` y que no haya secrets + `git push`;
   (d) dejar los pendientes para la próxima sesión en `docs/PROGRESO.md`.

## Reglas de dominio (decisiones de la spec que NO se reescriben)
- **Orquestación con LangGraph, NO ramificar a mano.** El grafo es una máquina de estados CON UN CICLO: clasificar → generar SQL → ejecutar → (éxito: sintetizar | error de DB: diagnosticar → regenerar SQL, loop máx. 3 ciclos). Esto es lo que el proyecto existe para demostrar — no lo colapses en if/else.
- **Esquema FIJO y pequeño:** `customers`, `products`, `orders`, `order_items`. Datos sintéticos seedeados con volumen real (varios meses de pedidos). No se agregan tablas en v1.
- **Solo-lectura EN PROFUNDIDAD:** el agente se conecta con un usuario de DB con permisos de **SELECT únicamente**. La defensa NO vive solo en el prompt — vive en la conexión. Además: límite de filas por query + timeout de ejecución.
- **Seguridad obligatoria:** rechazar operaciones de escritura/destructivas, inyección ("borra la tabla customers") y preguntas fuera del esquema permitido. Validar que el SQL generado no salga del esquema. Cap de ciclos de autocorrección = 3.
- **Anti-alucinación:** si la pregunta no se responde con los datos disponibles (ej. no hay columna de costo → margen no calculable), decirlo explícitamente y **NO inventar números**. Explicar por qué / derivar.
- **Modelo:** Haiku por defecto (clasificación + generación de SQL). Subir a Sonnet SOLO si las evals de SQL lo exigen, y que lo decida la data, no la intuición. Medir tokens siempre.
- **DB:** Postgres/Supabase. `DATABASE_URL` usa el **Session Pooler (puerto 5432, IPv4)** — la conexión directa es IPv6-only y falla desde Railway/Docker; el transaction pooler (6543) rompe los prepared statements. (Gotcha ya conocido del proyecto #1; documentarlo en `DECISIONS.md`.)
- **Alcance v1 (lo que está DENTRO, nada más):** NL→SQL sobre el esquema fijo, ejecución solo-lectura, loop de autocorrección, capa de seguridad, anti-alucinación. **Fuera de v1:** escritura, multi-tenant/multi-DB, auth/usuarios, charting/visualizaciones, subida de esquema arbitrario, analítica multi-turno (cohortes/forecasting), fine-tuning.
- **UI:** mínima-mínima en v1 (un input + un área de resultado, vía `frontend-design`). Es lo **PRIMERO que se recorta** si el timebox aprieta. **Multi-turno (memoria de conversación) = v2.**

## Estándares técnicos (production-readiness — el filtro de contratación)
- Secrets SOLO en `.env`; verificar `.gitignore` antes del primer commit. Repo público.
- Manejo de errores en TODA llamada externa (DB, API LLM): try/except + log + fallback. Nunca crash silencioso. Aquí el fallback central es el propio loop: error de SQL → diagnosticar → reintentar; agotados los 3 ciclos → mensaje honesto ("no pude responder con seguridad") + deriva.
- Validación fail-closed donde aplique (input vacío/mal formado → rechaza, no asume).
- Output estructurado vía **forced tool-use** cuando se necesite un enum/JSON válido (clasificación de la pregunta: respondible / fuera-de-esquema / destructiva). No parsear texto libre.
- **LangGraph para la orquestación multi-paso** — es el delta del proyecto y el estándar que más pesa aquí. Estado del grafo tipado y explícito; cada nodo con una sola responsabilidad.
- Logs estructurados (JSON a stdout, una línea por evento), sin PII. Loggear: intent, nº de ciclos de autocorrección, SQL final, status, latencia por etapa.
- **Evals como gate (Eval-Driven):** definir la **baseline PRIMERO** sobre los 5 flujos golden de la spec (+ el caso de inyección obligatorio), LUEGO fijar el umbral. Mezcla determinista + LLM-as-judge para la corrección de la respuesta. Correr las evals en **CI (GitHub Actions)** como gate de regresión en cada push. Nada se declara "funciona" sin la suite corrida.
- **Instrumentar antes de afirmar:** latencia por etapa (clasificar / generar SQL / ejecutar / sintetizar), honesta, nunca hand-waved. Costo por consulta medido de tokens reales. Métricas propias del loop: nº promedio de ciclos + tasa de recuperación de errores de SQL.
- **Conciencia de OWASP LLM Top 10**, en especial prompt-injection → SQL-injection: la capa de seguridad (usuario read-only + validación de esquema + rechazo de destructivo) es la mitigación central y una de las mejores historias de entrevista del proyecto. Trátala como feature de primera clase, no como afterthought.
- Funciones cortas, nombres descriptivos, sin abstracciones especulativas.

## Anti-patrones míos (interrumpir si aparecen)
- Refactorizar/embellecer algo que ya funciona antes de terminar la fase → terminado > perfecto.
- Meter features fuera del alcance v1 (charting, multi-turno, auth, multi-DB) → señalar la sección "Fuera de alcance" de la spec y NO implementar.
- **Sobre-ingeniar el grafo de LangGraph:** nodos especulativos, estado que no se usa, ramas para casos que no están en los 5 flujos → el grafo mínimo que prueba la autocorrección le gana a uno "completo".
- Pulir el sistema/arquitectura/los docs en vez de shippear el core → decírmelo de frente.
