# Fork Changelog

All notable fork-specific changes to `vangard-daz-mcp` are documented here.
This fork's version scheme is `<upstream-version>+bb.<n>` — see
[README.md#about-this-fork](README.md#about-this-fork). Upstream changes from
[bluemoonfoundry/daz-mcp-server](https://github.com/bluemoonfoundry/daz-mcp-server)
are not duplicated here — only fork-specific changes are listed below.

## 0.5.8+bb.8 — 2026-09-20

### Fixed

- **`daz_apply_material_preset`'s missing-files preflight reported real,
  present files as missing** whenever their path contained a percent-encoded
  character (Bug-Katalog #23). DSON stores content-relative texture/`.dsf`
  paths URL-encoded (e.g. `%20` for a space, `%203D` for `" 3D"`), but
  `extract_preset_map_paths` (`tools/material.py`) passed those strings
  straight through to the on-disk existence check without decoding them
  first — a file that actually exists at `.../DAZ 3D/Built-in Content/...`
  was compared against the literal string `.../DAZ%203D/Built-in%20Content/...`
  and never matched. Now decodes each extracted path with
  `urllib.parse.unquote()` before the check. The previous `allow_missing=true`
  workaround is no longer necessary for this specific false-positive case.

## 0.5.8+bb.7 — 2026-09-20

### Fixed

- **`daz_get_material` silently hid texture maps bound to a channel**
  (Bug-Katalog #34). It only ever read a property's scalar value
  (`getValue()`/`getColorValue()`) and never checked `getMapValue()` — a
  channel with a real diffuse/roughness/normal texture reported only its
  underlying flat color/number, with no indication a map existed at all.
  `_GET_MATERIAL_SCRIPT` in `_registry.py` now probes `getMapValue()` for
  every property and adds a `map` field (file path or `null`) alongside the
  existing `value` — a channel can carry both at once, with the map
  overriding the flat value visually.
- **`daz_copy_material` dropped texture maps when copying between
  materials**, same root cause. `_COPY_MATERIAL_SCRIPT` now also transfers
  `srcProp.getMapValue()` onto the destination property via `setMap()` and
  reports the count in a new `maps_copied` result field — the previous
  manual `daz_execute`/`setMap()` follow-up step is no longer necessary.

## 0.5.8+bb.6 — 2026-09-20

### Added

- **`daz_get_shell_visibility(shell_label)`** and
  **`daz_set_shell_visibility(shell_label, group_visibility)`**
  (`tools/scene.py`) — workaround for Bug-Katalog #35 (no way to read/write
  a face group's hidden state on a plain mesh/prop via DazScript). Live
  investigation found that `DzGeometryShellNode`s uniquely expose one real
  `DzBoolProperty` per face group (`facet_group_<name>_vis`, grouped under
  "/Shell/Visibility/Face Groups"), confirmed both in a saved `.duf`
  (`node_library` `studio_node_channels` extra) and live via
  `daz_execute`/`getNumProperties()` against a freshly created shell — no
  such property exists on the shelled node itself or on any other node
  type. Does not solve hiding on an arbitrary already-hidden mesh directly;
  the practical workaround is to put a Geometry Shell over the item and
  toggle its face groups instead of the Geometry Editor's hide, since that
  state is now readable/writable and persists in the `.duf`.

### Changed

- **Moved `daz_create_geometry_shell`/`daz_list_geometry_shells`'s DazScript
  fragments and registry entries from `_registry.py` into
  `_registry_fork.py`.** They were added to the upstream-shared file by
  mistake in `e8767d2` (2026-09-19, Bug-Katalog #31) despite being
  fork-only tools — `_registry.py` is net smaller after this move, not
  larger. Same rationale as the `bb.3` split below: keeps future
  `upstream/master` merges from ever needing to touch fork-added tools.

### Notes

- Tool count after this change: 159 tools in 15 modules.

## 0.5.8+bb.3 — 2026-09-14

### Added

- **`daz_create_child_bone(parent_label, name, origin, endpoint=None)`** and
  **`daz_set_skin_weights(figure_label, bone_weights)`** (`tools/rigging.py`,
  Phase 6.15) — close Bug-Katalog #30. Root cause found live: a
  runtime-created `DzBone` + `DzBoneBinding` reads its own weights back
  correctly but is silently ignored by the deformer until
  `DzSkinBinding.checkAndNormalize()` is called at least once afterward —
  undocumented anywhere in the DAZ SDK reference. Both tools call it as
  their last step and size every `DzWeightMap` against the figure's BASE
  (un-subdivided) geometry vertex count, never `getCachedGeom()`, which
  differs whenever SubDivision is active (same shape as the existing
  dForce influence-weights gotcha). Live-verified against the reference
  figure/bone chain from the bug report (`samor_1125_111_fitted_baked_rot`,
  `hairTail1`–`5` under `head`) and, for the auto-renormalization behavior,
  in isolation against `Genesis 8 Female`.
- 9 new unit tests (`tests/test_rigging.py`).

### Changed

- **Split fork-only script registrations out of `_registry.py` into a new
  `_registry_fork.py`.** `_registry.py` is shared with upstream and gets
  rebased/merged regularly; keeping fork-only tools (`daz_save_wearable_preset`,
  and now the two above) in a separate file means future `upstream/master`
  merges never need to touch them. `_register_scripts()` merges
  `_REGISTRY_FORK` in via a local import (avoids a circular import, since
  `_registry_fork.py` imports `_RESOLVE_NODE_JS` back from `_registry.py`).
  Net effect: `_registry.py` itself is now smaller than before this change,
  not larger.

### Notes

- Tool count after this change: 155 tools in 15 modules (118 upstream-shared
  registry scripts + 3 fork-only).
- Full suite green: 379 passed, 159 skipped (integration, not run against
  live DAZ Studio for this change), 0 failed.
- **Process note for future test runs:** `uv run pytest tests/` alone does
  **not** exclude `integration`-marked tests — `pyproject.toml`'s `addopts`
  only excludes `slow`. Those tests only skip at runtime if DAZ Studio is
  unreachable; if it's running (as it was during this session), running the
  bare suite executes them for real against the live scene. This bit us
  mid-session (`test_camera_integration.py`/`test_choreography_integration.py`
  created real cameras and scene content in the user's live instance).
  Always pass `-m "not integration"` for a plain regression check while DAZ
  Studio might be live.

## 0.5.8+bb.2 — 2026-09-12

### Fixed

- **`daz_create_camera`/`daz_create_light` left the new node's internal name
  empty.** Confirmed live: `Scene.addNode()` on a script-created
  `DzBasicCamera`/light does not auto-assign an internal name the way DAZ
  Studio's UI does — `getName()` stays `""`. `daz_list_cameras`/`daz_list_lights`
  (migrated to the `dazpy` library, which resolves nodes by that internal name)
  then failed to look the node back up, showing a blank `label` for anything
  created via these tools. Both create scripts now assign a unique internal
  name via `setName()` right after `Scene.addNode()` (`setName()` does not
  auto-dedupe on collision — confirmed live — so uniqueness is checked
  manually against `Scene.findNode()`).
- **`daz_list_cameras`/`daz_list_lights` never returned a `type` field**,
  and were missing `position` (and, for lights, `flux`) — a leftover gap
  from an incomplete migration off the original DazScript-registered
  implementation onto `dazpy`. Rather than patching the `dazpy` path
  piecemeal, both tools now call the already-registered, already-correct
  `vangard-list-cameras`/`vangard-list-lights` scripts (previously dead
  registry entries — nothing called them) — index-based, one HTTP round
  trip instead of one-plus-N, and immune to the internal-name problem
  above since they never resolve a node by name.
- This bug predates the `0.5.8+bb.1` upstream merge (confirmed identical on
  both sides of it) and is unrelated to any camera/light behavior upstream
  changed — pure incomplete-migration leftover in this fork/upstream's
  shared history.

### Notes

- Live-verified end to end: create → list → delete, for both cameras and
  lights, with duplicate labels/names to exercise the dedup path.
- 20/20 targeted camera/light integration tests green, 192/192 unit tests
  green, both CI pylint gates green (9.75 / 9.97 at the 7.0 threshold).

## 0.5.8+bb.1 — 2026-09-11

Rebasiert auf `bluemoonfoundry/daz-mcp-server` `0.5.8` (Merge von
`upstream/master` `dc8a41e`; vorherige Fork-Basis war `0.5.0`, Merge-Base
`0fa6f68`). Der `bb`-Zähler startet nach dem Basiswechsel wieder bei `.1`.

### Changed

- **Upstream hat den Großteil der Fork-Arbeit übernommen.** `daz_save_prop_asset`,
  `daz_load_morph_pro` und die Strand-Based-Hair-Tools wurden von upstream
  ausdrücklich aus diesem Fork geharvestet (PR #13, Beads `l1o`/`msn`/`a2y`);
  `daz_find_actions`, `daz_erc_freeze`, `daz_run_transfer_utility`, die
  dForce-Surface-Properties sowie die Bugfixes zu OBJ-Import, elementID-Auflösung,
  Material-Presets und BVH-Import sind dort parallel entstanden. Bei diesen
  Doppelentwicklungen wurde jeweils die Upstream-Fassung übernommen, um künftige
  Merges konfliktarm zu halten — inhaltlich verifiziert identisch.
- **Fork-eigene Tools nach dem Merge:** `daz_save_wearable_preset` (Phase 6.14,
  Windows-UI-Automation) ist derzeit das einzige Tool, das es nur hier gibt.
- `CHANGELOG.md` → `FORK_CHANGELOG.md` umbenannt (Konvention wie in
  `daz-script-server`). Der Inhalt war bereits fork-spezifisch; upstream führt
  selbst keinen Changelog, sodass der alte Name bei einem künftigen
  Upstream-Changelog kollidiert wäre.
- Die datierten „Aktueller Stand"-Abschnitte aus `CLAUDE.md` sind hierher
  gewandert; in `CLAUDE.md` bleiben nur die aktiven Regeln (Versionsschema,
  Bump-Regel), was die Konfliktfläche bei Upstream-Merges verkleinert.

### Fixed

- **`daz_set_dforce_influence_weights` nutzt jetzt die Simulations-Vertexzahl.**
  Mit dem Upstream-Fix `e607f6b` wird die Weight-Map über
  `modifier.getTargetVertexCount()` statt über die gerenderte/unterteilte
  Geometrie (`getCachedGeom()`) dimensioniert — beide unterscheiden sich live
  deutlich (z. B. 3401 vs. 13456 am selben Knoten), wodurch eine korrekt
  dimensionierte Map bisher still durch eine falsch dimensionierte ersetzt wurde.

### Notes

- Tool-Zahl nach dem Merge: 154 Tools in 14 Modulen, 119 Registry-Skripte
  (auf doppelte Registry-Keys und undefinierte Skriptreferenzen geprüft).
- 192 Unit-Tests grün (`-m "not integration"`); Integrations- und
  Render-Tests wurden nicht gegen eine laufende DAZ-Instanz nachgefahren.

## 0.5.0+bb.13 — 2026-09-09

### Added

- **`daz_save_wearable_preset(figure_label, output_path, dialog_timeout=30.0)`** — save a figure (with everything currently fit/parented to it) as a reusable Wearable(s) Preset, the fit-to-figure Content-Library asset type (Bug-Katalog #22 Teil 2). `DzWearablesAssetFilter.doSave()`, the script-API equivalent, reproducibly fails with an unexplained generic error under every configuration tried (see the bug entry for the full list of disproven hypotheses) — so this tool instead drives the real "File > Save As > Wearable(s) Preset" GUI action's two native dialogs directly via Windows UI Automation (`pywinauto`, new Windows-only dependency). No DAZ Studio window needs focus or foreground. Live-verified twice end-to-end against a real figure with a fitted test prop, fully reverted afterward.
- New module `_ui_automation.py`: reusable helpers for driving native DAZ Studio dialogs that have no working headless scripting path — window discovery/polling by owning process, the `WM_COMMAND`/`BN_CLICKED`-to-dialog-not-button trick needed for the native "Filtered Save" common dialog's default button (confirmed live: neither UIA `Invoke()` nor `BM_CLICK` on the button itself works), and the UIA `ValuePattern`/`get_value()` vs. `window_text()` gotcha for that dialog's filename field (the latter always shows only the static label).

### Notes

- Bundles *every* item currently fit/parented to the target figure — the Options dialog's node-inclusion checklist has no confirmed programmatic toggle mechanism (custom-painted checkboxes, no `TogglePattern`). Unfit anything you don't want included first.
- `pywinauto` is declared with a `platform_system == 'Windows'` marker; this tool raises a clear `ToolError` if unavailable rather than failing to import.

## 0.5.0+bb.12 — 2026-09-08

### Added

- **`daz_save_prop_asset(...)`** — save a node as a reusable Content-Library Figure/Prop Support Asset (`.duf` + geometry `.dsf`) via `DzNodeSupportAssetFilter`, the headless equivalent of File > Save As > Support Asset > Prop Asset (Bug-Katalog #22 Teil 1). Live-verified: writes `<content dir>/Props/.../*.duf` + `<content dir>/data/<vendor>/<product>/<item>/*.dsf`, fully silent, round-trip reloadable via `daz_load_file`. Resolves `BaseDataPath` automatically from `output_path` against the instance's configured content directories (required or `doSave()` fails with a generic error code). No thumbnail is generated by `doSave()` itself.

Investigated but not solved: `DzWearablesAssetFilter` (Wearable Preset / fit-to-figure behavior, Bug-Katalog #22 Teil 2) — identified the correct non-deprecated API and its `NodeNames`/`MaterialNames` `DzSettings` sub-object mechanism, but `doSave()` reproducibly fails with a generic error across every configuration tried. Left open rather than shipping a guessed fix; see Bug-Katalog #22 and `SKILL_DAZSCRIPT.md`.

## 0.5.0+bb.11 — 2026-09-07

### Added

- **`daz_load_morph_pro(...)`** — load an OBJ morph target onto a node via `DzMorphLoader` (Morph Loader Pro plugin), the headless equivalent of File > Import > Morph Loader Pro. Covers the full option set: load mode, mirroring, overwrite mode, reverse deformations, subdivision mapping, attenuation maps, ERC control-property linking (Bug-Katalog #14 follow-up). Live-verified against a hand-built test cube.

Two gotchas confirmed live and documented in the tool's docstring / `SKILL_DAZSCRIPT.md`: `setLoadMode`'s valid modes depend on the node type (a plain prop only accepts `PrimaryNode`, not the `EntireFigure` default), and `createMorph()` needs `RunSilent` on the passed `DzFileIOSettings` to avoid an OBJ import options dialog. Also: `overwrite_mode="MakeUnique"` does **not** silently resolve a morph-name collision — it opens a blocking interactive rename dialog regardless of `RunSilent`.

## 0.5.0+bb.10 — 2026-09-02

### Fixed

- **`daz_find_actions`** — reverted `bb.9`'s `actionGroup()` change. `daz_script_spec.d.ts` declares `DzAction.actionGroup()` as a method (parens), unlike its sibling `defaultMenu`/`description`/`simpleText` properties on the same class — but live against DS6 6.25, `actionGroup` is a genuine string **property**: `a.actionGroup()` throws `TypeError: ... is not a function` for all 875 actions, while `a.actionGroup` correctly returns values like `"Content Library"`, `"Geometry Editing"`, `"Inverse Kinematics"`. The spec was wrong for this member on this build; `bb.9` should never have shipped without a live check. Reverted to the original `a.actionGroup` property access.

## 0.5.0+bb.8 — 2026-09-02

### Added

- **`daz_find_actions(query)`** — search `DzActionMgr` by className/simpleText/description. Replaces the impossible `MainWindow.menuBar()` path (Bug-Katalog #14). Does not trigger actions.
- **`daz_erc_freeze(...)`** — headless ERC Freeze via `new DzERCFreeze()` (Property Hierarchy plugin), not `DzERCFreezeAction.trigger()`.

## 0.5.0+bb.1 — 2026-08-30

Fork baseline, based on `bluemoonfoundry/daz-mcp-server` at `0.5.0` (merge-base `0fa6f68`). Bundles fixes found while using the server for automated toon-shader (Filament-style) rendering of Genesis 8 characters.

### Fixed

- **Render-to-file did not persist.** `daz_set_render_output(output_path=...)` reported success but `daz_get_render_settings()` still showed `renderToFile: false` / `outputPath: null`. Root cause: the generated DazScript never called `opts.applyChanges()` after setting `opts.renderImgToId`, so the values were never handed to the active render-settings instance. Fixed in `daz_render`, `daz_render_with_camera`, `daz_batch_render_cameras`, `daz_render_animation`, `daz_set_render_output`, `daz_get_render_settings`. (`f40a7bf`)
- **`getNumMaterials` missing on `DzObject`.** `daz_apply_material_preset` and `daz_copy_material` called `getNumMaterials()`/`getMaterial()` directly on `node.getObject()`, which doesn't expose those methods — needs the `.getCurrentShape()` step first, the way `daz_list_materials` already did it. (`f40a7bf`)
- **Render engine selection was not readable/settable via script.** DAZ Studio's render engine dropdown maps to `DzRenderOptions.renderType` (0=Viewport, 1=Multi-pass OpenGL, 2=Iray), not `getActiveRenderer()`/`getNumRenderers()`. Added `daz_set_render_engine(engine)` and exposed `engine`/`renderType`/`renderTypeName` on `daz_get_render_settings()`. (`d754ec7`)
- **Viewport render with no output path opened a blocking file-name dialog**, which looked like a crash if left open too long (`daz_status()` stayed `running: true`). `daz_render`/`daz_render_with_camera` now require `DirectToFile` + an output path (argument or previously-set `renderImgFilename`) before calling `doRender()`, erroring instead of opening the dialog. (`d754ec7`, symmetry fix so both render entry points mirror image name/path via `renderMgr.getOptionHelper()` in `5421aa5`)
- **`daz_get_material` returned `null` for float-color channels** (Diffuse, Ambient, Emission, Rim color, etc.) even when the actual scene value was set correctly — needed `getFloatColorValue()` / `.red`/`.green`/`.blue`, not `col.red()`. (`d754ec7`)
- **`daz_set_morph` / `daz_set_property` / `daz_get_node` did not find modifier-stack morphs** (`eCTRL...`, `pCTRL...`, `pJCM...` channels) — only `node.getNumProperties()` was searched, not `obj.getNumModifiers()`/`getValueChannel()`. Locked dials are now unlocked before `setValue`. (`d754ec7`)
- **`daz_script_help("animation")` documented non-existent methods** (`setKeyFrame`, `getKeyFrame`, `deleteKey`). Corrected to the real keyframe API (`setValue(time, value)`, `setKeyValue(i, value)`, `deleteKeys(time, time)`, `deleteAllKeys()`), and fixed `Scene.getFPS()` (doesn't exist — use `4800 / Scene.getTimeStep()`) and `DzTimeRange.start`/`.end` (tick properties, not `getStart()`/`setStart()`). (`d754ec7`)

### Changed

- Git history for the two oldest fork commits was rewritten to correct a misattributed author (recorded as "GSH", actually Black-Byte): `f5979b2` → `f40a7bf`, `d899adb` → `3925ca7`.
