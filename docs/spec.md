# docs/spec.md — Analyst (agente SQL conversacional con LangGraph)
*Spec-Driven Development. Borrador de Fase 1 para tu revisión — confirma o ajusta lo marcado con 🔸 antes de congelar. Esto va al repo del #2 como `docs/spec.md`.*

## 0. Variables del proyecto
- **Nombre:** Analyst — agente SQL conversacional. Repo: `analyst-sql-agent`. 🔸 renombrable.
- **Tipo:** agente cloud con LLM, **orquestación multi-paso con LangGraph**.
- **Idioma del producto:** el agente entiende preguntas en ES y EN. Materiales (código, README, case study, Loom): **EN**.
- **Stack tentativo:** Python + LangGraph + Anthropic SDK + Postgres (Supabase) + FastAPI + UI web mínima (React, frontend-design) + Docker + Railway.

## 1. Problema
Los dueños y equipos no técnicos de un negocio no pueden responder preguntas sobre sus propios datos sin alguien que sepa SQL. "¿Cuáles fueron mis 5 productos más vendidos el mes pasado?" o "¿qué clientes no compran hace 90 días?" exigen un analista o un dashboard rígido. Pedir reportes es lento y no escala; los dashboards fijos no responden la pregunta nueva. El valor: que cualquiera pregunte en su idioma y obtenga la respuesta correcta de los datos reales, al instante.

## 2. Alcance v1
**Dentro (5):**
1. Pregunta en lenguaje natural (ES/EN) → SQL sobre un esquema **fijo y pequeño** (ventas: customers, products, orders, order_items).
2. Ejecuta el SQL en **modo solo-lectura** y devuelve respuesta clara: número o tabla pequeña + una frase que la interpreta.
3. **Loop de autocorrección (el corazón LangGraph):** si el SQL falla, el agente lee el error de la DB, lo diagnostica, corrige y reintenta (máx. 3 ciclos).
4. **Seguridad:** solo-lectura forzada a nivel de conexión; límite de filas/timeout por query; rechaza operaciones destructivas y preguntas fuera del esquema.
5. **Anti-alucinación:** si la pregunta no se puede responder con los datos disponibles, lo dice y **NO inventa números** (explica por qué / deriva).

**Fuera de alcance (mín. 5):** operaciones de escritura; múltiples bases / multi-tenant; autenticación y gestión de usuarios; generación de gráficos/visualizaciones (v2); subida de esquema arbitrario; analítica compleja multi-turno (cohortes, forecasting); fine-tuning. No se tocan antes del case study.

## 3. Decisiones cerradas
- **Orquestación con LangGraph, no ramificar a mano** — es el propósito declarado del #2: cerrar el gap de frameworks. El grafo es una máquina de estados **con un ciclo** (la autocorrección). Esto es lo que el proyecto existe para demostrar.
- **Modelo:** Haiku por defecto (clasificación + generación de SQL); subir a Sonnet solo si las evals de SQL lo exigen. Medir tokens.
- **Solo-lectura en profundidad:** usuario de DB con permisos de SELECT únicamente — la defensa no vive solo en el prompt.
- **Lead-time externo (Día 1, como la clínica):** cuenta Supabase + Railway.
- 🔸 **DB:** Postgres/Supabase (reúsas el patrón de deploy + el gotcha del session pooler como historia de entrevista) **o** SQLite (más simple, sin lead-time, pero pierdes ese reúso). Recomiendo Postgres por la historia.

## 4. Requisitos no funcionales (los que venden)
- **Latencia:** objetivo < 10s/pregunta, **instrumentada por etapa** (clasificación / generación SQL / ejecución / síntesis), honesta.
- **Precisión:** ≥ umbral en la suite de evals — **baseline primero, luego fijo el número** (no lo invento).
- **Costo:** objetivo por consulta, **medido** (tokens reales), no estimado.
- **Disponibilidad:** deploy 24/7, corre con la laptop apagada.
- **Seguridad:** conexión solo-lectura, límites de filas/timeout, validación de que el SQL generado no salga del esquema permitido.
- **Anti-abuso:** rate limit por sesión, truncado de input, cap de ciclos de autocorrección (3).

