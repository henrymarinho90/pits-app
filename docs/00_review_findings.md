# 00 — Auditoría de consistencia

Última actualización: 2026-10-10
Estado: v1.1 — ediciones del 2026-10-10: R1–R3 marcados como resueltos (D47, D48), notas en R5 y R12, nuevo R20; el inventario y las referencias `archivo:línea` siguen siendo la foto de `main` f3b2cc5 (03 v4, 05 v4, D1–D46). Reemplaza la auditoría integral original, que nunca se versionó

Alcance: consistencia entre `01`–`09` y `CLAUDE.md`. Las referencias a `06` van por sección porque ese archivo se reescribe cada sesión; el resto son `archivo:línea` de la rama `docs/update-status` al 2026-10-10. Esta auditoría solo lista; ediciones posteriores (2026-10-10): R1–R3 marcados como resueltos, notas en R5 y R12, nuevo R20 (ver sección 4).

Método: lectura completa de `01`–`05` y `07`–`09`; `06` en su versión actual. Sumas de `08` recalculadas (top 10 de carros 195.243, tramo 11–20 34.173, total 254.205; tabla de motos de agosto 2026 = 111.896): cuadran. Cifras de D43 y D46 contrastadas con `09` y `08`: coinciden.

## 1. Inventario de versiones y dependencias

| Archivo | Fecha de cabecera | Versión declarada | Dependencias declaradas | ¿Se cumple? |
|---|---|---|---|---|
| `00_review_findings.md` | 2026-10-10 | v1 | Reemplaza la auditoría integral original (no versionada) | Sí. `06 §2 tabla` ya la cita con ese nombre |
| `01_project_brief.md` | 2026-10-03 | v2 | "revisado después de la auditoría integral" (`01:4`) | No verificable: la original no está en git. Contenido desactualizado respecto de D43/D46 y `08` (R6, R7, R12) |
| `02_domain_taxonomy.md` | 2026-10-03 | v11 | Remite a `05` para el historial (`02:26`) y a `03` para el esquema físico | Sí. Residuos de v10 en `02:19` (R13) |
| `03_data_model.md` | 2026-10-03 | v4 | "alineado con `02_domain_taxonomy.md` v11" (`03:4`) | Sí: `02` es v11 y roles/tipos coinciden (`02:307-309` ↔ `03:130-135`). Desalineado con D46/`08` en `fx_rate` y `vehicle_registration_stat` (R1, R2) |
| `04_infra.md` | 2026-10-03 | v2 | Ninguna declarada | Parcial: presenta como medido lo que `06 §7` dice no auditado (R9) |
| `05_decisions_log.md` | 2026-10-10 | v4 | Regla de no borrar decisiones (`05:6`) | Sí: D1–D46 sin saltos; D3, D19, D24, D25 marcadas reemplazadas |
| `06_status.md` | 2026-10-10 | "tras cerrar Fase 0.5 y registrar D43–D46" | Tabla de versiones (`06 §2 tabla`) | Sí: v2/v11/v4/v2/v4 coinciden con las cabeceras; D1–D46 coincide con `05` |
| `07_lessons_learned.md` | 2026-10-09 | sin versión | Ninguna | N/A |
| `08_market_research.md` | 2026-10-03 | sin versión | Remite a `06` (pregunta abierta 2, `08:116`) | Sí: existe en `06 §4` (pregunta 2) |
| `09_us_market_research.md` | 2026-10-09 (3.ª ronda) | sin versión | las mismas convenciones de `08` (`09:5`); D43 | Sí. Referencias cruzadas rotas puntuales (R16) |

Notas: `07`, `08` y `09` no declaran versión; `06 §2 tabla` ya lo refleja. No quedan referencias a `claude_08_*` / `claude_09_*` en ningún `.md`, `.yml` o `.toml` del repo.

## 2. Contradicciones encontradas

Severidad: alta = afecta modelo o métricas; media = afecta plan o fases; baja = redacción, nombres o desactualización.

