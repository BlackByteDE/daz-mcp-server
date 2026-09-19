# Skill: Scene Architect
Tools for scene layout, hierarchy, and library management.

## Scene & Hierarchy
- `daz_scene_info`: Snapshot of the scene.
- `daz_get_node_hierarchy`: Skeleton/tree mapping.
- `daz_set_parent`: Attaching props or organizing the tree.
- `daz_get_scene_layout`: Full spatial map.

## Batch Operations (Performance)
Use these for 5-10x speedup when changing 3+ items:
- `daz_batch_set_properties`, `daz_batch_transform`, `daz_batch_visibility`, `daz_batch_select`.

## Spatial Analysis
- `daz_get_world_position`, `daz_get_bounding_box`.
- `daz_check_overlap`: Collision/penetration detection.
- `daz_find_nearby_nodes`: Find items within a radius.

## Content Library
- `daz_list_categories`, `daz_browse_category`: Navigating `.duf` files.
- `daz_search_content`: Keyword search across the library.
- `daz_load_file`, `daz_load_product`: Load by path or product name.
- `daz_check_compatibility`: Verify an asset works with a given figure.
- `daz_save_prop_asset`: Save a node as a reusable Prop/Figure Support Asset (`.duf` +
  geometry) into a configured content directory — headless equivalent of
  File > Save As > Support Asset > Prop Asset. `output_path` must resolve inside a
  configured content directory (see SKILL_DAZSCRIPT.md's "Content-Library asset export"
  section for the BaseDataPath/errCode 98 gotcha).

## Materials
- `daz_list_materials`, `daz_get_material`: Inspect surfaces on a node.
- `daz_set_material_property`: Set a surface property (color, reflectivity, etc.).
- `daz_apply_material_preset`, `daz_copy_material`: Apply presets or clone surfaces.
- `daz_convert_to_iray_uber`: Fix content that lands as legacy `DzDefaultMaterial` instead of
  `DzUberIrayMaterial` (common after merging raw/hand-authored `.duf` content) — see
  SKILL_DAZSCRIPT.md's "Materials — DzDefaultMaterial vs DzUberIrayMaterial" for why this happens
  and why the fix goes through shader-preset application rather than editing channel data.

## Scene Utilities
- `daz_save_scene`, `daz_save_scene_copy`: Save current or copy scene.
- `daz_get_selected_nodes`: Query current DAZ Studio selection.
- `daz_delete_node`: Remove a node from the scene.

## Strand-Based Hair
- `daz_create_strand_hair(target_node_label, dialog_timeout=30.0)`: Creates a native
  Strand-Based Hair node fit to a figure via `DzStrandHairCreateNodeAction` — the only
  DazScript path that produces hair with real geometry. Triggers a "Create New
  Strand-Based Hair" confirmation dialog, but **confirms it automatically via Windows UI
  Automation** (`pywinauto`, same dialog class/Accept control as `daz_create_geometry_shell`
  — Bug-Katalog #6/#31) instead of waiting on a human click — no polling loop needed, the
  tool returns the final result directly. Windows-only, same constraint as
  `daz_create_geometry_shell` / `daz_save_wearable_preset` (MCP server must run on the same
  machine as DAZ Studio).
- `daz_list_strand_hair_nodes`: Enumerate `DzStrandHairNode`s with target figure,
  `has_geometry`, and material zone labels. Hair color/shader/thickness go through the
  existing `daz_get_material` / `daz_set_material_property` tools against those zones —
  no dedicated hair-material tool exists or is needed. Guide density/scraggle styling is
  not scriptable at all (DAZ Studio Surfaces pane only).

## Geometry Shell *(fork-only)*
- `daz_create_geometry_shell(target_node_label, dialog_timeout=30.0)`: Creates a native
  Geometry Shell node on a target via `DzNewGeometryShellAction` — the only DazScript path
  that produces a shell with real geometry (`new DzGeometryShellNode()` doesn't work).
  Triggers a "Create New Geometry Shell" confirmation dialog like Strand-Based Hair does,
  but **confirms it automatically via Windows UI Automation** (`pywinauto`) instead of
  waiting on a human click — no polling loop needed, the tool returns the final result
  directly. Windows-only, same constraint as `daz_save_wearable_preset` (MCP server must
  run on the same machine as DAZ Studio). See Bug-Katalog #31 and SKILL_DAZSCRIPT.md's
  "Do NOT use UI Actions/Menus" note for the underlying dialog-blocking behavior.
- `daz_list_geometry_shells()`: Enumerate `DzGeometryShellNode`s with target node,
  `has_geometry`, and material zone labels (same shape as `daz_list_strand_hair_nodes`).