## 5. Arquitectura (grafo LangGraph)
```
Usuario (UI web mínima / API)
        │
        ▼
FastAPI ──► logging estructurado (sin PII)
        │
        ▼
LangGraph — máquina de estados:
  [clasificar pregunta]
        │
        ├─ fuera de esquema / no respondible ─► [rechazar + explicar]   (anti-alucinación)
        │
        └─ respondible ─► [generar SQL]
                                │
                                ▼
                        [ejecutar SQL (solo-lectura)]
                                │
                     ┌──────────┴───────────┐
                  éxito                   error de DB
                     │                        │
                     ▼                        ▼
              [sintetizar              [diagnosticar error]
               respuesta]                     │
                     │                 [regenerar SQL] ─┐  (loop, máx. 3)
                     ▼                        ▲         │
                Respuesta ◄───────────────────┘─────────┘
                              (si agota 3 ciclos → "no pude responder" + deriva)
```

## 6. Modelo de datos mínimo (esquema de negocio, fijo)
- `customers` (id, name, email, created_at)
- `products` (id, name, category, price)
- `orders` (id, customer_id, status, created_at)
- `order_items` (id, order_id, product_id, quantity, unit_price)

Datos sintéticos seedeados, con volumen suficiente para preguntas reales (varios meses de pedidos).
🔸 `sessions` (memoria de conversación acotada) — decidir si el multi-turno entra en v1 o v2.

## 7. Flujos de ejemplo (5) = baseline de evals
1. **Camino feliz:** "¿Cuántos pedidos hubo en mayo?" → SQL de conteo → número + frase.
2. **Acción núcleo:** "Top 5 productos por ingresos el último mes" → JOIN + agregación + orden → tabla correcta.
3. **Urgencia/edge (autocorrección):** una pregunta cuyo primer SQL falle (p. ej. columna ambigua) → el agente lee el error, corrige, reintenta y responde. **Este caso PRUEBA el loop de LangGraph.**
4. **"No sé":** "¿Cuál es mi margen de ganancia?" (no hay columna de costo) → no inventa; dice que el dato no está en el esquema.
5. **Fuera de tema:** "¿Qué clima hará mañana?" → redirige amable: solo responde sobre los datos del negocio.

Estos 5 SON la baseline de la suite de evals (Fase 5), definidos aquí. Caso extra obligatorio: destructivo/inyección ("borra la tabla customers") → debe **rechazar**.

## 8. Criterios de aceptación
- [ ] Pregunta real en lenguaje natural → respuesta correcta end-to-end.
- [ ] El loop de autocorrección recupera de al menos un error de SQL real (demostrable).
- [ ] Rechaza escritura/destructivo y preguntas fuera del esquema (seguridad).
- [ ] No inventa números cuando el dato no existe (anti-alucinación).
- [ ] Suite de evals corrida: baseline → resultado documentado, costo medido.
- [ ] Desplegado en cloud, responde con la laptop apagada.
- [ ] README reproducible (clonar → correr en < 10 min).

**Para "terminado-contratable" (set de evidencia):**
- [ ] `CASE_STUDY.md` (problema → arquitectura → decisiones → métricas → historia del loop).
- [ ] `docs/spec.md` y `docs/DECISIONS.md` en el repo.
- [ ] Reporte de evals (script + resultado).
- [ ] Loom (90s–enlazado en el README).

## 9. Métricas para el case study
% de evals · costo/consulta · latencia por etapa · nº promedio de ciclos de autocorrección · tasa de recuperación de errores de SQL · uptime.

---

## Decisiones que necesito de ti (🔸) antes de congelar el spec
1. **Dominio:** ¿el esquema de ventas SMB que propongo, o prefieres otro (clínica reusada, logística, inventario)?
2. **DB:** Postgres/Supabase (reúso + el gotcha como historia) o SQLite (más simple, sin lead-time)?
3. **UI:** ¿UI web mínima en v1 (usas frontend-design) o solo API en v1 y la UI a v2?
4. **Multi-turno:** ¿memoria de conversación en v1 o v2?

## Preguntas de estrés (respóndelas mentalmente antes de congelar)
1. ¿El alcance v1 se shippea en tu timebox? (Esquema chico + Haiku + loop acotado = sí, si no agregas charting.)
2. ¿Cada cosa "dentro" es imprescindible? (El loop sí — es el punto. El multi-turno y la UI son los candidatos a recortar.)
3. ¿Sé medir "funciona"? (Golden set de preguntas → respuesta esperada = sí.)
4. ¿Lead-time externo? (Supabase/Railway → Día 1.)
5. ¿Las decisiones quedarán en `docs/DECISIONS.md` con su porqué real? (Sí, al cierre de cada sesión.)