| ID | Docs implicados (archivo:línea) | Qué dice cada uno | Sev. | Acción sugerida |
|---|---|---|---|---|
| R1 | `03:553` vs `05:70` (D46), `08:246`, `06 §5 Riesgos` | 03: grano de `fx_rate` = "rate_date + currency_from + currency_to", con campos `rate` y `source_reference`. D46: "modelando el rango de vigencia (`vigenciadesde`-`vigenciahasta`)". 08: "El modelo debe usar rango de vigencia, no fecha única." | Alta | **Resuelto por D47 (2026-10-10).** Requiere D nueva (grano y columnas de vigencia de `fx_rate`) aprobada por Henry antes de editar `03` |
| R2 | `03:99`, `03:563`, `03:576` vs `08:10`, `05:70` (D46) | 03: `vehicle_registration_stat` "se integran en dbt según fecha, moneda, marca, modelo o geografía"; esquema "abierto hasta inspeccionar el dataset real del RUNT". 08: `u3vn-bdcy` "no `marca`" (solo clase, servicio, estado, departamento, municipio). D46: snapshot mensual. El nombre "registration" sugiere flujo; el dataset es parque (stock) | Alta | **Resuelto por D48 (2026-10-10).** Requiere D nueva: grano (corte mensual), nombre y columnas de la entidad, y cómo se une a marca/modelo si la fuente no los trae |
| R3 | `08:11-12`, `08:47-48`, `08:212` vs `CLAUDE.md:19`, `01:125`, `01:132`, `08:213` | 08: hipótesis de marcas "Validada: las 7 están en el top 10" (matrículas nuevas = flujo). Regla 5: "Demanda de repuestos se mide con parque automotor (stock), no con ventas/matrículas (flujo)". 01: pendiente "validar participación por marca en el parque automotor". 08 reconoce: "Sin evidencia: no hay parque por marca" | Alta | **Resuelto por D48 (2026-10-10).** Requiere D nueva: qué proxy (si alguno) se acepta mientras no exista parque por marca, o mantener las marcas prioritarias como hipótesis sin validar |
| R4 | `05:69` (D43), `09:99`, `09:551` | D43: "Es FLUJO (transacciones), no STOCK". 09 lo llama "semilla para demanda de repuestos por modelo" y "proxy del parque activo" (09:99, 09:551), aunque advierte "No usar como stock" y "son conteos de transacciones (FLUJO)" | Baja | Requiere D nueva antes de definir cualquier métrica de demanda con WA DOL. Mientras tanto, tratarlo solo como FLUJO (D43) |
| R5 | `CLAUDE.md:19` vs `05` (sin fila), `01:83`, `01:101`, `02:384`, `03:430` | La regla 5 no tiene fila D (solo se menciona FLUJO/STOCK dentro de D43 y D46). 01/02/03 usan "demanda" para eventos del marketplace ("demanda satisfecha e insatisfecha", "mart de demanda insatisfecha"). No es contradicción directa: es ambigüedad terminológica entre demanda de mercado y demanda observada en la plataforma. | Media | Requiere D nueva: formalizar la regla 5 y distinguir "demanda de mercado (parque)" de "demanda observada en plataforma (eventos)". D48 cubre la demanda de mercado; falta distinguirla de la demanda observada en la plataforma. |
| R6 | `01:224-237`, `01:232`, `01:231` vs `06 §3 Orden de fuentes`, `06 §5 paso 1`, `05:70`, `05:76` | 01: fases 0 a 10, sin Fase 1b ni línea EE. UU.; "5 \| GitHub Actions" (CI) después de Airflow. 06: CI en GitHub Actions dentro del paso 1 de Fase 1; Fase 1b (RUNT) antes de WA DOL. D44 usa GitHub Actions para la auditoría semanal (existe `.github/workflows/claude-recurrente.yml`). `06 §5 paso 1` declara la diferencia: CI mínimo (lint y test) como habilitador; el CI completo sigue en Fase 5 | Media | Corregir en `01` tras aprobación de Henry. Si cambia el orden de fases, D nueva (D40 define las fases) |
| R7 | `01:25`, `01:105` vs `05:69` (D43), `09:603` | 01: expansión a "otros mercados de Latinoamérica"; "El mercado inicial es Colombia." D43 y 09 incorporan una línea de EE. UU. (fuente WA, T3 "Requisitos para la web app en EE. UU."). 01 no la contempla (ni en alcance, ni en fuentes `01:140-147`, ni en fases) | Media | Corregir en `01` el alcance. Si EE. UU. pasa a ser mercado objetivo (no solo comparativo), requiere D nueva |
| R8 | `CLAUDE.md:27` vs `01` | CLAUDE.md: `01` contiene "tracks T1/T2/T3, monetización". `01` no tiene ninguno (sin coincidencias de "T1", "T2", "T3", "monetiz"); los tracks T1/T2/T3 están en `09:42`, `09:323`, `09:603`. CLAUDE.md tampoco lista `00_review_findings.md` | Baja | Corregir en `CLAUDE.md` (puntero a `09` o crear la sección en `01`) |
| R9 | `04:39`, `04:51-83`, `07:29` vs `06 §1`, `06 §7` | 04: "Docker Compose para servicios locales"; "Consumo medido del VPS — 2026-10-03" con servicios y RAM. 07: "El VPS tenía servicios sin límite de memoria". 06: no hay `docker-compose.yml`, `pyproject.toml` ni tests; "solo Docker está confirmado por Henry"; el VPS "no está auditado" | Media | Corregir en `04`: marcar §3, §10 como plan y §4–§6 como medición histórica no re-verificada. No ejecutar nada contra el VPS sin confirmación (regla 10) |
| R10 | `04:158-162`, `06 §5 pasos 3 y 5` vs `01:244` | Ruta raw `batch_id=<uuid>`: cada re-ejecución crea un objeto nuevo. 01: "la misma entrada produce el mismo resultado al reejecutarse". `06 §5 paso 5` resuelve la idempotencia en la salida normalizada (deduplicada por `vigenciadesde`), no en el nombre del objeto raw | Baja | Aclarar en `04` §8.1 que la idempotencia está en la salida normalizada, no en la ruta del raw |
| R11 | `03:574` vs `08:110`, `08:14`, `01:143` | 03: `vehicle` viene de "NHTSA vPIC + datos curados/específicos de Colombia según validación". 08: vPIC "no sirve como fuente de verdad de modelos para Colombia" (TVS, Zontes, Ceronte, AKT sin cobertura; Renault parcial) | Media | Corregir en `03` el estado de validación; elegir la fuente de `vehicle` para Colombia requiere D nueva |
| R12 | `01:125`, `01:142-143`, `03:363`, `03:575-576` vs `08:116`, `05:70` | Siguen como "pendiente"/"por validar": hipótesis de marcas, datasets de datos.gov.co, vPIC, fuente de `fx_rate`, RUNT, DANE. 08 ya los inspeccionó; TRM fijada en D46. Persisten pendientes reales: parque por marca y la decisión DANE (`05:81-86`) | Baja | Corregir en `01` y `03` solo el estado de validación, sin tocar el modelo. Parte de `03` resuelta en v5 (§G, D47/D48); queda `01`. |
| R13 | `02:19`, `02:576-578` vs `02:4`, `05:81-86` | 02 declara v11 pero la sección dice "Cambios principales de la v10". 02 lista 3 preguntas abiertas; `05`, `03:635-640` y `06 §4` listan 4 (falta historial de precio/inventario) | Baja | Corregir en `02` |
| R14 | — | Retirado: no es contradicción (ver "Áreas sin contradicciones"). El ID no se reutiliza | — | — |
| R15 | `09:583`, `09:601` vs `05:69`, `09:39` | 09: "PROPUESTA para Henry. No es una decisión."; "Decisión de dominio pendiente para Henry" (WA vs NHTSA Complaints). Resumen y D43: Henry eligió WA DOL. También cita la TRM como "decisión vigente" antes de D46 | Baja | Corregir en `09`: anotar que la propuesta pasó a D43 y que la TRM es D46 |
| R16 | `09:82` vs `08:27` | 09: "cifra Colombia en T1i". T1i (`09:298-321`) no trae el parque; la cifra (14.391.640 motos, ~64 %) está en 08 | Baja | Corregir en `09` la referencia |
| R17 | `09:31` vs `09:239-241` | Resumen: "AutoZone, O'Reilly, Advance y NAPA suman unos USD 60.700 M". El detalle usa GPC Automotive global (USD 15.378.608 mil, con Europa y Australasia); NAPA North America es 9.520.042 y GPC no separa EE. UU. de Canadá. AZO incluye México y Brasil | Baja | Corregir en `09` la redacción del resumen: alcance geográfico no homogéneo |
| R18 | `09:501`, `09:591`, `09:457` vs `09:208`, `09:20`, `09:199` | Ficha 7 y comparativo: IDs de BLS "no se verificaron". T1e: "IDs confirmados" (`cu.item`, FRED). Ficha 5: "no se tiene una" key de Census; resumen y `09:199`: Henry aportó una key y la API respondió | Baja | Corregir en `09` las fichas 5 y 7 (desactualizadas respecto de rondas posteriores) |
| R19 | `09:33` vs `09:645` | Resumen: "No hay mandato federal ni estatal de factura electrónica B2B/B2C." Cuerpo (T3 9.1): marca Inferencia; "sin WebSearch no se pudo descartar exhaustivamente a nivel estatal" | Baja | Corregir en `09` el resumen: "no se encontró", no "no hay" |
| R20 | `08:246` vs D47 | 08: "El modelo debe usar rango de vigencia, no fecha única." D47 fija fecha única con expansión diaria | Baja | Anotar en `08:246` "Superado por D47" (no se edita 08 en este PR) |

