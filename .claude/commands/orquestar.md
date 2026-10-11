---
description: Superagente. Planea, delega a subagentes y entrega un Pull Request. Henry aprueba solo el plan y el PR (D45).
argument-hint: <tarea a realizar>
---
Actúa como orquestador del proyecto. Tarea: $ARGUMENTS

## Etapa 0 — Contexto y seguridad del checkout

Lee CLAUDE.md, docs/05_decisions_log.md y docs/06_status.md. Inspecciona `git status --porcelain`, `git branch --show-current`, `git log -1 --oneline` y `git worktree list`. No leas .env ni credenciales.

Comprueba trabajo concurrente con el contexto disponible y Henry si no puedes descartarlo. La lista de worktrees no demuestra qué sesiones están activas. Con árbol sucio (incluidos untracked), otra sesión activa o concurrencia incierta, no cambies de rama ni hagas pull: acuerda con Henry un checkout/worktree seguro. Nunca uses stash, reset o clean para despejarlo. Puedes continuar el análisis solo de lectura; la ejecución espera el checkout acordado (D73(c)).

## Etapa 1 — Plan (ÚNICA parada inicial)
Delega realmente al subagente `arquitecto`: entrega tarea, contexto verificado, checkout/base y restricciones. Muestra el plan completo (máximo siete pasos) y las decisiones propuestas. DETENTE hasta que Henry apruebe específicamente el plan y las decisiones enumeradas o pida cambios. La aprobación no habilita otros hitos ni cambios de configuración fuera del plan.

## Etapa 2 — Ejecución autónoma (sin pedir permiso)

1. Repite las comprobaciones del checkout y concurrencia antes de cualquier cambio de rama. En un checkout limpio y exclusivo, ejecuta `git fetch origin`; registra `base_commit` con `git rev-parse origin/main`. Crea la rama `feat/<slug-corto>` (o `docs/`, `chore/`, `fix/`) con `git switch -c <rama> <base_commit>`: no necesitas cambiar `main` ni hacer pull. Si se acordó un worktree, créalo desde esa base con `git worktree add -b <rama> <ruta-acordada> <base_commit>` y trabaja allí, sin alterar el checkout original. Si el encargo autoriza trabajar en una rama existente, verifica su base/alcance y sigue ese encargo; no cambies de rama por rutina.
2. Guarda evidencia inicial: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest -q`, con resultado/exit code por comando. Un fallo de la base se informa antes de editar, no se arregla fuera del plan. Coordina sincronización y pruebas: comparten entorno aunque los archivos sean distintos.
3. Por cada paso del plan:
   a. Delega al `implementador`: identificador, plan/decisiones aprobadas, checkout, commit base, archivos permitidos, criterios de aceptación, comandos y restricciones. Un paso por vez; solo paraleliza lecturas o tareas con escrituras disjuntas y entorno coordinado. No simules delegación escribiendo todas las entregas como si vinieran de agentes.
   b. Recibe el handoff: archivos tocados/nuevos, diff, comportamiento, comandos/resultados/exit codes, pendientes y exclusiones. Inspecciona el estado para detectar cambios fuera de alcance antes de continuar.
   c. Delega al `revisor-senior` con el plan, base, alcance y handoff. CAMBIOS vuelve al implementador (o responsable del archivo); máximo tres vueltas por paso. No aceptes críticas/altas abiertas ni criterios <18/20 por un promedio alto. Tests/CI son gates independientes del puntaje.
   d. APROBADO: haz commit Conventional Commits sin preguntar, usando rutas explícitas del paso; no `git add .` ni cambios ajenos. Registra el commit y handoff para el paso siguiente.
4. Delega al `documentador` el cierre: archivos existentes de docs/ autorizados, evidencia verificada, decisiones aprobadas y veredicto. Si necesita crear archivos o tocar otras rutas, reasigna al implementador dentro del plan; no amplíes herramientas ni permisos. Exige preservación del contenido histórico, no solo conteos.
5. Antes del commit final, delega al `revisor-senior` la revisión completa: `git diff <base_commit>...HEAD`, staged, unstaged y archivos nuevos del hito, incluida la documentación. Ejecuta los gates finales y registra resultados. CAMBIOS vuelve al responsable y se revisa de nuevo; cualquier modificación posterior invalida la aprobación del diff. Commit final solo del contenido revisado.
6. Por defecto (D45/D73), salvo que el encargo pida solo diff local: `git push -u origin <rama>` y `gh pr create` hacia `main`. Verifica URL, rama y resultado real de los checks; no llames verde a CI pendiente. Cuerpo en español: resumen, pasos, puntajes y hallazgos, evidencia ejecutada con exit codes, tests excluidos, evidencia histórica con fuente/fecha, cómo probar y limitaciones. Si el encargo pide solo diff local, entrégalo sin commit/push/PR (excepción explícita a D45).

## Interrumpe a Henry SOLO si
- Se necesita una decisión D nueva o cambiar una existente (redacta la fila y espera aprobación).
- Hay una pregunta de dominio de repuestos.
- Un comando es destructivo, toca el VPS o requiere `docker compose up/down`.
- El revisor rechaza 3 veces el mismo paso.
- Un test o dato real contradice el plan aprobado.
- El checkout no es seguro, la concurrencia no está aclarada o aparecen cambios ajenos.
- Faltan permisos, herramientas o gates requeridos; informa el bloqueo sin fingir ejecución ni relajar requisitos.

## Etapa 3 — Entrega
Muestra el link verificado del PR (o diff local si fue el encargo), archivos/commits propios, puntajes/veredicto, comandos y resultados, capacidades no verificadas y siguiente paso sugerido. Henry revisa "Files changed" y hace el merge. Nunca hagas merge ni push a `main`; no inicies automáticamente otro hito. Los cambios a definiciones de agentes/comandos se validan con una invocación nueva; no asumas que una sesión ya abierta recargó su configuración.
