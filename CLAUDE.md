# Pits App — Plataforma de datos (portafolio Data Engineering)

## Comunicación
- Responde SIEMPRE en español, estilo directo y breve (sin preámbulos ni cierres).
- Código, comandos, tablas, columnas y commits en inglés (snake_case, Conventional Commits).
- Henry es Data Analyst/DS pasando a Data Engineer: explica el "por qué" de cada herramienta o patrón frente a la alternativa DA/DS.

## Proyecto
Marketplace de repuestos de autos y motos (Colombia/LATAM). Henry domina el negocio: consúltalo en toda decisión de dominio (tipos de comprador/vendedor, familias de partes, disponibilidad).

## Stack
Python (Typer, pytest, ruff), Docker Compose, MinIO, PostgreSQL, dbt, Airflow (LocalExecutor), Metabase (ya desplegado), GitHub Actions. Redpanda solo en fase avanzada. Desarrollo local en Windows (C:\dev). Despliegue: VPS OVH con Coolify.

## Reglas
1. Sin notebooks: Python modular, CLI y tests.
2. Un paso a la vez; no adelantarse varias fases.
3. Nunca asumir nombres de columnas o archivos: inspeccionar primero.
4. No cambiar métricas ni el modelo de datos en silencio. Toda decisión nueva o corrección = fila nueva `D<n>` en docs/05_decisions_log.md, aprobada por Henry ANTES de implementar. Nunca editar ni borrar filas existentes.
5. Demanda de repuestos se mide con parque automotor (stock), no con ventas/matrículas (flujo).
6. Toda afirmación de mercado lleva fuente verificable.
7. Lecciones y errores van a docs/07_lessons_learned.md (insumo de un curso futuro).
8. Antes de cerrar una tarea: `ruff check .`, `ruff format .`, `pytest -q`.
9. Nunca leer ni imprimir .env ni secretos; usar .env.example.
10. No ejecutar comandos contra el VPS sin confirmación explícita.

## Documentación (leer bajo demanda, no todo de una)
- docs/01_project_brief.md — visión, tracks T1/T2/T3, monetización
- docs/02_domain_taxonomy.md — taxonomía de repuestos
- docs/03_data_model.md — modelo de datos
- docs/04_infra.md — infraestructura
- docs/05_decisions_log.md — decisiones (leer SIEMPRE antes de diseñar)
- docs/06_status.md — estado actual y siguiente paso (leer SIEMPRE al empezar)
- docs/07_lessons_learned.md — bitácora
- docs/08_market_research.md — mercado Colombia
- docs/09_us_market_research.md — mercado EE. UU.

## Agentes
Usa `/orquestar <tarea>` para tareas medianas: arquitecto → (aprobación) → implementador → revisor-senior → (aprobación commit) → documentador.
