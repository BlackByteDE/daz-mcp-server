# Skill: DazScript Specialist
Rules for writing DazScript for DAZ Studio 4.24+.

## Globals & Environment
- `Scene` (DzScene), `App` (DzApp), `MainWindow`.
- Version check: `App.longVersionString`.

## Scripting Rules
- **No Bare Returns:** Wrap in IIFE: `(function(){ return {foo:42}; })()`.
- **Node Finding:** Labels are **not** unique (e.g. two `Hip` nodes). Prefer `Scene.findNodeByElementID(id)`, or `parent.findNodeChildByLabel(label, true)`. `findNodeByLabel` returns the first match only.
- **Creation:** Use `new DzBasicCamera()` or `new DzSpotLight()`. Do NOT use UI Actions/Menus.
- **Coordinate System:** Genesis figures face **+Z** (Front).
- **Element ID:** `node.elementID` is a property, not a method.

## Common Property Internal Names
- **Transforms:** `XTranslate`, `YRotate`, `Scale`.
- **Lights:** `Flux`, `Shadow Softness`, `Spread Angle`, `Environment Mode`.

## Verified API Patterns (live-tested against DAZ Studio 4.24)

These were confirmed by running scripts against a live instance. Do not assume alternatives work.

### Saving the scene
```javascript
Scene.saveScene(filePath);   // saves without a dialog — the ONLY working headless save
// BROKEN: App.saveScene(), App.getInterface().saveScene(), Scene.setFilename(),
//         MainWindow.triggerAction(), MainWindow.saveScene(), MainWindow.saveSceneAs()
// BLOCKS (opens UI dialog): MainWindow.doDAZSave(), MainWindow.doDAZSaveAs()
```

### Materials — always go through getCurrentShape()
```javascript
var shape = node.getObject().getCurrentShape();  // DzShape — has getNumMaterials()
// BROKEN: node.getObject().getNumMaterials() — DzObject has no materials directly
```

### Bounding box
```javascript
var bbox = node.getWSBoundingBox();          // returns DzBox3
var cx = (bbox.minX + bbox.maxX) / 2;       // compute center manually
// BROKEN: node.getBoundingBox(), bbox.getCenter()
```

### Render options — property assignment, no setter methods
```javascript
var opts = App.getRenderMgr().getRenderOptions();
opts.renderImgFilename = path;   // BROKEN: opts.setRenderImgFilename(path)
opts.aspectWidth  = w;           // BROKEN: opts.setImageSize(w, h)
opts.aspectHeight = h;
// Read back the same properties: opts.renderImgFilename, opts.aspectWidth, opts.aspectHeight
```

### Bone naming by generation
**Authoritative** — probed live from DAZ Studio 4.24. Full reference: `src/vangard_daz_mcp/genesis_bones.json`.

Genesis 3 and Genesis 8 share identical internal bone names. Genesis 9 uses a completely different `l_`/`r_` underscore scheme.

| Joint | Genesis 3 & 8 | Genesis 9 |
|-------|--------------|-----------|
| Hip / root | `hip` | `hip` |
| Pelvis | `pelvis` | `pelvis` |
| Spine (low→high) | `abdomenLower`, `abdomenUpper`, `chestLower`, `chestUpper` | `spine1`, `spine2`, `spine3`, `spine4` |
| Neck (low→high) | `neckLower`, `neckUpper` | `neck1`, `neck2` |
| Head | `head` | `head` |
| Eyes | `lEye` / `rEye` | `l_eye` / `r_eye` |
| Shoulder (upper arm) | `lShldrBend` / `rShldrBend` | `l_upperarm` / `r_upperarm` |
| Shoulder twist | `lShldrTwist` / `rShldrTwist` | *(no direct equivalent)* |
| Forearm | `lForearmBend` / `rForearmBend` | `l_forearm` / `r_forearm` |
| Hand | `lHand` / `rHand` | `l_hand` / `r_hand` |
| Thigh | `lThighBend` / `rThighBend` | `l_thigh` / `r_thigh` |
| Shin | `lShin` / `rShin` | `l_shin` / `r_shin` |
| Foot | `lFoot` / `rFoot` | `l_foot` / `r_foot` |

**Detection:** `fig.getName()` contains `"Genesis3"`, `"Genesis8"`, or `"Genesis9"`.