Totales: 19 hallazgos (R14 retirado): 3 resueltos (R1 por D47; R2 y R3 por D48) y 16 vigentes. Vigentes por severidad: alta 0, media 5 (R5, R6, R7, R9, R11), baja 11 (incluye R20). Severidad original de los resueltos: alta.

### Áreas sin contradicciones

- Decisiones D1–D42 vs `01`–`04`: sin contradicciones salvo R1, R2, R11 y R5. Verificado en particular D3→D29 (`01:201`, `04:151-173`), D19→D32 (`03:379-403`, `02:346-352`), D24→D26 y D25→D28 (`02:210-264`), D41/D42 (`03:89-93`, `03:130-135`), D9 (`04:93-96`), D8 (`04:78`, `04:218`), D7 (`01:236`, `04:207-209`).
- Decisiones reemplazadas (D3, D19, D24, D25): ninguna sigue reflejada como vigente en `01`–`04`.
- D40 (fases por capacidad demostrada) vs `01:224-237`: coherente (la tabla tiene columna "Habilidad demostrada").
- D44/D45: no contradicen `01`–`04`; `01` no los menciona (son de proceso).
- Nombres de archivo `08`/`09`: D43, D46, `06` y `09` citan los nombres nuevos.
- `05` vs `06` (versión y rango de decisiones): coinciden.
- Cifras de D43 (44.875.179 filas, 2020-01 a 2026-08, NY 12,5 M) y D46 (8.360 filas, 1991, `u3vn-bdcy`): coinciden con `09` y `08`.
- D43 vs D46: coherentes; D43 ya remitía a la TRM recomendada en `08:16`. `05` agrupa por tema, no por número.
- Aritmética de `08` (carros 2025 y motos ago-2026): cuadra.
- Diferencia de conteo `u3vn-bdcy` (191.640 vs 191.293, `08:72`/`08:136`): `08` ya la declara sin explicar (`08:266`); no se reporta como hallazgo nuevo.

