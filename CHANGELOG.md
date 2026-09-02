# Changelog

All notable fork-specific changes to `vangard-daz-mcp` are documented here. This fork's version scheme is `<upstream-version>+bb.<n>` — see [README.md#about-this-fork](README.md#about-this-fork). Upstream changes from [bluemoonfoundry/daz-mcp-server](https://github.com/bluemoonfoundry/daz-mcp-server) are not duplicated here — only fork-specific fixes are tracked.

## 0.5.0+bb.9 — 2026-09-02

### Fixed

- **`daz_find_actions`** — `actionGroup` was read as a property (`a.actionGroup`) instead of called as a method (`a.actionGroup()`); per `daz_script_spec.d.ts`, `DzAction.actionGroup()` is a method, unlike the sibling `defaultMenu`/`description`/`simpleText` properties on the same class. Every match's `actionGroup` field returned the stringified function instead of the real group name.

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