**Fallback pattern for generation-agnostic scripts:**
```javascript
var lUpperArm = findBone(fig, "l_upperarm") || findBone(fig, "lShldrBend");
var neckUp    = findBone(fig, "neck2")      || findBone(fig, "neckUpper");
var lEye      = findBone(fig, "l_eye")      || findBone(fig, "lEye");
var spineTop  = findBone(fig, "spine3")     || findBone(fig, "chestUpper");
```

### Re-parenting nodes
```javascript
// BROKEN: node.setNodeParent(newParent, inPlace)  — method does not exist
// CORRECT: call addNodeChild on the NEW parent; it auto-detaches from current parent
newParent.addNodeChild(node, maintainWorldTransform);
// To explicitly remove from current parent (without deleting):
currentParent.removeNodeChild(node, inPlace);
// inPlace=true preserves world position by adjusting local transform
```

### Cameras — Perspective view is NOT a DzCamera
`Scene.getNumCameras()` returns 0 in a fresh scene. The "Perspective Camera" seen in the
DAZ Studio viewport is a built-in viewport mode, not a `DzCamera` object. Only cameras
created with `new DzBasicCamera()` (or loaded from a `.duf`) appear in `Scene.getNumCameras()`.
Always handle `camera_count == 0` as a valid state.

### Keyframe animation — correct API
Time is in **ticks**, not frames: `var time = frame * Scene.getTimeStep();`

```javascript
// DzFloatProperty (camera controls, morph/transform props): two-arg setValue = keyframe
prop.setValue(time, value);      // creates/overwrites a key at that time (ticks)
prop.setValue(value);            // one-arg: sets current value, NO keyframe

// DzNumericProperty subclass (props from findProperty on figures):
prop.setDoubleValue(time, value);  // two-arg form = keyframe

// READ
prop.getNumKeys();
prop.getKeyTime(i);              // ticks
prop.getKeyValue(i);

// UPDATE existing key by index — never creates a new key
prop.setKeyValue(i, value);

// DELETE one key (range start==end). deleteKey() does not exist.
prop.deleteKeys(time, time);

// DELETE ALL keys on this property — not a substitute for single-key delete
prop.deleteAllKeys();

// BROKEN: prop.setKeyFrame(frame, value) — does not exist on any property class
// BROKEN: prop.getKeyFrame(index)        — use getKeyTime(i)
// BROKEN: prop.deleteKey(index)          — use deleteKeys(time, time)
// BROKEN: prop.setKey(frame, value)      — does not exist on any property class
// BROKEN: prop.getAnimation()            — does not exist
```

### Camera controls — always use dedicated control accessors (DzBasicCamera)
Never use `findProperty("Focal Length")` etc. on cameras. Use the typed control methods defined
in `DzBasicCamera` — they always return a `DzFloatProperty` / `DzBoolProperty` you can
call `.setValue()` on:

```javascript
var time = frame * Scene.getTimeStep();
camera.getDepthOfFieldControl().setBoolValue(true);   // enable DOF (DzBoolProperty)
camera.getFocalDistanceControl().setValue(200);        // focal distance in cm
camera.getFocalDistanceControl().setValue(time, 200);  // keyframe focal distance
camera.getFocalLengthControl().setValue(85);           // focal length in mm
camera.getFocalLengthControl().setValue(time, 85);     // keyframe focal length
camera.getFStopControl().setValue(2.8);               // aperture / F-stop
camera.getFocalPointScaleControl().setValue(1.0);     // focal point scale

// BROKEN: cam.findProperty("Focal Distance")  — returns null on a bare DzBasicCamera
// BROKEN: cam.findProperty("Focal Length")    — same; use getFocalLengthControl()
// BROKEN: cam.findProperty("F/Stop")          — use getFStopControl()
```

