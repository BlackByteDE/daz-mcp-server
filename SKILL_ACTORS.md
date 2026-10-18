# Skill: Character Choreographer
Tools for morphs, emotions, and movement.

## Morph Discovery
- `daz_list_morphs`: Use `include_zero=False` to see active morphs.
- `daz_search_morphs`: Pattern match (e.g., "smile", "muscle"). Includes morphs at 0 by
  default (`include_zero=True`); pass `include_zero=False` to see only active ones.
- `daz_set_morph`: Set a single morph by name and value.
- `daz_load_morph_pro`: Import a new OBJ morph target via Morph Loader Pro (load mode —
  default `Auto` picks the one DAZ accepts for figure/prop,
  mirroring, overwrite mode, reverse deformations, subdivision, attenuation maps, ERC
  control-property linking). See SKILL_DAZSCRIPT.md's "Morph Loader Pro" gotchas.

## Emotional Direction
- `daz_set_emotion`: Apply `happy`, `angry`, `confident`, etc., with `intensity`.
- `daz_set_body_language`: Full-body posture archetypes (`confident`, `defeated`, `alert`, `relaxed`).
- `daz_direct_gaze`: Eye-direction control (`camera`, `up`, `down`, `left`, `right`, `away`).
- Handles naming differences between Genesis 8 and 9.

## Posing & Interaction
- `daz_look_at_character`, `daz_look_at_point`: Cascading rotation (eyes to torso).
- `daz_reach_toward`: Pseudo-IK for arms.
- `daz_interactive_pose`: Pre-built handshake, hug, or fight spacing.
- `daz_reset_pose`: Clear all pose values to default.
- `daz_save_pose` / `daz_load_pose`: Save/restore figure poses to/from file.

## Wardrobe & dForce
- `daz_list_fitted_items`: See what clothing/hair is fitted to a figure.
- `daz_fit_clothing` / `daz_unfit_item`: Attach or detach clothing. Fitting projects the
  figure's body morphs and JCMs onto the item; pass `morph_projection=False` to fit
  without that (e.g. rigid hair).
- `daz_set_morph_projection(node_labels, enabled=False, remove_existing=True)`
  *(fork-only)*: Switch auto-follow morph projection off (or back on) on already fitted
  items and remove the morphs projected so far; `enabled=None` only reports them. Saved
  with the item. Treat all parts of one unit alike (hair cap + ties + braids), or gaps open
  at the seams. Background: SKILL_DAZSCRIPT.md's "Auto-follow morph projection".
- `daz_run_dforce_simulation`: Run cloth physics simulation.
- `daz_bake_simulation`: Bake sim results; `daz_set_dforce_property` to tune parameters.
- `daz_get_figure_info`, `daz_set_subdivision`: Diagnostics and mesh LOD.
- `daz_export_fbx`, `daz_export_obj`: Export figure/scene to interchange formats.

## Rigging (Extra Bones) *(fork-only)*
- `daz_create_child_bone(parent_label, name, origin, endpoint=None)`: Add a child
  `DzBone` under an existing bone of a figure (e.g. `head`) with an (initially
  empty) skin-binding weight map ready for `daz_set_skin_weights`.
- `daz_set_skin_weights(figure_label, bone_weights)`: Write per-vertex general
  skin weights (dense array or sparse `{index: weight}`) for one or more bones
  and re-normalize the skin binding.
- `daz_get_rigidity_weights(node_label)` / `daz_set_rigidity_weights(node_label,
  weights=None, face_groups=None, material_groups=None, clear=False)`: The rigidity
  weight map (Node Weight Map Brush "Rigid") that rigidity groups use to keep parts
  (buttons, buckles) from stretching under morphs/fitting. Created if missing, saved
  with the asset. Not a dForce map — for dForce pinning use
  `daz_set_dforce_influence_weights`.
- Use for hair-tail/ponytail jiggle rigs or any other runtime bone chain on a
  fitted prop-turned-figure (see `daz_run_transfer_utility` to first convert a
  plain prop into a `DzFigure` with a real skin binding). Both tools call
  `DzSkinBinding.checkAndNormalize()` internally — without it, a
  runtime-created bone binding is silently ignored by the deformer even
  though its weights read back correctly (Bug-Katalog #30). See
  SKILL_DAZSCRIPT.md's "Runtime bone rigging" section for the live-verified
  details and the subdivision vertex-count gotcha.

## Action & Pathing
- `daz_create_character_path`: Animate walking with auto-rotation.
- `daz_arrange_characters`: Formations (semicircle, circle, line).
- `daz_choreograph_action`: Coordinated multi-character sequences.
