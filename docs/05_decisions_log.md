# 05 — Registro de decisiones

Última actualización: 2026-10-09
Estado: v3

Regla: una decisión nunca se borra. Si cambia, se agrega una nueva decisión y la anterior queda marcada como reemplazada.

## A. Arquitectura e infraestructura

| # | Estado | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|---|
| D1 | Vigente | Desarrollo local con Docker Compose; VPS de OVH como producción | Permite probar sin arriesgar servicios del VPS | Desarrollar directamente en producción |
| D2 | Vigente | PostgreSQL como warehouse inicial | Volumen del proyecto y objetivo pedagógico no requieren warehouse cloud desde el inicio | BigQuery/Snowflake como dependencia inicial |
| D3 | Reemplazada por D29 | MinIO como capa raw en parquet | Se buscaba conservar respuestas para reproceso | Cargar APIs directo a Postgres |
| D4 | Vigente | dbt para transformaciones | SQL versionado, tests, documentación y lineage lógico | Scripts SQL sueltos/notebooks |
| D5 | Vigente | Airflow como orquestador; LocalExecutor como punto de partida | Permite aprender DAGs, retries, schedules y backfills sin infraestructura distribuida adicional | CeleryExecutor en el MVP |
| D6 | Vigente | Sin Spark en el MVP | El volumen no justifica su complejidad | Agregar Spark solo para mostrar la herramienta |
| D7 | Vigente | Redpanda solo en fase opcional de streaming | El streaming debe responder a una necesidad del proyecto | Introducir Kafka/streaming desde el inicio |
| D8 | Vigente | Reutilizar Metabase existente si el aislamiento es suficiente | Reduce consumo de recursos | Segundo Metabase sin necesidad |
| D9 | Vigente | Límites de memoria en servicios nuevos | Protege al resto del VPS ante consumo inesperado | Contenedores sin límites |

## B. Modelo de dominio y catálogo

| # | Estado | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|---|
| D10 | Vigente | Familias por sistema funcional con `vehicle_scope` | Evita árboles duplicados para carro/moto | Familias separadas por tipo de vehículo |
| D11 | Vigente | Jerarquía familia -> subfamilia -> `part_type` -> `part` | Kits apuntan a una clase y fitment resuelve la pieza concreta | Tipos como texto libre |
| D12 | Vigente | Varios códigos por pieza en `part_code` | Existen códigos OEM, superseded, aftermarket, interchange, SKU, barcode | Un código único por pieza |
| D13 | Vigente | Ediciones y revisiones de catálogo append-only | Preserva auditoría | Sobrescribir `status` sin historial |
| D14 | Vigente | Guardar trust score y condición senior al momento de envío | El estado histórico no debe depender del score actual | Recalcular eventos pasados con reputación presente |
| D15 | Vigente | Trust score técnico combina calidad y volumen con techo | Evita scores sin límite | Rating x volumen sin normalizar |
| D16 | Vigente | Valores derivados se calculan en dbt salvo snapshots históricos | Evita duplicidad y contradicción | Persistir cada score derivado en origen |
| D17 | Vigente | Natural keys para seeds; surrogate keys para entidades operativas | Legibilidad en taxonomías y estabilidad en transacciones | Un único estilo de PK |
| D18 | Vigente | `sales_order` en vez de `order` | Evita palabra reservada y quoting innecesario | `order` |
| D19 | Reemplazada por D32 | `listing` única por vendedor + parte + condición | Permitía nueva/usada | Omitía que un vendedor puede tener stock en varias ciudades |
| D20 | Vigente | `manufacture_country` usa ISO 3166-1 alpha-2 | Evita variantes de escritura | País como texto libre |
| D21 | Vigente | `fitment` será sintético inicialmente | No se dispone de fuente pública confirmada para compatibilidad Colombia | Extraer catálogos con licencia sin permiso |
| D22 | Vigente | Servicios como mano de obra, alineación y balanceo fuera del MVP | Mantener foco en repuestos | Modelar servicios completos desde Fase 0 |
| D23 | Vigente | `corrective_repair` y `preventive_maintenance` separados | Tienen triggers y reglas diferentes | Una sola categoría genérica |
| D24 | Reemplazada por D26 | Test inicial reemplazaba historial hasta primera edición revisada | Resolvía arranque en frío | Historial siempre en cero al inicio |
| D25 | Reemplazada por D28 | Senior solo por score >= 50 | Umbral único | Requerir rol empresarial |
| D26 | Vigente | Mezcla gradual entre test e historial | Evita salto abrupto del score | Reemplazo total después de la primera revisión |
| D27 | Vigente | Revisión posterior puede corregir certificación automática | Permite control de calidad y pérdida posterior de condición senior | Certificación automática irreversible |
| D28 | Vigente | Senior por score >= 50 o historial >=50 revisadas y >=90% aprobadas | Permite que comunidad confiable llegue a senior | Renormalización o votos manipulables |

