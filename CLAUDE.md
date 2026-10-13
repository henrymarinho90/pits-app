# Pits App — Plataforma de datos + marketplace CO/US + talleres CO

## Comunicación
- Responde SIEMPRE en español, estilo directo y breve (sin preámbulos ni cierres).
- Código, comandos, tablas, columnas y commits en inglés (snake_case, Conventional Commits).
- Henry es Data Analyst/DS pasando a Data Engineer: explica el "por qué" de cada herramienta o patrón frente a la alternativa DA/DS.

## Proyecto
Tres productos (D68): plataforma de datos (portafolio DE, lo implementado hoy), marketplace web de autopartes Colombia + EE. UU. (mercados domésticos separados, D71) y app de gestión de talleres pequeños solo Colombia con facturación electrónica. El warehouse es analítico; las apps tendrán OLTP propia (D70). Los productos avanzan por hitos aprobados. Henry domina el negocio: consúltalo en toda decisión de dominio (tipos de comprador/vendedor, familias de partes, disponibilidad).

## Stack
Python (Typer, pytest, ruff), Docker Compose, SeaweedFS (S3, D57), PostgreSQL, dbt, Airflow (LocalExecutor), Metabase (ya desplegado), GitHub Actions. Redpanda solo en fase avanzada. Desarrollo local en Windows (C:\dev). Despliegue: VPS OVH con Coolify.

## Reglas
1. Sin notebooks: Python modular, CLI y tests.
2. Un paso a la vez; no adelantarse varias fases.
3. Nunca asumir nombres de columnas o archivos: inspeccionar primero.
4. No cambiar métricas ni el modelo de datos en silencio. Toda decisión nueva o corrección = fila nueva `D<n>` en docs/05_decisions_log.md, aprobada por Henry ANTES de implementar. Nunca editar ni borrar filas existentes, salvo la celda Estado de una decisión reemplazada o ajustada (D73(b)).
5. Demanda de repuestos se mide con parque automotor (stock), no con ventas/matrículas (flujo).
6. Toda afirmación de mercado lleva fuente verificable.
7. Lecciones y errores van a docs/07_lessons_learned.md (insumo de un curso futuro).
8. Antes de cerrar una tarea: `uv run ruff check .`, `uv run ruff format .`, `uv run pytest -q`.
9. Nunca leer ni imprimir .env ni secretos; usar .env.example.
10. No ejecutar comandos contra el VPS sin confirmación explícita.

## Documentación (leer bajo demanda, no todo de una)
- docs/01_project_brief.md — visión, productos y alcance (D68–D73)
- docs/02_domain_taxonomy.md — taxonomía de repuestos
- docs/03_data_model.md — modelo de datos
- docs/04_infra.md — infraestructura
- docs/05_decisions_log.md — decisiones (leer SIEMPRE antes de diseñar)
- docs/06_status.md — estado actual y siguiente paso (leer SIEMPRE al empezar)
- docs/07_lessons_learned.md — bitácora
- docs/08_market_research.md — mercado Colombia
- docs/09_us_market_research.md — mercado EE. UU., tracks T1/T2/T3 y monetización
- docs/10_next_project_playbook.md — playbook destilado de las lecciones para arrancar el próximo proyecto más rápido

## Agentes
Usa `/orquestar <tarea>` para tareas medianas: arquitecto → (aprobación del plan) → implementador → revisor-senior → documentador → PR (aprobación del PR). Dentro de un plan aprobado los agentes commitean, hacen push de la rama y abren el PR sin pedir permiso (D45, D73(a)).