## 3. Afirmaciones sin fuente verificable (regla 6)

`01`: la única afirmación de mercado sin fuente es `01:52` ("El inventario de repuestos está distribuido entre tiendas, distribuidores, importadores, talleres, concesionarios, fabricantes y personas naturales"). Es conocimiento de Henry; conviene etiquetarla igual que `02:499` ("experiencia de Henry"). Las marcas de `01:123-134` están rotuladas como hipótesis: cumplen la regla.

`08`: todas las filas llevan fuente y fecha. Debilidades de verificación, no de citación:

- Cifras de ANDI-FENALCO leídas por resumen automático y sin abrir el PDF (`08:6`, `08:37-45`, `08:265`). Antes de publicarlas hay que contrastarlas con el PDF.
- `08:63`: el ensamble local de las 7 marcas de motos se apoya en un directorio de afiliados sin fecha, que la propia fila describe como "no un censo oficial".
- `08:42`: ambigüedad AKT/SYM sin resolver.

`09`:

| Línea | Afirmación | Problema |
|---|---|---|
| `09:32` | "ClearMechanic, el líder regional" | Es autodeclaración del proveedor (`09:318`: "#1 en Latinoamérica" según el proveedor). Redactar como "declara" |
| `09:33` | "No hay mandato federal ni estatal de factura electrónica" | Inferencia por ausencia de evidencia (`09:645`). Ver R19 |
| `09:305` | ProColombia: "más de 6.900 empresas..." | Sin año ni fuente primaria en la página; la propia fila lo descarta como conteo |
| `09:321` | ASOPARTES: COP 29,5 billones | Dato de prensa/gremio de 2022 deducido por contexto; la nota de jul-2026 ($26,3 billones) sin fuente primaria. La conversión a USD mezcla TRM 2026 con ventas 2022 |
| `09:611-612`, `09:623`, `09:627` | Umbrales de nexo, facilitadores y leyes de privacidad | Fuentes secundarias (SSTGB, IAPP), marcadas "Prensa" |
| `09:629-630` | Fechas de leyes de privacidad (3.5) y Ley 1581 (3.6) | Marcadas Inferencia, "NO usar como Hecho"; 3.6 "No consultado" |
| `09:55-56`, `09:65` | Hedges (metodología no reproducible, 18,3 vs 18,2) y MEMA USD 467.000 M ("the market" asumido light-duty) | Calidad media-baja declarada |
| `09:23` | Archivos fuente por ítem en `Phase 0.5 Market Research/us_research/findings/` | Fuera del repo: un tercero no puede verificar la evidencia |

