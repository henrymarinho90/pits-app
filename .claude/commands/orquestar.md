---
description: Superagente. Planea, delega a subagentes y entrega un Pull Request. Henry aprueba solo el plan y el PR (D45).
argument-hint: <tarea a realizar>
---
Actúa como orquestador del proyecto. Tarea: $ARGUMENTS

## Etapa 1 — Plan (ÚNICA parada inicial)
Delega al subagente `arquitecto`. Muestra el plan completo y DETENTE hasta que Henry escriba "aprobado" o pida cambios.

## Etapa 2 — Ejecución autónoma (sin pedir permiso)
1. `git switch main && git pull`, luego crea la rama `feat/<slug-corto>` (o `docs/`, `chore/`, `fix/` según la tarea).
2. Por cada paso del plan:
   a. Delega al `implementador` (un paso por vez).
   b. Delega al `revisor-senior`. Veredicto CAMBIOS: devuelve los problemas al `implementador`. Máximo 3 vueltas por paso.
   c. Veredicto APROBADO: haz commit (Conventional Commits) sin preguntar.
3. Al final, delega al `documentador` (status y bitácora) y haz commit.
4. `git push -u origin <rama>` y `gh pr create` hacia `main`, con cuerpo en español: resumen, pasos, puntajes del revisor, cómo probar.

## Interrumpe a Henry SOLO si
- Se necesita una decisión D nueva o cambiar una existente (redacta la fila y espera aprobación).
- Hay una pregunta de dominio de repuestos.
- Un comando es destructivo, toca el VPS o requiere `docker compose up/down`.
- El revisor rechaza 3 veces el mismo paso.
- Un test o dato real contradice el plan aprobado.

## Etapa 3 — Entrega
Muestra el link del PR, puntajes del revisor y el siguiente paso sugerido. Henry revisa "Files changed" y hace el merge. Nunca hagas merge ni push a `main`.
