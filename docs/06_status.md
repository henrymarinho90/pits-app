# 06 — Estado del proyecto

Última actualización: 2026-10-03
Estado: actualizado después de la revisión integral.

Este archivo se actualiza al final de cada sesión y funciona como punto de partida para una conversación nueva.

## 1. Fase actual

**Fase 0 — dominio y arquitectura conceptual: cerrada nuevamente después de la revisión.**

Siguiente fase:

**Fase 0.5 — investigación de mercado y validación de fuentes reales.**

## 2. Documentación vigente

| Archivo | Versión/estado |
|---|---|
| `00_review_findings.md` | Auditoría integral |
| `01_project_brief.md` | v2 |
| `02_domain_taxonomy.md` | v11 |
| `03_data_model.md` | v4 |
| `04_infra.md` | v2 |
| `05_decisions_log.md` | v2; D1–D42 |
| `06_status.md` | vigente |
| `07_lessons_learned.md` | vigente |

## 3. Terminado en Fase 0

- Visión del proyecto redefinida como data platform para un marketplace simulado.
- Alcance de producto separado del alcance de UI/pagos.
- Taxonomía de partes y vehículos definida.
- Sistema de confianza de contributor de catálogo definido.
- Reputación comercial separada de la confianza técnica.
- Identidad unificada mediante `account` + roles.
- Modelo de publicaciones, búsquedas, negociaciones y ofertas definido.
- Modelo de órdenes y reseñas comerciales definido; una orden pertenece a un comprador y un vendedor.
- ERD conceptual actualizado.
- Convenciones de procedencia e ingesta definidas.
- Raw storage redefinido como payload inmutable antes de parquet.
- Infraestructura local/producción documentada.
- Reglas mínimas de backups, secrets, healthchecks y límites definidas.
- Decision Log actualizado hasta D42.
- Bitácora de lecciones actualizada.

## 4. Preguntas abiertas

No bloquean la investigación de mercado:

1. Unidades finales de `quantity_unit`.
2. Uso de código DANE desde el MVP para geografía.
3. Reputación comercial: score único o separado buyer/seller.
4. Historial de precio e inventario: core Fase 3 o extensión posterior.

## 5. Próximo paso — Fase 0.5

La siguiente sesión debe usar investigación web y fuentes primarias cuando estén disponibles.

### Objetivos

1. Medir participación por marca en el parque automotor de Colombia, separando autos y motos cuando la fuente lo permita.
2. Confirmar el portafolio actual de marcas de Auteco.
3. Confirmar qué marcas fabrican o ensamblan vehículos/motos en Colombia.
4. Verificar qué datasets relevantes de datos.gov.co siguen disponibles y documentar su esquema real.
5. Verificar cobertura real de NHTSA vPIC para las marcas prioritarias.
6. Evaluar si existen fuentes oficiales útiles para ciudades/códigos DANE.
7. Identificar una primera fuente real suficientemente estable para la Fase 1.

### Entregable

`08_market_research.md`

Debe incluir por cada hallazgo:

- afirmación;
- fuente;
- fecha de consulta;
- cobertura;
- limitaciones;
- cómo afecta el modelo o el roadmap.

## 6. Entrada a Fase 1

La Fase 1 empieza cuando exista una fuente real elegida y su schema haya sido inspeccionado.

Entregable esperado:

```text
source -> raw MinIO -> manifest -> parser/normalizer -> tests
```

Debe demostrar:

- llamada reproducible;
- raw payload preservado;
- batch ID;
- schema validado;
- idempotencia;
- manejo de errores;
- tests unitarios;
- documentación de cómo reejecutar un batch.

## 7. Bloqueos

Ninguno para iniciar Fase 0.5.

## 8. Regla para la siguiente conversación

Antes de agregar una herramienta o entidad nueva, responder:

1. ¿Qué problema del negocio o del pipeline resuelve?
2. ¿Qué habilidad de Data Engineering demuestra?
3. ¿Cuál es el grano o contrato de datos?
4. ¿Cómo se prueba?
5. ¿Cómo se recupera/reprocesa si falla?
