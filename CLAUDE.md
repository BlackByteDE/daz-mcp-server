# CLAUDE.md (Project Index)

## Primary Commands
- `uv sync` - Install dependencies
- `uv run pytest tests/ -v` - Run all tests
- `uv run vangard-daz-mcp` - Run the MCP server

## Skill Modules (Reference with @)
- **@SKILL_DEVELOPMENT.md**: Server architecture, MCP registry, and testing.
- **@SKILL_DAZSCRIPT.md**: DazScript environment, globals, syntax rules, and "gotchas."
- **@SKILL_SCENE.md**: Scene layout, hierarchy, batch operations, and content browsing.
- **@SKILL_ACTORS.md**: Morphs, emotions, posing, interaction, and character movement.
- **@SKILL_CINEMA.md**: Cameras, lighting, animation, shot composition, and rendering.

## Architecture Summary
- **Version:** 0.4.0
- **Bridge:** Connects to DazScriptServer (port 18811)
- **Registry:** 137 tools registered across 13 tool modules.
- **Structure:** Modular — `_mcp.py` holds shared FastMCP instance; `tools/__init__.py` imports all 13 modules so `@mcp.tool()` decorators fire at import time.
- **Phase 4.8:** Lighting Animation — `daz_animate_light`, `daz_create_light_sequence`
- **Phase 4.9:** Shot Planning — `daz_plan_shot`, `daz_create_storyboard`
- **Phase 4.10:** Focus & DOF — `daz_set_focus_point`, `daz_animate_focus_pull`
- **Phase 4.11:** Visual Composition — `daz_set_scene_atmosphere`, `daz_apply_visual_style`
- **Phase 4.12:** Multi-Scene Management — `daz_export_node_config`, `daz_import_node_config`
- **Phase 4.13:** Performance Timing — `daz_time_expression`, `daz_sync_character_beats`
- **Phase 5:** Gap Coverage — `daz_list_materials`, `daz_get_material`, `daz_set_material_property`, `daz_set_morph`, `daz_delete_node`, `daz_list_lights`, `daz_create_light`, `daz_list_cameras`, `daz_create_camera`, `daz_save_scene`, `daz_get_selected_nodes`, `daz_set_render_output`, `daz_reset_pose`
- **Phase 6.1:** Wardrobe — `daz_list_fitted_items`, `daz_fit_clothing`, `daz_unfit_item`
- **Phase 6.2:** dForce Simulation — `daz_run_dforce_simulation`, `daz_bake_simulation`, `daz_set_dforce_property`
- **Phase 6.3:** Pose Library — `daz_save_pose`, `daz_load_pose`
- **Phase 6.4:** Material Preset — `daz_apply_material_preset`, `daz_copy_material`
- **Phase 6.5:** Figure Diagnostics — `daz_get_figure_info`, `daz_set_subdivision`
- **Phase 6.6:** Scene Export — `daz_export_fbx`, `daz_export_obj`

## Render API (DazScriptServer native endpoints)
`daz_render_async`, `daz_render_with_camera_async`, `daz_batch_render_cameras_async` use
`POST /render` and `POST /render/batch` directly (not the script registry). Render IDs have
prefix `rnd-`; `daz_cancel_request` routes these to `POST /render/:id/cancel` automatically.
`daz_render_batch` — new: submit up to 100 variants with per-variant morph overrides.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