## C. Decisiones añadidas por la revisión integral

| # | Estado | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|---|
| D29 | Vigente; reemplaza D3 | MinIO conserva primero el payload raw inmutable en su formato original; parquet se genera después como representación normalizada | “Raw” debe permitir replay y auditoría sin depender de una interpretación previa del schema | Usar únicamente parquet como raw |
| D30 | Vigente | Identidad unificada en `account` con múltiples roles | Una misma persona o negocio puede comprar, vender y contribuir datos | Tablas `buyer` y `seller` como identidades separadas |
| D31 | Vigente | Separar `catalog_contributor_trust` de `marketplace_reputation` | Miden comportamientos distintos y tienen evidencia diferente | Un único score de reputación para todo |
| D32 | Vigente; reemplaza D19 | Grano de listing = seller + part + condition + location | El mismo vendedor puede tener la misma parte en varias ciudades | Unicidad sin ubicación |
| D33 | Vigente | Modelar negociación con `negotiation` + `offer_event` append-only | Permite ofertas, contraofertas y reconstrucción temporal del estado | Guardar solo “precio final” o una única oferta mutable |
| D34 | Vigente | Frontend, pagos y logística reales quedan fuera del MVP; sus eventos de negocio sí están dentro | Permite construir un data product realista sin desviar el proyecto hacia full-stack | Eliminar órdenes/ofertas del modelo o construir todo el marketplace |
| D35 | Vigente | La fórmula de reputación comercial se difiere; primero se modelan eventos fuente | Evita diseñar un score arbitrario sin datos que permitan probarlo | Inventar una fórmula antes de tener hechos del marketplace |
| D36 | Vigente | Toda ingesta debe tener metadata mínima de procedencia y batch | Habilita debugging, replay, idempotencia y lineage | Cargar filas sin poder rastrear su origen |
| D37 | Vigente | `part_code_edit` usa payload/snapshot para representar cambios multicolumna y creación | `old_value/new_value` no representan una entidad con varios atributos | Una sola pareja de valores para cualquier cambio |
| D38 | Vigente | Geografía se modela como entidad `location`, pero el uso de código DANE se decide tras inspeccionar fuentes oficiales | Evita texto libre inconsistente sin inventar un estándar no validado todavía | Hardcodear ciudades o códigos antes de revisar fuente |
| D39 | Vigente | El proyecto tendrá tests de negocio además de tests de schema | `not_null`/`unique` no detectan reglas semánticas rotas | Limitar calidad a constraints básicas |
| D40 | Vigente | Las fases se definen por capacidad demostrada, no solo por herramienta instalada | El objetivo es aprender Data Engineering, no coleccionar tecnologías | Checklist centrado en “instalar Airflow/dbt/etc.” |
| D41 | Vigente | Una `sales_order` pertenece a un comprador y un vendedor; un checkout multivendedor se divide en órdenes | Mantiene revenue, fulfillment y reviews en un grano comercial inequívoco | Una orden con items de vendedores diferentes y seller implícito |
| D42 | Vigente | `buyer_type` y `seller_type` se guardan en `account_role.role_type`, no en `business_profile` | Las cuentas individuales (por ejemplo `driver`) no tienen perfil comercial pero necesitan clasificación | Clasificación solo en `business_profile` |

## D. Fuentes de datos

| # | Estado | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|---|
| D43 | Vigente (2026-10-09) | Primera fuente de ingesta incremental de EE. UU.: WA DOL "Vehicle Registration Transactions" (`brw6-jymh`, data.wa.gov, Socrata SODA). No reemplaza la fuente de Fase 1 de Colombia (TRM `32sa-8pi3`): se agrega después. | Abierta y sin costo; trae make, model, model_year y ZIP; es mensual (2020-01 a 2026-08, 44.875.179 filas) con llave incremental `start_of_month`; reutiliza el extractor SODA de la TRM. Riesgos por probar: reescritura de meses pasados (lookback + upsert), `make` sin normalizar, cifras como string, licencia ODbL (share-alike si se publica una base derivada). Es FLUJO (transacciones), no STOCK. Ver `09_us_market_research.md`, T2. | FRED (requiere key; poca relación con el dominio), NY `w4pv-hbkt` (STOCK sin columna model, 12,5 M filas), vPIC (dimensión sin llave incremental) |

## E. Decisiones todavía abiertas

Estas no reciben ID hasta ser resueltas:

1. Unidades finales de `quantity_unit`.
2. Normalización geográfica con código DANE desde el MVP o después.
3. Reputación comercial: score único vs score separado como comprador y vendedor.
4. Historial de precio/inventario: Fase 3 base o extensión SCD2.

## F. Cómo agregar una decisión nueva

Formato mínimo:

```text
DXX — Título corto
Estado: vigente / reemplazada
Decisión:
Por qué:
Alternativas consideradas:
Impacto:
Reemplaza a: opcional
```

Una decisión importante debe quedar aquí incluso si también aparece explicada en otro documento.
