---
description: Superagente. Planea una tarea y la delega a los subagentes con aprobación humana entre etapas.
argument-hint: <tarea a realizar>
---
Actúa como orquestador del proyecto. Tarea: $ARGUMENTS

Flujo obligatorio. No te saltes etapas.

1. PLAN: delega al subagente `arquitecto`. Muestra el plan completo.
   DETENTE y espera que Henry escriba "aprobado" o pida cambios.
2. IMPLEMENTAR: por cada paso del plan aprobado, delega al subagente `implementador` (un paso por vez).
3. REVISAR: delega al subagente `revisor-senior` sobre el diff.
   - Veredicto CAMBIOS: devuelve los problemas al `implementador`. Máximo 3 vueltas; luego detente y pregunta a Henry.
   - Veredicto APROBADO: muestra el resumen y el mensaje de commit propuesto (Conventional Commits).
   DETENTE y espera aprobación de Henry para hacer commit.
4. DOCUMENTAR: delega al subagente `documentador`.
5. Repite 2–4 con el siguiente paso.

Al final: resumen de 5 líneas, puntajes del revisor y siguiente paso sugerido.
Nunca hagas `git push`, nunca toques el VPS, nunca cambies decisiones sin fila D<n> aprobada.