### Materials — DzDefaultMaterial vs DzUberIrayMaterial
Content merged into a scene as raw DSON (a hand-authored `.duf`, or a from-scratch scene-merge
exporter's output) reliably instantiates as the legacy `DzDefaultMaterial` ("DAZ Studio Default
(RSL)" in the UI), never `DzUberIrayMaterial`, no matter how complete the material's
`studio_material_channels` data is — confirmed by direct isolation testing (a byte-for-byte copy
of a real, working Iray Uber material's channel data, dropped into a self-contained merge, still
comes back as `DzDefaultMaterial`). The legacy shader doesn't even read modern fields like
`diffuse.channel.image_file`, so textures silently fail to display regardless of how correct the
data is. Use `daz_convert_to_iray_uber(node_label)` to fix this — it goes through Daz's own
shader-preset **application** codepath (`App.getContentMgr().openFile()` on a selected node, the
same thing that runs when a user drags a Shader Preset from Smart Content onto a figure) instead
of describing a shader in JSON, and reliably promotes every zone to genuine `DzUberIrayMaterial`.
This resets every channel to shader defaults — follow up with `daz_set_material_property` per
zone.

### Colors — linear values need `setFloatColorValue`, not `setColorValue`
```javascript
// setColorValue(QColor) is 0-255 sRGB-int and Daz gamma-DECODES it on the way in.
// Correct for a UI hex-picker value ("#RRGGBB", what daz_set_material_property expects),
// WRONG if you already have a linear-space 0-1 float (e.g. from another DCC's shader graph):
prop.setColorValue(new QColor(38, 26, 20));   // feeding linear 0.15 in as if it were sRGB 38/255
prop.getFloatColorValue();                     // reads back ~0.015, NOT 0.15 — silently darkened

// Linear-native setter — round-trips exactly:
prop.setFloatColorValue(new DzFloatColor(0.15, 0.1, 0.08, 1.0));
prop.getFloatColorValue();                     // reads back {red:0.15, green:0.1, blue:0.08, alpha:1}
```

### Texture maps — `setMap()` works on any mappable channel, color or numeric
```javascript
// Confirmed live on both classes — no per-channel-type table needed:
prop.setMap("C:/path/to/texture.png");   // DzFloatColorProperty (e.g. Diffuse Color)
prop.setMap("C:/path/to/rough.png");     // DzFloatProperty too (e.g. Glossy Roughness, Normal Map)
prop.isMapped();                          // true after setMap()
prop.getMapValue().getFilename();         // read back the path
// BROKEN assumption: that setMap only exists on image-specific property classes — it doesn't
// need one; probe with `typeof prop.setMap === 'function'` if unsure on a given class.
```

### Probing unknown objects
When a method name is uncertain, enumerate at runtime before writing the script:
```javascript
var methods = [];
for (var k in SomeObject) {
    if (typeof SomeObject[k] === 'function') methods.push(k);
}
return { methods: methods };
```

### Morph Loader Pro (`DzMorphLoader`) — confirmed live
Requires the Morph Loader Pro plugin active in the running instance (`typeof DzMorphLoader
!== "function"` if not). Two gotchas confirmed by live testing (round-tripped a hand-built
cube OBJ through `daz_load_morph_pro`):

```javascript
// setLoadMode(mode, node) validity depends on what node IS — wrong mode raises immediately:
//   plain prop (no skeleton)        -> PrimaryNode only
//   legacy (non-"single skin") figure -> EntireFigure, SelectedNodes, or PrimaryNode
//   "single skin" figure            -> SingleSkinFigure or SingleSkinFigureFromGraft only
// EntireFigure is NOT a safe default for props — check what kind of node you have first.

// createMorph()/createMorphs() need RunSilent on the DzFileIOSettings passed in, same as
// the OBJ importer, or DAZ Studio opens an OBJ import options dialog and blocks:
var settings = new DzFileIOSettings();
settings.setIntValue("RunSilent", 1);

// BROKEN ASSUMPTION: setOverwriteExisting(MakeUnique) silently auto-renames on a name
// collision. It does NOT — DAZ Studio opens a blocking interactive "morph already exists"
// rename dialog regardless of RunSilent on the file settings. There is no known
// FileIOSettings/loader flag that suppresses it. Avoid the collision instead of trying to
// suppress the prompt: check daz_search_morphs/daz_list_morphs for the target name first
// and pass one you know is unique.
```

### Content-Library asset export (`DzNodeSupportAssetFilter`) — confirmed live
`DzSaveFilter`/`DzSaveFilterMgr` are **deprecated** ("script-based presets... in favor of
DSON") — do not use them. The current DSON-based path is the `DzAssetIOFilter` family
(`docs.daz3d.com` group `File Input and Output Objects`), each with an official sample link.
For saving a node as a reusable Prop/Figure Support Asset:

```javascript
var node = Scene.findNodeByLabel("My Prop");
var filter = new DzNodeSupportAssetFilter();
filter.setNode(node);

var settings = new DzFileIOSettings();
filter.getDefaultOptions(settings);
// RunSilent (and every other key on this settings object) is a STRING "yes"/"no", not
// an int/bool — settings.setIntValue("RunSilent", 1) silently does nothing useful here.
settings.setStringValue("RunSilent", "yes");

// REQUIRED or doSave() fails with a generic errCode 98 (DZ_OPERATION_FAILED_ERROR).
// Must be one of App.getContentMgr().getContentDirectoryPath(i) — and outputPath itself
// must be a path INSIDE that same directory. The log (%APPDATA%/DAZ 3D/Studio6/log.txt)
// names this exact cause: dznodesupportassetfilter.cpp(1547): Running silent. No
// "BaseDataPath" defined. — worth checking that log whenever doSave() returns a bare
// numeric error code with no obvious reason.
settings.setStringValue("BaseDataPath", "C:/Users/me/Documents/DAZ 3D/Studio/My Library");
settings.setStringValue("VendorName", "MyStudio");
settings.setStringValue("ProductName", "My Product");
settings.setStringValue("ItemName", "My Prop");

var outputPath = "C:/Users/me/Documents/DAZ 3D/Studio/My Library/Props/MyProduct/My Prop.duf";
var err = filter.doSave(settings, outputPath, "");   // err.valueOf() === 0 on success
```

Confirmed live: writes the `.duf` preset at `outputPath` AND the actual geometry as
`<BaseDataPath>/data/<Vendor>/<Product>/<Item>/....dsf` (Daz's standard content layout) —
round-trip reloadable via the normal scene-merge importer. No thumbnail (`.duf.png`) is
generated by `doSave()` itself (compare to a UI-driven save, which produces one alongside
the `.duf`) — thumbnailing appears to be a separate, still-unconfirmed step.

### Wearable Preset export (`DzWearablesAssetFilter`) — confirmed live (Bug-Katalog #22 Teil 2)

`DzWearablesAssetFilter` (Wearable Preset, auto-fit-to-figure behavior) has no `setNode()` —
which node(s) to include goes through the `NodeNames` sub-settings. **The entry's VALUE is
the node LABEL; the key is ignored.** The filter resolves each value with
`Scene.findNodeByLabel()`, so labels must be unique, and only the listed nodes end up in
the preset:

```javascript
var filter = new DzWearablesAssetFilter();
var s = new DzFileIOSettings();
filter.getDefaultOptions(s);
s.setBoolValue("RunSilent", true);          // Bool here — NOT the "yes" string of DzNodeSupportAssetFilter
var nn = s.getSettingsValue("NodeNames");   // DzSettings sub-object
nn.setStringValue("0", jacket.getLabel());  // key arbitrary, VALUE = node label
nn.setStringValue("1", boots.getLabel());
s.setSettingsValue("NodeNames", nn);         // write back onto the parent
s.setBoolValue("SmartParent", true);
s.setBoolValue("BypassFilter", true);        // skip the property-view filtering
var err = filter.doSave(s, "C:/.../Presets/Wearables/Outfit.duf", "");   // 0 on success
// Other keys read in silent mode: PoseTarget, CompressOutput, SaveSimulationData (Bools),
// PostLoadEnable/PostLoadScriptPath/PostLoadScriptSettings, MaterialNames (sub-settings
// keyed by material name, values = property names).
```

BROKEN, do not retry: `nodeNames.setStringValue(node.getName(), "1")` (key = node, value =
dummy) — the filter then looks for a node *labelled* "1", finds none, and `doSave()` fails
with the generic `errCode 98`/`100`. That layout was the whole reason Bug #22 Teil 2 looked
unsolvable. Return codes: 98 = `NodeNames` empty or final write failed, 100 = no entry
resolved to a node, 528 = empty output path. `doSave()` writes no thumbnail.

### Asset thumbnails — confirmed live

Neither asset filter writes `.duf.png`/`.tip.png` headless. On the Filament viewport
`Dz3DViewport.captureImage()` returns a null `DsImage` and `renderThumbnail(node, path)`
returns `false` (other signatures: "incompatible arguments"). What works: a normal
render-to-file with `opts.renderType = opts.ScreenShot` ("Viewport" engine, no Iray) and
`opts.imageSize = new QSize(s, s)` — the PNG comes out RGBA with a transparent background.
`opts.aspectWidth`/`aspectHeight` are **read-only** (assigning throws — keep that out of
any `finally` restore block). Frame with your own temp `DzBasicCamera`: distance =
bbox radius / sin(`cam.getFieldOfView()` / 2), then `aimAt(center)`;
`v3.frameCameraOnBox()`/`frameCameraOnSelectedNodes()` had no visible effect on the
render. See `daz_render_asset_thumbnail` (`_registry_fork.py`).

`daz_save_wearable_preset` uses this path by default (`items=[...]` to pick nodes).

**Fallback (`use_ui_automation=True`): drive the real GUI action's native dialogs via
Windows UI Automation** (`pywinauto`, Windows-only — see `_ui_automation.py`). It always
bundles every fitted item but does produce a thumbnail. Trigger `MainWindow.getActionMgr().findAction("DzWearablesAssetFilterAction")
.trigger()` (figure pre-selected, must already have ≥1 item fit/parented to it or DAZ shows a
"Selection Error" dialog instead of the save dialog), then automate the two resulting windows:

```python
# 1. Native "Filtered Save" file dialog (class "#32770"). Its filename field's
#    window_text()/WM_GETTEXT ALWAYS show only the static label ("Dateiname:") —
#    checking success that way is a trap. Use UIA ValuePattern instead:
edit = win.child_window(auto_id="1001", control_type="Edit")
edit.set_edit_text(str(output_path))
assert edit.get_value() == str(output_path)   # get_value(), never window_text()

# Its Save button: neither UIA .invoke() nor a raw win32gui BM_CLICK on the button's
# own HWND triggers the action (both return without error, dialog stays open). What
# works — WM_COMMAND/BN_CLICKED sent to the DIALOG window, not the button:
win32gui.SendMessage(dialog_hwnd, win32con.WM_COMMAND, win32api.MAKELONG(1, 0), 0)

# 2. The resulting Qt6 "Wearable(s) Preset Save Options" dialog (auto_id prefix
#    "App.WearablesAssetFilterDialog") behaves normally — .invoke() on
#    "...BasicDlgButtonGrpBox.BasicDlgAcceptDialogBtn" works fine, no workaround needed.
# Its node-inclusion checklist (TreeItems under "...AssetFilterNodeAssetSelectionView")
# has no confirmed toggle mechanism (no TogglePattern, is_selected() always 0 — likely
# custom-painted checkboxes) — left at its default (bundles everything currently
# fitted to the figure).

# DAZ finishes writing the file a moment AFTER the dialog visually closes — poll
# path.exists() briefly rather than checking once immediately after Accept.
```

### Modifier Asset export (`DzModifierSupportAssetFilter`) — confirmed live (Bug-Katalog #37)

Same `DzAssetIOFilter` family as the Prop Asset filter, no `setNode()`. Works headless
once `NodeNames` is laid out the way the filter reads it: **one sub-settings entry keyed
by the root node's internal NAME (`getName()`, or a bone name), holding String entries
whose VALUE is the morph name** (property internal name); the keys inside are ignored.

```javascript
var node = Scene.findNodeByLabel("My Dress");
Scene.selectAllNodes(false); node.select(true);   // root = primary selection if RootLabel is empty
var f = new DzModifierSupportAssetFilter();
var s = new DzFileIOSettings();
f.getDefaultOptions(s);
s.setBoolValue("RunSilent", true);                 // Bool, NOT the "yes" string
s.setStringValue("RootLabel", "");                 // else resolved via findNodeByLabel
s.setStringValue("BaseDataPath", "C:/Users/Public/Documents/My DAZ 3D Library"); // a content dir
s.setStringValue("VendorName", "blackbyte.de");    // required
s.setStringValue("ProductName", "Product");        // required
var nn = s.getSettingsValue("NodeNames");
var sub = new DzSettings();
sub.setStringValue("0", "MyDress_PullDown");       // VALUE = morph name, key ignored
nn.setSettingsValue(node.getName(), sub);          // KEY = node NAME, not label
s.setSettingsValue("NodeNames", nn);
f.doSave(s, "", "");   // 0 on success; the path argument is ignored
// -> <BaseDataPath>/data/<item asset dir>/Morphs/<VendorName>/<ProductName>/<morph>.dsf
// Optional Bools: CompressOutput, ForceUniqueIDs.
```

BROKEN, do not retry: morph name as the KEY with a dummy value (`node -> {morph: "1"}`,
and every variant of that) — the filter finds no property, writes nothing and still
returns 0. Morphs coming from cloud-encrypted files are skipped the same silent way.

Two cases pop a **modal** box regardless of `RunSilent`: no root node (nothing selected /
`RootLabel` not found → "Selection Error"), and a node not loaded from a saved `.dsf`
asset → "Resource Error" ("Figure/Prop Assets must be saved before saving Modifier
Asset(s)."). Check `node.assetUri.filePath` ends in `.dsf` first.

`daz_save_modifier_asset` does all of the above. Its `use_ui_automation=True` fallback
drives the real dialog (`App.MorphAssetFilterDlg`) — UIA `Expand()`/`Toggle()` are no-ops
on its tree, but keyboard input works (`*` expands all, Down/Space ticks a row). Tick rows
*before* editing the Vendor/Product fields: keyboard ticking alone does not re-enable the
Accept button. The Asset Directory field is a read-only combo, pick it with the arrow keys.

### Pose Preset export (`DzPoseAssetFilter`) — confirmed live

Same `NodeNames` shape as the Modifier Asset filter, one level per node: **a
sub-settings entry keyed by the skeleton's or a bone's internal NAME, holding String
entries whose VALUE is a property internal name** (`XRotate`, ..., morph names under
the skeleton key). Root = `RootLabel` (findNodeByLabel) or the primary selection.

```javascript
var skel = fig.getSkeleton();
Scene.selectAllNodes(false); skel.select(true);
var f = new DzPoseAssetFilter();
var s = new DzFileIOSettings();
f.getDefaultOptions(s);
s.setBoolValue("RunSilent", true);
s.setStringValue("RootLabel", "");
var nn = new DzSettings();
var nodes = [skel].concat(skel.getAllBones());
for (var i = 0; i < nodes.length; i++) {
    var sub = new DzSettings(), k = 0;
    for (var j = 0; j < nodes[i].getNumProperties(); j++)
        sub.setStringValue(String(k++), nodes[i].getProperty(j).name);
    nn.setSettingsValue(nodes[i].getName(), sub);   // KEY = node NAME
}
s.setSettingsValue("NodeNames", nn);
s.setBoolValue("SaveCurFrame", false);              // true (default) = current frame only
s.setIntValue("StartFrame", 0);                     // frames, not ticks
s.setIntValue("EndFrame", 34);                      // inclusive
s.setBoolValue("BypassFilter", false);              // false = the dialog's channel set
f.doSave(s, "C:/.../Presets/Poses/Walk.duf", "");  // 0 on success
```

Offer every property: with `BypassFilter` false the filter keeps exactly what the
dialog saves (verified: identical channel URLs to a GUI preset); `true` writes all of
them (~2x the channels, incl. "Disable Transform" etc.). BROKEN, do not retry: the
figure LABEL as a String value in `NodeNames` (the Wearable layout) — returns 0 and
writes a 242-byte `.duf` with 0 channels; bone names as plain String keys → 98.
Tool: `daz_save_pose_preset`.

### Hidden polygons (Geometry Editor hide) — confirmed live (Bug-Katalog #35)

The hidden state lives on the **base** mesh, not on the cached (SubD) mesh:

```javascript
var obj = node.getObject();
var mesh = obj.getCurrentShape().getGeometry();      // DzFacetMesh (base cage)
mesh.isFacetHidden(i);  mesh.hasHiddenFacets();  mesh.getVisibleFacets();
// hide a face group / surface: select it, then hide the selection
var g = mesh.findFaceGroup("lThigh");                 // or findMaterialGroup("Legs")
mesh.beginFacetSelectionEdit(); mesh.deselectAllFacets();
mesh.selectFacets(g, true); mesh.finishFacetSelectionEdit();
mesh.hideSelectedFacets();
mesh.showFacetsByIndexList(g, false);                 // unhide that group (true = no-op)
mesh.hideAllFacets(); mesh.invertHiddenFacets();      // unhide everything
// BROKEN: every *ByIndexList method rejects plain JS arrays and face-group .toList()
//         ("incompatible arguments") — pass the DzFaceGroup/DzMaterialGroup itself.
// BROKEN: new DzFaceGroup() / new DzIndexList() — not constructible from script.
// BROKEN: triggering DzFacetHideSelectedAction — no effect from script.
```

`obj.getCachedGeom()` (what the viewport and the OBJ exporter use) keeps the old
flags until the SubD cache is rebuilt — `n.update()`, `forceCacheUpdate()`,
`invalidateFacetGroups()` do not do it; toggling the shape's `lodlevel` property
(0↔1, then back) does. The hidden state is **not** saved in the `.duf`. Tools:
`daz_get_hidden_facets` / `daz_set_hidden_facets`.

### Auto-follow morph projection on fitted items — confirmed live

A fitted `DzFigure` (clothing, hair) gets projected copies of the target figure's morphs
as modifiers: body shapes (breast, booty, head shape) **and** the pose-driven JCMs
(`pJCMNeckBack_27`, `pJCMCollarTwist_*` …). On a rigid head-weighted hair item those
moved parts by up to 2 cm, changing with the neck pose every frame, and body morphs
made long hair "grow" with the breasts.

```javascript
// Persistent switch, saved with the item — survives save + reload:
fittedNode.getFollowingProjectionOptions().disableMorphProjection = true;
// (DzFollowingProjectionOptions; also has nameFilters, typeFilters,
//  excludeSourceGroups, overrideInclude — semantics untested)

// BROKEN as a fix: obj.removeModifier(m) on the projected morphs. Works for the
// session, but DAZ regenerates every projected morph when the scene is loaded again.
```

Set it on every part that has to move as one unit (e.g. hair cap + ties + braids):
mixing projected and unprojected parts opens gaps at the seams.

Probed live 2026-10-18 (G8F + Blazer Shoes, scratch scene):

```javascript
// Recognising a projected morph — BOTH must hold:
var isProjected = String(m.assetUri.filePath) === ""          // scene-local "#name", no .dsf
    && m.getValueControl().getFollowProperty() ===
       target.getObject().findModifier(m.getName()).getValueControl();
// followProperty alone is NOT enough: vendor-shipped fit morphs (FBMHeight, FBMThin ...
// from the item's own .dsf) follow the target too — they have a filePath.
// Not usable: valueControl.isDynamicallyAutoFollow() (false on all), canAutoFollow()
// (true on almost all), getFollowingProjectionOptions().getNumCorrelatedMorphs() (0).
```

- Setting `disableMorphProjection = true` does **not** remove already projected
  morphs in the running session — they keep deforming. Remove them with
  `obj.removeModifier(m)`; with the switch on, posing, re-fitting and save + reload
  do not bring them back.
- Projection runs **deferred** (event loop, after the script returns), triggered by
  `setFollowTarget()` and only for target morphs that are active at that time. A
  switch set *after* `setFollowTarget()` in the same script does not stop the queued
  pass — set it before fitting.
- Turning the switch back off regenerates nothing, not even after reload; a re-fit
  (`setFollowTarget(null)` → target) queues a new projection.
- `DzFigure.clearGeneratedMorphs()` removed only one of six projected morphs (the
  inactive one) — not a substitute for `removeModifier`.

Tool: `daz_set_morph_projection` (and `daz_fit_clothing(morph_projection=False)`).

### Missing Files prompts — confirmed live (Bug-Katalog #6)

`ContentMgr.openFile()` / a scene load with a missing texture shows, in order:
"Missing Files" (`App.MissingAssetsDialog`, OK =
`...BasicDlgButtonGrpBox.BasicDlgAcceptDialogBtn`), then one "Missing File"
(`App.WarningMessageBox`, "Could not find file: <path>", buttons Locate... / Skip /
Stop Asking) per file, then "Missing Files" again. All answer to UIA `Invoke()`;
dismissed within ~0.3 s DAZ carries on, left open it crashes.
`App.startPromptSuppression()` does **not** help (dialog still shows, crash ~10 s
later). `daz_load_file` and `daz_apply_material_preset(allow_missing=True)` run
`_ui_automation.drive_missing_files_dialogs` next to the load.

### Rigidity weight map ("Rigid") — confirmed live (Bug-Katalog #18 Teil 2)

```javascript
var shape = node.getObject().getCurrentShape();
var map = shape.getRigidityMap();          // DzWeightMap or null; BASE vertex count
map.getFloatWeight(i); map.setFloatWeight(i, 0.75);   // reads back 0.749996 (quantized)
// create one (figure or prop):
var m = new DzWeightMap(); m.setNumWeights(shape.getGeometry().getNumVertices());
shape.setRigidityMap(m);                    // the weight group then lists a DzRigidMapContext
// BROKEN: weightGroup.getWeightMapContext(i).getWeightMap() -> DzTSharedPointer<DzWeightMap>,
//         opaque in DazScript (only className/inherits). Same for getChildWeights(),
//         getWeightMapForBinding(binding, bool).
// BROKEN: new DzWeightMap(n, name) -> 0 weights; always call setNumWeights(n).
```

Saved with the geometry (DSON `rigidity`). Used by the rigidity groups, not by dForce
(dForce pinning = `DzDForceModifier.setInfluenceWeights()`).

### Runtime bone rigging (`new DzBone` + `DzSkinBinding`) — confirmed live (Bug-Katalog #30)

Adding a child bone to an existing figure at runtime (`new DzBone()` +
`parent.addNodeChild(bone, true)` + `new DzBoneBinding()` +
`skin.addBoneBinding(binding)` + `binding.setWeights(weightMap)`) all succeed
without throwing, and `binding.getWeights()` reads the written values back
correctly — but the deformer silently keeps using whatever it had cached
before. Rotating the new bone does **nothing** to `getCachedGeom()` / the
figure's WS bounding box, live-confirmed with `invalidate()`, `update()`,
`skin.invalidate()`, and `obj.forceCacheUpdate(node, true)` all present and
still no effect.

```javascript
// The missing call — DzSkinBinding has a normalize family that was never
// tried: checkAndNormalize(), normalize(), invalidateBlendWeights(). Any one
// of the three flips the same internal state; checkAndNormalize() is the
// most semantically apt. Confirmed live: without it, a rotated bone leaves
// getCachedGeom() completely unchanged; with it (called once, after adding
// the binding and writing its weights), the same rotation moves the
// weighted vertices as expected.
skin.checkAndNormalize();

// BROKEN as a fix (all tried live, all no-ops on their own):
skin.invalidate();
skin.update();
obj.forceCacheUpdate(fig, true);   // note: first arg is the NODE, not a bool
Scene.update();
```

The effect is **persistent** for the rest of the session once triggered —
it flips state on the whole `DzSkinBinding`, not per bone-binding. A second,
brand-new bone added afterward deforms correctly without needing its own
`checkAndNormalize()` call, but call it after every weight-writing batch
anyway (cheap, idempotent) since there is no live-confirmed case where it's
guaranteed unnecessary.

`checkAndNormalize()` also renormalizes competing weights at touched
vertices automatically — confirmed live: a vertex initially 100% weighted to
`head`, given a NEW weight of `0.7` on a sibling bone with `head`'s own
weight left untouched at `1.0` (sum `1.7`), comes back after
`checkAndNormalize()` as `head=0.3`, `newBone=0.7` (sum `1.0`). The new/just
-written weight is treated as authoritative; do **not** manually zero out
the parent bone's weight first — that would double-count against what
`checkAndNormalize()` already does.

**Vertex-count gotcha, same shape as the dForce `setInfluenceWeights`
pitfall:** size every `DzWeightMap` to the figure's BASE (un-subdivided)
geometry vertex count, never `getCachedGeom().getNumVertices()`:

```javascript
var shape = fig.getObject().getCurrentShape();
var numVerts = shape.getGeometry().getNumVertices();   // correct — base cage
// WRONG when SubDivision is active — this is the smoothed/output mesh,
// a different (larger) count with different indexing:
// var numVerts = fig.getObject().getCachedGeom().getNumVertices();
```

Live-measured on `Genesis 8 Female` with SubD active: base 16556 vertices vs.
65806 cached — a `DzWeightMap` sized/indexed against the cached count is
silently wrong for the base-resolution skin binding.

MCP tools: `daz_create_child_bone(parent_label, name, origin, endpoint=None)`
and `daz_set_skin_weights(figure_label, bone_weights)` in
`daz-mcp-server/src/vangard_daz_mcp/tools/rigging.py` — both call
`checkAndNormalize()` internally and size weight maps against the base
geometry, so callers don't need to replicate any of the above by hand.