Fuera de alcance, solo como nota: `02:531` declara que `engine_overheating` en motos "no tiene fuente" y `02:533-539` lista fuentes cualitativas sin verificar (incluye redes sociales y España).

## 4. Qué NO se corrigió y por qué

- Esta auditoría solo lista. No se modificó ningún documento existente.
- R1, R2 y R3 quedaron resueltos el 2026-10-10 por D47 y D48 (aprobadas por Henry); se conserva el hallazgo original como registro.
- R4, R5, R11 (y R7/R6 si cambian alcance u orden de fases) tocan modelo de datos, métricas o fases: requieren fila `D<n>` aprobada por Henry antes de implementar (regla 4).
- R8, R10, R12, R13, R15–R20 son desactualizaciones o redacción: se pueden corregir en el doc indicado sin decisión nueva, con aprobación del plan por Henry (D45). No se editaron aquí para no mezclar auditoría y cambios.
- R9: la corrección es de redacción en `04`, pero verificar el estado real del VPS exige confirmación explícita de Henry (regla 10). No se ejecutó nada contra el VPS.
- R14: retirado (D43 y D46 son coherentes); en cualquier caso no se editan filas existentes del log (regla 4).
- Decisión de dominio cerrada el 2026-10-10 (D48): la demanda se mide solo con el parque RUNT por clase (sin marca); marca/modelo se modelan sintéticos.
