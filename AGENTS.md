# Codex Duo project workflow

This project uses the user's saved Codex Duo defaults for development tasks automatically.
This is an explicit project preference; no slash command or repeated setup is required.

- Before implementation or bug-fix work, load the `codex-duo` skill and read `codex_duo_defaults`
  with the actual current chat project cwd as explicit `project_root` on every codex_duo_* call. Use the actual saved worker model, effort and turn limit.
  If the plugin tools have not refreshed, read `plugins/codex-duo/skills/codex-duo/SKILL.md`
  and use its local `codex_duo_workflow.py defaults` helper.
- Follow the saved activation mode. `automatic_project` routes user-requested development
  through the current chat coordinator and supported native workers, bounded by saved
  parallel count, actual host capacity and shared total turn limit. `manual` requires the user
  to ask for Codex Duo. The current user request supplies the task scope.
- Read-only checks, ordinary questions, configuration updates, and an explicit request
  not to launch models do not start workers. A worker must never recursively invoke Codex Duo.
- Keep task JSON and handoff files internal. Do not ask the user to copy paths, select
  the same models again, or repeat an existing authorization.
- Use the native worker only if its discovered tool supports the saved model and effort.
  If unavailable, disclose the limitation and continue independently authorized work in
  the current chat; do not silently substitute a worker or launch a separate CLI model.
- Changes to saved defaults affect subsequent tasks. Do not modify preferences automatically,
  or reset the per-task worker turn budget by creating another task ID.
- Do not create user-owned chats unless explicitly requested. Preserve unrelated files
  and global configuration. Do not commit, push, or rewrite history without user instruction.
- Verify relevant changes with `python3 -B -m unittest discover -s tests -v`.
  When shared panel sources change, rebuild with `node native-build/build.mjs`, then inspect
  the actual panel. Offline tests do not prove native model execution.

- Menu project selection only edits that project; it never reroutes Codex chats. New projects
  require explicit automatic enable/save to add a managed AGENTS.md block. Ordinary reads and
  switching never enable projects. Existing chats may need one explicit `$codex-duo` call or reload.

<!-- codex-duo:begin -->
## Codex Duo project workflow

For user-requested implementation or bug fixes, load the `codex-duo` skill and read
`codex_duo_defaults` with the actual current chat project directory as `project_root`.
Pass this same explicit root to every codex_duo_* call; menu selection never routes chats.
Resolve project overrides before global defaults. Follow saved activation:
automatic_project uses this chat and supported native workers, bounded by saved parallel
count, actual host capacity and shared total turn limit; simple tasks use one;
manual requires the user to request Codex Duo. Ordinary questions, read-only checks,
configuration changes and explicit no-model requests do not start workers.
Workers must not recursively invoke Codex Duo. Preserve task scope and existing authorization;
do not create chats, commit, publish or change global configuration without a user request.
<!-- codex-duo:end -->
