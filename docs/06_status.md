# 06 — Estado del proyecto

Última actualización: 2026-10-14
Estado: hito A de marca, proporciones regionales de marca y línea (D135–D140) IMPLEMENTADO en `feat/regional-brand-share` (worktree `C:\dev\pits-app-brand`, base `794c168` = merge del PR #28; commits S1 `03f3bb3`, S2 `b2bb6a8`, S3 `d43f38d`, S4 `2921022`, S5 `2b31a6c` y S6 `8d93f02`); corrida real local del 2026-10-14 con Docker local, no VPS; cierre documental S7 en curso, commit pendiente; revisión final única por `revisor-senior` (D130), commit final, PR en draft y CI no verificados por el documentador; revisión por Henry de las seeds pendiente (§3, §5, §7). Corrección (2026-10-14, reportada por el orquestador): el hito Demanda es PR #28, MERGED el 2026-10-14T15:50:22Z (merge `794c168`); S4 `5c17f5c` y S5 `00a1f90` de ese hito ya existen, lo que corrige el hallazgo B2 de su revisión. Sin merge, CI ni despliegue del hito A verificados por el documentador. Antes: hito Demanda de repuestos con parque RUNT (D131–D134) IMPLEMENTADO en `feat/parts-demand-fleet` (worktree `C:\dev\pits-app-demand`, base `33525d4`, commits S1 `d7a856b`, S2 `9f66676` y S3 `4317f9a`); cierre documental S5 en curso, commit pendiente; revisión final única pendiente (D130), commit final, PR en draft y CI no verificados por el documentador; revisión por Henry del `vehicle_group` del seed pendiente (§3, §5, §7). Corrección (2026-10-14, verificado por el orquestador con `gh pr list`): PR #27 está MERGED (2026-10-13T19:06:03Z, merge `33525d4` en `main`); donde esta línea o §1 dicen "PR #27 en draft", se leen como históricos. Antes: hito C, DANE/DIVIPOLA (D121–D130) IMPLEMENTADO en `feat/dane-divipola` (worktree `C:\dev\pits-app-dane`, rebasada sobre `main` `497d0e3`, que ya incluye el playbook `10`); cierre documental S7 en curso (commit pendiente); PR #27 en draft; revisión final única pendiente (D130). Sin merge, CI ni despliegue verificados por el documentador (§3, §5, §7). Antes: hito Fase 5, CI completo (D112–D116) IMPLEMENTADO en `feat/ci-contract` (worktree `C:\dev\pits-app-ci`, base `main` `e4f160f`, que ya incluye el hito B). Cierre documental S6 en curso (§3). PR #25 en draft. Run 38420161592 (`pull_request`, HEAD `96c5651`) con 4 jobs en verde, verificado por el revisor. Sin merge ni required checks verificados por el documentador; el run 38419204583 sobre `7a4d3b8` es anterior y lo reportó el orquestador. Antes: hito Aislamiento de listeners de SeaweedFS (D117–D120) IMPLEMENTADO en `feat/seaweedfs-listener-isolation` (worktree `C:\dev\pits-app-swiso`; commits P1 `9c959e9`, P2 `4b8e7e9` y P3 `23799d7`, HEAD `23799d7` antes de este cierre). P4 es este cierre documental, con commit pendiente de revisión independiente. Sin merge, CI ni despliegue verificados por el documentador (§3, §5). Antes: hito Endurecimiento y optimización (D104–D111) IMPLEMENTADO en `feat/hardening-optimization` (worktree `C:\dev\pits-app-hardening`), apilado sobre `feat/runt-fleet-snapshot` (PR #20, mergeado en `main` como `9ab6893`). Henry resolvió los pendientes del hito (2026-10-13, literal: "merged, acepto tus recomendaciones, sigue"): pendiente 1 APROBADO (limitación de D104(c): el admin borra con DeleteObjects) y pendiente 2 DIFERIDO (filer y master sin autenticación en la red Docker; requiere una D propia antes del VPS). El PR de este hito ya no está bloqueado por pendientes de Henry (§3, §5, §7). Sin merge, CI ni despliegue verificados por el documentador. Antes: hito Fase 1b, parque automotor RUNT `u3vn-bdcy` (D96–D103) IMPLEMENTADO en `feat/runt-fleet-snapshot` (worktree `C:\dev\pits-app-runt`), sobre base `49493ff` (merge del PR #19, 2026-10-12 21:08 UTC); S1–S6 implementados y revisados (commits `7ed71db`, `b0e52c8`, `ad2ece5`, `9a761d8`, `e7a57a0`, `0d748a3`); S7 es este cierre documental (commit pendiente). Pendiente: revisión final del diff completo por `revisor-senior` contra `49493ff`, commit final, PR, CI y merge (§3, §5, §7). Sin merge, CI ni despliegue verificados por el documentador. Antes: hito Fase 4, orquestación con Airflow (D89–D95) IMPLEMENTADO en `feat/airflow-trm` (worktree `C:\dev\pits-app-airflow`), sobre base `b74e8c0` (merge del PR #18, mergeado 2026-10-12 14:35 UTC; el hito dbt quedó en ese PR); S1–S6 implementados y revisados (puntajes finales 94–96); S7 es este cierre documental. Pendiente: revisión final del diff completo por `revisor-senior` contra `b74e8c0`, commit final, PR, CI y merge (§3, §5, §7). Sin merge, CI ni despliegue verificados por el documentador. Antes: hito dbt sobre `landing.fx_rate` (D78, D85–D88) IMPLEMENTADO en `feat/dbt-fx-rate` (worktree `C:\dev\pits-app-dbt`), sobre `main` `2980760`; pasos S1–S5 implementados y revisados por el revisor (puntajes 9,3–9,5); corrida real OK el 2026-10-11 (§3). Revisión independiente del diff completo por `revisor-senior` (2026-10-12): vuelta 1 CAMBIOS 9,2/10, solo docs, corregidos en S6. Pendiente: re-revisión, commit final, PR, CI y merge (§3, §5, §7). Sin merge ni CI verificados por el documentador; no hay siguiente hito iniciado (§5). Antes: hito loader fx_rate a Postgres (Fase 3, D78–D84) IMPLEMENTADO en `feat/fx-rate-loader` (worktree `C:\dev\pits-app-load`), apilado sobre `feat/trm-normalize` (base `d89d997`, según el plan); pasos S1–S7 implementados, revisados y commiteados; corrida real contra `pits_warehouse` OK el 2026-10-11 (§3). Pendiente: PR, CI y merge. Antes: hito TRM normalize IMPLEMENTADO en `feat/trm-normalize` (worktree `C:\dev\pits-app-trm`), apilado sobre `chore/agents-preflight` (PR #14); pendiente de PR, revisión independiente del diff y commit final; plan aprobado por Henry el 2026-10-11 (D74–D77). Sin merge ni CI verificados. PR #12 (extractor TRM) y PR #13 (alineación de alcance D68–D73) mergeados en `main`, verificados con `gh pr view` en esta sesión. Ajustes de agentes y `/orquestar` de D73 con plan específico aprobado; entregados en PR desde `chore/agents-preflight` (base `origin/main` `d1d867f`), pendiente de merge (§1-ter). Siguiente paso sugerido: dbt sobre `landing.fx_rate` (hito siguiente según D78), sin fecha; no iniciado (§5).

Histórico de hitos anteriores (evidencia conservada, no reejecutada aquí): D68–D73 aprobadas por Henry el 2026-10-10 y registradas en `05` (v12); `01` v4, `03` v10, `04` v6 alineados; alcance vigente en §1-bis. Antes: paso 3 de Fase 1 (extractor TRM) implementado en PR, con evidencia de corrida real; D64–D67 aprobadas por Henry el 2026-10-10 y registradas en `05` (v11). Antes: paso 2 de Fase 1 (storage y Postgres locales, perfil `core`) CERRADO en PR; D60–D63 aprobadas por Henry el 2026-10-10 y registradas en `05` (v10). Antes: D57 (storage SeaweedFS, memoria M1 768m, inmutabilidad opción A), D58 (marker `contract`) y D59 (demanda solo `ACTIVO`) aprobadas por Henry el 2026-10-10 y registradas en `05` (v9). Antes: spike de storage SeaweedFS 4.48 completado en la rama `spike/seaweedfs` (`docs/spikes/seaweedfs.md`; 14/14 tests de contrato y 30 offline); Fase 1 paso 1 cerrado (D49). Antes: spike planeado y bloqueo de storage (sin evidencia); segunda ronda regional y D52–D56 (calibración del parque con Boyacá y Risaralda, marca primero, servicio público aparte, alcance de la demanda). Antes: D50 y D51; Fase 0.5 y D43–D48 (D47 grano de `fx_rate`; D48 demanda con parque RUNT, marca/modelo sintético).

Este archivo se actualiza al final de cada sesión y funciona como punto de partida para una conversación nueva.

## 1. Fase actual

Hito A de marca, proporciones regionales de marca y línea (D135–D140): IMPLEMENTADO en la rama `feat/regional-brand-share`; cierre documental S7 en curso, pendiente de la revisión final única (D130), commit, PR en draft y CI (§3, §5, §7). Antes: hito Demanda de repuestos con parque RUNT (D131–D134): IMPLEMENTADO en la rama `feat/parts-demand-fleet`; cierre documental S5 en curso, pendiente de la revisión final única (D130), commit, PR en draft y CI (§3, §5, §7). Corrección 2026-10-14: PR #27 MERGED (merge `33525d4`). Antes: Hito C, DANE/DIVIPOLA (D121–D130): IMPLEMENTADO en la rama `feat/dane-divipola`; cierre documental S7 en curso, pendiente de la revisión final única del diff (D130), commit, PR #27 (draft) y CI (§3, §5, §7). Antes: Hito Fase 5, CI completo (D112–D116): IMPLEMENTADO en la rama `feat/ci-contract`; cierre documental S6 en curso, pendiente de revisión independiente, commit, PR y required checks (§3, §5, §7). Antes: hito de aislamiento de listeners de SeaweedFS (D117–D120): IMPLEMENTADO en la rama `feat/seaweedfs-listener-isolation`; cierre documental P4 en curso, pendiente de revisión independiente, commit, PR, CI y merge (§3, §5). Antes: hito de endurecimiento y optimización (D104–D111): IMPLEMENTADO en la rama `feat/hardening-optimization`; Henry aprobó el pendiente 1 y difirió el pendiente 2 (2026-10-13); el PR ya no está bloqueado por pendientes de Henry (§3, §7). Antes: **Fase actual: Fase 1b (parque automotor RUNT `u3vn-bdcy`, D96–D103)**: hito IMPLEMENTADO en `feat/runt-fleet-snapshot`, pendiente de revisión final, PR, CI y merge (§3); siguiente paso sin elegir, lo decide Henry (§5). Antes: **Fase 4 (orquestación)**: hito Airflow (D89–D95) IMPLEMENTADO en `feat/airflow-trm`, pendiente de revisión final, PR, CI y merge (§3); siguiente paso sin elegir, lo decide Henry (§5). Antes: **Fase actual: Fase 1 — primera ingesta real: EN CURSO (pasos 1, 2 y 3 implementados: D49, D60–D63 y D64–D67; paso 3 mergeado en PR #12; hito TRM normalize implementado en PR, D74–D77, §3 y §5; hito loader fx_rate (Fase 3, D78–D84) implementado en la rama, §3 y §5; hito dbt sobre `landing.fx_rate` (D85–D88) implementado en la rama, §3; siguiente paso sin elegir: Fase 4 (Airflow, D40) o Metabase sobre `marts.fct_fx_rate_daily`, lo decide Henry, §5).**

Fase 0.5 — investigación de mercado y validación de fuentes: CERRADA, con brechas documentadas.

Brechas (ver `08_market_research.md`, "No encontrado"):

- Parque por marca a nivel nacional: no encontrado. `u3vn-bdcy` trae clase, servicio, estado, departamento y municipio, pero no `marca`.
- Parque por marca a nivel subnacional: parcial. Boyacá y Risaralda sirven de calibración (D52, D55); el resto tiene datos viejos o sin cobertura (§3, "Investigación regional").
- Ensamble de carros (Chevrolet, Renault y otras): sin evidencia con fuente oficial.
- Cifras de ANDI-FENALCO leídas por resumen automático; nadie abrió el PDF original (`08_market_research.md`, método y "No encontrado"). Verificar antes de publicar.

Objetivo de la Fase 1: primera ingesta real (`source -> raw SeaweedFS (D57) -> manifest -> parser/normalizer -> tests`).

Paso 1 (esqueleto Python) cerrado (D49): hay `pyproject.toml`, `uv.lock`, paquete `pits` (src layout), CLI `pits` (`--help`, `version`), 7 tests y CI mínimo en `.github/workflows/ci.yml`. Paso 2 cerrado (en PR): `docker-compose.yml` (perfil `core`), `pits storage init` y bucket `pits-raw` (ver §3).

## 1-bis. Alcance vigente (D68–D73, 2026-10-10)

Aprobado por Henry el 2026-10-10 (literal: "Aprobado, implementa cambios del prompt"). Fuente: `05` §D68–D73; cita de visión en D68. No cambia la fase actual (§1).

**Qué está aprobado:**

- **Tres productos en un repo** (D68): (1) plataforma de datos, la base actual con las fases de `01` §10 (D40); (2) marketplace web de autopartes para Colombia y EE. UU. (D71); (3) app de gestión de talleres pequeños, solo Colombia, con facturación electrónica (D68, D69, D72). Cada producto avanza por hitos aprobados uno a uno.
- **Warehouse analítico** (D68, D70): no procesa checkout, reservas de inventario ni emisión fiscal. Las apps tienen base OLTP propia, separada del warehouse por base y rol (en local puede ser la misma instancia, sin aislamiento de CPU/I/O). Ninguna app escribe en el warehouse ni lo lee para operar. Los hechos llegan por outbox transaccional y export al raw con manifest (al menos una vez; dedupe por `event_id`; no exactly-once). Airflow orquesta datos; un worker operacional maneja facturas y webhooks.
- **Mercados domésticos separados** (D71): Colombia y EE. UU. con moneda, impuestos, políticas y vendedores propios por mercado; catálogo compartible; sin cross-border en el MVP.
- **Taller** (D69): mano de obra y servicios entran como entidades operativas nuevas (orden de servicio y sus líneas), con diseño en hito propio. Marketplace sin servicios. `repair_job`/`repair_job_part` siguen siendo conocimiento técnico (`03` §15-16).
- **Identidad de apps** (D72): `user` (autenticación) y tenant con `membership`; `account` sigue siendo la identidad comercial del marketplace; toda fila privada del taller lleva `tenant_id` y se autoriza en el servidor.
- **Proceso** (D73): D45 confirmado (dentro de un plan aprobado, los agentes hacen commits, push y PR sin pedir permiso; Henry aprueba plan y PR; `CLAUDE.md` alineado en este hito por instrucción de Henry). Al reemplazar o ajustar una decisión, en la fila vieja solo se edita Estado. El ajuste de `/orquestar` con preflight/worktree se aplicó localmente con plan específico aprobado; ver §1-ter.
- **Reemplazos**: D22 → "Reemplazada por D69 para el producto taller"; D34 → "Reemplazada parcialmente por D68 (frontend)". Ajustes de Estado: D2 y D60 (D70), D30 (D72), D46 (D71). Pagos y logística reales siguen fuera hasta decisión propia.

**Qué NO está aprobado** (no se implementa sin decisión propia):

- Stack de las apps: FastAPI, SQLAlchemy/Alembic, Next.js u otros son ejemplos de D70, no decisiones.
- Orden comercial del MVP (taller frente a marketplace) y si el marketplace captura lead o procesa checkout.
- Detalles de dominio: definición de tenant, autos y motos por país, política de compatibilidad visible, servicios de taller en detalle.
- Proveedor fiscal y proveedor de pagos.
- Cualquier app o compose nuevo: este hito es solo documental.

**Preguntas abiertas** (`05` §F, puntos 6 a 15, sin ID hasta resolver): stack de apps; proveedor fiscal y de pagos; retención de datos personales y fiscales frente a D61; política de compatibilidad visible frente a D21; prioridad comercial del MVP; marketplace lead frente a checkout; autos y motos por país; definición de tenant (D72); "Solo COP y USD" en `fx_rate`; clientes oficiales en el taller frente a D56.

**Aplicado por instrucción de Henry ("aplica todos los cambios y sigue", 2026-10-10):** Estado de D2 y D60 → ajustada por D70; D30 → ajustada por D72; D46 → ajustada por D71 (D73(b)). `CLAUDE.md` alineado: título, Proyecto, regla 4 (D73(b)), línea de 01, línea de 09 (tracks) y línea de Agentes (D45, D73(a)).

## 1-ter. Agentes y orquestación — ajuste local (D45, D73)

Plan específico aprobado por Henry en esta sesión (literal: "Aprobado: aplicar y verificar los ajustes"). El arquitecto de Claude propuso el plan y el documentador propuso el cierre en invocaciones separadas de solo lectura; Hermes aplicó los patches. No se atribuye esta implementación al subagente implementador.

- Aplicado en los cuatro agentes y `/orquestar`: alcance de tres productos; preflight de Git/concurrencia; checkout/worktree acordado antes de cambiar rama; contratos de entrada/handoff por paso; auto-fix limitado a archivos propios; críticas/altas bloqueantes; revisión independiente del diff completo después de documentar; preservación del contenido anterior, no solo conteos.
- Se conservaron `name`, `tools` y `model`: arquitecto/revisor `inherit`, implementador `sonnet`, documentador `haiku`. No hay quinto agente, permisos nuevos, stack nuevo ni D74. `05` permanece íntegro con 73 IDs únicos; las 88 lecciones previas se conservan y se añade la 89.
- Los límites de solo lectura del revisor son instrucciones, no un sandbox: conserva Bash. El documentador no tiene Write; creación de archivos o cambios fuera de docs/ vuelven al orquestador/implementador. Este hito no amplía herramientas para resolverlo.
- Evidencia ejecutada por Hermes en esta sesión: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format .`, `uv run ruff format --check .`, `uv run pytest -q` y `git diff --check`, todos exit 0. Ruff informó `55 files left unchanged`; no son todos Python: `format --check --verbose .` confirmó que también recorre Markdown, incluidos los archivos de `.hermes/` presentes en esa corrida (dos entonces; hoy hay tres). No hubo snapshot previo de esos untracked para una comparación independiente; no se afirma preservación byte a byte de ellos, aunque Ruff reportó cero cambios. Pytest: 296 passed, 28 deselected (contrato S3 excluido). Comprobación programática: frontmatter y modelos/tools conservados; 73 decisiones y las 88 lecciones previas sin cambios.
- Consulta de GitHub ejecutada en esta sesión: [PR #12](https://github.com/henrymarinho90/pits-app/pull/12) MERGED (`mergedAt` 2026-10-11T03:07:34Z); [PR #13](https://github.com/henrymarinho90/pits-app/pull/13) MERGED (`mergedAt` 2026-10-11T03:16:04Z), check `ci` SUCCESS. Ese CI es del PR #13, no de este diff local.
- Revisión independiente de Claude, vuelta 1: CAMBIOS (89/100); detectó la atribución incorrecta de los 55 archivos a Python y la comparación contra Git exigida al documentador sin Bash. Hermes corrigió ambos puntos. El revisor ejecutó `uv sync --locked`, Ruff check/format --check y pytest (296 passed, 28 deselected), todos exit 0. Las correcciones requieren una nueva revisión del diff completo; su veredicto se adjunta a la entrega, no se autoasigna aquí. Vuelta 2: APROBADO 92/100 con 3 hallazgos bajos, corregidos; el diff final se revisa de nuevo antes del commit.
- Preflight ejercitado con `/orquestar` en una invocación nueva: primer intento con reglas Bash acotadas denegado (no cuenta como validación); segundo intento con Bash habilitado solo para esa invocación ejecutó `git status --porcelain`, `git branch --show-current`, `git log -1 --oneline` y `git worktree list`, todos exit 0. Confirmó los siete archivos modificados y `.hermes/` untracked, bloqueó cambio de rama y pidió acuerdo de checkout/concurrencia. No se cambió configuración de permisos del proyecto.
- No se ejecutó un ciclo `/orquestar` completo de implementación/commits/PR, ni tests S3, Docker, VPS o despliegue. Las corridas de infraestructura de §3 son históricas, no evidencia de este ajuste.
- Entrega: Henry aprobó entregarlo por PR separado (2026-10-11, "Aprobado todo, continua e implementa"); el checkout pasó a la rama `chore/agents-preflight` (base `origin/main` `d1d867f`) con `git switch -c`, sin stash/reset; número de PR y estado de CI se citan en la entrega; `.hermes/` queda fuera de alcance, sin edición deliberada (con la salvedad de Ruff anterior). Los cambios requieren una invocación nueva de Claude; no se presume recarga en sesiones abiertas.

## 2. Documentación vigente

| Archivo | Versión/estado |
|---|---|
| `00_review_findings.md` | "Auditoría de consistencia" v1.3 (2026-10-10; R1–R3 resueltos por D47 y D48, R6 por D49, R2 renombrada por D51; la original nunca se versionó) |
| `01_project_brief.md` | v4 (2026-10-10); tres productos, mercados por país, fuera de alcance reformulado, diagrama OLTP/outbox/raw (D68–D71); SeaweedFS (D57) |
| `02_domain_taxonomy.md` | v13 (2026-10-10); nota en §17 sobre frontend (D68); `fleet_operator` (D54) |
| `03_data_model.md` | v17 (2026-10-14); linaje regional de marca y línea en §3, calibración regional, grano, fórmula pooled, `sample_size_ok` y límites en §27, y conservación del scope regional en §30 (D135–D140, hito A de marca); v16 (2026-10-14); demanda de repuestos por parque en §27 (linaje, grano, métrica y límites) y conservación real en §30 (D131–D134, hito Demanda); v15 (2026-10-13); geografía DANE en §27 (`marts.dim_municipality`, mapa y fct DANE; D121–D128, hito DANE/DIVIPOLA), §17 y pregunta 2 de §I resueltas; v14 (2026-10-12); linaje de `vehicle_fleet_snapshot` en §3 y nota de implementación en §27 (D96–D103, Fase 1b); municipio de matrícula; v13 (2026-10-11); linaje dbt de `fx_rate` en §3 y §26 (D85–D88); v12 (2026-10-11); linaje de `landing.fx_rate` en §3 y tabla en §26 (D79–D82); v11 (2026-10-11); nota de implementación de `fx_rate` para la TRM en §26 (D77, D76); v10 (2026-10-10); §1 aclara modelo fuente/analítico frente a OLTP (D70, D72); mapeo del manifest en §3 (D65, D66); `vehicle_registration_stat` renombrada a `vehicle_fleet_snapshot` (D51); desglose por servicio y marca primero (D52–D56); filtro `ACTIVO` (D59) |
| `04_infra.md` | v16 (2026-10-14); migración 0006 y tabla `landing.regional_fleet_brand_count` en §8.3, y nota de marca regional sin DAG en §10.1 (D135–D138, hito A de marca); v15 (2026-10-13); migración 0005 en §8.3, medición del scheduler con `divipola_snapshot` en §9 y DAG `divipola_snapshot` en §10.1 (D121–D130, hito DANE/DIVIPOLA); v14 (2026-10-13); jobs `pg` y `contract` del CI en §8.4 y revisión de `-volume.max` y disco en §15 (D112–D116, hito Fase 5); v13 (2026-10-13); listeners y `security.toml` de SeaweedFS en §8.1.1, riesgo del filer CERRADO en §11 y checklist en §15 (D117–D120, hito Aislamiento); v12 (2026-10-13); identidades y bucket policy en §8.1.1, medición de D111 y dbt (D110) en §9, DAG `airflow_log_retention` en §10.1, secretos S3 y riesgo del filer en §11, retención de logs y escaneo en §13 (D104–D111, hito Endurecimiento); v11 (2026-10-12/13); medición de Postgres y del scheduler con `runt_fleet_snapshot` en §9, segundo DAG en §10.1 y volúmenes y disco en §14 (D96–D103, Fase 1b); v10 (2026-10-12); orquestación con Airflow en §9 (medición), §10.1 (perfil `orchestration` y los dos archivos de compose, D95), §11 (secretos y riesgos) y §13 (logs), D89–D95; v9 (2026-10-11); rol `pits_transformer`, matriz, `profiles.yml`, dependencias dbt y `.venv` en §8.3–§8.4, §9 y §11 (D85–D88); v8 (2026-10-11); PostgreSQL del warehouse en §8.3, medición de memoria de Postgres en §9, notas de roles y log en §11 y §13 (D79–D82); v7 (2026-10-11); zona `pits-normalized` en §8.2 (D74, D75, D76); v6 (2026-10-10); nota OLTP/warehouse en §7 y §8.3 (D70), sin cambios de compose; §8.1 con el contrato del batch raw (D65); perfil `core` (D60–D63); GOMEMLIMIT SeaweedFS 500MiB (D63); bucket `pits-raw` (D61) |
| `05_decisions_log.md` | v23 (2026-10-14); D1–D140 (D135–D140, hito A de marca, aprobadas 2026-10-14, sección E-8; Estado de D55 ajustado por D140 y §F punto 5 resuelto; D141 es la siguiente libre); v22 (2026-10-14); D1–D134 (D131–D134, hito Demanda de repuestos con parque RUNT, aprobadas 2026-10-14, sección E-7; D135 no existe y la siguiente libre es D135; sin filas existentes ni celdas Estado editadas); v21 (2026-10-13); D1–D130 (D121–D130, hito DANE/DIVIPOLA, sección E-6, aprobadas 2026-10-13; sin filas existentes ni celdas Estado editadas; §F punto 2 resuelto); v20 (2026-10-13); D1–D120 (D112–D116, hito Fase 5, sección E-5); v19 (2026-10-13); D1–D111 y D117–D120 (D117–D120 hito Aislamiento de listeners, aprobadas 2026-10-13, sección E-4; Estado de D57 ajustado por D117; D73(b)); v18 (2026-10-13); D1–D111 (D104–D111 hito Endurecimiento, aprobadas 2026-10-13, sección E-3; D104(c) con limitación pendiente de Henry; Estado de D57, D62, D64, D66, D67, D89, D95 y D102 ajustado; D73(b)); v17 (2026-10-12); D1–D103 (D96–D103 hito Fase 1b, aprobadas 2026-10-12, sección E-2; Estado de D74 por D98, de D79 y D81 por D99, de D88 y D92 por D101; D73(b)); v16 (2026-10-12); D1–D95 (D89–D95 hito Fase 4, Airflow, aprobadas 2026-10-12; Estado de D79 ajustado por D91, D80 por D90, D82 por D90, D85 por D91 y D88 por D90 y D91, D73(b)); v15 (2026-10-11); D1–D88 (D85–D88 hito dbt, aprobadas 2026-10-11; Estado de D79 y D80 ajustado por D86 y de D49 por D88); v14 (2026-10-11); D1–D84 (D78–D84 hito loader fx_rate, aprobadas 2026-10-11; Estado de D74 ajustado por D79); v13 (2026-10-11); D1–D77 (D74–D77 hito TRM normalize, aprobadas 2026-10-11; Estado de D62 y D65 ajustado por D75); v12 (2026-10-10); D1–D73 (D68–D73 alineación de alcance, aprobadas 2026-10-10); celdas Estado de D2, D22, D30, D34, D46 y D60 actualizadas (D73(b)); D60–D63 y D64–D67 aprobadas 2026-10-10 |
| `spikes/seaweedfs.md` | spike SeaweedFS 4.48 (2026-10-10), mergeado en `main` (PR #9); incluye los borradores D57 y D58 (aprobados; ver `05`) |
| `06_status.md` | vigente (2026-10-14) |
| `07_lessons_learned.md` | vigente, sin versión; lecciones 1–168 (164–168 del hito A de marca, 2026-10-14; 158–163 del hito Demanda de repuestos con parque RUNT, 2026-10-14; 152–157 del hito DANE/DIVIPOLA, 2026-10-13; 142–151 del hito Fase 5, 2026-10-13; 136–141 del hito Aislamiento de listeners, 2026-10-13; 128–135 del hito Endurecimiento, 2026-10-13; 118–127 del hito Fase 1b, 2026-10-12/13; 106–117 del hito Airflow, 2026-10-12; 102–105 del hito dbt, 2026-10-11; 96–101 del hito loader fx_rate, 2026-10-11) |
| `08_market_research.md` | Ficha 9 (Boyacá `em3d-hmim` y Risaralda `x9pp-pcn5`, verificada por API el 2026-10-14; hito A de marca); corrección del 2026-10-12 del corte vigente de `u3vn-bdcy` (OCTUBRE 2026, Ficha 1; citas de AGOSTO 2026 marcadas como superadas); fechas de consulta 2026-10-03 (antes `claude_08_market_research.md`) |
| `09_us_market_research.md` | tercera ronda, 2026-10-09 (antes `claude_09_us_market_research.md`) |
| `10_next_project_playbook.md` | v1 (2026-10-13; regla 1 del TL;DR y §3.1 citan D130 en el hito DANE/DIVIPOLA, las excepciones por paso siguen como Inferencia pendiente); playbook para el próximo proyecto a partir de las lecciones 1–151 y D1–D120 |
| `research/parque_por_marca.md` | investigación 2026-10-10 (D50); sección 7 (2026-10-14): comparación con la corrida regional real (diferencia AUTECO y participaciones pooled; no es dato nacional); segunda ronda 2026-10-10, sección "Segunda ronda" (base de D52 y D55) |

## 3. Terminado

### Fase 0 (dominio y arquitectura conceptual)

- Visión del proyecto como data platform para un marketplace simulado; alcance de producto separado de UI/pagos.
- Taxonomía de partes y vehículos; confianza de contributor y reputación comercial separadas; identidad unificada `account` + roles.
- Modelo de publicaciones, búsquedas, negociaciones, ofertas, órdenes y reseñas; ERD conceptual.
- Convenciones de procedencia e ingesta; raw como payload inmutable antes de parquet (D29).
- Infraestructura local/producción documentada, con reglas mínimas de backups, secrets, healthchecks y límites.

### Fase 0.5 (investigación de fuentes)

- `08_market_research.md` con fichas de datasets, hipótesis validadas/refutadas y lista de "No encontrado".
- D43 (WA DOL como primera fuente de EE. UU., se agrega después de la de Colombia) y D46 (orden de fuentes de Fase 1).
- `09_us_market_research.md`: comparación EE. UU. vs Colombia.
- Flujo de trabajo con agentes: D44 y D45.

### Orden de fuentes (D46, D43)

1. Fase 1: TRM Superfinanciera `32sa-8pi3`.
2. Fase 1b: parque RUNT `u3vn-bdcy`, snapshot mensual.
3. Después: WA DOL `brw6-jymh` (D43).

Justificación por ruta crítica: RUNT va antes que WA DOL porque es parque (STOCK) de Colombia, el mercado principal, y aplica la regla demanda = parque. WA DOL es FLUJO (transacciones) y de EE. UU.

La TRM tiene relevancia de dominio secundaria: los precios del marketplace se fijan primero en COP (confirmado por Henry; ajustado por D71: cada mercado en su moneda, COP en Colombia y USD en EE. UU.). Sirve como referencia de costo de importación (Inferencia, `08_market_research.md`). Se elige primero por ingeniería: ejercita el patrón raw -> manifest -> parser sin el ruido del dominio.

### Fase 1, paso 1: esqueleto Python (D49)

- `pyproject.toml` y `uv.lock`; paquete `pits` (src layout); CLI Typer `pits` con `--help` y `version`.
- 7 tests pytest; `ruff check` y `ruff format` en verde.
- Demostrado: `uv sync --locked`; `uv run pits version` → 0.1.0 (Windows); CI verde en GitHub Actions (`.github/workflows/ci.yml`, `setup-uv` fijado a `@v10.3.0`; PR #5).
- Atiende R6 de `00_review_findings.md`: CI mínimo en Fase 1. El CI completo (`dbt build`) sigue en Fase 5 (D40).

### Fase 1, paso 2: storage y Postgres locales (D57, D60–D63; en PR)

- `docker-compose.yml` (`name: pits`, perfil `core`): SeaweedFS 4.48 (`server -s3`, `127.0.0.1:8333`, `GOMEMLIMIT` 500MiB, `mem_limit` = `memswap_limit` 768m) y Postgres 17.11 Debian con digest fijo (`127.0.0.1:${POSTGRES_HOST_PORT:-5433}`, `mem_limit` = `memswap_limit` 1g, `shm_size` 256m, initdb con `C.UTF-8` builtin). `docker-compose.spike.yml` sin cambios.
- Memoria (D63): 3/3 corridas `-m contract` verdes, sin OOM. Picos `memory.peak` 526,1 / 513,4 / 538,0 MiB frente a un límite de 684510412 B (85 % de 768 MiB). Con GOMEMLIMIT 600MiB la corrida 2 dio 86 % (criterio no cumplido). Postgres: lectura puntual de `memory.current` = 130818048 B (~125 MiB) tras el primer up, 2026-10-10; sin log guardado.
- Bucket `pits-raw` con versioning y sin Object Lock (D61): `pits storage init` dos veces, primero created=true/changed=true y después created=false/changed=false.
- Write-once (D62): `tests/contract/test_conditional_put_contract.py` con `IfNoneMatch="*"`: 2.º put → 412, contenido intacto, 1 versión.
- Tests: offline (`uv run pytest -q`) con `botocore.stub.Stubber` para `load_storage_settings` y `ensure_raw_bucket`, y CLI `pits storage init` con `CliRunner`. Contrato: `uv run --env-file .env pytest -m contract -q`.
- Cierre del plan (paso 7, 2026-10-10): `ruff check` y `ruff format --check` OK, `pytest -q` 90 passed (22 contract deselected); `docker compose down` sin `-v` (volúmenes `pits_postgres_data`, `pits_seaweedfs_data` y `pits_spike_seaweedfs_data` conservados).

### Fase 1, paso 3: extractor TRM (D64–D67; mergeado en PR #12)

- Código: cliente SODA con reintentos y timeouts (`src/pits/sources/soda/`, D64); raw store write-once y manifest v1 (`src/pits/ingestion/`, D65); extractor de la TRM (`src/pits/sources/trm/`, D66); CLI `pits extract trm`. Tests offline con `httpx.MockTransport` y `MemoryRawStore`; contrato contra SeaweedFS (`tests/contract`).
- `CLAUDE.md` (Stack) ya dice SeaweedFS; lo editó Henry y se comitea en este PR.
- Corrida real del 2026-10-11 UTC contra datos.gov.co, con SeaweedFS local:
  - 1.ª corrida (sin batch previo; `incremental` se registra como `mode=full`): 8.365 filas, 9 archivos `payload-*.json`, 1.001.892 bytes (≈ 0,96 MiB), watermark hasta 2026-10-10, 5,5 s.
  - 2.ª corrida (incremental): 0 filas; arrastra el watermark (2026-10-10), 1,7 s.
- Tests: `uv run --env-file .env pytest -m contract` 28 passed; `uv run pytest -q` 296 passed.
- Memoria (criterio D63, `scripts/measure_storage_memory.sh`, `memory.peak` del contenedor SeaweedFS): 3/3 corridas `-m contract` (26 tests; medidas antes de añadir los 2 últimos tests de contrato de TRM) con picos 499,8 / 515,6 / 515,8 MiB (524120064 / 540663808 / 540880896 B), frente a 652,8 MiB (684510412 B = 85 % de 768 MiB). Sin OOM.
- Cómo reejecutar (D66):
  - `uv run --env-file .env pits extract trm`: incremental desde el watermark (`vigenciadesde > watermark`, sin relectura). Sin batch committed, hace backfill completo desde 1991-12-02 y lo registra como `mode=full`; la salida imprime el modo efectivo.
  - `--full`: recarga todo el dataset.
  - `--since YYYY-MM-DD`: recarga desde esa fecha inclusive. Si deja un hueco respecto al watermark (más de un día después), sale con exit 2.
  - Cada corrida crea un batch nuevo (`batch_id` uuid4). Nunca sobrescribe batches previos; un batch sin `manifest.json` es huérfano y se ignora.
  - Las fechas (`extraction_date`, `started_at`, `finished_at`) van en UTC. `extraction_date` es la fecha UTC de `started_at`.
- Exit codes: 0 committed; 1 error permanente o de configuración (esquema cambiado, manifest corrupto, 412 de escritura); 2 uso (`--full` con `--since`, fecha inválida, `--since` con hueco); 3 transitorio, seguro reintentar (red, 429/5xx tras 4 intentos, dataset reemplazado durante la corrida, dataset vacío en `--full`).
- Salida: `batch_id=… mode=… rows=… files=… watermark_from=… watermark_to=… manifest=s3://pits-raw/…/manifest.json`. Errores en stderr como `error: …`; el token nunca se imprime.
- Limitaciones aceptadas (detalle en `05`): 412 ambiguo tras un reintento (D65); correcciones a TRMs ya cargadas no se capturan sin `--full` o `--since` (D66).

### Fase 1, hito TRM normalize (D74–D77; implementado en PR, pendiente de merge)

Procedencia: la evidencia de esta sección la reportó el orquestador en la sesión del 2026-10-11 (commits, tests y corridas). El documentador no reejecutó tests, Docker ni la CLI. La comparación independiente contra `base_commit` la hace el revisor-senior, no este documento.

- Alcance (plan aprobado 2026-10-11, literal: "Aprobado todo, continua e implementa"): normalizer TRM a `fx_rate` (D47) con replay desde raw (D76), verificación de bytes ante 412 (D75) y zona `pits-normalized` (D74). Sin loader a Postgres, dbt, Airflow, parquet ni apps.
- Commits de implementación: S1 `d9021e1`, S2 `36c0d4e`, S3 `2d80eea`, S4 `3c4310e`, S5 `0f52904` y S6 `66a1ae6`. S7 es el commit de documentación de este paso.
- Tests (reportados, 2026-10-11): offline `uv run pytest -q` 503 passed. Contrato `uv run --env-file .env pytest -m contract`: suite completa 36 passed, repetida tras la vuelta 2 de S6 y verificada por el revisor (2026-10-11).
- Memoria (criterio D63, 3/3 corridas con la suite contract): picos `memory.peak` 554,5 / 505,0 / 503,9 MiB (581464064 / 529494016 / 528343040 B), frente a 652,8 MiB (684510412 B = 85 % de 768 MiB). Máximo 554,5 MiB, sin OOM. Medición hecha antes de la vuelta 2 de S6 (533 tests; ahora 539); la vuelta 2 no tocó la ruta de datos.
- Corrida real (2026-10-11, SeaweedFS local, datos de datos.gov.co):
  - `pits storage init` creó `pits-normalized`.
  - `pits normalize trm`: `outcome=created`, `rows=12735`, `coverage=1991-12-02..2026-10-13`, `inputs=2`, `fingerprint=caa8bc5c31305114109a5a793ad3ec833d1285e8684897260047306c92d6c268`.
  - 2.ª corrida: `already_present`, con el mismo fingerprint y sin escrituras nuevas.
  - Aviso D76(f): el rango de vigencia de 6 días superó el umbral de 5 días. Es aviso en stderr, no error. El diseño se basó en un rango de 4 días (2026-10-10 a 2026-10-13, API consultada el 2026-10-11). Pendiente de decisión de Henry (§7).
- Decisiones de implementación: documentadas en `03` §26 (`row_count` del manifest raw del batch = registros leídos de sus páginas; orden estricto entre páginas; fila fuera del watermark = error; formato de valor ASCII `[0-9]+(\.[0-9]+)?`; `since` vacío que borra la cola = `CoverageError`) y en `04` §8.2 (zona normalized; BotoCoreError o 5xx al verificar el bucket = exit 3; `S3_NORMALIZED_BUCKET` validado también por `pits extract`).
- Riesgo D65 (412 ambiguo): cerrado por D75. Ante 412, `put_once` compara sha256 y longitud; con bytes idénticos el resultado es `already_identical` (éxito sin escritura); con bytes distintos es conflicto permanente (exit 1). Un GET transitorio sale con exit 3.

**Runbook**

- Normalizar: `uv run --env-file .env pits normalize trm [--warn-range-days N]` (default 5). Lee solo manifests committed de `pits-raw`; nunca llama a SODA. Salida: `outcome=… fingerprint=… inputs=N baseline=<batch_id> rows=… coverage=A..B csv=s3://… manifest=s3://…`.
- Prerrequisito: el bucket `pits-normalized` lo crea `pits storage init`. `pits normalize trm` solo verifica que exista y tenga versioning Enabled; si falta, falla y no lo crea.
- Reintentar: es seguro. Si el objeto ya existe con el mismo contenido, la salida es `already_present` (exit 0). Si el CSV quedó sin manifest (caída entre CSV y manifest), la corrida lo completa.
- Códigos de salida: 0 `created` o `already_present`; 1 error permanente; 2 uso (Typer); 3 transitorio, seguro reintentar. `CoverageError` y demás errores de datos (`TrmDataError`) se envuelven en `NormalizePermanentError` → exit 1 (`src/pits/sources/trm/normalize.py`); `RawStoreTransientError` y `RawBucketTransientError` → exit 3.
- Conflicto (412 con bytes distintos bajo la misma key): si cambió la lógica de transformación sin subir `rules_version`, el mismo fingerprint produce bytes distintos. Subir `rules_version` (cambia el fingerprint): es un cambio de código en la constante `DEFAULT_RULES_VERSION` de `src/pits/sources/trm/normalize.py`; no hay opción de CLI. Luego volver a normalizar. No sobrescribir objetos existentes.
- Hueco o solape de cobertura: revisar la fuente (fecha y `source_reference` del error) antes de tocar la salida. No rellenar con la tasa anterior. Un `since` vacío que borra la cola falla a propósito (D76(c)); reextraer la cola con `pits extract trm --since YYYY-MM-DD` y volver a normalizar.
- Manifest corrupto en raw: exit 1 (D65). Con D67, solo un administrador lo corrige; el normalizer no lo repara.
- Rango largo (más de `--warn-range-days`): aviso en stderr; no bloquea. Ver §7 para la decisión pendiente sobre el umbral.

### Fase 3, loader fx_rate a Postgres (D78–D84; implementado en la rama, corrida real pendiente)

Procedencia: plan aprobado por Henry el 2026-10-11 (literal: "aprobado", sobre el plan con D78–D84 y los nombres `pits_warehouse`, `landing` y `ops`). Pasos S1–S6 implementados según el orquestador; S7 es este documento. Base `d89d997`; rama `feat/fx-rate-loader`, worktree `C:\dev\pits-app-load`. El documentador no tiene Bash: no ejecutó `git`, tests, Docker ni la CLI. Los nombres de código de esta sección se verificaron contra `src/pits/warehouse/`, `src/pits/normalized/reader.py`, `tests/pg/`, `tests/contract/test_fx_rate_load_e2e.py` y `scripts/measure_storage_memory.sh`. La comparación contra la base la hace el revisor-senior.

**Demostrado (evidencia de la sesión del 2026-10-11, hora local según el log):**

- Memoria de Postgres (`scripts/measure_storage_memory.sh`, `C=pits-postgres`, `EXPECTED_LIMIT=1073741824`, `PEAK_LIMIT=912680550`, `EXPECTED_GOMEMLIMIT` vacío; carga `pytest -m pg -q`). Log de la sesión, no versionado. 3/3 corridas con rc=0 y `81 passed, 726 deselected` cada una. `memory.peak` 120229888, 120696832 y 70983680 B (114,66, 115,11 y 67,70 MiB). Máximo 115,11 MiB = 11,2 % de 1 GiB, por debajo del 85 %. Sin OOM (`oom=0`, `OOMKilled=false`, `RestartCount=0`). Criterio cumplido. Detalle en `04` §9.
- Pico del loader con tracemalloc (log `trace_loader.log` de la sesión, no versionado; medición del cliente, no del servidor): `rows=12735 csv_bytes=1833902`; primera carga `outcome=loaded inserted=12735`, pico `4838302 bytes (4.61 MiB)`, current `289713`; segunda carga `outcome=already_loaded`, pico `4839008 bytes (4.61 MiB)`, current `290517`.
- Gates del revisor en S6 (reportados por el coordinador, no reejecutados aquí): `ruff check` OK; `ruff format` 99 archivos OK; `pytest -q` 690 passed; `pytest -m pg` 81 passed; contract+pg 1 passed. Disco C: 45 GB libres antes y después de la medición.

**Aprobado (2026-10-11):**

- D78–D84 ("aprobado"). D74: Estado → "Ajustada por D79" (D73(b)).
- Umbral de rango largo D76(f): "Deja así" (5 días), sin D nueva (cierra el pendiente de §7).
- D60 no se ajusta: D79 implementa los usuarios de mínimo privilegio que D60 dejaba para Fase 3, pero no cambia ninguna de sus decisiones (imagen, memoria, puerto, volumen, healthcheck, locale, credenciales desde `.env`).

**Corrida real y pendientes:**

- Corrida real (2026-10-11, Docker local, `uv run --env-file .env`; no VPS):
  - `pits db migrate` → `database=pits_warehouse applied=2 skipped=0` (exit 0, ~1 s); repetido → `applied=0 skipped=2` (exit 0).
  - `pits load fx-rate` (1.ª) → `outcome=loaded load_id=1 rows=12735 inserted=12735 updated=0 deleted=0 coverage=1991-12-02..2026-10-13` (exit 0, ~1,6 s); fingerprint `caa8bc5c31305114109a5a793ad3ec833d1285e8684897260047306c92d6c268`, el mismo del artefacto normalizado de D76.
  - `pits load fx-rate` (2.ª) → `outcome=already_loaded load_id=1 inserted=0 updated=0 deleted=0` (exit 0, ~1,2 s).
  - Consulta como `pits_reader`: 12.735 filas, 1991-12-02..2026-10-13, un solo `load_id`; `ops.load_run` con 1 fila; `DELETE` del reader → `InsufficientPrivilege`.
  - Disco C: 45 GB libres antes y después; volúmenes Docker 74,58 MB → 85,57 MB (`docker system df`).
- Revisión final del hito (`revisor-senior`, diff completo contra `d89d997` + corrida real re-verificada en solo lectura): APROBADA 9,4/10 (2026-10-11). Pendiente: PR y CI.
- Commits del hito: 36598b7 (S1), 050c96f (S2), b7fe95b (S3), cf26d00 (S4), 188c26b (S5), 64e24ce (S6 e2e y medición), 9f523f8 (script, DATA_DIR), 725fe02 (S7 docs) y el commit de la evidencia de la corrida real.
- Disco C: el plan fijó 10 GB libres como umbral para abortar S6 (41 GB al planear). El coordinador reporta 45 GB antes y después de la medición (§3).
- `sslmode=disable` solo en loopback. En el VPS requiere una D nueva (`04` §8.3).

**Runbook del loader**

- Requisitos: perfil `core` arriba (`docker compose up -d`; Postgres en `127.0.0.1:5433` por defecto). `.env` con `POSTGRES_USER`/`POSTGRES_PASSWORD` (admin, solo para migrar), `PITS_PG_LOADER_PASSWORD` y `PITS_PG_READER_PASSWORD`. `pits load fx-rate` además lee el bucket normalized con las credenciales de storage de `.env`.
- Migrar: `uv run --env-file .env pits db migrate`. Salida: `database=pits_warehouse applied=N skipped=M`. Es idempotente y vuelve a fijar las contraseñas de loader y reader desde `.env`. Una migración nueva es un archivo `NNNN_<name>.sql` nuevo; nunca se edita uno aplicado (sha256 distinto = exit 1).
- Cargar: `uv run --env-file .env pits load fx-rate [--fingerprint SHA] [--repair]`. Salida: `outcome=… load_id=… fingerprint=… rows=… inserted=… updated=… deleted=… coverage=A..B manifest=s3://…`. La segunda corrida sin cambios da `already_loaded`.
- `--fingerprint SHA` (64 hex en minúsculas) fuerza un artefacto. Sirve para (a) recuperarse de un manifest antiguo corrupto: un manifest corrupto bloquea la selección automática (exit 1); se carga el fingerprint de un artefacto sano; (b) cargar uno anterior al cargado, que sin el flag da exit 1 por retroceso.
- Deriva (exit 1, "Warehouse drifted"): `--repair` vuelve a aplicar el artefacto. Su salida imprime `outcome=loaded`.
- Exit codes: 0 `loaded`, `already_loaded` o migración correcta. 1 permanente: configuración, manifest o hash, constraint, verificación, deriva sin `--repair`, retroceso, migraciones no aplicadas, privilegios, autenticación (28P01, 28000). 2 uso (Typer; `--fingerprint` que no es hex de 64). 3 transitorio, seguro reintentar: S3 transitorio, conexión rechazada, lock ocupado (también el del `db migrate`), 55P03, 40001, 40P01, 57P01, 57P03.
- Limitación de autenticación: un 28000 sin intercambio de contraseña se clasifica como transitorio (D83).
- Excepciones no tipadas: traceback y exit 1, sin variables locales.
- Lock ocupado (exit 3): hay otro `db migrate` o `load` en curso. Esperar y reintentar.
- Tests: offline `uv run pytest -q`; Postgres `uv run --env-file .env pytest -m pg -q` (incluye el e2e de `tests/contract/test_fx_rate_load_e2e.py`, que lleva ambos markers).
- Limpieza manual de bases y roles de prueba huérfanos. No hay comando de CLI. Cada test `pg` crea y borra su propia base y sus roles (fixture de alcance función); la sesión solo barre huérfanos con patrones exactos al iniciar. Si quedan restos, con Postgres local y sin sesiones `pg` activas, como admin sobre la base `postgres`: `DROP DATABASE IF EXISTS pits_test_<uuid8> WITH (FORCE);` y luego `DROP ROLE IF EXISTS` para `pits_owner_t<uuid8>`, `pits_loader_t<uuid8>` y `pits_reader_t<uuid8>`. Es destructivo: solo local y con confirmación de Henry. Nunca sobre los roles reales `pits_owner`, `pits_loader` ni `pits_reader`.

**Riesgos abiertos del loader:** `sslmode=disable` (solo loopback); verificador SCRAM en el log del servidor si `log_statement` = `ddl` o `all` (`04` §8.3); `db migrate` requiere la contraseña admin en `.env`; 28000 ambiguo (D83); un manifest corrupto bloquea la selección automática hasta usar `--fingerprint`; `GENERATED ALWAYS` no impide `OVERRIDING SYSTEM VALUE` a quien tiene INSERT (el loader es código propio, D81); D67 sigue pendiente (credenciales de ingesta del raw con permisos admin).

### Hito dbt sobre `landing.fx_rate` (D78, D85–D88; implementado en la rama)

Procedencia: plan aprobado por Henry el 2026-10-11 (literal: "aprobado", sobre D85–D88 y sus cuatro recomendaciones: freshness warn 2 días y error 7 días; `marts.fct_fx_rate_daily` desde ya; conversiones e inversa fuera del hito; reader solo ve `marts`). Base `main` `2980760` (PR #17). Worktree `C:\dev\pits-app-dbt`, rama `feat/dbt-fx-rate`. Commits de implementación: S1 `0f29b6c` (build, D85), S2 `a976402` (rol transformer, D86), S3 `f2af10c` (`pits transform`, D88), S4 `c61bee5` (modelos y tests, D87) y S5 `43a91a7` (tests pg). S6 es este documento. Puntajes del revisor: S1 9,4 (vuelta 2), S2 9,3, S3 9,5 (vuelta 2), S4 9,5 (vuelta 2), S5 9,4. El documentador no tiene Bash: los hashes y puntajes son los que reporta el orquestador y no se verificaron contra Git. La comparación contra `base_commit` la hace el revisor-senior.

**Demostrado (sesión del 2026-10-11, reportado por el orquestador y el revisor):**

- Gates del revisor: `pytest -q` 728 passed; `pytest -m pg` 120 passed (unos 2 minutos); contract+pg 1 passed; `ruff` OK; `pits transform parse` OK sin warnings.
- Corrida real (Docker local, `uv run --env-file .env`; no VPS; fuente: `dbt_real_run.md`):
  - `df C:`: 44 GB libres antes y después; volúmenes Docker 88,59 MB después.
  - `pits db migrate` → `database=pits_warehouse applied=1 skipped=2` (exit 0): solo se aplicó `0003_transformer_grants.sql`.
  - `pits transform build` (1.ª) → `PASS=35 WARN=0 ERROR=0 SKIP=0 TOTAL=35` (exit 0, ~7 s).
  - `pits transform build` (2.ª) → `PASS=35 TOTAL=35` (exit 0, ~9 s).
  - `pits transform freshness` → `1 of 1 PASS freshness of ops.load_run` (exit 0).
  - Como `pits_reader`: `marts.fct_fx_rate_daily` con 12.735 filas, 1991-12-02..2026-10-13; mart contra landing con `EXCEPT ALL` en ambos sentidos = 0 filas; `staging.stg_fx_rate` → `InsufficientPrivilege`.
  - Contraseña del transformer en `transform/target` y `transform/logs`: 0 archivos.
  - Las tres contraseñas de rol en `.env` son distintas (verificado sin imprimirlas); `pits db migrate` fijó los verificadores. Rota la del reader que cambió Henry (§7).
- Evidencia de S4 en base de prueba (revisor, sin datos reales): build 35 PASS; freshness WARN a 3 días y ERROR a 8 días; si falla un test de staging, el mart queda en SKIP y el anterior intacto; la contraseña no aparece en 91 archivos de `target/` y `logs/`.

**Aprobado (2026-10-11):**

- D85–D88 (literal "aprobado") con las cuatro recomendaciones del plan.
- Estado de D79 y D80 → "ajustada por D86"; de D49 → "ajustada por D88" (D73(b)). D85 se redactó ya con el host de `profiles.yml` como `env_var`, según lo acordado con el orquestador.
- Tres ajustes que figuran en D85 y D88 pero no en el texto del plan aprobado, confirmados por Henry el 2026-10-12 (literal: "si"): `exclude-dependencies` de `dbt-core-experimental-parser`; el host de `profiles.yml` por `env_var('PITS_PG_HOST','127.0.0.1')`; y `claude-recurrente.yml` con `--only-group dev`.

**Demostrado: pico de memoria de Postgres con carga dbt (`pytest -m pg`):**

- Criterio D63 aplicado a Postgres en §3 del loader. Mide el contenedor `pits-postgres`, no el proceso dbt del host (subproceso de `pits transform`), que no se midió. Resultado: 3/3 corridas de `pytest -m pg` (120 tests, incluidos los 7 de dbt) con `scripts/measure_storage_memory.sh` (`C=pits-postgres`, `DATA_DIR=/var/lib/postgresql/data`, reinicia el contenedor), 2026-10-11: rc=0, sin OOM, `RestartCount=0`; `memory.peak` 80.752.640 B (77,01 MiB), 67.342.336 B (64,22 MiB) y 64.163.840 B (61,19 MiB); máximo = 7,5 % de 1 GiB (límite 85 % = 912.680.550 B). `CRITERIO: OK`. Datos de Postgres: 76M. Log: scratchpad `measure_pg_dbt.log` (no versionado).

**Pendiente:**

- Revisión del diff completo por `revisor-senior` contra `base_commit` `2980760`: vuelta 1 (2026-10-12) CAMBIOS 9,2/10, sin críticas ni altas; hallazgos de docs (etiqueta de la medición de memoria, `README.md`, `04` §8.3) corregidos en S6. Gates de esa vuelta: `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest -q` 728 passed, `pits transform parse` y `git diff --check`, todos exit 0; `pytest -m pg` no reejecutado (Docker apagado). Falta re-revisión, commit final, PR y CI (el paso `pits transform parse` de `ci.yml` no está verificado en GitHub Actions).

**Runbook del hito dbt**

- Migrar: `uv run --env-file .env pits db migrate`. Exige `PITS_PG_TRANSFORMER_PASSWORD` (16 caracteres o más): un `.env` sin ella rompe la migración, aunque loader y reader estén completos.
- Construir: `uv run --env-file .env pits transform build` (dbt build: modelos y pruebas como `pits_transformer`, con preflight y lock).
- Frescura: `uv run --env-file .env pits transform freshness` (`ops.load_run`, warn a 2 días y error a 7 días).
- Parse offline: `uv run pits transform parse` (sin credenciales ni conexión; es el paso de CI).
- Equivalente directo con dbt: `uv run dbt build --project-dir transform --profiles-dir transform`. Aviso: se salta las protecciones del wrapper (validación de la contraseña, preflight, lock y entorno limpio). Sin la contraseña en el entorno, libpq puede leer `pgpass.conf` del usuario de Windows.
- Recuperación: si `landing` quedó mal, corregirlo con `uv run --env-file .env pits load fx-rate --repair` (o con un artefacto nuevo, `--fingerprint`) y volver a correr `pits transform build`. No se edita el mart a mano.
- `dbt --version` consulta PyPI (requiere red); no es telemetría.

**Riesgos abiertos del hito:** `assert_mart_equals_staging` lee el mart y corre después de materializarlo (conciliación, no compuerta; D87); las vistas que algún día existan en `marts` correrían con los privilegios de `pits_transformer` (usar `security_invoker`; hoy no hay, D86); `dbt build` no corre en CI hasta Fase 5 (D40); sesión de dbt sin `TimeZone` fijada (`04` §8.4).

### Fase 4, orquestación con Airflow (D89–D95; implementada en `feat/airflow-trm`)

Procedencia: plan S1–S7 y D89–D94 aprobados por Henry el 2026-10-12 (literal: "Aprobadas todas tus recomendaciones, sigue"), con P1–P9 resueltas en esa misma respuesta (lista en "Aprobado" abajo); D95 aprobada con "1. opcion b" y "2. Si, seteala tu mismo" (`AIRFLOW_API_SECRET_KEY`). Merge del PR #18 y arranque de Airflow: "merge y arranca Airflow". Base `b74e8c0` (merge del PR #18). Worktree `C:\dev\pits-app-airflow`, rama `feat/airflow-trm`. Commits de implementación: S2 `91544fd`, S1 `85b7596`, S3 `40ac5ce`, S4 `3b719eb`, S5 `523844f` y S6 `6c1a77a` (HEAD antes de este cierre); S7 es este cierre documental. Revisiones del revisor (vuelta inicial → final): S1 78→91→95; S2 88→92→96; S3 79→94; S4 91→94; S5 82→94; S6 88→94. El documentador no tiene Bash: hashes y puntajes son los que reporta el orquestador y no se verificaron contra Git; la comparación contra `base_commit` `b74e8c0` la hace el revisor-senior.

**Demostrado (sesión del 2026-10-12, reportado por el orquestador y el revisor):**

- Gates: `pytest -q` 778 passed; `pytest -m pg` 126 passed tras S1, 132 passed tras S4 (revisor) y 135 passed en la revisión final (2026-10-12); orchestration 83 passed dentro de la imagen; `ruff` OK.
- `pits db init-airflow-meta`: `status=created` y luego `status=unchanged`.
- Primer `up`: falló con `database "airflow_meta\n" does not exist` (el `print` dentro del `_CMD` dejaba el newline); corregido (lección 108).
- Stack healthy; `/api/v2/monitor/health` con metadatabase, scheduler y dag_processor healthy.
- Primera corrida programada `scheduled__2026-10-12T15:00:00+00:00` en success en 29 s: extract incremental con 0 filas; normalize created con inputs=3 y fingerprint `b1c56b61…`; load loaded con `load_id=2` y 0/0/0; build PASS=35; freshness PASS.
- Nota de la metadata: la corrida `scheduled__2026-10-12T15:00:00+00:00` aparece con build=failed (17:58:34 UTC) y load con attempt 2 (18:00 UTC). Viene de un `tasks clear` sin fechas y de una versión previa de `tasks test` durante el desarrollo de S6 (lección 115). Los 29 s originales (17:45:43–17:46:11 UTC) siguen valiendo; no es una regresión.
- Suite `-m airflow`: 7 passed en 1365,6 s (incluye lock retenido y SeaweedFS caído con el backoff real).
- Escaneo de secretos en los logs: 0 apariciones de las variables; `SODA_APP_TOKEN` vacío. El escaneo se hizo desde el scheduler y no incluye `AIRFLOW_ADMIN_PASSWORD` (solo lo tiene el apiserver).
- Host: disco C: 47–48 GB libres; imagen `pits-airflow:dev` de 1380040724 B (1,38 GB; `docker image inspect`, build del 2026-10-12 a las 20:06:39 UTC).

**Demostrado: memoria con el criterio de D89 (análogo a D63), 2026-10-12:**

- 3/3 corridas por contenedor, rc=0, sin OOM ni reinicios. `CRITERIO OK`.
- scheduler (límite 2 GiB): picos 603742208/610160640/569274368 B; máximo 581,9 MiB (28 %); IDLE 120 s.
- apiserver (límite 1 GiB): 254160896/253865984/254291968 B; 242,5 MiB (24 %); IDLE 60 s.
- dag-processor (límite 768 MiB): 266727424/266993664/266350592 B; 254,6 MiB (33 %); IDLE 60 s.
- postgres (`pits-postgres`, instancia compartida con el warehouse y la metadata; límite 1 GiB): 69353472/61849600/59973632 B; 66,1 MiB (6,5 %); IDLE 60 s.
- Carga: `scripts/run_dag_and_wait.sh trm_daily` (extract incremental). Una primera tanda en segundo plano la cortó Claude Code por RAM del host; se repitió (lección 116).
- El revisor confirmó que bajar IDLE no invalida el criterio (`memory.peak` se acumula desde el restart).
- Procedencia de las cifras: las del scheduler salen de la primera tanda (`measure_airflow.log`, IDLE 120 s), que también terminó apiserver y dag-processor con CRITERIO OK pero no llegó a postgres. Apiserver, dag-processor y postgres reportados vienen de la repetición (logs 2–4, IDLE 60 s).
- No se midió una corrida con extract full. dbt corre dentro del cgroup del scheduler (subproceso de la tarea); no hay medición separada del proceso dbt.

**Aprobado (2026-10-12):**

- Plan S1–S7 y D89–D94: "Aprobadas todas tus recomendaciones, sigue". D95: "1. opcion b"; "2. Si, seteala tu mismo" para `AIRFLOW_API_SECRET_KEY`.
- P1: 10:00 America/Bogota (15:00 UTC); la "tasa promedio" es la TRM de `32sa-8pi3`. P2: metadata DB en la misma instancia. P3: imagen slim. P4: exit desconocido o señal sin reintento. P5: WSL2 con 12381814784 B (~11,5 GiB), medido con `docker info` el 2026-10-12. P6: credenciales S3 admin aceptadas solo en local; D67 queda para su propio hito. P7: se acepta que `pits-normalized` crezca (~1,8 MB por corrida). P8: reutilizar `POSTGRES_HOST_PORT`. P9: freshness ERROR hace fallar la corrida.
- Levantar: "ya encendi docker, autorizo que corras ese comando" (core up) y "autorizo el up de orchestration, sigue".
- Secretos: se añadieron al final de `C:\dev\pits-app\.env` cinco variables generadas (`AIRFLOW_METADB_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_API_JWT_SECRET`, `AIRFLOW_API_SECRET_KEY` y `AIRFLOW_ADMIN_PASSWORD`), según el orquestador, sin leer el archivo ni imprimir valores.
- Repetir la medición de memoria cortada: "1".

**Pendiente:**

- Revisión final del diff completo por `revisor-senior` contra `base_commit` `b74e8c0`; commit final de S7; PR; CI; merge. Nada de esto está verificado por el documentador.
- Job `orchestration` de `.github/workflows/ci.yml` (D94): no verificado en GitHub Actions.
- No medido: corrida con extract full; proceso dbt separado; `COMPOSE_FILE` con `:` en Linux (no probado).
- Riesgos abiertos del hito: §7.

**Runbook del hito Airflow**

- Levantar: `docker compose -f docker-compose.yml -f docker-compose.orchestration.yml --profile core --profile orchestration up -d`, o `COMPOSE_FILE` con separador `;` en Windows. UI en `http://127.0.0.1:8080`, usuario `admin`, contraseña `AIRFLOW_ADMIN_PASSWORD`.
- `uv run --env-file .env pits db init-airflow-meta` antes del primer `up` de orchestration, con el core ya arriba (requiere Postgres; idempotente; `status=created` o `status=unchanged`).
- Al des-pausar un DAG, Airflow crea la corrida del último punto cron ya pasado.
- `pools set` en `airflow-init` revierte los cambios de slots hechos en la UI.
- Reprocesar: trigger con conf `extract_mode` = `since` o `full`. `--repair` y `--fingerprint` solo por CLI manual.
- Cambiar DAGs exige `docker build` y recrear los contenedores.
- Tests de orchestration: dentro de la imagen (no colectan en el host Windows, D94). CI los corre en Linux: `uv run --locked --project orchestration pytest orchestration/tests -q`. En Windows, el comando verificado por el revisor (83 passed; necesita red) está en `README.md`, sección Orquestación.
- Integración (`-m airflow`): solo desde Git Bash, lejos de las 15:00 UTC y sin corridas activas; `MSYS_NO_PATHCONV=1`.
- `airflow tasks clear` sin fechas limpia todas las corridas; usar `-s`/`-e` con `-t load` (`-t '^load$'` no limpia nada).
- Exit 2 de `scripts/run_dag_and_wait.sh` deja la corrida viva.

### Fase 1b, parque RUNT (D96–D103; implementado en `feat/runt-fleet-snapshot`)

Procedencia: plan S1–S7 y D96–D102 aprobados por Henry el 2026-10-12 (literal: "Apruebo con todas las recomendaciones. 1. Municipio de matricula. 2. Si, normaliza sin tildes. 3. No se. 4. no conozco la regla."); D100 ajustada por Henry ("Si, confirmo la redaccion sin tildes"); D103 aprobada el 2026-10-12 ("si"); siguiente hito elegido por Henry ("2. Fase 1b, sigue con eso"). Base `49493ff` (merge del PR #19, 2026-10-12 21:08 UTC). Worktree `C:\dev\pits-app-runt`, rama `feat/runt-fleet-snapshot`, HEAD `0d748a3` antes de este cierre. Commits de implementación: S1 `7ed71db`, S2 `b0e52c8`, S3 `ad2ece5`, S4 `9a761d8`, S5 `e7a57a0` y S6 `0d748a3`; S7 es este cierre documental (commit pendiente). Revisiones del revisor (vuelta inicial → final): S1 87→95; S2 91→95; S3 92→96; S4 94; S5 94; S6 88→95. El documentador no tiene Bash: hashes, cifras y puntajes son los que reporta el orquestador y no se verificaron contra Git; la comparación contra `49493ff` la hace el revisor-senior.

**Demostrado (sesión del 2026-10-12 y 2026-10-13, reportado por el orquestador; no reejecutado por el documentador):**

- Extracción (`pits extract runt`): 1.ª corrida `committed`, batch `18f6e703-55d0-4373-8867-5e3e768d1ca4`, publicación 2026-10, 191.922 filas, 39 archivos, 50.385.046 B, 36 s. 2.ª corrida: `unchanged`.
- Normalización (`pits normalize runt`): `created`, fingerprint `70485cbc…3064`, 10 partes (36.142.223 B en total; la mayor de 3.806.402 B), `content_sha256` `39116e37…0498`, `vehicle_count_total` 22.655.040, 13,9 s, RSS 154,8 MiB (tracemalloc 75,6 MiB). 2.ª corrida: `already_present` en 0,4 s.
- Carga (`pits load vehicle-fleet`): `pits db migrate` → `applied=1 skipped=3`; `loaded` con `load_id` 41, 191.922 filas, 14,8 s, RSS del cliente 87,4 MiB. 2.ª corrida: `already_loaded`. Consulta como `pits_reader`: 191.922 filas, suma de `vehicle_count` 22.655.040.
- dbt real: `build` con `tag:vehicle_fleet` PASS=59; `build` con `tag:fx_rate` PASS=35; `freshness` PASS.
- DAG: la corrida programada `scheduled__2026-10-12T16:00` terminó en `success` en unos 45 s (extract `unchanged`, normalize `already_present`, load `already_loaded`, build PASS=59, freshness PASS).
- Force de la integración: batch `eb0d2d38`, fingerprint `324cbe55`, `load_id` 42.
- Force medido (una sola corrida, 2026-10-13): batch `f0b0bb41-d33d-4215-aacb-f416e3e34cb3`, `created` con fingerprint `39c5d67c…`, `load_id` 59, build PASS=59, freshness PASS.
- Estado de los datos: hoy hay 3 batches RUNT en `pits-raw` (unos 151 MB) y 3 artefactos en `pits-normalized` (unos 108 MB), todos permanentes. No forzar más corridas sin motivo (ver §7).

**Tests (reportados por el orquestador):**

- `uv run pytest -q`: 1023 passed.
- `pytest -m pg` completo (S5): 186 passed. Parciales posteriores: `transform_pg` 21 passed. `uv run --env-file ../pits-app/.env pytest -m pg -q` (suite completa) dio 188 passed, 0 failed, exit 0, en 486,5 s (2026-10-13 03:41–03:49 UTC), tras arreglar `test_nul_byte`. Ese test ahora inyecta el NUL en el CSV del artefacto, porque D103 hace que el normalizer lo rechace. Contract completo: 45 passed (misma fecha). Cifra reportada por el orquestador, no reejecutada por el documentador.
- Contrato RUNT (`contract` runt): 7 passed.
- Orchestration dentro de la imagen: 125 passed.
- Integración `-m airflow`: la suite completa en segundo plano la cortó Claude Code por falta de RAM del host (lección 127). Se rehízo en partes, con la aprobación de Henry ("2"): 7/7 rápidos (`test_5` se corrigió porque el mensaje incluye `--select tag:fx_rate`); `test_3` (lock, 629 s) PASS; `test_4` (SeaweedFS caído, 595 s) PASS; `test_runt_dag_it`: 2 passed y 1 skipped (la corrida con force solo corre con `PITS_IT_FORCE=1`).

**Memoria (criterio D63/D89, reportada):**

- `pits-postgres` con los tests `pg` del loader y el e2e: 3/3 corridas, picos 113709056, 115159040 y 114356224 B; máximo 109,8 MiB (10,7 % de 1 GiB).
- Scheduler con `runt_fleet_snapshot` en `unchanged`: 3/3 corridas, máximo 640401408 B (610,7 MiB, 30 % de 2 GiB).
- Scheduler con `force` (ruta pesada): una sola corrida, por decisión de Henry (2026-10-13, respuesta "2"); pico 642220032 B (612,5 MiB, 30 %). Una corrida no es una distribución: su pico queda en el mismo orden que el de `unchanged` (640401408 B), pero no se midió como máximo de tres corridas.
- Ninguna corrida tuvo OOM.

**Disco (reportado):** C: de 37 a 44 GB libres. Volúmenes: `pits_postgres_data` 459,5 MB; `pits_seaweedfs_data` 183,3 MB; `pits_airflow_logs` 4,4 MB. Build cache de Docker: 2,8 GB, de los que 1,7 GB son recuperables; no se borró, porque requiere permiso de Henry.

**Incidente (reportado):** un `&` mal puesto hizo que un implementador ejecutara `uv` en `C:\dev\pits-app` y resincronizara su `.venv`. No tocó archivos versionados. No se registró como lección: no estaba en la lista aprobada para el cierre; queda a criterio del orquestador.

**Aprobado (2026-10-12 y 2026-10-13):** plan S1–S7 y D96–D102 (literal en la procedencia); D103 ("si"); ajuste de D100 ("Si, confirmo la redaccion sin tildes"); medir la ruta pesada con una sola corrida force ("2", 2026-10-13); ejecutar la suite de integración en partes ("2").

**Respuestas de dominio (Henry, 2026-10-12):** el municipio del RUNT es el de matrícula (D97, `03` §3). La marca que indica `INCONSISTENTE`: Henry no lo sabe. La regla de publicación del RUNT: Henry no la conoce.

**Runbook del hito Fase 1b**

- Extraer: `uv run --env-file .env pits extract runt [--force]`. Sin `--force`, un `rowsUpdatedAt` igual al del último batch committed da `unchanged` sin escritura; `--force` crea el batch igual (D96). Un manifest RUNT previo corrupto da exit 1; `--force` no lo repara por sí solo, y la corrida siguiente se recupera solo si cae en una partición más nueva (D96).
- Normalizar: `uv run --env-file .env pits normalize runt`. Si el contenido ya existe, `already_present`. No tiene `--force`. Con un manifest RUNT corrupto, `list_committed` valida todas las particiones, así que ni `extract --force` desbloquea el normalizer: requiere intervención de un administrador (D67).
- Cargar: `uv run --env-file .env pits load vehicle-fleet [--publication YYYY-MM] [--fingerprint SHA] [--repair]`. Una transacción por publicación con el xact lock de D90. Un artefacto más viejo que el último `load_run` de la misma publicación da exit 1, salvo `--fingerprint` (D99).
- Transformar: `uv run --env-file .env pits transform build --select tag:vehicle_fleet` (o `tag:fx_rate`) y `pits transform freshness --select …`. Sin `--select`, freshness evalúa también `load_run_fleet` (D101). Un valor fuera de `^tag:[a-z_]+$` da exit 2.
- DAG `runt_fleet_snapshot` (diario, 11:00 America/Bogota = 16:00 UTC; D102): param `force` (solo bool) pasa `--force`. Antes de ejecutar integración, revisar que no haya corridas programadas cerca de 15:00 y 16:00 UTC.
- Integración: `PITS_IT_FORCE=1` agrega unos 86 MB permanentes en el raw y normalized. Con `-k`, usar los nombres `test_runt_*`. Al pasar un conf JSON por `bash -c` hay que poner comillas simples (lección 125).

**Pendiente:**

- Revisión del diff completo por `revisor-senior` contra `49493ff`, commit final de S7, PR, CI y merge. Nada de esto está verificado por el documentador.
- `README.md` (estructura, sección Orquestación con dos DAGs, ventanas de 15:00 y 16:00 UTC, "125 passed", `PITS_IT_FORCE`, comandos del RUNT): HECHO por otro agente (fuera de `docs/`; el documentador no lo editó). Verificación pendiente del orquestador.
- Sin medir: el proceso dbt por separado y una corrida con extract full en el hito RUNT.

### Hito Endurecimiento y optimización (D104–D111; implementado en `feat/hardening-optimization`)

Procedencia: encargo de Henry el 2026-10-13 (literal: "Si, hagamos eso, lanza el arquitecto para endurecimiento, que sirva de optimizacion"); plan S1–S7 y D104–D111 aprobados por Henry el 2026-10-13 (literal: "aprobadas todas"). Worktree `C:\dev\pits-app-hardening`, rama `feat/hardening-optimization`, apilada sobre `feat/runt-fleet-snapshot` (PR #20, todavía abierto). HEAD antes de este cierre: `038e373` (S6). El documentador no tiene Bash: no ejecutó git, tests, Docker ni la CLI. Hashes, cifras y puntajes son los que reporta el orquestador; la comparación contra la base la hace el revisor-senior. Sin merge, CI ni despliegue verificados por el documentador.

**Commits y revisiones (reportados por el orquestador):**

- S1 `83e12ae`: revisión 92→97.
- S2 `986e756`: 95.
- S3 `8ba93f2`: 91→95.
- S4 `1df3ab9`: 89→93.
- S5 `ce875cb`: 94.
- S6 `038e373`: 93.
- S7: este cierre documental; commit pendiente de revisión independiente.

**Demostrado (sesión del 2026-10-13, reportado por el orquestador; no reejecutado por el documentador):**

- `.env`: comprobaciones booleanas de variables, sin imprimir valores; después se añadieron 4 variables `PITS_S3_*` sin imprimir valores.
- SeaweedFS recreado y healthy. `storage init` dos veces: `policy=applied`.
- Contrato de identidades: 13 passed y 1 xfail. Una key falsa da `InvalidAccessKeyId`.
- Cadena en el host con identidades reales, todo exit 0: TRM `load_id=60` con 12.735 filas; RUNT `unchanged` / `already_present` / `already_loaded`.
- Contract completo: 59 passed y 1 xfail.
- Airflow recreado: scheduler sin admin S3; 3 DAGs; retención en success.
- Integración `-m airflow`: 7 rápidos passed (incluye el escaneo de secretos con writer y reader requeridos); `test_4` (SeaweedFS caído) passed en 578 s. `test_3` y `test_runt_2` omitidos, según el plan.
- Humo con la imagen bytecode: `trm_daily` y `runt_fleet_snapshot` en success.
- `pits storage orphans` (D107), corrida real: raw groups=69 committed=69 orphans=0; normalized groups=68 committed=68 orphans=0.
- Tests: `pytest -q` 1111 passed; orchestration dentro de la imagen 137 passed; `pytest -m pg -k load` 91 passed; `pytest -m pg -k transform` 59 passed. Revisión final (2026-10-13, reportada por el orquestador): suite `pg` completa 188 passed de 188 (en dos grupos: 97 y 91); contract 59 passed y 1 xfailed.
- Mediciones: D110 (dbt, 3 builds, mediana 9,500 s, sin cambios) y D111 (imagen bytecode, −48,7 % y −46,8 %): ver `04_infra.md` §9.

**Aprobado (2026-10-13):**

- Plan S1–S7 y D104–D111 ("aprobadas todas"), con D104 en su texto original.
- Estado de D57, D62, D64, D66, D67, D89, D95 y D102 ajustado (D73(b)).

**Decisiones de Henry sobre los pendientes del hito (2026-10-13, literal: "merged, acepto tus recomendaciones, sigue"):**

- Pendiente 1, D104(c), APROBADO: el admin de SeaweedFS 4.48 sí borra con DeleteObjects. El texto aprobado decía que la policy también bloquea al admin, y eso no se sostuvo al probarlo. La limitación queda aprobada con su mitigación: el admin solo se usa en `storage init` y en los tests contract, y el test `xfail(strict=True)` `test_policy_denies_admin_multi_delete` avisa cuando se corrija.
- Pendiente 2, filer y master sin autenticación desde la red Docker `pits_default`, DIFERIDO por decisión de Henry: queda como riesgo abierto (§7). Antes de cualquier despliegue en el VPS hará falta una D propia (JWT en `security.toml` o una red separada).

**Runbook del hito Endurecimiento:**

- Identidades: `storage init` usa `pits_admin` (`S3_*`); extract y normalize usan `pits_writer` (`PITS_S3_WRITER_*`); load y orphans usan `pits_reader` (`PITS_S3_READER_*`). Si falta una variable, exit 1 con su nombre; no hay fallback al admin.
- Inventario: `uv run --env-file .env pits storage orphans` (solo lectura, identidad reader; exit 0, 1 o 3; muestra como máximo 20 unexpected).
- Quitar la policy (break-glass): admin con `delete_bucket_policy`, solo con confirmación de Henry. Rollback de S4: volver a `AWS_*` en compose y recrear.
- Retención de logs de Airflow: DAG `airflow_log_retention`, diario a las 03:00 America/Bogota.
- Ventanas de D106: no correr `pits extract` a mano entre 14:45 y 15:30 UTC ni entre 15:45 y 16:30 UTC, ni con corridas activas.
- Si cambian los nombres de los buckets: recrear `seaweedfs` y volver a correr `storage init`. Si cambia el JSON de identidades: recrear `seaweedfs`.

### Hito Aislamiento de listeners de SeaweedFS (D117–D120; implementado en `feat/seaweedfs-listener-isolation`)

Procedencia: plan P1–P4 y D117–D120 aprobados por Henry el 2026-10-13 (literal: "Si, apruebo todo, repo publico"), junto con los planes de los hitos A (CI, D112–D116, en otra rama) y C (DANE, D121+) y sus autorizaciones. Antes, al diferir el riesgo del filer, Henry había dicho: "merged, acepto tus recomendaciones, sigue", con la condición de una D propia antes del VPS (D117 y D118). Worktree `C:\dev\pits-app-swiso`, rama `feat/seaweedfs-listener-isolation`, HEAD `23799d7` antes de este cierre. El documentador no tiene Bash: no ejecutó git, tests, Docker ni la CLI. Hashes, cifras, puntajes y listeners son los que reporta el orquestador o el revisor. La comparación contra la base de la rama la hace el revisor-senior; base de la rama `5a6b6c8` (merge-base con origin/main).

**Commits y revisiones (reportados por el orquestador):**

- P1 `9c959e9`: revisión 91.
- P2 `4b8e7e9`: revisión 90 → 93.
- P3 `23799d7`: revisión 92.
- P4: este cierre documental; commit pendiente de revisión independiente.

**Demostrado (sesión del 2026-10-13, 14:15–14:16 UTC, fuera de las ventanas de D106; reportado por el orquestador, no reejecutado por el documentador):**

- Antes del cambio: orphans raw 77/77/0 y normalized 76/76/0; sha256 de manifests raw `7d990709…51e7fb` y normalized `f5d0614c…902cdd9`.
- Se añadió la key de `security.toml` a `.env` sin imprimirla; `docker compose config --quiet` OK; `up -d seaweedfs` healthy; `storage init` con `policy=applied`.
- Después del cambio: orphans y sha256 idénticos a los de antes; contrato de red D119: 13 passed; contract completo: 72 passed y 1 xfail (el de D104(c)); el scheduler alcanza S3 (`pits storage orphans` vía `docker exec`).
- Probe `scripts/probe_seaweedfs_isolation.sh`: `CRITERIO: OK` (70 passed y 1 xfail contra el probe).
- Contrato D119 antes del cambio: 8 fallos y 3 pasados (rojo esperado).
- Verificación del revisor sobre los listeners en vivo: solo `::8333` y `::18333` escuchan; 8181 y 9101 no escuchan; el Env del contenedor no tiene `AWS_*` ni la key.

**Aprobado (2026-10-13):**

- Plan P1–P4 y D117–D120 ("Si, apruebo todo, repo publico").
- Estado de D57 → "ajustada por D104; ajustada por D117" (D73(b)).
- Riesgos residuales de D120 aceptados. El punto (f), telemetría anónima de weed, sigue pendiente de decisión antes del VPS.

**Pendiente:**

- Revisión final del diff completo por `revisor-senior` contra la base de la rama; commit de P4; PR; CI y merge. Nada de esto está verificado por el documentador.
- Antes del VPS, con confirmación explícita de Henry (regla 10): correr el probe y el contrato D119 allí, y decidir la telemetría anónima de weed (D120, f).
- Coordinación con el hito A (D112–D116, otra rama): el que mergee segundo rebasa y ajusta la cabecera de `05` (v19) y las secciones que toque.

**Runbook del hito Aislamiento:**

- Rotar la key del filer: cambiar `PITS_SEAWEEDFS_FILER_JWT_KEY` en `.env` y recrear `seaweedfs`; `security.toml` se regenera en cada `up`. Si falta la key, cualquier `docker compose` sobre el archivo falla por el `:?`. No imprimir la key.
- Mantenimiento de SeaweedFS: `docker exec -it pits-seaweedfs weed shell`. El master y el filer no son accesibles desde el host (D117; D120, g).
- Pre-flight del VPS: `scripts/probe_seaweedfs_isolation.sh` y después el contrato D119 (`tests/contract/test_seaweedfs_network_contract.py`, marker `contract`), solo con confirmación de Henry.
- Apuntar el contrato D119 a otra red: `PITS_SWNET_NETWORK` (default `pits_default`) y `PITS_SWNET_HOST` (default `seaweedfs`).

### Hito Fase 5, CI completo (D112–D116; implementado en `feat/ci-contract`)

Procedencia: plan S1–S6 y D112–D116 aprobados por Henry el 2026-10-13 (literal: "Si, apruebo todo, repo publico"), junto con los planes del hito B (D117–D120, sección E-4) y del hito C. Base `main` `e4f160f`. Worktree `C:\dev\pits-app-ci`. El documentador no tiene Bash: no ejecutó git, tests, Docker ni GitHub. Hashes, revisiones y runs son los reportados por el orquestador; los hashes de S5 se leyeron en el reflog local del repo, no en un `git log` del documentador.

**Commits (reportados por el orquestador; hashes del reflog local):**

- Ya en `main` vía el PR #22 (merge `423babb`): `d04a8c1` (S1, paridad y guardas de locale, D112), `95e4fba` (S2, job pg con credenciales efímeras, D112 y D114), `c1a0be7` y `2dca95d` (S4, dbt build y verify por la CLI, D113).
- Fix de la carrera de `_is_dead` (ESRCH de procfs): commit `a635f36` en el PR #24, rama `fix/operator-test-esrch`. El job `orchestration` falló por esa carrera en el run 38412141157. PR #24 ya mergeado en `main` (merge `e4f160f`, base de esta rama; reportado por el orquestador).
- S5 en `feat/ci-contract` (reflog local): `9abef4a` (job contract con SeaweedFS vía compose, D115), `7d03e3e` (trigger temporal de push para iterar), `9dd272c` (liberar disco y diagnósticos de volúmenes), `f8fef66` (retira el trigger temporal) y `e0b7c31` (fixes bajos: diagnósticos del job contract solo en fallo y paridad extendida). El commit `e0b7c31` está en el reflog local, pero no tiene revisión independiente.
- Cierre de los e2e (reportado por el orquestador, 2026-10-13): `5682c5a` (cambio: `raises=AssertionError`, `-m contract` completo y el trigger temporal de push de rama; quedó con un literal `"\n"` roto porque los gates se encadenaron mal), `7a4d3b8` (arreglo del literal) y `96c5651` (retira el trigger temporal por última vez). PR #25 en draft.

**Revisiones (reportadas por el orquestador):** S4 aprobado; S3 98; S5 93. S6 (este cierre) sin revisar.

**Demostrado (reportado por el orquestador; no reejecutado por el documentador):**

- Run 38419204583 sobre `7a4d3b8`: 4 jobs verdes (`ci`, `orchestration`, `pg` y `contract`). `contract`: 72 passed, 1 xfailed y 0 skipped; los 2 e2e pasan en el junit (73 tests en total).
- Evidencia previa, run 38416999520 (antes de que `contract` incluyera los e2e): 4 jobs verdes; `contract` 70 passed y 1 xfail, 0 skipped; el junit trae 13 testcases del contrato de red D119.
- `pg`: `dbt build` PASS=94 e idempotente; `verify` OK.
- Run que falló con el disco del runner: 38416302958 (15 "failed to find writable volume"; ~14 GB medidos antes de liberar en el run 38416999520; tras liberar quedaron unos 32 GB y el run salió verde).
- Run 38420161592 (`pull_request`, sobre HEAD `96c5651`): 4 jobs en verde. Evidencia verificada por el revisor.

**Aprobado (2026-10-13):**

- Plan S1–S6 y D112–D116 ("Si, apruebo todo, repo publico").
- Celdas Estado (D73(b), solo "ajustada"): D58 (ajustada por D115), D84 (ajustada por D112 y D115) y D88 (ajustada por D113). D49 sin cambios: D113 solo la complementa, y la relación figura en la fila de D113. "Complementada" ya no aparece en 05.

**Pendiente:**

- Bloqueo de los e2e: RESUELTO por el implementador (`5682c5a` (cambio), `7a4d3b8` (arreglo del literal), validado en el run 38419204583, reportado por el orquestador). `contract` usa `-m contract` completo, que incluye los 2 e2e; `pg` usa `pg and not contract`. Cada test corre en exactamente un job, y lo exige `tests/test_ci_parity.py` (markers, addopts y comandos de cada job). Refuerzo de la paridad: `66ae5d6` (addopts, universo de markers {contract, pg, airflow}, job `ci` sin `-m`, secretos del upload derivados del step de credenciales), validado en el run 38421370055 (pull_request, 4 jobs verdes; contract 72 passed y 1 xfailed). Este documento no toca `ci.yml`.
- PR #25 en draft: revisión independiente del head final, paso a ready y comprobación de que el run corresponde a ese head. No verificado por el documentador.
- Revisión final del diff completo por `revisor-senior` contra `e4f160f`; commit de docs; PR. Nada de esto está verificado por el documentador.
- S7, para Henry: marcar `ci`, `orchestration`, `pg` y `contract` como required checks en la branch protection de `main`.
- Lección 145: el xfail de `test_policy_denies_admin_multi_delete` lleva `raises=AssertionError` (aplicado en `5682c5a`, reportado por el orquestador).

### Hito C, DANE/DIVIPOLA (D121–D130; implementado en `feat/dane-divipola`, PR #27 en draft)

**Corrección (2026-10-14, verificada por el orquestador con `gh pr list`):** PR #27 está MERGED (2026-10-13T19:06:03Z, merge `33525d4` en `main`). El estado "en draft" de este encabezado y de los pendientes de esta sección es histórico; no se editó el texto original.

Procedencia: plan C y D121–D129 aprobados por Henry el 2026-10-13 (literal: "Si, apruebo todo, repo publico"), con las respuestas recomendadas 1–9; D130 por instrucción de Henry (literal: "continua con el C DANE/DIVIPOLA y aplica la revision al final del hito"). Base: `main` `497d0e3`, que ya incluye el playbook `10`. Worktree `C:\dev\pits-app-dane`, rama `feat/dane-divipola`. El documentador no tiene Bash: no ejecutó git, tests, Docker, la CLI ni GitHub. Hashes, cifras y puntajes son los que reportan el orquestador o el implementador; la comparación contra `497d0e3` la hace el revisor-senior.

**Commits tras el rebase (reportados por el orquestador):** S1 `5e63dac`, S2 `b50ad76`, S3 `e0e420e`, S4 `a8295ef`, S5 `880387c`, S6 `95212e6` y ajuste de S5 `6769284` (seed de CI y tests pg). S7 es este cierre documental; commit pendiente.

**Desviaciones del plan (reportadas por el implementador):**

- `.gitignore` ignoraba `*.csv`; se añadió `!transform/seeds/*.csv` (lección 152).
- El seed de CI (D113) se extendió con DIVIPOLA sintético, porque sin él se rompía el build completo del job pg (lección 153).
- 3 tests pg existentes se adaptaron al grafo nuevo y a la migración 5 (lección 153).
- Dependencia de orden de arranque: `tag:vehicle_fleet` necesita que `dim_municipality` exista y `tag:divipola` necesita los modelos del RUNT. Si falta la dimensión, el fct del RUNT se construye igual y solo fallan los nodos DANE (lección 154).

**Demostrado (evidencia del implementador, reportada; no reejecutada por el documentador):**

- ruff 0/0.
- `pytest -q`: 1217 passed.
- Contract: 78 passed y 1 xfailed.
- Orchestration dentro de la imagen: 163 passed.
- pg: la primera corrida dio 233 passed y 10 failed; tras el ajuste, los archivos afectados dieron 29 passed. La suite pg completa no se re-corrió en local; la valida el CI del PR #27 (pendiente).

**Demostrado (evidencia en vivo del orquestador, 2026-10-13, 18:58–19:06 UTC, fuera de las ventanas de D106; entorno local con Docker; no hay evidencia de VPS en este hito):**

- `pits db migrate`: applied=1, skipped=4.
- Extract: committed, batch `96d4047b`, `rows_updated` 2025-01-24, rows 1122.
- Normalize: created, fingerprint `68995037…7efee`.
- Load: loaded, load_id 68, inserted 1122.
- `build --select tag:divipola`: PASS=90, WARN=0, ERROR=0.
- Segunda pasada: unchanged / already_present / already_loaded, y build PASS=90.
- Cobertura real: `map_runt_municipality_dane` con 293 pares y 0 sin código; `dim_municipality` con 1122 filas; `fct_vehicle_fleet_snapshot` y `fct_vehicle_fleet_snapshot_dane` con 191.922 filas cada uno y la misma suma de vehículos (22.655.040), con 0 vehículos sin código; `dane_match_method` auto_norm en 179.776 filas y curated en 12.146.
- Rebuild de `pits-airflow:dev` y recreación de apiserver, scheduler y dag-processor: los 3 healthy y sin import errors.
- `divipola_snapshot` despausado (timetable `0 7 * * 1`). Al despausar corrió automáticamente el intervalo programado del 2026-10-12; después, un disparo manual (`manual__it_20261013T190345_1189`). Ambos dieron unchanged / already_present / already_loaded y build PASS=90.
- Memoria del scheduler (`scripts/measure_storage_memory.sh`, RUNS=1, límite 2 GiB): idle 261.091.328 B; pico 608.960.512 B (580,8 MiB, 28 % de 2 GiB); oom=0; `CRITERIO: OK`. Una sola medición (D129).
- DAG `runt_fleet_snapshot` con la imagen nueva (`manual__it_20261013T190500_50`): success; unchanged / already_present / already_loaded; build PASS=99.
- `pits storage orphans` (D107): pits-raw 79/79/0 y pits-normalized 78/78/0.

**Evidencia de CI (reportada por el orquestador; no verificada por el documentador):**

- Run 38452140143 (`pull_request`, sobre el head `6769284`): success.
- Job `pg`: 245 passed; seed `divipola_municipality=1114`; verify OK.
- Job `contract`: 78 passed y 1 xfailed.
- Revisión final, vuelta 1 (`revisor-senior`, reportada por el orquestador): CAMBIOS (92). Las correcciones de esa vuelta se aplican en docs/ y README.md; la vuelta siguiente revisa de nuevo el diff completo.

**Aprobado (2026-10-13):**

- Plan C y D121–D129 ("Si, apruebo todo, repo publico") con las respuestas 1–9 (texto en `05` sección E-6).
- D130 ("continua con el C DANE/DIVIPOLA y aplica la revision al final del hito"), confirmada por Henry el 2026-10-13 (literal: "apruebo tal cual"). La aprobación incluye el commit por paso del implementador, el PR en draft hasta la aprobación final y el aviso "no mergear aún".
- Ninguna celda Estado de D1–D120 se ajustó: D45 y D73 no cambian su texto con D130, así que no llevan "ajustada por D130".

**Pendiente:**

- Revisión final única del diff completo por `revisor-senior` contra `497d0e3` (D130). Cualquier cambio posterior invalida la aprobación.
- Commit de este cierre documental (S7) y push de la rama.
- PR #27: sigue en draft hasta que la revisión final apruebe; después se avisa a Henry "no mergear aún" antes de cualquier merge. CI del PR #27 (incluye el job pg con DIVIPOLA sintético): no verificado por el documentador.
- Sin merge ni CI verificados por el documentador.

**Runbook DANE/DIVIPOLA:**

- Migrar: `uv run --env-file .env pits db migrate` (aplica la migración 0005).
- Extraer DIVIPOLA: `uv run --env-file .env pits extract divipola [--force]`. Sin `--force`, `rowsUpdatedAt` igual al del último batch da `unchanged`.
- Transformar: `uv run --env-file .env pits transform build --select tag:divipola`.
- Orden de despliegue: cargar DIVIPOLA antes de activar la imagen nueva del RUNT.
- Cambiar las columnas del seed `transform/seeds/runt_municipality_dane_exception.csv` exige `dbt build --full-refresh`.
- Añadir una excepción de municipio = PR con una fila en el seed y su `decision_id`. Un `not_in_divipola` requiere aprobación de Henry (D128).

### Hito Demanda de repuestos con parque RUNT (D131–D134; implementado en `feat/parts-demand-fleet`)

Procedencia: hito elegido por Henry el 2026-10-14 (literal: "Demanda por parque (Recomendado)"). P1 = "Solo dato real (Recomendado)"; P2 = "Todas las clases" (no la recomendada car + motorcycle); plan con "Aprobado todo" (incluye core up, consulta de clases, corrida real y rebuild/recreate de Airflow); textos de D131–D134 con "Aprobado" (`05` sección E-7). Base `33525d4` (merge del PR #27 en `main`). Worktree `C:\dev\pits-app-demand`, rama `feat/parts-demand-fleet`. Commits de implementación: S1 `d7a856b` (seed y tests), S2 `9f66676` (marts y tests de D134) y S3 `4317f9a` (tests pg y verify del CI). La evidencia no reporta hash para un paso S4 (no verificado). S5 es este cierre documental, con commit pendiente.

El documentador no tiene Bash: no ejecutó git, tests, dbt, Docker, la CLI ni GitHub. Hashes, cifras y exit codes son los que reporta el orquestador en la sesión del 2026-10-14; la comparación contra `33525d4` la hace el revisor-senior.

**Desviaciones (reportadas por el orquestador):**

- La consulta de clases reales se hizo como admin, por el socket local del contenedor, con `default_transaction_read_only=on`; el plan decía `pits_reader` (lección 161).
- Docker Desktop estaba apagado al empezar la corrida; el orquestador lo arrancó y levantó `core` (lección 162).
- `docker compose` se ejecutó desde el worktree con `--env-file` apuntando a `C:/dev/pits-app/.env`, el `.env` del checkout principal, sin copiarlo (lección 163).

**Demostrado (sesión del 2026-10-14, evidencia del orquestador; no reejecutada por el documentador):**

- Línea base (`33525d4`): `uv sync --locked`, `ruff check`, `ruff format --check` y `pytest -q` (1217 passed, 334 deselected), exit 0.
- Tras S3: `ruff check` 0; `ruff format` 0; `pytest -q` 1217 passed, 344 deselected, exit 0; `pits transform parse` exit 0; `pytest -m "pg and not contract" -k "parts_demand or transform or ci_seed"` con `-x`: 100 passed, 1461 deselected, 27 min 39 s, exit 0 (PIPESTATUS).
- Precondición de clases: 98 `vehicle_class_norm` en la publicación 2026-10. Seed: 70 `machinery` y 28 en los otros grupos.
- Corrida real: `pits transform build --select tag:vehicle_fleet` → PASS=134, WARN=0, ERROR=0 (rc 0, 22 s); `tag:divipola` → PASS=125, WARN=0 (rc 0, 18 s); segunda pasada de `tag:vehicle_fleet` → PASS=134 (rc 0, 34 s, idempotencia).
- `fct_parts_demand_scope`, publicación 2026-10: `included` 22.166.682; `excluded_service_no_registra` 234.737; `excluded_service_oficial` 209.327; `excluded_status_inconsistente` 41.349; `excluded_service_otros` 2.945. Suma 22.655.040 = `stg_vehicle_fleet_snapshot` 22.655.040 (cuadra con §3, hito DANE/DIVIPOLA).
- `fct_parts_demand_fleet`: 147.935 filas; suma de `active_vehicle_count` 22.166.682 (= `included`); 0 filas sin código DANE.
- Por segmento y grupo. `particular`: motorcycle 14.601.922; car 6.352.156; heavy 106.577; machinery 11.269; other 45; trailer 7. `fleet`: car 556.524; heavy 523.554; motorcycle 14.569; machinery 53; other 4; trailer 2.
- Airflow: build de `pits-airflow:dev` con `docker compose --env-file C:/dev/pits-app/.env` (`COMPOSE_FILE` con `;`), rc 0, 20 s; `up -d --force-recreate` de `airflow-init`, `scheduler`, `apiserver` y `dag-processor`, rc 0. La imagen contiene `fct_parts_demand_*.sql`.
- DAG `runt_fleet_snapshot` sin force (`scripts/run_dag_and_wait.sh`): run `manual__it_20261014T150836_2390` en success, 54 s: extract, normalize, load, build (PASS=134, WARN=0, 23 s) y freshness en success.
- Docker: WSL2 con MemTotal 12.381.810.688 B; `docker compose --profile core up -d` con postgres y seaweedfs ya Running y healthy. No se hizo `docker compose down`.

**Hallazgo (consulta de la publicación 2026-10):** casi toda la maquinaria y los remolques no están ACTIVO en PARTICULAR ni en PÚBLICO (p. ej. SEMIREMOLQUE: 4 de 127.741; EXCAVADORA: 2 de 25.257); quedan en las exclusiones por servicio o estado. Por eso incluir todas las clases casi no cambia el total frente a car + motorcycle + heavy (lección 158).

**No medido:** memoria del hito. Inferencia del plan: agregación SQL de unas 192 mil filas, sin cambios de contenedores ni de límites. No verificado.

**Aprobado (2026-10-14):**

- Hito "Demanda por parque (Recomendado)"; P1 "Solo dato real (Recomendado)"; P2 "Todas las clases"; plan "Aprobado todo"; textos de D131–D134 "Aprobado" (`05` sección E-7).
- D135 no existe: se eliminó en el plan; la siguiente libre es D135. D113 sin cambios.
- Ninguna celda Estado de D1–D130 se ajustó.
- P3, P4 y P5 no están aprobados; siguen pendientes (§7). Texto original conservado. RESUELTOS después por el hito A de marca (2026-10-14, "Aprobado todo"): P3 por D140, P4 y P5 por D139 y D140 (§3 del hito A).

**Pendiente:**

- Revisión final única del diff completo por `revisor-senior` contra `33525d4` (D130). Cualquier cambio posterior invalida la aprobación.
- Revisión por Henry del `vehicle_group` del seed (`transform/seeds/vehicle_class_demand_scope.csv`, D133): es inferencia del orquestador.
- Commit final de S5 (este cierre), push, PR en draft y CI: no verificados por el documentador.
- Antes de cualquier merge: aviso a Henry "no mergear aún" hasta la aprobación final (D130).
- Marca y línea sintéticas (D131): hito propio, no iniciado. Ver §5 y §7.

**Runbook del hito Demanda:**

- Construir: `uv run --env-file .env pits transform build --select tag:vehicle_fleet` (incluye el seed y los marts de demanda). El DAG `divipola_snapshot` construye `tag:divipola` (D129).
- Orden de despliegue: cargar DIVIPOLA antes de activar la imagen nueva del RUNT (lección 154; runbook de Hito C en esta sección).
- Clase nueva en el RUNT: aparece como 'unmapped' con warn. Se clasifica con una fila nueva en el seed y su `decision_id`, por PR.
- El DAG `runt_fleet_snapshot` construye los marts de demanda con `tag:vehicle_fleet` (corrida manual del 2026-10-14, build PASS=134).
- Compose: `--env-file` con la ruta absoluta del `.env` del checkout principal; no copiar el archivo (lección 163).

### Hito A de marca, proporciones regionales de marca y línea (D135–D140; implementado en `feat/regional-brand-share`)

Procedencia: plan aprobado por Henry el 2026-10-14 (`05` sección E-8). Literales: siguiente hito "Merged, marca sintetica"; P3 "Ponderar por el RUNT" (no era la recomendación, igual peso por región); P6 "Todas + sample_size_ok (Recomendado)"; P8 "Extraer sin placa" (no era la recomendación); plan "Aprobado todo"; textos de D135–D140 "Aprobado". Base `794c168` (merge del PR #28, MERGED 2026-10-14T15:50:22Z). Worktree `C:\dev\pits-app-brand`, rama `feat/regional-brand-share`. Commits de implementación: S1 `03f3bb3` (extractor, D136), S2 `b2bb6a8` (normalizer, D137), S3 `d43f38d` (migración 0006 y loader, D138), S4 `2921022` (staging y seeds, D139), S5 `2b31a6c` (marts, D140) y S6 `8d93f02` (CI, pg y contract e2e). S7 es este cierre documental, con commit pendiente.

El documentador no tiene Bash: no ejecutó git, tests, dbt, Docker, la CLI ni GitHub. Hashes, cifras y exit codes son los que reporta el orquestador en la sesión del 2026-10-14; la comparación contra `794c168` la hace el revisor-senior.

**Desviaciones de implementación (reportadas por el implementador; detalle en `05` E-8, notas 1 a 9; no cambian D135–D140):**

- Se quitó el `+tags` global de seeds de `transform/dbt_project.yml`: dbt suma los tags entre niveles. Las seeds RUNT ya declaraban el tag en `_seeds.yml`.
- `assert_regional_brand_weight_present` solo falla para los `source_system` de la seed con filas en landing; un build sin datos regionales no falla.
- Orden del scope: clase, luego estado, luego servicio. Valores: `excluded_class`, `excluded_status`, `excluded_service`, `included`.
- `auteco_line_brand_map` acepta `sin_evidencia` y tiene 43 líneas `SIN ASIGNAR` explícitas. Frente a la investigación en Boyacá: BAJAJ 5.276 (investigación: 5.272) y SIN ASIGNAR 499 (investigación: 503), 4 filas con typos aislados asignadas a BAJAJ por inferencia.
- `brand_alias` solo tiene alias observados: AUTECO BAJAJ, AUTECO VICTORY y AUTECO KYMCO. AUTECO KAWASAKI no existe en las fuentes.
- Nombres de columnas de los marts elegidos por el implementador (`05` E-8, nota 6).
- Manifest normalizado con `vehicle_total` y `row_count`; la tabla landing incluye `rows_updated`.
- Requeridos vacíos = error permanente. Verificado en la API el 2026-10-14: 0 filas con `clase`, `marca`, `linea`, `servicio` o `estado` nulos o vacíos en las dos fuentes.
- Una fila con `placa` en la página N deja huérfanas las páginas anteriores, igual que en DIVIPOLA; `pits storage orphans` las lista.

**Demostrado (sesión del 2026-10-14, evidencia del orquestador; no reejecutada por el documentador):**

- Línea base (`794c168`): `uv sync --locked`, `ruff check`, `ruff format --check` y `pytest -q` (1217 passed), exit 0.
- Al cierre de S6 (implementador), exit 0: `ruff check`, `ruff format --check` y `pits transform parse`; `pytest -q` 1329 passed, 404 deselected; `pytest -m pg -k "brand or transform or ci_seed"` 151 passed, 1582 deselected, 43 min 57 s. Tests dbt con tag `fleet_brand`: 113, ninguno mezcla familias (inspección del manifest y test pytest). Contract e2e de brand-fleet: solo colectados (9); los corre el CI.
- Verificación previa en la API (2026-10-14): `$select=clase,marca,modelo,linea,cilindraje` con `$order=:id ASC` devuelve solo esas claves. `count(*)`: Risaralda 453.925 y Boyacá 182.379. `rowsUpdatedAt`: Risaralda 1783366796 con 6 columnas (incluye `placa`); Boyacá 1725049480 con 18 columnas. Códigos DANE en `fct_parts_demand_fleet`: 15 = BOYACA y 66 = RISARALDA.
- Corrida real (`uv run --env-file C:/dev/pits-app/.env` desde el worktree; Docker local, no VPS):
  - `pits db migrate`: applied=1 skipped=5, rc 0.
  - Boyacá: extract `645dd080-55da-44c3-b406-42878252cc9b` (committed; rows_updated 2024-08-30; 182.379 filas; 37 archivos; 45 s; la 2.ª corrida da `unchanged` en 3 s). Normalize `created`, fingerprint `ae2f6a75…92a4`, 24.539 filas, 182.379 vehículos, 8 s (2.ª: `already_present`). Load `loaded`, load_id=70, inserted 24.539, 3 s (2.ª: `already_loaded`).
  - Risaralda: extract `86437341-f2d7-43e0-933f-d59efd1bddf9` (committed; rows_updated 2026-07-06; 453.925 filas; 91 archivos; 62 s; la 2.ª corrida da `unchanged`). Normalize `created`, fingerprint `7ce6a87e…a549`, 8.878 filas, 453.925 vehículos, 9 s (2.ª: `already_present`). Load `loaded`, load_id=71, inserted 8.878, 4 s (2.ª: `already_loaded`).
  - Placa: escaneo de los 91 payloads raw de Risaralda con la identidad reader: 0 claves `"placa"`.
- `pits transform build`:

  | Selector | PASS | WARN | ERROR | rc | Tiempo |
  |---|---|---|---|---|---|
  | `tag:vehicle_fleet` | 134 | 0 | 0 | 0 | 28 s |
  | `tag:divipola` | 125 | 0 | 0 | 0 | 20 s |
  | `tag:fleet_brand` | 121 | 1 | 0 | 0 | 16 s |
  | `tag:fleet_brand` (2.ª, idempotencia) | 121 | 1 | 0 | 0 | 15 s |

  El WARN es `assert_regional_pooling_no_weight`: la clase GRUA (12 en Boyacá) no tiene peso porque no hay GRUA ACTIVO PARTICULAR en el RUNT de Boyacá ni de Risaralda. Sus 6 filas quedan con `pooling_status='no_runt_weight'` y `pooled` NULL. Es el comportamiento diseñado.
- Scope (`fct_regional_fleet_brand_scope`): Boyacá `included` 181.817, `excluded_service` 500, `excluded_class` 62; Risaralda `included` 453.922, `excluded_class` 3. Los totales cuadran con el raw: 182.379 y 453.925.
- Pesos (`fct_regional_brand_weight`, publicación 2026-10): 39 filas. AUTOMOVIL: Boyacá 72.610 y Risaralda 87.907. MOTOCICLETA: Boyacá 174.180 y Risaralda 323.366.
- Marts: `fct_regional_brand_share` 1.967 filas; `fct_regional_line_share` 59.381 filas; 17 clases, de ellas 6 con `sample_size_ok`.
- Participación pooled (dato regional real, ponderado por el RUNT; no es nacional):

  | Clase | Marcas |
  |---|---|
  | AUTOMOVIL | CHEVROLET 30,36 %, RENAULT 27,91 %, MAZDA 11,36 %, KIA 6,68 %, HYUNDAI 4,54 %, NISSAN 4,26 % |
  | MOTOCICLETA | YAMAHA 19,02 %, BAJAJ 18,85 %, AKT 16,65 %, SUZUKI 13,25 %, HONDA 10,92 %, VICTORY 3,56 % |

  SIN ASIGNAR pooled: MOTOCICLETA 0,50 %, MOTOCARRO 0,22 %, MOTOTRICICLO 2,34 %.
- No se midió la memoria. Los tiempos de build son bajos. No se hizo `docker compose down`. El raw crece con 2 batches nuevos (37 y 91 archivos); el tamaño en MB no se midió.

**Aprobado (2026-10-14):**

- Hito A de marca y D135–D140 con texto "Aprobado" (`05` E-8). P3 = ponderar por el RUNT; P6 = "Todas + sample_size_ok (Recomendado)"; P8 = extraer sin placa. Plan "Aprobado todo", que incluye P4 a, P5 a, P7 revisión en el PR, P9 a y P10 reparto determinista para el hito B.
- D55: Estado → "Vigente (2026-10-10); ajustada por D140" (D73(b)). §F punto 5: RESUELTA por D140, texto original conservado.
- D141 es la siguiente libre. Ninguna otra fila existente ni celda Estado cambia.

**Pendiente:**

- Revisión final única del diff completo por `revisor-senior` contra `794c168` (D130). Cualquier cambio posterior invalida la aprobación.
- Revisión de Henry de las seeds: P7 (mapa de clases), `brand_alias` y `auteco_line_brand_map`, con sus inferencias (typos, SPEED, AGILITY, CBF y SG).
- Commit de S7, push, PR en draft y CI: no verificados por el documentador. Aviso a Henry "no mergear aún" hasta la aprobación final (D130).
- Hito B (sintético nacional, P10 determinista): no iniciado.
- Memoria del hito: no medida.

**Runbook del hito A (CLI manual; sin DAG, D135):**

- Requisito: perfil `core` arriba (`docker compose up -d`; Postgres en `127.0.0.1:5433`). Desde el worktree, `--env-file` apunta a la ruta absoluta del `.env` del checkout principal (en la corrida, `C:/dev/pits-app/.env`), sin copiarlo (lección 163). Los comandos de abajo abrevian esa ruta como `.env`.
- Migrar: `uv run --env-file .env pits db migrate` (aplica la 0006; salida `database=pits_warehouse applied=N skipped=M`).
- Extraer: `uv run --env-file .env pits extract brand-fleet --source boyaca` y luego `--source risaralda`. `--force` crea un batch aunque `rowsUpdatedAt` no haya cambiado. Sin `--force`, si `rowsUpdatedAt` es igual al del último batch, sale `unchanged`.
- Normalizar: `uv run --env-file .env pits normalize brand-fleet --source boyaca` (y `risaralda`). Salidas: `created` o `already_present`. Es seguro reintentar.
- Cargar: `uv run --env-file .env pits load brand-fleet --source boyaca` (y `risaralda`). Salidas: `loaded` o `already_loaded`. Cada `--source` reemplaza solo el snapshot de su `source_system`.
  - `--fingerprint SHA` fuerza un artefacto concreto. Una regresión da exit 1 salvo `--fingerprint` (D138).
  - `--repair` re-aplica el artefacto si la verificación posterior (conteo, suma y digest) encuentra deriva; sin él, la deriva es exit 1.
- Orden de build (obligatorio): `uv run --env-file .env pits transform build --select tag:vehicle_fleet` y luego `uv run --env-file .env pits transform build --select tag:fleet_brand`. Los pesos leen `marts.fct_parts_demand_fleet`, que pertenece a `tag:vehicle_fleet`.
- Códigos de salida: 0 committed, `created`, `unchanged`, `loaded`, `already_present` o `already_loaded`. 1 permanente: esquema distinto del contrato, fila con `placa` (sin escritura), conservación rota, página > 8 MiB, deriva sin `--repair` o regresión sin `--fingerprint`. 2 uso (Typer). 3 transitorio, seguro reintentar: truncamiento de la extracción, `rowsUpdatedAt` que cambia a mitad de la extracción, lock ocupado (D90), S3 o red.
- Pesos desfasados tras una publicación nueva del RUNT: `runt_fleet_snapshot` reconstruye `tag:vehicle_fleet`, incluido `fct_parts_demand_fleet`, pero no `tag:fleet_brand`. Los pesos regionales quedan desfasados hasta correr el build de `tag:fleet_brand` a mano. No hay DAG que lo haga (D135).
- Huérfanos: `pits storage orphans` reconoce el layout `regional_fleet_brand/`. Una fila con `placa` en una página N deja huérfanas las anteriores.

### Resueltos por D47 y D48 (2026-10-10)

- R1 (grano de `fx_rate`): D47, fecha única; el normalizer expande el rango de la TRM a una fila por día.
- R2 (entidad y grano del parque RUNT) y R3 (marcas validadas con flujo): D48, demanda solo con el parque RUNT `u3vn-bdcy` por clase/geografía; marca/modelo sintético, calibrado con investigación pública.
- Pregunta de dominio (¿parque RUNT por clase como único insumo de demanda?): respondida por Henry, ver D48.

### Decisiones D50 y D51 (2026-10-10)

- T1: derecho de petición a MinTransporte por parque por marca — descartado (D50); se trabaja con fuentes públicas y el sintético de D48.
- Investigación de fuentes de parque por marca: `docs/research/parque_por_marca.md`.
- D51: `vehicle_registration_stat` renombrada a `vehicle_fleet_snapshot` (stock, no flujo).

### Decisiones D52–D56 (2026-10-10, segunda ronda regional)

- D52: desglose sintético marca/línea calibrado con el parque activo de Boyacá (`em3d-hmim`) por clase, aplicado a RUNT `u3vn-bdcy` (corte OCTUBRE 2026) del segmento PARTICULAR. Ajusta D48: de matrículas (flujo) a parque regional (stock).
- D53: la marca es la dimensión primaria del desglose; la línea es secundaria y puede agruparse en `OTRAS`.
- D54: el servicio PÚBLICO (1.100.711 vehículos, corte OCTUBRE 2026) es un segmento de flotas aparte, con comprador `fleet_operator`; no recibe el desglose de D52/D55.
- D55: calibración multirregión con Boyacá y Risaralda (`x9pp-pcn5`), pooling de conteos por clase; `AUTECO` se reasigna a marca real por línea; lo no asignable queda `SIN ASIGNAR`.
- D56: fuera de la demanda: `OFICIAL` y ventas al gobierno; `NO REGISTRA` y `OTROS` quedan fuera del MVP. Las tres categorías se conservan en `vehicle_fleet_snapshot`. Las motos de domicilio se quedan en PARTICULAR.

### Investigación regional de parque por marca (segunda ronda, 2026-10-10)

Fuente: `research/parque_por_marca.md`, sección "Segunda ronda". Estado por región:

- Nacional: no encontrado. Ninguna fuente pública nacional con marca.
- Segunda fuente con marca encontrada: Risaralda `x9pp-pcn5` (datos 2026-07-06; "registrado", sin `servicio` ni `estado`). Se suma a Boyacá `em3d-hmim` (datos 2024-08-30; ACTIVO; casi solo PARTICULAR).
- Parcial: Floridablanca `g7i9-xkxz` (datos 2023-02-10; automóvil PUBLICO, HYUNDAI 68,4 %), AMCO Pereira `fvnt-frpb` (datos 2020-11-07; solo transporte público), Fusagasugá `aj2e-7jwg` (datos 2026-06-01; muestra de 48.636 filas).
- No encontrado: Bogotá; Medellín y Cali (parque sin marca); Bucaramanga; Atlántico `n4ic-hiug` (datos solo hasta 2022).
- Caldas `dkxf-ikd7` (datos 2020) y Barbosa `syiu-8mvf` (datos 2020, título 2018): no vigentes. La fecha "actualizado 2026" de la primera ronda era la de metadatos.
- Corte RUNT `u3vn-bdcy`: OCTUBRE 2026 (ACTIVO 22.613.691; INCONSISTENTE 41.349; total 22.655.040). El corte AGOSTO 2026 citado en `08` ya no existe en la fuente (ver §7).

### Spike de storage S3: SeaweedFS 4.48 (2026-10-10, rama `spike/seaweedfs`, mergeada a `main` en PR #9)

Detalle completo en `docs/spikes/seaweedfs.md`. Resultados:

- Imagen `chrislusf/seaweedfs:4.48` inspeccionada (entrypoint, `Cmd` = `mini`, sin variables AWS); un contenedor `server -s3` con `mem_limit` 512m, `GOMEMLIMIT` 400MiB, solo `127.0.0.1:8333`, healthcheck `/healthz`.
- Tests de contrato (boto3 1.43.111, path-style): 14/14 con `-m contract` y 30 offline, sin `xfail`. Cubren buckets, objetos, Unicode, re-subida, multipart de 128 MiB con hash, versioning, delete markers, Object Lock COMPLIANCE/GOVERNANCE y legal hold.
- Persistencia: objeto testigo legible tras `docker compose down` (sin `-v`) y `up -d`, con hash idéntico.
- Memoria del cgroup (`memory.peak`): 420,2 / 440,5 / 456,8 MiB en tres corridas no comparables (82–89 % de 512 MiB); sin OOM. Reposo ~130 MiB. Cliente con tracemalloc ~51,8 MB.
- Disco: +128 MiB con un objeto de 128 MiB; liberado al borrar el bucket.
- No probado: s3fs y dbt (solo boto3); identidades distintas de la admin (no se probó Object Lock con identidad sin bypass); validación a 768m (hecha en el paso 2, D63); VPS (Linux nativo).
- Limpieza pendiente: el volumen `pits_spike_seaweedfs_data` se conserva (borrarlo es decisión de Henry). El contenedor está apagado.

### Decisiones D57–D59 (2026-10-10, cuestionario)

- D57: storage SeaweedFS 4.48 (`server -s3`) reemplaza a MinIO; memoria M1 (`mem_limit` = `memswap_limit` 768m, `GOMEMLIMIT` 600MiB, no validado aún; validado y ajustado a 500MiB por D63, ver §3 "Fase 1, paso 2"); raw inmutable opción A (write-once por `batch_id` + versioning en el bucket raw).
- D58: marker `contract` excluido por defecto (`addopts`); CI sin tests de contrato hasta tener job con SeaweedFS. CERRADO (D115, 2026-10-13): el job `contract` del CI levanta SeaweedFS con el compose y corre `pytest -m contract` completo (incluye los 2 e2e contract+pg). Texto original, conservado: "CI sin tests de contrato hasta tener job con SeaweedFS."
- D59: la demanda y el desglose sintético usan solo `ACTIVO`; `INCONSISTENTE` (41.349) se conserva en `vehicle_fleet_snapshot` pero no entra en la demanda.

### Flujo de trabajo (D44, D45)

- `/orquestar`: arquitecto -> implementador -> revisor-senior -> documentador.
- Henry aprueba solo el plan y el Pull Request. `main` cambia solo vía PR.
- Las ingestas recurrentes van en Airflow, no en agentes.
- Siguen requiriendo aprobación: decisiones D nuevas, preguntas de dominio, comandos destructivos, comandos al VPS y 3 revisiones fallidas seguidas.

## 4. Preguntas abiertas

Las de `05_decisions_log.md` §F. Ninguna bloquea el primer paso de Fase 1.

1. Unidades finales de `quantity_unit`.
2. Normalización geográfica con código DANE desde el MVP o después. RESUELTA por D121–D128 (hito DANE/DIVIPOLA, §3; decisión de Henry 2026-10-13). Texto original conservado. Evidencia nueva (`08_market_research.md`, Obj. 6): DIVIPOLA existe como dataset oficial de DANE (`gdxc-w37w`, 1.122 filas, corte 30-dic-2024), pero `u3vn-bdcy` no trae código DANE, solo nombre de municipio. Inferencia de 08: si se usa DANE, Fase 3 necesita una tabla de equivalencias de nombres (tildes, "BOGOTA" vs "BOGOTÁ, D.C."). La decisión sigue siendo de Henry y se vuelve necesaria al llegar a Fase 1b.
3. Reputación comercial: score único o separado buyer/seller.
4. Historial de precio e inventario: core Fase 3 o extensión SCD2.

## 5. Próximo paso — Fase 1

Ordenado por ruta crítica: cada paso depende del anterior. Consistente con D40 (fases por capacidad demostrada), `04_infra.md` §3, §7, §8, §10 y D5/D44.

### Paso 1 — hecho (D49)

**Paso 1: esqueleto del proyecto Python.** Cerrado; ver §3. `pyproject.toml` con `uv`, paquete, CLI Typer, pytest y ruff. Incluye un workflow mínimo de GitHub Actions que solo corre `ruff check`, `ruff format --check` y `pytest -q`, como habilitador. Esto difiere de `01_project_brief.md` §10, que ubica GitHub Actions en Fase 5: allí la capacidad demostrada es el CI completo (lint, unit tests y `dbt build`), que sigue en Fase 5 (D40). Mover CI mínimo a Fase 1 se formalizó en D49 (atiende R6 de `00_review_findings.md`); el CI completo sigue en Fase 5. Va primero porque sin poder testear y correr código ningún otro paso es verificable. Flujo: `/orquestar`, plan aprobado por Henry, rama propia, PR.

### Paso 2 — hecho (D60–D63, en PR)

Evidencia en §3. Pendientes técnicos heredados de D57 (no bloquean el paso 3):

- Validación en VPS OVH: requiere confirmación explícita de Henry (regla 10).
- Volumen `pits_spike_seaweedfs_data` conservado con datos de prueba: borrarlo (`docker volume rm`) es decisión de Henry.
- Disco C: 29 GB libres (`df -h /c` tras la medición del paso 2, 2026-10-10). Las mediciones son de Docker sobre WSL2; el VPS es Linux nativo.

### Paso 3 — hecho (D64–D67, mergeado en PR #12)

Evidencia y cómo reejecutar en §3. Se escribe cada página como `payload-NNNNN.json` con `IfNoneMatch="*"` (D62) y objetos ≤ 8 MiB con `put_object` secuencial (D65); no hay multipart ni `TransferConfig`. Medición de memoria con el criterio de D63: 3/3 corridas `-m contract` (26 tests; medidas antes de añadir los 2 últimos tests de contrato de TRM).

### Próximo paso — hito técnico TRM: normalización (D47), replay desde raw, reconciliación 412 y loader

**Estado: IMPLEMENTADO en PR** (rama `feat/trm-normalize`, worktree `C:\dev\pits-app-trm`, apilada sobre `chore/agents-preflight`, PR #14). Plan aprobado por Henry el 2026-10-11 (literal: "Aprobado todo, continua e implementa"): pasos S1–S7 y D74–D77. Pasos S1–S6 implementados y S7 documentado; evidencia en §3 "Fase 1, hito TRM normalize" (reportada por el orquestador, 2026-10-11). Pendiente: revisión independiente del diff completo, commit final, apertura de PR y CI; ninguno verificado aquí. Loader a Postgres, dbt, Airflow, parquet y apps quedan fuera de este hito.

**Siguiente paso sugerido (hito loader fx_rate, §3; superado por el hito dbt, §3 y §5):** dbt sobre `landing.fx_rate` (hito siguiente según D78), sin fecha; no iniciado al cerrar el loader. El loader está implementado en la rama, con corrida real OK (§3). Fase 1b (RUNT `u3vn-bdcy`) sigue sin orden decidido por Henry. Descripción previa del hito (2026-10-10), conservada; los puntos actualizados por D74–D77 se marcan en línea. **Prerrequisito cumplido: PR #12 (paso 3) mergeado en `main`, verificado con `gh pr view`.** Rama apilada: `feat/trm-normalize` sale de `chore/agents-preflight` (no de `main`), por instrucción de Henry (2026-10-11). Este hito es técnico de Fase 1 y va separado del alcance de producto (§1-bis): no implica apps, OLTP, outbox ni orden comercial.

- Entrada (D76(a)-(b), reemplaza "el último batch committed"): todos los manifests committed de `superfinanciera_trm`/`32sa-8pi3`, validados estrictamente y ordenados por `commit_order = (extraction_date, finished_at, batch_id)`. Baseline = último `full` más los batches posteriores en orden ascendente; sin `full` committed, la corrida falla. Se leen desde `pits-raw` sin volver a llamar a la API. El loader no entra en este hito (Fase 3, `01` §10, D40).
- Salida: `fx_rate` (`03_data_model.md` §26) con una fila por día calendario del rango `vigenciadesde`–`vigenciahasta` (D47). Fines de semana y festivos heredan la TRM vigente. Grano: `rate_date` + `currency_from` + `currency_to`. Artefacto: `fx_rate.csv` + `manifest.json` en `pits-normalized` (D74, D76(e)).
- Monedas: solo el par USD→COP con `rate` = COP por 1 USD y unidad `COP` obligatoria (D77, aprobada 2026-10-11; solo para la TRM, no restringe `fx_rate` genérica). Henry pidió "Solo COP y USD" (2026-10-10).
- Dedupe: sustituido por la política de D76(b)-(c). `full` reemplaza el estado; `since` borra la cola `vigenciadesde ≥ S` e inserta; `incremental` hace upsert `> from_exclusive`; gana el último aplicado. Ya no se usa "el batch committed más reciente" como fuente de la fila por fecha. Mismos inputs producen el mismo CSV y fingerprint (D76(e)).
- Replay: reconstruir la salida completa desde el raw, sin tocar la fuente. El raw conserva el rango original (D47).
- Tests: unitarios de la expansión y del dedupe; replay sobre `MemoryRawStore`; validaciones de dominio (§7).
- Reconciliación de 412 por hash (D65, lección 83): ante un 412 se compararía el hash del objeto existente con el del payload propio antes de fallar. Cambia la limitación aceptada de D65, así que requiere una D nueva aprobada antes de implementar (regla 4). Resuelto por D75 (aprobada 2026-10-11): verificación de bytes por sha256 y longitud ante 412; implementada en S3 (§3).
- Loader a Postgres: su diseño (schema, tablas, carga) no está decidido. Requiere decisión propia antes de implementar; ver `04_infra.md` §8.3 y D70 (el warehouse no recibe escrituras de las apps). Fuera de este hito (D74): queda en Fase 3 (`01` §10, D40).

Contexto del storage (paso 2): MinIO comunitario ya no se distribuye (repo `minio/minio` archivado 2026-04-25, imágenes `minio/minio` y `minio/mc` en 404 en Docker Hub, CVE altos sin parche libre, p. ej. CVE-2026-41145, GHSA-hv4r-mvr4-25vw); se usa SeaweedFS. `04_infra.md` §8.1 guarda `manifest.json` junto al payload en el storage, así que Postgres no es requisito del manifest.

### Siguiente paso — decide Henry (tras el hito A de marca)

Sin iniciar. Pendiente de este hito: revisión final única por `revisor-senior` contra `794c168` (D130); revisión de Henry de las seeds (P7, `brand_alias` y `auteco_line_brand_map`; `05` E-8, notas 4 y 5); commit de S7, PR en draft y CI (no verificados por el documentador). Las opciones siguientes están registradas como opciones, no como decisiones. Cada una requiere plan aprobado por Henry (D45) y una D propia si cambia el modelo o las métricas.

1. Hito B: sintético nacional de marca y línea, con reparto determinista (P10). Henry lo eligió como siguiente hito en el literal "Merged, marca sintetica"; no hay plan propio aprobado.
2. Metabase sobre los marts de demanda (`marts.fct_parts_demand_fleet`, `marts.fct_parts_demand_scope`) y los regionales (`marts.fct_regional_*`). Metabase ya está desplegado (D8). El rol `pits_reader` ve `marts` (D86); antes de dar acceso a terceros, hace falta la decisión de acceso (§7).
3. Preparar el VPS OVH con Coolify. Cualquier comando contra el VPS requiere confirmación explícita de Henry (regla 10); no se ejecutó ninguno en este hito.
4. WA DOL `brw6-jymh` (D43), tercera fuente del orden de §3, de EE. UU.

### Siguiente paso — decide Henry (tras el hito Demanda; superado por el hito A de marca, §3 y arriba)

Sin iniciar. Pendiente de este hito: revisión final única por `revisor-senior` contra `33525d4` (D130); revisión por Henry del `vehicle_group` del seed (D133); commit de S5, PR en draft y CI (no verificados por el documentador). Las opciones siguientes están registradas como opciones, no como decisiones. Cada una requiere plan aprobado por Henry (D45) y una D propia si cambia el modelo o las métricas.

1. Marca sintética (D131): hito propio con Boyacá `em3d-hmim`, Risaralda `x9pp-pcn5`, seed AUTECO y pooling de D55 (P3, `05` §F punto 5). Recomendaciones del arquitecto pendientes de aprobación: P3 igual peso por región; P4 mantener SIN ASIGNAR visible; P5 sin desglose por marca. RESUELTO por el hito A de marca (2026-10-14): P3 por D140, P4 por D139 y P5 por D140; texto original conservado.
2. Metabase sobre los marts de demanda (`marts.fct_parts_demand_fleet` y `marts.fct_parts_demand_scope`). Metabase ya está desplegado (D8). El rol `pits_reader` ve `marts` (D86).
3. Preparar el VPS OVH con Coolify. Cualquier comando contra el VPS requiere confirmación explícita de Henry (regla 10); no se ejecutó ninguno en este hito.
4. WA DOL `brw6-jymh` (D43), tercera fuente del orden de §3, de EE. UU.

### Siguiente paso — decide Henry (tras el hito DANE/DIVIPOLA)

Sin iniciar. Pendiente de este hito: revisión final única del diff completo por `revisor-senior` contra `497d0e3` (D130); commit del cierre documental S7; el PR #27 pasa de draft a ready solo tras esa aprobación, con aviso a Henry "no mergear aún". El CI del PR no está verificado por el documentador. Cualquier hito siguiente requiere plan aprobado por Henry (D45); no se ha creado ninguna D nueva para elegir.

### Siguiente paso — decide Henry (tras el hito Fase 5, CI completo)

Sin iniciar. Pendiente de este hito: revisión independiente del diff por `revisor-senior` contra `e4f160f`, commit de docs, paso del PR #25 de draft a ready (§3), y required checks en `main` (S7, Henry). Antes del VPS: `-volume.max` y disco (`04_infra.md` §15), además de probe y contrato D119 allí, con confirmación de Henry (regla 10). Cualquier hito siguiente requiere plan aprobado por Henry (D45); no se ha creado ninguna D nueva para elegir.

### Siguiente paso — decide Henry (tras el hito Aislamiento de listeners)

Sin iniciar. Pendiente de este hito: revisión independiente del diff por `revisor-senior`, commit de P4, PR, CI y merge (no verificados por el documentador). Antes del VPS: probe y contrato D119 allí, con confirmación de Henry (regla 10), y decidir la telemetría anónima de weed (D120). El hito A (D112–D116, otra rama) debe rebasar sobre esta entrega. Cualquier hito siguiente requiere plan aprobado por Henry (D45); no se ha creado ninguna D nueva para elegir.

### Siguiente paso — decide Henry (tras el hito Endurecimiento; superado por el hito Aislamiento, §3 y arriba)

Sin iniciar. Siguiente paso: el merge del PR de este hito (endurecimiento), que ya no tiene pendientes de Henry bloqueando; el PR #20 (`feat/runt-fleet-snapshot`) quedó mergeado en `main` como `9ab6893`. Después, opciones registradas, no decisiones: (a) DANE/DIVIPOLA (pregunta abierta 2); (b) demanda de repuestos con el parque RUNT (D48, D52, D55); (c) Metabase sobre `marts`; (d) D propia para JWT o red separada del filer (pendiente 2, diferido), obligatoria antes de cualquier VPS. Cualquiera requiere plan aprobado por Henry (D45). No se ha creado ninguna D nueva para elegir.

### Siguiente paso — decide Henry (tras el hito Fase 1b)

Sin elegir y sin iniciar. Opciones registradas, no decisiones: (a) DANE/DIVIPOLA con tabla de equivalencias de municipio (pregunta abierta 2, §4 y §7; `08` Objetivo 6); (b) demanda de repuestos con el parque RUNT (D48, D52, D55), medida con `vehicle_count` y filtro `ACTIVO` (D59); (c) Metabase sobre `marts.fct_vehicle_fleet_snapshot` y `marts.fct_fx_rate_daily` (el reader ve `marts`, D86), con su propia decisión de acceso antes de darlo a terceros (§7); (d) D67, credenciales de mínimo privilegio para la ingesta del raw (§7). Cualquiera requiere plan aprobado por Henry (D45). No se ha creado ninguna D nueva para elegir.

### Siguiente paso — decide Henry (tras el hito Airflow)

Sin elegir y sin iniciar. Opciones registradas, no decisiones: (a) Metabase sobre `marts.fct_fx_rate_daily` (el reader ya lo ve, D86), con su propia decisión de acceso antes de dar el reader a terceros (§7); (b) Fase 1b con RUNT `u3vn-bdcy` (sin orden decidido; pregunta abierta 2, DANE, §7); (c) D67, credenciales de mínimo privilegio para la ingesta del raw (hoy son admin, §7). Cualquiera requiere plan aprobado por Henry (D45). No se ha creado ninguna D nueva para elegir.

### Siguiente paso — decide Henry (tras el hito dbt; superado por el hito Airflow, §3 y arriba)

Sin elegir y sin iniciar. Opciones registradas, no decisiones: (a) Fase 4, Airflow (D40, D5) para orquestar la carga del loader y el `pits transform build`; (b) Metabase sobre `marts.fct_fx_rate_daily` (el reader ya lo ve, D86), con su propia decisión de acceso antes de dar el reader a terceros (§7). Cualquiera requiere plan aprobado por Henry (D45). No se ha creado ninguna D nueva para elegir.

### Pasos siguientes

3. (Hecho en el paso 3, D64 y D65.) Extractor SODA de TRM: paginación con `$order`, reintentos, token opcional (`X-App-Token`, desde variable de entorno). Escribe cada página en `pits-raw` (SeaweedFS, D57) con la key de D61: `superfinanciera_trm/extraction_date=YYYY-MM-DD/batch_id=<uuid>/payload-NNNNN.json`, con escritura condicional `IfNoneMatch="*"` (D62).
4. (Hecho en el paso 3, D65.) Manifest v1 (`manifest.json`, escrito al final como commit marker) con ID del dataset, atribución y licencia. Mapeo a `03_data_model.md` §3: `ingestion_batch_id` = `batch_id`; `ingested_at` = `finished_at`; `raw_object_path` = `s3://pits-raw/<files[].key>`; `record_hash` = `files[].sha256` (por archivo). `source_record_id` no aplica: la TRM no trae ID de registro; la llave natural es `vigenciadesde`.
5. Parser/normalizer: casteo de strings, validación de schema y salida normalizada que expande cada rango (`vigenciadesde`-`vigenciahasta`) a una fila por día calendario (D47, grano `rate_date` de `03_data_model.md` §26), deduplicada por fecha para que reejecutar un batch no cree duplicados lógicos; tests unitarios. Documentar cómo reejecutar un batch. Nota (2026-10-11): la política de inputs es D76 (baseline + posteriores), no dedupe por batch más reciente. Hecho en el hito TRM normalize (S1–S6, en PR; §3).

Después: Fase 1b con RUNT `u3vn-bdcy` (snapshot mensual). El DAG de Airflow (D5, D44) corresponde a Fase 4 (`01_project_brief.md` §10), con perfil `orchestration` (`04_infra.md` §10.1).

### Contrato de la fuente TRM (`08_market_research.md`, Ficha 2)

| Atributo | Valor |
|---|---|
| Dataset | `32sa-8pi3`, Superintendencia Financiera de Colombia |
| Endpoint | `https://www.datos.gov.co/resource/32sa-8pi3.json` |
| Licencia | CC BY-SA 4.0 |
| Frecuencia | Diaria |
| Filas | 8.360 al 2026-10-03, desde 1991-12-02 |
| Columnas | `valor` number; `unidad` text; `vigenciadesde` calendar_date; `vigenciahasta` calendar_date |
| Tipos en el JSON | Todo llega como string; se castea en el parser |
| Llave incremental | `vigenciadesde` |
| Autenticación | Ninguna; token opcional `X-App-Token` |

### Riesgos

- Fines de semana y festivos: una fila cubre varios días (`vigenciadesde` 2026-10-03, `vigenciahasta` 2026-10-05). El normalizer expande el rango a una fila por día (D47); raw y manifest conservan el rango original.
- Hay al menos 9 datasets TRM duplicados con esquemas distintos (`mcec-87by`, `ceyp-9c7c`, `djvb-n8kv`, `dit9-nnvp`, otros). Fijar `32sa-8pi3` y verificar atribución en el manifest.
- Rate limit sin token: número exacto no encontrado en la documentación. Registrar un token y manejar reintentos con backoff (reintentos implementados en D64; token opcional).
- Paginar siempre con `$order=vigenciadesde` (o `:id`).
- Tope por petición: 50.000 es el límite documentado para Socrata API 2.0; 08 no verificó qué versión sirve datos.gov.co. Con 8.360 filas cabría en una petición, pero se pagina para demostrar el patrón.

### Entregable de Fase 1 (criterios de salida)

- Llamada reproducible, raw payload preservado, batch ID, schema validado, idempotencia, manejo de errores, tests unitarios y documentación de cómo reejecutar un batch.

## 6. Entrada a Fase 1

Condición de entrada cumplida (D46, `08_market_research.md` Ficha 2). Entregable: ver §5.

## 7. Bloqueos y pendientes

- Pendiente (Henry), hito Demanda (2026-10-14): revisar el `vehicle_group` de cada clase en `transform/seeds/vehicle_class_demand_scope.csv` (D133). Es inferencia del orquestador y se revisa en el PR.
- Pendiente (Henry), hito de marca sintética (D131): P3, P4 y P5 siguen sin decisión. Recomendaciones del arquitecto (2026-10-14, no aprobadas): P3, método de pooling de D55 con igual peso por región (`05` §F punto 5); P4, líneas sin marca con SIN ASIGNAR visible; P5, público por marca sin desglose por marca. El hito requiere Boyacá `em3d-hmim` y Risaralda `x9pp-pcn5`, y el seed AUTECO. Los bullets de pooling, líneas sin asignar y desglose público de más abajo siguen vigentes. RESUELTO por el hito A de marca (2026-10-14, "Aprobado todo"): P3 = ponderar por el RUNT (D140); P4 = SIN ASIGNAR visible (D139); P5 = sin desglose por marca del público (D140). Texto original conservado.
- Pendiente (Henry): en su `.env` local, `POSTGRES_HOST_PORT=5433` si no lo puso (D60; 5432 suele estar ocupado por Postgres nativo de Windows).
- Pendiente (Henry): la auditoría semanal (`.github/workflows/claude-recurrente.yml`, D44) no funciona. El `workflow_dispatch` del PR #6 (run 38072914197, 2026-10-10) pasó checkout, setup-uv y `uv sync --locked --no-install-project`, pero falló en `anthropics/claude-code-action@v1`: "Claude Code is not installed on this repository". Acción (Henry): instalar la GitHub App https://github.com/apps/claude en el repo, confirmar el secret `CLAUDE_CODE_OAUTH_TOKEN` y relanzar con `gh workflow run claude-recurrente.yml`.
- Pendiente (Henry): borrar o conservar el volumen `pits_spike_seaweedfs_data` (con datos de prueba). Borrarlo es destructivo: no se ejecutó.
- Pendiente técnico: s3fs y dbt no probados contra SeaweedFS (entran con el primer consumidor). La validación de memoria se hizo con GOMEMLIMIT 500MiB (D63).
- Aprobado como D67 (2026-10-10): en Fase 3, las credenciales de ingesta del raw no tendrán `s3:DeleteObject`. Pendiente técnico de Fase 3: aplicarlo y probarlo.
- Cerrado por D75 (aprobada 2026-10-11; implementado en S3, §3 del hito TRM normalize): riesgo D65 de 412 ambiguo. Antes, si un `put_object` se guardaba pero se perdía la respuesta, el reintento recibía 412 y la corrida salía con exit 1 aunque el objeto fuera propio (lección 83). Ahora, ante 412 se comparan sha256 y longitud: bytes idénticos = `already_identical`; bytes distintos = conflicto permanente (exit 1), sin sobrescribir.
- Riesgo abierto: corridas concurrentes sin lock. Dos corridas a la vez crean dos batches; ambos pueden quedar committed. El watermark sale del batch con `finished_at` más reciente dentro de la partición `extraction_date` más nueva. CERRADO (D106, aceptado con evidencia, 2026-10-13): sin lock; los tests muestran que dos batches TRM incrementales con desorden dan las mismas `(rate_date, rate)`, y que con dos batches RUNT de la misma publicación gana el último. Regla de runbook de ventanas (§3, hito Endurecimiento).
- Riesgo abierto: posible truncamiento. La paginación termina cuando `len(rows) < $limit`; si el servidor limita `$limit` por debajo de 1000, un batch incompleto podría quedar committed como válido. Falta una guarda contra el total de la API. CERRADO (D105, 2026-10-13): `count(*)` con el mismo `$where` antes de paginar; si no cuadra, exit 3 "Truncated extraction", sin manifest.
- CERRADO para `u3vn-bdcy` (D96, Fase 1b, 2026-10-12): el extractor RUNT hace un conteo previo con `$group`, que debe devolver exactamente una publicación; su `count` es el total esperado y la paginación debe llegar a él. El texto de arriba se conserva. Para la TRM, el extractor no cambió en este hito: ese riesgo sigue en su formulación original.
- Riesgo abierto: huérfanos sin inventario. Los batches sin `manifest.json` (corridas abortadas) se acumulan en `pits-raw`; los lectores los ignoran, pero no hay listado ni limpieza. CERRADO el inventario (D107, 2026-10-13): `pits storage orphans` lista los huérfanos en solo lectura (raw 69 de 69 committed, normalized 68 de 68, sin huérfanos). La limpieza no se implementó: no hay `--delete`.
- Riesgo abierto: credenciales admin de SeaweedFS en la ingesta hasta Fase 3 (D67). CERRADO (D104, 2026-10-13): la ingesta usa `pits_writer` y no el admin (D67 implementada). Queda la limitación del pendiente 1, aprobada por Henry el 2026-10-13: el admin todavía puede borrar con DeleteObjects.
- Riesgo abierto: token sobre http. El default de `SODA_BASE_URL` es https; si se configura http, `X-App-Token` viaja sin cifrar. CERRADO (D108, 2026-10-13): un token con base que no sea https da `SodaConfigError` (exit 1), sin mostrar el token; http sin token sigue permitido.
- Riesgo abierto (D65): un manifest corrupto bloquea las corridas incremental y `--since` (exit 1); `--full` no lee manifests previos. Runbook: con D67 solo un administrador puede corregirlo.
- Pendiente de dominio, normalizer (paso 5, hecho en el hito TRM normalize): validaciones de dominio no definidas, por ejemplo rangos con `vigenciahasta` anterior a `vigenciadesde` o rangos solapados. Definir con Henry antes de implementar. Resuelto por D76(d) (aprobado 2026-10-11).
- Pendiente de dominio: "Solo COP y USD" (Henry, 2026-10-10) aplica al normalizer. No está escrito en `03_data_model.md` §26; si es una regla del modelo, requiere una D nueva aprobada antes de implementar (regla 4). Resuelto por D77 (aprobada 2026-10-11), solo para la TRM.
- Pendiente de Fase 4 (DAG): Henry pidió la "Tasa promedio a las 10:00 AM CST". Aclarar antes de fijar el horario: CST es UTC-6 en sentido literal, y la hora de Colombia es UTC-5 todo el año. Además, EE. UU. central usa CDT (UTC-5) hasta el 1 de noviembre de 2026, así que "10:00 CST" puede significar 15:00 UTC (CDT) o 16:00 UTC (CST literal). El dataset se reemplaza a ~23:05 UTC (D66).
- Pendiente técnico: el spike corrió sobre Docker/WSL2 con C: al 95 % (26 GB libres en el spike; 29 GB tras el paso 2); validar en VPS requiere confirmación explícita de Henry (regla 10).
- Pendiente (Henry): KEK de SSE-S3 en texto plano en el filer (el log avisa si falta `s3.sse.kek.passphrase`; cifrado en reposo no habilitado): decidir antes del VPS.
- Pendiente (Henry), método de pooling de D55: suma de conteos u otra ponderación (`05` §F, punto 5). La interpretación aplicada está sujeta al PR. RESUELTO por D140 (P3 = C, ponderar por el parque RUNT); `05` §F punto 5 resuelto. Texto original conservado.
- Pendiente (Henry), líneas sin asignar: en Boyacá, AUTECO deja 8,6 % sin marca real (503 de 5.862 filas, incluye PLUS con 75). PLATINO (Risaralda) no está verificado; ACTIVE 110 y LEGEND quedarían sin asignar. RESUELTO por D139 (P4 = a, hito A de marca, 2026-10-14): SIN ASIGNAR es visible; la seed tiene 499 de 5.862 filas AUTECO en Boyacá (la investigación da 503; 4 filas de diferencia por inferencia, `05` E-8 nota 4), y PLATINO, ACTIVE 110 y LEGEND, sin fuente en Boyacá, quedan SIN ASIGNAR explícito. Texto original conservado.
- Pendiente (Henry), desglose por marca del segmento público: sin calibración aprobada (D54). Floridablanca (2023) y AMCO (2020) son muestras viejas o de un solo tipo de servicio. RESUELTO por D140 (P5 = a, hito A de marca, 2026-10-14): el segmento PÚBLICO no tiene desglose por marca. Texto original conservado.
- Pendiente (docs): `08` cita el corte AGOSTO 2026 de `u3vn-bdcy`, que ya no existe en la fuente (corte OCTUBRE 2026). Corregir la cita por PR; no cambia métricas.
- CERRADO en S7 del hito Fase 1b (2026-10-12, pendiente de merge): `08` corregido con el corte OCTUBRE 2026 (publicado el 2026-10-05; 191.922 filas y 22.655.040 vehículos; API consultada el 2026-10-12, según el orquestador). Las citas de AGOSTO 2026 quedan marcadas como superadas en `08`. `03` §27 ya lo indicaba desde 2026-10-10.
- HECHO (otro agente): `README.md` actualizado (estructura, sección Orquestación con dos DAGs, ventanas de 15:00 y 16:00 UTC, "125 passed", `PITS_IT_FORCE`, comandos del RUNT). Fuera de `docs/`; el documentador no lo editó.
- Infraestructura: solo Docker está confirmado por Henry. El estado del VPS (Coolify, Metabase y demás servicios) no está auditado.
- Pendiente: auditar el VPS (re-medir lo registrado en `04_infra.md` §4–§6, medición del 2026-10-03 no re-verificada, ver R9, y cumplir el checklist de §15). Requiere confirmación explícita de Henry antes de ejecutar cualquier comando contra el VPS. No bloquea el desarrollo local de Fase 1; bloquea cualquier despliegue.
- Pendiente de dominio: pregunta abierta 2 (DANE), antes de Fase 1b. RESUELTA por D121–D128 (hito DANE/DIVIPOLA, §3).
- Hallazgos de severidad alta de `00_review_findings.md` (R1–R3): ninguno vigente; resueltos por D47 y D48 (ver §3).
- Configuración D73(c) aplicada localmente con plan específico aprobado: arquitecto alineado con los tres productos; `/orquestar` ya exige preflight y checkout/worktree seguro (§1-ter). Entregado en PR desde `chore/agents-preflight`, pendiente de merge; sin prueba end-to-end del ciclo completo.
- Cerrado (Henry, 2026-10-11, literal: "Deja así"): aviso de rango largo D76(f). La corrida real del 2026-10-11 tuvo un rango de vigencia de 6 días y superó el umbral de aviso de 5 días (aviso, no error). El umbral sigue en 5 días; sin D nueva.
- Suite `-m contract` completa repetida tras la vuelta 2 de S6 (2026-10-11): 36 passed; ver §3 "Fase 1, hito TRM normalize". Cerrado.
- Pendientes bajos de S3 aplicados en S4 (`3c4310e`): `raw_store.py:181` usa if/raise en vez de assert y `:194` cierra `resp['Body']` antes de devolver None.
- Deuda técnica: `pits.normalized` depende de `pits.sources.trm` (contract, `FxDay`) y fija la fuente TRM. Parametrizar al llegar una segunda fuente de tasas (D77 no restringe `fx_rate` genérica).
- CERRADA para el fingerprint (Fase 1b, S1, 2026-10-12): el fingerprint vive en `pits.normalized.fingerprint` (D98) y ya no depende de `pits.sources.trm`. Los errores de normalize siguen viniendo de `trm.normalize`. El texto de arriba se conserva.
- Riesgos que siguen abiertos tras el hito: corridas concurrentes del extractor sin lock; truncamiento si el servidor limita `$limit`; huérfanos sin inventario; credenciales admin hasta Fase 3 (D67); disco C: al 97 % (19 GB libres) en la sesión del hito. `pits-normalized` no tiene lifecycle (D74).
- Loader fx_rate a Postgres (D78–D84, §3): implementado, revisado y con corrida real OK. Pendiente: PR y CI.
- CERRADO (2026-10-11, hito dbt, §3): las tres contraseñas de rol (loader, reader y transformer) son distintas en `.env`; Henry cambió la del reader y `pits db migrate` fijó los verificadores. Texto original, conservado sin cambios: Riesgo aceptado (Henry, 2026-10-11, literal: "que tengn la misma m vale madre, siguele"): en el `.env` local `PITS_PG_LOADER_PASSWORD` y `PITS_PG_READER_PASSWORD` tienen el mismo valor, así que quien conozca la del reader puede entrar como loader y escribir en `landing.fx_rate`. Antes de dar acceso al reader a terceros (Metabase) o de pasar al VPS, usar valores distintos; `pits db migrate` vuelve a fijar ambos verificadores.
- Loader: `sslmode=disable` solo en loopback; el VPS requiere una D nueva antes de usar Postgres allí.
- Loader: el verificador SCRAM de las contraseñas queda en el log del servidor si `log_statement` es `ddl` o `all` (`04` §8.3). La imagen usa el default.
- CERRADO (hito dbt, 2026-10-11; D86 y D85–D88): los schemas `staging`, `intermediate` y `marts` los crea el bootstrap, y dbt está implementado (§3). Texto original, conservado: Pendiente de dbt: `staging`, `intermediate` y `marts` (hito siguiente; `04` §8.3).
- CERRADO (Henry, 2026-10-12, literal: "si"): tres ajustes de D85 y D88 confirmados (§3, hito dbt).
- CERRADO (2026-10-12): pico de memoria de Postgres con carga dbt medido, `CRITERIO: OK` (§3, hito dbt). Sigue sin medir la memoria del proceso dbt en el host; se mide al orquestarlo en Fase 4.
- Riesgo abierto (revisión 2026-10-12): el lock de `pits transform` no se coordina con `pits load fx-rate` ni `pits db migrate`; una carga durante `dbt build` puede hacer que tests y mart vean estados distintos de `landing`. Aceptable en local; resolver al orquestar en Airflow (Fase 4). CERRADO (2026-10-12, D90; hito Airflow, §3): load y transform ya compartían la clave de advisory lock por accidente; lo que faltaba era `pits db migrate`. Ahora load toma un xact lock, transform un lock de sesión durante dbt y migrate un lock de sesión en el warehouse; lock ocupado = exit 3. El pool de Airflow (1 slot, `max_active_runs=1`) no sustituye al lock.
- CERRADO (Henry, 2026-10-12, P1): 10:00 America/Bogota (15:00 UTC); la "tasa promedio" es la TRM de `32sa-8pi3` (D92). Cierra el pendiente de horario de Fase 4 ("10:00 AM CST").
- Riesgo abierto (D89–D95, 2026-10-12): las tareas heredan el entorno del scheduler (metadata, Fernet, JWT). El subproceso de `pits` no lo hereda (allow-list, D92).
- Riesgo abierto: credenciales S3 admin en Airflow (D67 pendiente; P6: aceptadas solo en local). CERRADO (D104(d), 2026-10-13): el scheduler ya no recibe credenciales admin de S3.
- Riesgo abierto: si el proceso de la tarea muere por SIGKILL u OOM, dbt puede sobrevivir (fuera del grupo del supervisor).
- Riesgo aceptado (P7, Henry, 2026-10-12): `pits-normalized` crece ~1,8 MB por corrida sin lifecycle (D74).
- Riesgo abierto: SimpleAuthManager guarda la contraseña del admin en texto plano (solo loopback, 127.0.0.1:8080).
- Riesgo abierto: la guarda de ±15 min de los tests `-m airflow` solo se evalúa al inicio, y la suite tarda ~23 min.
- Riesgo abierto: los logs de Airflow (volumen `pits_airflow_logs`) crecen sin limpieza. CERRADO (D109, 2026-10-13): el DAG `airflow_log_retention` borra los `*.log` de más de 30 días y los directorios vacíos; corrida real con `deleted_files=0 freed_bytes=0 removed_dirs=0`. No limpia la metadata DB.
- Riesgo abierto: el separador `:` de `COMPOSE_FILE` en Linux no se probó.
- Riesgo abierto (Fase 1b, almacenamiento): crecimiento permanente de `pits-raw` y `pits-normalized` por publicación y por cada `--force` (hoy 3 batches, unos 151 MB, y 3 artefactos, unos 108 MB; lección 121). No hay lifecycle (D61, D74); la purga es decisión de Henry.
- Riesgo abierto (Fase 1b, dominio): el municipio es el de matrícula (D97). La demanda geográfica mide dónde está matriculado el vehículo, no dónde se usa.
- Riesgo abierto (Fase 1b, dominio): Henry no conoce la marca que indica `INCONSISTENTE` ni la regla de publicación del RUNT. D59 excluye `INCONSISTENTE` de la demanda, pero su significado no está confirmado.
- Riesgo abierto (Fase 1b): DANE sigue pendiente (pregunta abierta 2, §4). El municipio de `u3vn-bdcy` viene como nombre, sin código DANE; D100 normaliza nombres sin unaccent y no usa DANE. CERRADO por D121–D128 (hito DANE/DIVIPOLA, §3): el cruce por código se hace en `marts.map_runt_municipality_dane` y `marts.fct_vehicle_fleet_snapshot_dane`; el fct de D100 no cambia. Texto original conservado.
- APROBADO por Henry (2026-10-13, literal: "merged, acepto tus recomendaciones, sigue"), pendiente 1: D104(c). En SeaweedFS 4.48 el admin SÍ borra con DeleteObjects (multi-delete), aunque se agreguen `s3:DeleteObjects`, `s3:Delete*` o `s3:*` (5 variantes, probe efímero). DeleteObject y DeleteObjectVersion del admin dan 403; writer, reader y anónimo están bloqueados en todo. El texto aprobado decía que la policy también bloquea al admin; ese texto no se sostiene. Limitación aprobada por Henry el 2026-10-13. Mitigación: el admin solo se usa en `storage init` y en los tests contract; test `xfail(strict=True)` `test_policy_denies_admin_multi_delete`, que avisa cuando se corrija.
- DIFERIDO por decisión de Henry (2026-10-13), pendiente 2: riesgo nuevo. Requiere una D propia antes del VPS. El filer (:8888) y el master (:9333) de SeaweedFS responden sin autenticación desde la red Docker `pits_default` (verificado desde el scheduler). Por la API HTTP del filer se puede borrar sin pasar por las identidades ni la policy. Desde el host no son accesibles. Mitigación prevista: una D propia (JWT en `security.toml` o red separada) antes de cualquier despliegue en el VPS. CERRADO (D117/D118, 2026-10-13, aprobado por Henry: "Si, apruebo todo, repo publico"): el master y el filer escuchan solo en loopback dentro del contenedor (D117); el gRPC de S3 y las escrituras HTTP del filer exigen la key de `security.toml` (D118). Verificación en vivo en §3 del hito Aislamiento. Riesgos residuales en D120 (líneas siguientes).
- Riesgo abierto (Endurecimiento): buckets `pits-contract-*` con retention compliance. Evidencia de la revisión final (2026-10-13, reportada por el orquestador): hoy hay 0 buckets `pits-contract-*`. Los de COMPLIANCE, con 2 min de retención, los purga la corrida `contract` siguiente, como dice D58. El aviso "retention still active" solo aparece si se vuelve a correr antes de 2 min y es transitorio. No contradice D58.
- Riesgo abierto (Endurecimiento): `/opt/pits/src` sin compilar (D111); compilarlo requiere una D nueva.
- Riesgo abierto (Endurecimiento): si cambia el JSON de identidades hay que recrear `seaweedfs` (el s3.json se monta al arrancar).
- Riesgo abierto (Endurecimiento): `docker-compose.spike.yml` sigue con `AWS_*` (independiente de D104); no levantarlo junto con `core`.
- Riesgo aceptado (D120, Henry 2026-10-13): `LifecycleDelete` en 18333 no tiene efecto mientras no haya lifecycle (D61, D74).
- Riesgo aceptado (D120): master y filer son accesibles dentro del propio contenedor; `docker exec` ya es admin.
- Riesgo aceptado (D120): las lecturas del filer van sin firma, pero solo por loopback.
- Riesgo aceptado (D120): 8333 sigue abierto a contenedores con credenciales (por diseño, D104).
- Riesgo aceptado (D120): de 18333 solo se verificó `RemoveIdentity`; los demás métodos IAM comparten `checkAdminAuth` según el código.
- Riesgo aceptado (D120, g): el mantenimiento pasa a ser `docker exec pits-seaweedfs weed shell`.
- Pendiente antes del VPS (D120, f): telemetría anónima de weed activa por defecto (el log lo menciona); decidir antes de desplegar.
- Pendiente antes del VPS (D120): correr el probe `scripts/probe_seaweedfs_isolation.sh` y el contrato D119 allí, solo con confirmación de Henry (regla 10).

- Riesgo abierto (Fase 5, CI): el paso "Free disk space" depende del layout del runner. Según el orquestador, `ubuntu-latest` migra a Ubuntu 26 el 19 de octubre de 2026; el documentador no verificó esa fecha en una fuente. Revisar el paso antes de esa fecha (D115).
- Riesgo abierto (Fase 5, VPS): el agotamiento de volúmenes de SeaweedFS por disco libre (`-volume.max=0`) puede darse también en el VPS. Candidata a una D antes del VPS; no fijar `-volume.max` en compose sin esa D (D115; `04_infra.md` §15).
- Riesgo aceptado (D114): los post-steps (por ejemplo, checkout y la caché de setup-uv) heredan el env del job, con los secretos efímeros enmascarados con `::add-mask::`. No se pueden vaciar; el upload del junit sí los vacía a nivel de step.
- RESUELTO (Fase 5, `5682c5a` (cambio) y `7a4d3b8` (arreglo del literal), validado en el run 38419204583, reportado por el orquestador): el filtro dejaba fuera los dos e2e con ambos markers (`tests/contract/test_fx_rate_load_e2e.py` y `tests/contract/test_vehicle_fleet_load_e2e.py`). Ahora `contract` corre `-m contract` completo (§3).
- Riesgo abierto (DANE/DIVIPOLA): el tiempo del job pg del CI crece por los tests dbt; cada build tarda unos 15–20 s y el timeout del job es de 30 min.
- Riesgo abierto (DANE/DIVIPOLA): no hay IT `-m airflow` ni e2e contract+pg para DIVIPOLA.
- Riesgo abierto (DANE/DIVIPOLA): los tests usan DIVIPOLA sintético; no hay fixture con datos reales por la licencia CC BY-SA en un repo público.
- Riesgo abierto (DANE/DIVIPOLA, dependencia de orden): `tag:vehicle_fleet` necesita `dim_municipality` y `tag:divipola` necesita los modelos del RUNT; si falta la dimensión, solo fallan los nodos DANE (lección 154). Runbook en §3.

- Pendiente (Henry), seeds del hito A de marca (D139, 2026-10-14): (a) el mapa de clases P7, `transform/seeds/regional_vehicle_class_map.csv`, con inferencias marcadas para revisión en el PR (MICRO BUS, TRACTO-CAMION, CAMION D.TROQUE, MINI BUS, AMBULANCIA, VAN, MOTO TRACTOR, NA, AUTOMOVIL ELECTRICO, MOTOCICLETA ELECTRICA y SIN CLASE); (b) `transform/seeds/brand_alias.csv`, con solo alias observados (AUTECO BAJAJ, AUTECO VICTORY, AUTECO KYMCO; AUTECO KAWASAKI no existe en las fuentes); (c) `transform/seeds/auteco_line_brand_map.csv`, con las inferencias (typos, SPEED, AGILITY, CBF y SG) y 43 líneas `SIN ASIGNAR` explícitas. Se revisan en el PR; no se han aprobado.
- RESUELTO (hito A de marca, P8 = b "Extraer sin placa", D136, 2026-10-14): la placa no se extrae de Risaralda. El escaneo de los 91 payloads raw dio 0 claves `"placa"`. El riesgo residual de huérfanos sigue abierto abajo.
- Riesgo abierto (hito A de marca, pesos desfasados): `runt_fleet_snapshot` no construye `tag:fleet_brand` (D135). Tras una publicación nueva del RUNT, los pesos de `marts.fct_regional_brand_weight` quedan con la publicación anterior hasta el build manual de `tag:fleet_brand`, después de `tag:vehicle_fleet`. Mitigación: runbook de §3. Automatizarlo requiere una D propia.
- Riesgo aceptado (hito A de marca, GRUA sin peso): GRUA (12 vehículos en Boyacá) no tiene peso en ninguno de los dos RUNT de calibración. Sus filas quedan `no_runt_weight` con warn (`assert_regional_pooling_no_weight`). Es el comportamiento diseñado (D140); no se corrige con un fallback.
- Riesgo abierto (hito A de marca, huérfanos): si una página N de la extracción trae `placa`, la extracción sale con exit 1 y deja huérfanas las páginas anteriores, igual que en DIVIPOLA. `pits storage orphans` las lista. No hay limpieza automática (D107).
- Riesgo abierto (hito A de marca, crecimiento del raw): cada corrida con cambios agrega batches en `pits-raw` y artefactos en `pits-normalized`. En la corrida del 2026-10-14 se añadieron 2 batches (37 y 91 archivos); el tamaño en MB no se midió. Sin lifecycle (D61, D74); la purga es decisión de Henry.
- Riesgo abierto (hito A de marca, dominio): los datos son de dos departamentos con cortes distintos (Boyacá 2024-08-30; Risaralda 2026-07-06). Risaralda no permite filtrar servicio ni estado (D55), así que su calibración incluye PÚBLICO y OFICIAL. El segmento PÚBLICO no tiene desglose por marca (D140).

## 8. Regla para la siguiente conversación

Antes de agregar una herramienta o entidad nueva, responder:

1. ¿Qué problema del negocio o del pipeline resuelve?
2. ¿Qué habilidad de Data Engineering demuestra?
3. ¿Cuál es el grano o contrato de datos?
4. ¿Cómo se prueba?
5. ¿Cómo se recupera/reprocesa si falla?
