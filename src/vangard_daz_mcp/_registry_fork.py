"""DazScript fragments and registry entries for fork-only tools.

Kept separate from ``_registry.py`` on purpose: that file is shared with
upstream (``bluemoonfoundry/daz-mcp-server``) and gets rebased/merged
regularly (see CLAUDE.md's Fork-Versionsschema section). Anything that
exists only in this fork lives here instead, so an upstream merge never
needs to touch fork-added tools at all. See FORK_CHANGELOG.md for what's
fork-only and why.

``_register_scripts()`` in ``_registry.py`` merges ``_REGISTRY_FORK`` (below)
into ``_REGISTRY`` at registration time via a local import — imported inside
the function body, not at module top level, to avoid a circular import
(this module imports ``_RESOLVE_NODE_JS`` back from ``_registry.py``).
"""
from __future__ import annotations

from ._registry import _RESOLVE_NODE_JS

# Phase 6.14: Wearable Preset save (Bug-Katalog #22 Teil 2)
#
# Headless path, live-verified 2026-10-10. DzWearablesAssetFilter.doSave()
# works silently once its settings are laid out the way the filter reads
# them — the long-standing errCode 98 came from a wrong NodeNames layout:
#   - RunSilent is a Bool (setBoolValue), not the "yes" string the
#     DzNodeSupportAssetFilter uses.
#   - NodeNames holds String entries whose VALUE is the node's LABEL (the
#     key is ignored); the filter resolves it via Scene.findNodeByLabel(),
#     so labels must be unique in the scene. Only the listed nodes end up
#     in the preset.
#   - SmartParent / PoseTarget / BypassFilter / CompressOutput /
#     SaveSimulationData are Bools on the top-level settings.
# doSave() return codes seen: 98 (NodeNames empty, or the final write
# failed), 100 (no NodeNames entry resolved to a scene node), 528 (empty
# output path).
_SAVE_WEARABLE_PRESET_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var fig = resolveNode(args.figureLabel);

    var nodes = [];
    var i, n;
    if (args.items && args.items.length) {
        for (i = 0; i < args.items.length; i++) nodes.push(resolveNode(args.items[i]));
    } else {
        // Same notion of "fitted" as daz_list_fitted_items, minus the
        // figure's own bones (they show up as direct children).
        for (i = 0; i < Scene.getNumNodes(); i++) {
            n = Scene.getNode(i);
            if (!n || n === fig || n.inherits("DzBone")) continue;
            var ft = (typeof n.getFollowTarget === "function") ? n.getFollowTarget() : null;
            var parent = (typeof n.getNodeParent === "function") ? n.getNodeParent() : null;
            if ((ft && ft.elementID === fig.elementID) ||
                (parent && parent.elementID === fig.elementID)) nodes.push(n);
        }
    }
    if (nodes.length === 0) {
        throw new Error("Nothing to save: no items are fit or parented to '" + fig.getLabel() + "'");
    }

    var labels = [];
    for (i = 0; i < nodes.length; i++) {
        var lbl = nodes[i].getLabel();
        var first = Scene.findNodeByLabel(lbl);
        if (!first || first.elementID !== nodes[i].elementID) {
            throw new Error("Label '" + lbl + "' is not unique in the scene; the Wearable(s) " +
                "Preset filter resolves items by label and would save the wrong node. " +
                "Rename one of them first.");
        }
        labels.push(lbl);
    }

    Scene.selectAllNodes(false);
    fig.select(true);

    var filter = new DzWearablesAssetFilter();
    var s = new DzFileIOSettings();
    filter.getDefaultOptions(s);
    s.setBoolValue("RunSilent", true);
    var nn = s.getSettingsValue("NodeNames");
    for (i = 0; i < labels.length; i++) nn.setStringValue(String(i), labels[i]);
    s.setSettingsValue("NodeNames", nn);
    s.setBoolValue("SmartParent", args.smartParent !== false);
    s.setBoolValue("PoseTarget", args.poseTarget === true);
    s.setBoolValue("BypassFilter", true);
    if (args.compressOutput !== undefined) s.setBoolValue("CompressOutput", !!args.compressOutput);
    if (args.saveSimulationData !== undefined) s.setBoolValue("SaveSimulationData", !!args.saveSimulationData);

    var err = filter.doSave(s, args.outputPath, "");
    var code = (err && err.valueOf) ? err.valueOf() : err;
    if (code !== 0) {
        var why = {
            98: "no items resolved, or writing the file failed (check DAZ Studio's log.txt)",
            100: "none of the item labels resolved to a scene node",
            528: "empty output path"
        }[code] || "unknown error";
        throw new Error("DzWearablesAssetFilter.doSave failed (error code " + code + "): " + why);
    }

    var outPath = args.outputPath.replace(/\\.[^.\\/\\\\]*$/, "") + ".duf";
    if (!new DzFileInfo(outPath).exists()) {
        throw new Error("doSave reported success but no file exists at " + outPath);
    }
    return { success: true, figure: fig.getLabel(), outputPath: outPath, items: labels };
})()
"""

# Content-Library thumbnails for a saved asset (<name>.duf.png 91x91,
# <name>.tip.png 256x256, RGBA with transparent background). Neither
# DzWearablesAssetFilter nor DzNodeSupportAssetFilter writes them headless.
# Live-verified 2026-10-10: Dz3DViewport.captureImage() returns a null image
# and renderThumbnail(node, path) returns false on the Filament viewport, so
# this goes through a regular render-to-file with the "Viewport" engine
# (renderType ScreenShot — fast, no Iray): hide everything except the items
# and their descendants, aim a temporary camera at their combined bounding
# box (3/4 front view, distance from the camera's field of view), render
# each size, then restore visibility, render options, viewport camera and
# selection in a finally block. opts.aspectWidth/aspectHeight are read-only
# — imageSize alone sets the square output.
_RENDER_ASSET_THUMBNAIL_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var items = [];
    var i, n;
    for (i = 0; i < (args.nodeLabels || []).length; i++) items.push(resolveNode(args.nodeLabels[i]));
    if (items.length === 0) throw new Error("nodeLabels must name at least one node");
    var outputs = args.outputs || [];

    function isInside(node) {
        while (node) {
            for (var k = 0; k < items.length; k++) if (node === items[k]) return true;
            node = node.getNodeParent();
        }
        return false;
    }

    var rm = App.getRenderMgr(), opts = rm.getRenderOptions();
    var v3 = MainWindow.getViewportMgr().getActiveViewport().get3DViewport();
    var helper = rm.getOptionHelper();
    var np = helper ? helper.findProperty("Image Name") : null;
    var pp = helper ? helper.findProperty("Image Path") : null;
    var saved = { renderType: opts.renderType, toId: opts.renderImgToId, file: opts.renderImgFilename,
        w: opts.imageSize.width, h: opts.imageSize.height, cam: opts.camera, vpCam: v3.getCamera(),
        np: np ? np.getValue() : null, pp: pp ? pp.getValue() : null, sel: Scene.getPrimarySelection() };
    var hidden = [], cam = null, written = [], failure = null, restoreErrors = [];
    function restore(name, fn) { try { fn(); } catch (e) { restoreErrors.push(name + ": " + e); } }

    try {
        for (i = 0; i < Scene.getNumNodes(); i++) {
            n = Scene.getNode(i);
            if (!n.getObject() || isInside(n)) continue;
            if (n.isVisible()) { n.setVisible(false); hidden.push(n); }
        }
        var bb = items[0].getWSBoundingBox();
        var minX = bb.minX, minY = bb.minY, minZ = bb.minZ, maxX = bb.maxX, maxY = bb.maxY, maxZ = bb.maxZ;
        for (i = 1; i < items.length; i++) {
            bb = items[i].getWSBoundingBox();
            minX = Math.min(minX, bb.minX); minY = Math.min(minY, bb.minY); minZ = Math.min(minZ, bb.minZ);
            maxX = Math.max(maxX, bb.maxX); maxY = Math.max(maxY, bb.maxY); maxZ = Math.max(maxZ, bb.maxZ);
        }
        var c = new DzVec3((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2);
        var dx = maxX - minX, dy = maxY - minY, dz = maxZ - minZ;
        var radius = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2;

        cam = new DzBasicCamera();
        cam.setName("ZZThumbCam"); cam.setLabel("ZZThumbCam");
        Scene.addNode(cam);
        var fov = cam.getFieldOfView();
        var dist = radius / Math.sin(fov / 2) * 1.02;
        // 3/4 view from the front (Genesis faces +Z), slightly above.
        var len = Math.sqrt(0.25 + 0.1225 + 1);
        cam.setWSPos(new DzVec3(c.x + 0.5 / len * dist, c.y + 0.35 / len * dist, c.z + 1.0 / len * dist));
        cam.aimAt(c);
        v3.setCamera(cam);

        opts.renderType = opts.ScreenShot;
        opts.camera = cam;
        opts.renderImgToId = opts.DirectToFile;
        for (i = 0; i < outputs.length; i++) {
            var path = outputs[i].path, size = outputs[i].size;
            var slash = path.lastIndexOf("/");
            new DzDir(path.substring(0, slash)).mkpath(path.substring(0, slash));
            opts.imageSize = new QSize(size, size);
            opts.renderImgFilename = path;
            if (np) np.setValue(path.substring(slash + 1));
            if (pp) pp.setValue(path.substring(0, slash));
            opts.applyChanges();
            MainWindow.repaintActive3DViewport();
            rm.doRender(opts);
            if (!new DzFileInfo(path).exists()) throw new Error("Render wrote no file at " + path);
            written.push({ path: path, size: size });
        }
    } catch (e) {
        failure = String(e);
    } finally {
        for (var j = 0; j < hidden.length; j++) restore("visibility", function(){ hidden[j].setVisible(true); });
        restore("renderType", function(){ opts.renderType = saved.renderType; });
        restore("renderImgToId", function(){ opts.renderImgToId = saved.toId; });
        restore("renderImgFilename", function(){ opts.renderImgFilename = saved.file; });
        restore("imageSize", function(){ opts.imageSize = new QSize(saved.w, saved.h); });
        restore("camera", function(){ opts.camera = saved.cam; });
        restore("Image Name", function(){ if (np && saved.np !== null) np.setValue(saved.np); });
        restore("Image Path", function(){ if (pp && saved.pp !== null) pp.setValue(saved.pp); });
        restore("applyChanges", function(){ opts.applyChanges(); });
        restore("viewport camera", function(){ if (saved.vpCam) v3.setCamera(saved.vpCam); });
        restore("temp camera", function(){ if (cam) Scene.removeNode(cam); });
        restore("selection", function(){ Scene.selectAllNodes(false); if (saved.sel) saved.sel.select(true); });
    }
    if (failure) throw new Error("Thumbnail render failed: " + failure +
        (restoreErrors.length ? " (restore problems: " + restoreErrors.join("; ") + ")" : ""));
    var labels = [];
    for (i = 0; i < items.length; i++) labels.push(items[i].getLabel());
    return { success: true, nodes: labels, files: written, restoreErrors: restoreErrors };
})()
"""

# UI-Automation fallback for the same save (use_ui_automation=True).
# Selects the target figure and fires DzWearablesAssetFilterAction. This
# BLOCKS on two native dialogs (a file-save dialog, then a Qt options
# dialog) — must be submitted via the async endpoint. The Python-side
# tool (daz_save_wearable_preset, _ui_automation.py) drives those dialogs
# via Windows UI Automation once this has fired.
_TRIGGER_WEARABLE_SAVE_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var fig = resolveNode(args.figureLabel);
    Scene.selectAllNodes(false);
    fig.select(true);
    var mgr = MainWindow.getActionMgr();
    var act = mgr.findAction("DzWearablesAssetFilterAction");
    if (!act) throw new Error("DzWearablesAssetFilterAction not found in DzActionMgr");
    act.trigger();
    return { success: true, figure: fig.getLabel() };
})()
"""

# Phase 6.20: Modifier Asset save (Bug-Katalog #37)
#
# Preflight shared by the headless path (_SAVE_MODIFIER_ASSET_SCRIPT below)
# and the UI-Automation fallback: runs synchronously first so a typo'd morph
# name or an unsaved item fails fast instead of after a dialog was opened.
_MODIFIER_ASSET_PREFLIGHT_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var node = resolveNode(args.nodeLabel);
    var obj = node.getObject();
    if (!obj) throw new Error("Node '" + node.getLabel() + "' has no geometry object (no modifiers to save)");
    var available = [];
    var byName = {};
    var byLabel = {};
    for (var i = 0; i < obj.getNumModifiers(); i++) {
        var m = obj.getModifier(i);
        var entry = { name: m.getName(), label: m.getLabel(), type: m.className() };
        available.push(entry);
        byName[entry.name] = entry;
        byLabel[entry.label] = entry;
    }
    var morphs = [];
    var missing = [];
    var wanted = args.morphNames || [];
    for (var j = 0; j < wanted.length; j++) {
        var hit = byName[wanted[j]] || byLabel[wanted[j]];
        if (hit) morphs.push(hit); else missing.push(wanted[j]);
    }
    var cm = App.getContentMgr();
    var dirs = [];
    for (var k = 0; k < cm.getNumContentDirectories(); k++) dirs.push(cm.getContentDirectoryPath(k));
    // The filter refuses (with a MODAL "Resource Error", RunSilent or not)
    // unless the node itself comes from a saved .dsf asset.
    var assetFile = (node.assetUri && node.assetUri.filePath) ? String(node.assetUri.filePath) : "";
    var assetContentDir = null;
    for (var d = 0; d < dirs.length && assetFile; d++) {
        if (new DzFileInfo(dirs[d] + assetFile).exists()) { assetContentDir = dirs[d]; break; }
    }
    return { node: node.getLabel(), nodeName: node.getName(), morphs: morphs,
             missing: missing, available: available, contentDirectories: dirs,
             assetFile: assetFile, isSavedAsset: /\\.dsf$/i.test(assetFile),
             assetContentDir: assetContentDir };
})()
"""

# Headless Modifier Asset save, live-verified 2026-10-10 (Bug-Katalog #37).
# The long-standing "returns 0, writes nothing" came from a wrong NodeNames
# layout. What DzModifierSupportAssetFilter actually reads in silent mode:
#   - RunSilent: Bool.
#   - Root node: RootLabel (resolved via findNodeByLabel) or, if empty, the
#     primary selection — we leave RootLabel empty and select the node, so a
#     duplicate label can't pick the wrong one.
#   - BaseDataPath / VendorName / ProductName: required strings.
#   - NodeNames: sub-settings keyed by the root node's NAME (or a bone name);
#     each holds String entries whose VALUE is a property's internal name —
#     the morph name; keys are ignored. Morphs from cloud-encrypted files
#     are skipped silently.
#   - CompressOutput / ForceUniqueIDs: Bools. The doSave() path argument is
#     ignored; files go to <BaseDataPath>/data/<item asset dir>/Morphs/
#     <vendor>/<product>/<morph>.dsf.
# Two failure modes still show a MODAL box regardless of RunSilent (no root
# node; node not from a .dsf asset) — the preflight rules both out first.
_SAVE_MODIFIER_ASSET_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var node = resolveNode(args.nodeLabel);
    var assetFile = (node.assetUri && node.assetUri.filePath) ? String(node.assetUri.filePath) : "";
    if (!/\\.dsf$/i.test(assetFile)) {
        throw new Error("Node '" + node.getLabel() + "' is not backed by a saved Figure/Prop " +
            "Asset (.dsf) — save it with daz_save_prop_asset first.");
    }
    Scene.selectAllNodes(false);
    node.select(true);

    var f = new DzModifierSupportAssetFilter();
    var s = new DzFileIOSettings();
    f.getDefaultOptions(s);
    s.setBoolValue("RunSilent", true);
    s.setStringValue("RootLabel", "");
    s.setStringValue("BaseDataPath", args.baseDataPath);
    s.setStringValue("VendorName", args.vendorName);
    s.setStringValue("ProductName", args.productName);
    var nn = s.getSettingsValue("NodeNames");
    var sub = new DzSettings();
    var names = args.morphNames || [];
    for (var i = 0; i < names.length; i++) sub.setStringValue(String(i), names[i]);
    nn.setSettingsValue(node.getName(), sub);
    s.setSettingsValue("NodeNames", nn);
    if (args.compressOutput !== undefined) s.setBoolValue("CompressOutput", !!args.compressOutput);
    if (args.forceUniqueIds !== undefined) s.setBoolValue("ForceUniqueIDs", !!args.forceUniqueIds);

    var err = f.doSave(s, "", "");
    var code = (err && err.valueOf) ? err.valueOf() : err;
    if (code !== 0) {
        throw new Error("DzModifierSupportAssetFilter.doSave failed (error code " + code +
            ") — check DAZ Studio's log.txt for a 'Running silent. No ... defined.' line");
    }
    return { success: true, node: node.getLabel(), assetFile: assetFile,
             baseDataPath: args.baseDataPath, morphs: names };
})()
"""

# Selects the node and fires DzModifierAssetFilterAction. BLOCKS on the
# modal "Modifier Asset(s) Save Options" dialog (or on a "Resource Error"
# box if the node itself was never saved as a Figure/Prop Asset) — submit via
# the async endpoint only; daz_save_modifier_asset drives the dialog.
_TRIGGER_MODIFIER_ASSET_SAVE_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var node = resolveNode(args.nodeLabel);
    Scene.selectAllNodes(false);
    node.select(true);
    var act = MainWindow.getActionMgr().findAction("DzModifierAssetFilterAction");
    if (!act) throw new Error("DzModifierAssetFilterAction not found in DzActionMgr");
    act.trigger();
    return { success: true, node: node.getLabel() };
})()
"""

# Phase 6.27: Pose Preset save (static or animated range)
#
# Headless, live-verified 2026-10-24 against a GUI-saved animated preset
# (identical channel set). The old "errCode 0, empty .duf" came from a wrong
# NodeNames layout. What DzPoseAssetFilter reads in silent mode:
#   - RunSilent: Bool. Root: RootLabel (findNodeByLabel) or, if empty, the
#     primary selection — we select the figure and leave RootLabel empty.
#   - NodeNames: one sub-settings entry per node, keyed by the skeleton's
#     NAME or a bone NAME; its String entries' VALUES are property internal
#     names (transforms, and morph names under the skeleton key); keys inside
#     are ignored. Offering every property is fine: unless BypassFilter is
#     set, the filter keeps only what the GUI's Pose Preset dialog would.
#   - SaveCurFrame (Bool, default true) / StartFrame / EndFrame (Int, frames).
#   - CompressOutput: Bool. Return codes: 98 (no root node / NodeNames empty),
#     528 (empty output path).
_SAVE_POSE_PRESET_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var fig = resolveNode(args.figureLabel);
    var skel = fig.getSkeleton ? fig.getSkeleton() : null;
    if (!skel) throw new Error("'" + fig.getLabel() + "' is not a figure (no skeleton)");

    var step = Scene.getTimeStep();
    var range = Scene.getAnimRange();
    var start = (args.startFrame !== undefined) ? args.startFrame : Math.round(range.start / step);
    var end = (args.endFrame !== undefined) ? args.endFrame : Math.round(range.end / step);
    if (!args.currentFrameOnly && end < start) {
        throw new Error("endFrame (" + end + ") is before startFrame (" + start + ")");
    }

    var nodes = [skel].concat(skel.getAllBones());
    var nn = new DzSettings();
    var offered = 0;
    var i, j, k;
    for (i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var sub = new DzSettings();
        k = 0;
        for (j = 0; j < n.getNumProperties(); j++) {
            var p = n.getProperty(j);
            if (p.inherits("DzNumericProperty")) sub.setStringValue(String(k++), p.name);
        }
        if (n === skel && args.includeMorphs !== false && skel.getObject()) {
            var obj = skel.getObject();
            for (j = 0; j < obj.getNumModifiers(); j++) {
                var m = obj.getModifier(j);
                if (m.inherits("DzMorph")) sub.setStringValue(String(k++), m.getName());
            }
        }
        if (k) nn.setSettingsValue(n.getName(), sub);
        offered += k;
    }

    var prevSel = Scene.getSelectedNodeList();
    Scene.selectAllNodes(false);
    skel.select(true);

    var f = new DzPoseAssetFilter();
    var s = new DzFileIOSettings();
    f.getDefaultOptions(s);
    s.setBoolValue("RunSilent", true);
    s.setStringValue("RootLabel", "");
    s.setSettingsValue("NodeNames", nn);
    s.setBoolValue("SaveCurFrame", !!args.currentFrameOnly);
    s.setIntValue("StartFrame", start);
    s.setIntValue("EndFrame", end);
    s.setBoolValue("BypassFilter", args.bypassFilter === true);
    if (args.compressOutput !== undefined) s.setBoolValue("CompressOutput", !!args.compressOutput);

    var err;
    try {
        err = f.doSave(s, args.outputPath, "");
    } finally {
        Scene.selectAllNodes(false);
        for (i = 0; i < prevSel.length; i++) prevSel[i].select(true);
    }
    var code = (err && err.valueOf) ? err.valueOf() : err;
    if (code !== 0) {
        var why = { 98: "no root figure, or nothing to save", 528: "empty output path" }[code] ||
            "check DAZ Studio's log.txt";
        throw new Error("DzPoseAssetFilter.doSave failed (error code " + code + "): " + why);
    }
    return { success: true, figure: fig.getLabel(), outputPath: args.outputPath,
             currentFrameOnly: !!args.currentFrameOnly,
             startFrame: args.currentFrameOnly ? null : start,
             endFrame: args.currentFrameOnly ? null : end,
             propertiesOffered: offered };
})()
"""

# Phase 6.15: Extra bones / skin weights (Bug-Katalog #30)
#
# DzSkinBinding does not pick up a newly added DzBoneBinding's weights until
# checkAndNormalize() is called on it at least once afterward — confirmed
# live (see docs/daz-mcp-bridge-bugs.md #30, Nachtrag 2026-09-14). Without
# that call the deformer keeps using whatever weight state it had cached
# before, so a bone rotation silently does nothing to the mesh even though
# DzBoneBinding.getWeights() correctly reads back the values just written.
#
# checkAndNormalize() also re-normalizes existing bone weights at touched
# vertices to keep the per-vertex total at 1.0 (confirmed live: setting a new
# bone's weight to 0.7 on a vertex previously 100% weighted to its parent
# bone reduces the parent's weight to 0.3 automatically) — callers do not
# need to manually zero out the parent bone's weight first.
#
# Weight maps must be sized to the BASE (un-subdivided) geometry vertex
# count — node.getObject().getCurrentShape().getGeometry().getNumVertices()
# — never to getCachedGeom().getNumVertices(), which reflects the current
# SubD level and can be a much larger, differently-indexed count (same
# gotcha as the dForce influence-weights vertex count, see
# _SET_DFORCE_INFLUENCE_WEIGHTS_SCRIPT in _registry.py).
_FIND_FIGURE_ANCESTOR_JS = """\
    function findFigureAncestor(node) {
        var n = node;
        while (n) {
            if (typeof n.getSkinBinding === "function") return n;
            n = (typeof n.getNodeParent === "function") ? n.getNodeParent() : null;
        }
        return null;
    }
"""

_CREATE_CHILD_BONE_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + _FIND_FIGURE_ANCESTOR_JS + """
    var args = getArguments()[0] || {};
    var parentId = args.parentLabel;
    var boneName = args.name;
    var originArr = args.origin;
    var endpointArr = args.endpoint;

    if (!boneName) throw new Error("name is required");
    if (!originArr || originArr.length !== 3) throw new Error("origin must be [x, y, z]");

    var parent = resolveNode(parentId);
    var figure = findFigureAncestor(parent);
    if (!figure) {
        throw new Error("Parent node '" + parentId + "' has no DzFigure ancestor with a skin binding.");
    }
    var skin = figure.getSkinBinding();
    if (!skin) throw new Error("Figure '" + figure.getLabel() + "' has no skin binding.");

    var bone = new DzBone();
    bone.setName(boneName);
    bone.setLabel(boneName);
    parent.addNodeChild(bone, true);

    var origin = new DzVec3(originArr[0], originArr[1], originArr[2]);
    bone.setOrigin(origin);

    var endpoint;
    if (endpointArr && endpointArr.length === 3) {
        endpoint = new DzVec3(endpointArr[0], endpointArr[1], endpointArr[2]);
    } else {
        endpoint = new DzVec3(origin.x, origin.y + 5, origin.z);
    }
    bone.setEndPoint(endpoint);

    var shape = figure.getObject().getCurrentShape();
    var numVerts = shape.getGeometry().getNumVertices();

    var binding = new DzBoneBinding();
    binding.setBone(bone);
    var wm = new DzWeightMap();
    wm.setNumWeights(numVerts);
    binding.setWeights(wm);
    skin.addBoneBinding(binding);

    // See docs/daz-mcp-bridge-bugs.md #30 -- without this the new binding's
    // (currently all-zero) weights never reach the deformer, and any weights
    // written to it later via daz_set_skin_weights would not either.
    skin.checkAndNormalize();

    return {
        success: true,
        figure: figure.getLabel(),
        parent: parent.getLabel(),
        bone: bone.getLabel(),
        elementID: bone.elementID,
        vertexCount: numVerts,
        origin: { x: origin.x, y: origin.y, z: origin.z },
        endpoint: { x: endpoint.x, y: endpoint.y, z: endpoint.z }
    };
})()
"""

_SET_SKIN_WEIGHTS_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var figureId = args.figureLabel;
    var boneWeights = args.boneWeights || {};

    var figure = resolveNode(figureId);
    var skin = (typeof figure.getSkinBinding === "function") ? figure.getSkinBinding() : null;
    if (!skin) {
        throw new Error("Node '" + figureId + "' has no skin binding (getSkinBinding() returned null) -- pass a figure, not a prop.");
    }

    var shape = figure.getObject().getCurrentShape();
    var numVerts = shape.getGeometry().getNumVertices();

    var updated = [];
    var errors = [];

    for (var boneName in boneWeights) {
        var bone = figure.findBone(boneName);
        if (!bone) { errors.push(boneName + ": bone not found on figure"); continue; }

        var binding = skin.findBoneBinding(bone);
        if (!binding) {
            binding = new DzBoneBinding();
            binding.setBone(bone);
            var freshMap = new DzWeightMap();
            freshMap.setNumWeights(numVerts);
            binding.setWeights(freshMap);
            skin.addBoneBinding(binding);
        }

        var wm = binding.getWeights();
        if (!wm || wm.getNumWeights() !== numVerts) {
            wm = new DzWeightMap();
            wm.setNumWeights(numVerts);
        }

        var spec = boneWeights[boneName];
        var count = 0;
        if (spec && typeof spec.length === "number") {
            // dense: float[numVerts]
            if (spec.length !== numVerts) {
                errors.push(boneName + ": dense array length " + spec.length + " != vertex count " + numVerts);
            } else {
                for (var i = 0; i < numVerts; i++) {
                    wm.setFloatWeight(i, parseFloat(spec[i]));
                }
                count = numVerts;
            }
        } else {
            // sparse: {"vertexIndex": weight, ...}
            for (var key in spec) {
                var idx = parseInt(key, 10);
                if (isNaN(idx) || idx < 0 || idx >= numVerts) { errors.push(boneName + ": vertex index out of range: " + key); continue; }
                wm.setFloatWeight(idx, parseFloat(spec[key]));
                count++;
            }
        }

        binding.setWeights(wm);
        updated.push({ bone: boneName, weightsSet: count });
    }

    // See docs/daz-mcp-bridge-bugs.md #30 -- without this call none of the
    // weight writes above reach the deformer, and other bones' weights at
    // the touched vertices are not renormalized to sum back to 1.0.
    skin.checkAndNormalize();

    return {
        success: true,
        figure: figure.getLabel(),
        vertexCount: numVerts,
        updated: updated,
        errors: errors
    };
})()
"""

# Phase 6.16: Geometry Shell (Bug-Katalog #31)
#
# Creates a native DzGeometryShellNode via DzNewGeometryShellAction — there
# is no known direct-constructor path that produces a shell with real
# geometry (new DzGeometryShellNode() does not work). Like
# DzStrandHairCreateNodeAction (see _CREATE_STRAND_HAIR_SCRIPT in
# _registry.py), this BLOCKS on a DAZ Studio confirmation dialog and must be
# submitted via the async endpoint; the daz_create_geometry_shell MCP tool
# confirms the dialog itself via Windows UI Automation, no human click
# needed. Moved here from _registry.py on 2026-09-20 (was originally added
# to the upstream-shared file by mistake in commit e8767d2).
_CREATE_GEOMETRY_SHELL_SCRIPT = """\
(function(){
    var args = getArguments()[0] || {};
    var targetLabel = args.targetNodeLabel;

    var target = Scene.findNodeByLabel(targetLabel);
    if (!target) target = Scene.findNode(targetLabel);
    if (!target) throw new Error("Target node not found: " + targetLabel);

    function shellLabels() {
        var labels = [];
        for (var i = 0; i < Scene.getNumNodes(); i++) {
            var n = Scene.getNode(i);
            if (n.inherits("DzGeometryShellNode")) labels.push(n.getLabel());
        }
        return labels;
    }

    var before = shellLabels();

    var mgr = MainWindow.getActionMgr();
    var act = mgr.findAction("DzNewGeometryShellAction");
    if (!act) throw new Error("Action 'DzNewGeometryShellAction' not found in DzActionMgr");

    Scene.selectAllNodes(false);
    target.select(true);

    // Like DzStrandHairCreateNodeAction (see vangard-create-strand-hair),
    // this blocks until a human confirms/cancels DAZ Studio's own dialog —
    // meant to be run via the async endpoint, never synchronously.
    act.trigger();

    var after = shellLabels();
    var newLabels = [];
    for (var i = 0; i < after.length; i++) {
        if (before.indexOf(after[i]) === -1) newLabels.push(after[i]);
    }

    if (newLabels.length === 0) {
        throw new Error(
            "No new Geometry Shell node appeared after the action ran. " +
            "The user likely cancelled the confirmation dialog, or DAZ Studio " +
            "is still waiting for it to be confirmed."
        );
    }

    var newNode = Scene.findNodeByLabel(newLabels[0]);
    var obj = newNode.getObject();

    return {
        success: true,
        node: newNode.getLabel(),
        target: target.getLabel(),
        has_geometry: !!obj
    };
})()
"""

_LIST_GEOMETRY_SHELLS_SCRIPT = """\
(function(){
    var result = [];
    for (var i = 0; i < Scene.getNumNodes(); i++) {
        var n = Scene.getNode(i);
        if (!n.inherits("DzGeometryShellNode")) continue;

        var target = n.getTarget();
        var obj = n.getObject();
        var hasGeometry = !!obj;
        var materials = [];
        if (obj) {
            var shape = obj.getCurrentShape();
            if (shape) {
                for (var m = 0; m < shape.getNumMaterials(); m++) {
                    var mat = shape.getMaterial(m);
                    var lbl = (typeof mat.getLabel === "function") ? mat.getLabel() : mat.getName();
                    materials.push(lbl || mat.getName());
                }
            }
        }

        result.push({
            label: n.getLabel(),
            name: n.getName(),
            target: target ? target.getLabel() : null,
            has_geometry: hasGeometry,
            materials: materials
        });
    }
    return { count: result.length, nodes: result };
})()
"""

# Phase 6.17: Shell face-group visibility (Bug-Katalog #35 workaround)
#
# DzGeometryShellNode is the only node type whose DazScript API exposes a
# real, queryable per-face-group hide/show state: one DzBoolProperty per
# face group, named facet_group_<name>_vis and grouped under
# "/Shell/Visibility/Face Groups" in the Parameters pane. Confirmed live
# (2026-09-20) both in a saved .duf (node_library studio_node_channels
# extra) and via daz_execute against a freshly created shell. Unlike
# Geometry-Editor hiding on a plain mesh (see the hidden-facets scripts
# below, Bug-Katalog #35), the shell state persists in the .duf.
_GET_SHELL_VISIBILITY_SCRIPT = """\
(function(){
    var args = getArguments()[0] || {};
    var label = args.shellLabel;
    var n = Scene.findNodeByLabel(label);
    if (!n) n = Scene.findNode(label);
    if (!n) throw new Error("Node not found: " + label);
    if (!n.inherits("DzGeometryShellNode")) {
        throw new Error("Node '" + label + "' is not a DzGeometryShellNode (found " +
            n.className() + "). It only works on a Geometry Shell node's OWN " +
            "face-group visibility toggles. For Geometry-Editor hidden polygons on " +
            "a regular mesh/prop use daz_get_hidden_facets instead (Bug-Katalog #35).");
    }
    var groups = [];
    for (var i = 0; i < n.getNumProperties(); i++) {
        var p = n.getProperty(i);
        var name = p.getName();
        if (name.indexOf("facet_group_") === 0 && name.lastIndexOf("_vis") === name.length - 4) {
            groups.push({ name: name, label: p.getLabel(), visible: !!p.getValue() });
        }
    }
    return { node: n.getLabel(), count: groups.length, groups: groups };
})()
"""

_SET_SHELL_VISIBILITY_SCRIPT = """\
(function(){
    var args = getArguments()[0] || {};
    var label = args.shellLabel;
    var settings = args.groupVisibility || {};
    var n = Scene.findNodeByLabel(label);
    if (!n) n = Scene.findNode(label);
    if (!n) throw new Error("Node not found: " + label);
    if (!n.inherits("DzGeometryShellNode")) {
        throw new Error("Node '" + label + "' is not a DzGeometryShellNode (found " +
            n.className() + "). It only works on a Geometry Shell node's OWN " +
            "face-group visibility toggles. For Geometry-Editor hidden polygons on " +
            "a regular mesh/prop use daz_set_hidden_facets instead (Bug-Katalog #35).");
    }
    var byId = {};
    var byLabel = {};
    var i, p, name;
    for (i = 0; i < n.getNumProperties(); i++) {
        p = n.getProperty(i);
        name = p.getName();
        if (name.indexOf("facet_group_") === 0 && name.lastIndexOf("_vis") === name.length - 4) {
            byId[name] = p;
            byLabel[p.getLabel()] = p;
        }
    }
    var applied = [];
    var errors = [];
    for (var key in settings) {
        if (!settings.hasOwnProperty(key)) continue;
        var prop = byId[key] || byLabel[key];
        if (!prop) {
            errors.push(key + ": no matching face group visibility property");
            continue;
        }
        prop.setValue(settings[key] ? 1 : 0);
        applied.push({ group: prop.getLabel(), name: prop.getName(), visible: !!settings[key] });
    }
    return { node: n.getLabel(), applied: applied, errors: errors };
})()
"""

# Geometry-Editor hidden-polygon state on a plain mesh (Bug-Katalog #35).
# Confirmed live (2026-10-17, G8F): the state IS scriptable -- on the BASE
# DzFacetMesh (getCurrentShape().getGeometry()), not on getCachedGeom():
#   read:   isFacetHidden(i), hasHiddenFacets()
#   hide:   selectFacets(faceGroup, true) + hideSelectedFacets()
#   unhide: showFacetsByIndexList(faceGroup, false)   (true = no-op)
#   all:    hideAllFacets() + invertHiddenFacets() unhides everything
# Plain JS arrays are rejected by every *ByIndexList method ("incompatible
# arguments"); a DzFaceGroup/DzMaterialGroup from findFaceGroup()/
# findMaterialGroup() is accepted. getCachedGeom() -- what the viewport and
# the OBJ exporter's IgnoreInvisible filter see -- only picks the flags up
# when the SubD cache is rebuilt; n.update(), forceCacheUpdate(),
# invalidateFacetGroups() do not, toggling the shape's "lodlevel" does.
# The hidden state is NOT saved in the .duf (gone after a reload).
_HIDDEN_FACETS_COMMON = """\
    function resolveMesh(label) {
        var n = Scene.findNodeByLabel(label);
        if (!n) n = Scene.findNode(label);
        if (!n) throw new Error("Node not found: " + label);
        var obj = n.getObject();
        var shape = obj ? obj.getCurrentShape() : null;
        var mesh = shape ? shape.getGeometry() : null;
        if (!mesh || !mesh.inherits("DzFacetMesh")) {
            throw new Error("Node '" + label + "' has no polygon mesh (" + n.className() + ")");
        }
        return {node: n, obj: obj, shape: shape, mesh: mesh};
    }
    function hiddenFlags(mesh) {
        var flags = [];
        var total = 0;
        for (var i = 0; i < mesh.getNumFacets(); i++) {
            var h = mesh.isFacetHidden(i);
            flags.push(h);
            if (h) total++;
        }
        return {flags: flags, total: total};
    }
    function groupStats(mesh, flags, kind, onlyHidden) {
        var isFace = kind === "face";
        var num = isFace ? mesh.getNumFaceGroups() : mesh.getNumMaterialGroups();
        var out = [];
        for (var gi = 0; gi < num; gi++) {
            var g = isFace ? mesh.getFaceGroup(gi) : mesh.getMaterialGroup(gi);
            var cnt = g.count();
            var hid = 0;
            for (var k = 0; k < cnt; k++) if (flags[g.getIndex(k)]) hid++;
            if (onlyHidden && hid === 0) continue;
            out.push({name: g.getName(), facets: cnt, hidden: hid});
        }
        return out;
    }
    function refreshCache(m) {
        // Rebuild the cached (SubD) mesh so the viewport/exporters see the new flags.
        var lod = m.shape.findProperty("lodlevel");
        if (lod) {
            var v = lod.getValue();
            lod.setValue(v === 0 ? 1 : 0);
            m.obj.forceCacheUpdate(m.node, true);
            lod.setValue(v);
        }
        m.obj.forceCacheUpdate(m.node, true);
        return !!lod;
    }
"""

_GET_HIDDEN_FACETS_SCRIPT = """\
(function(){
    var args = getArguments()[0] || {};
""" + _HIDDEN_FACETS_COMMON + """
    var m = resolveMesh(args.nodeLabel);
    var onlyHidden = args.onlyHidden !== false;
    var hf = hiddenFlags(m.mesh);
    return {
        node: m.node.getLabel(),
        total_facets: m.mesh.getNumFacets(),
        hidden_facets: hf.total,
        face_groups: groupStats(m.mesh, hf.flags, "face", onlyHidden),
        material_groups: groupStats(m.mesh, hf.flags, "material", onlyHidden)
    };
})()
"""

_SET_HIDDEN_FACETS_SCRIPT = """\
(function(){
    var args = getArguments()[0] || {};
""" + _HIDDEN_FACETS_COMMON + """
    var m = resolveMesh(args.nodeLabel);
    var mesh = m.mesh;
    var hide = args.hidden !== false;
    var applied = [];
    var errors = [];

    if (args.unhideAll) {
        mesh.hideAllFacets();
        mesh.invertHiddenFacets();
    }

    function apply(names, kind) {
        for (var i = 0; i < names.length; i++) {
            var g = kind === "face" ? mesh.findFaceGroup(names[i]) : mesh.findMaterialGroup(names[i]);
            if (!g) {
                errors.push(kind + " group not found: " + names[i]);
                continue;
            }
            if (hide) {
                mesh.beginFacetSelectionEdit();
                mesh.deselectAllFacets();
                mesh.selectFacets(g, true);
                mesh.finishFacetSelectionEdit();
                mesh.hideSelectedFacets();
            } else {
                mesh.showFacetsByIndexList(g, false);
            }
            applied.push({group: names[i], kind: kind, facets: g.count()});
        }
    }
    apply(args.faceGroups || [], "face");
    apply(args.materialGroups || [], "material");

    // Leave no facet selection behind (it would show up in the Geometry Editor).
    mesh.beginFacetSelectionEdit();
    mesh.deselectAllFacets();
    mesh.finishFacetSelectionEdit();

    var refreshed = args.refresh !== false ? refreshCache(m) : false;
    var hf = hiddenFlags(mesh);
    return {
        node: m.node.getLabel(),
        hidden: hide,
        applied: applied,
        errors: errors,
        hidden_facets: hf.total,
        total_facets: mesh.getNumFacets(),
        cache_refreshed: refreshed
    };
})()
"""

# Rigidity weight map (Bug-Katalog #18 Teil 2). Confirmed live 2026-10-17:
# the map behind the Node Weight Map Brush's "Rigid" entry is
# DzShape.getRigidityMap() -- a plain, fully scriptable DzWeightMap
# (get/setFloatWeight, sized to the BASE vertex count) that DazScript can't
# reach through DzRigidMapContext.getWeightMap() (returns an opaque
# DzTSharedPointer). It is saved with the geometry (DSON "rigidity") and
# survives a scene reload. It belongs to the rigidity groups (parts that must
# keep their shape under morphs/fitting), not to dForce -- dForce pinning is
# InfluenceWeights. Creating it: new DzWeightMap() + setNumWeights(n) +
# shape.setRigidityMap(map); the figure's weight group then lists a
# DzRigidMapContext like after createWeightMap("Rigid"). Values are stored
# quantized (0.75 reads back as 0.749996).
_RIGIDITY_COMMON = """\
    function rigidityTarget(label) {
        var n = resolveNode(label);
        var obj = n.getObject ? n.getObject() : null;
        var shape = obj ? obj.getCurrentShape() : null;
        var mesh = shape ? shape.getGeometry() : null;
        if (!mesh) throw new Error("Node '" + label + "' has no geometry (" + n.className() + ")");
        return {node: n, shape: shape, mesh: mesh, numVerts: mesh.getNumVertices()};
    }
    function groupVertices(mesh, kind, name) {
        var g = kind === "face" ? mesh.findFaceGroup(name) : mesh.findMaterialGroup(name);
        if (!g) return null;
        var seen = {};
        var verts = [];
        for (var k = 0; k < g.count(); k++) {
            var f = mesh.getFacet(g.getIndex(k));
            var ids = [f.vertIdx1, f.vertIdx2, f.vertIdx3, f.vertIdx4];
            for (var j = 0; j < 4; j++) {
                var v = ids[j];
                if (v >= 0 && !seen[v]) { seen[v] = true; verts.push(v); }
            }
        }
        return verts;
    }
    function stats(map, numVerts, includeWeights) {
        var nonZero = 0, minW = null, maxW = null, sparse = {};
        for (var i = 0; i < map.getNumWeights(); i++) {
            var w = map.getFloatWeight(i);
            if (w === 0) continue;
            nonZero++;
            if (minW === null || w < minW) minW = w;
            if (maxW === null || w > maxW) maxW = w;
            if (includeWeights) sparse[String(i)] = Math.round(w * 10000) / 10000;
        }
        var out = {num_weights: map.getNumWeights(), num_vertices: numVerts,
                   non_zero: nonZero, min_non_zero: minW, max: maxW};
        if (includeWeights) out.weights = sparse;
        return out;
    }
"""

_GET_RIGIDITY_WEIGHTS_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + _RIGIDITY_COMMON + """
    var args = getArguments()[0] || {};
    var t = rigidityTarget(args.nodeLabel);
    var map = t.shape.getRigidityMap();
    var out = {node: t.node.getLabel(), has_map: !!map, num_vertices: t.numVerts};
    if (!map) return out;
    var st = stats(map, t.numVerts, args.includeWeights === true);
    for (var k in st) if (st.hasOwnProperty(k)) out[k] = st[k];
    return out;
})()
"""

_SET_RIGIDITY_WEIGHTS_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + _RIGIDITY_COMMON + """
    var args = getArguments()[0] || {};
    var t = rigidityTarget(args.nodeLabel);
    var map = t.shape.getRigidityMap();
    var created = false;
    if (!map) {
        map = new DzWeightMap();
        map.setNumWeights(t.numVerts);
        map.setName("RigidityMap");
        t.shape.setRigidityMap(map);
        map = t.shape.getRigidityMap();
        created = true;
    }
    if (map.getNumWeights() !== t.numVerts) map.setNumWeights(t.numVerts);

    var errors = [];
    var written = 0;
    function put(i, w) {
        if (isNaN(i) || i < 0 || i >= t.numVerts) { errors.push("vertex index out of range: " + i); return; }
        w = parseFloat(w);
        if (isNaN(w)) { errors.push("not a number for vertex " + i); return; }
        map.setFloatWeight(i, Math.max(0, Math.min(1, w)));
        written++;
    }

    if (args.clear) {
        for (var c = 0; c < t.numVerts; c++) map.setFloatWeight(c, 0);
    }
    var spec = args.weights;
    if (spec && typeof spec.length === "number") {
        if (spec.length !== t.numVerts) {
            errors.push("dense array length " + spec.length + " != vertex count " + t.numVerts);
        } else {
            for (var d = 0; d < spec.length; d++) put(d, spec[d]);
        }
    } else if (spec) {
        for (var key in spec) if (spec.hasOwnProperty(key)) put(parseInt(key, 10), spec[key]);
    }
    var groups = [["face", args.faceGroups || {}], ["material", args.materialGroups || {}]];
    var applied = [];
    for (var gi = 0; gi < groups.length; gi++) {
        var kind = groups[gi][0], gmap = groups[gi][1];
        for (var name in gmap) {
            if (!gmap.hasOwnProperty(name)) continue;
            var verts = groupVertices(t.mesh, kind, name);
            if (!verts) { errors.push(kind + " group not found: " + name); continue; }
            for (var vi = 0; vi < verts.length; vi++) put(verts[vi], gmap[name]);
            applied.push({group: name, kind: kind, vertices: verts.length, weight: gmap[name]});
        }
    }

    var out = {node: t.node.getLabel(), created: created, written: written,
               groups: applied, errors: errors};
    var st = stats(map, t.numVerts, false);
    for (var k in st) if (st.hasOwnProperty(k)) out[k] = st[k];
    return out;
})()
"""

# Phase 6.25: Auto-follow morph projection on fitted items
#
# Live-verified 2026-10-18 (G8F + Blazer Shoes, scratch scene):
#   - DzFollowingProjectionOptions.disableMorphProjection is the persistent
#     switch (saved with the item). A projected morph is recognised by BOTH:
#     its assetUri has no filePath (scene-local "#name"), AND its value
#     control's getFollowProperty() is exactly the value control of the
#     same-named modifier on the follow target. Vendor-shipped follower morphs
#     (e.g. FBMHeight from the item's own .dsf) also follow the target but
#     have a filePath — they are never touched.
#   - Setting the switch does NOT remove already projected morphs in the
#     running session (they keep deforming); removeModifier() does, and with
#     the switch on they are not regenerated by posing, re-fitting or reload.
#   - Projection runs deferred (event loop) after setFollowTarget(); the
#     switch must be on BEFORE setFollowTarget() or the queued projection
#     still happens. Turning it back off regenerates nothing by itself — a
#     re-fit (setFollowTarget(null) → target) queues a new projection.
#   - DzFigure.clearGeneratedMorphs() is not a substitute: it removed only
#     one of six projected morphs (the inactive one).
_MORPH_PROJECTION_SCRIPT = "(function(){\n" + _RESOLVE_NODE_JS + """
    var args = getArguments()[0] || {};
    var labels = args.nodeLabels || [];
    var enabled = (args.enabled === true || args.enabled === false) ? args.enabled : null;
    var removeExisting = args.removeExisting !== false;
    var allowUnfitted = args.allowUnfitted === true;

    function projectedMorphs(node, target) {
        var out = [];
        if (!target || !target.getObject()) return out;
        var obj = node.getObject(), tobj = target.getObject();
        if (!obj) return out;
        for (var i = 0; i < obj.getNumModifiers(); i++) {
            var m = obj.getModifier(i);
            if (!m.inherits("DzMorph")) continue;
            if (m.assetUri && String(m.assetUri.filePath) !== "") continue;
            var vc = m.getValueControl();
            var fp = (vc && typeof vc.getFollowProperty === "function") ? vc.getFollowProperty() : null;
            var tm = tobj.findModifier(m.getName());
            if (!fp || !tm || fp !== tm.getValueControl()) continue;
            out.push(m);
        }
        return out;
    }

    var results = [];
    for (var li = 0; li < labels.length; li++) {
        var r = {node: String(labels[li])};
        try {
            var node = resolveNode(labels[li]);
            r.node = node.getLabel();
            if (typeof node.getFollowingProjectionOptions !== "function") {
                throw new Error("not a figure (no follow projection options) — props never get projected morphs");
            }
            var target = node.getFollowTarget();
            r.target = target ? target.getLabel() : null;
            if (!target && !allowUnfitted) throw new Error("not fitted to a figure (no follow target)");
            var opts = node.getFollowingProjectionOptions();
            r.previous_enabled = !opts.disableMorphProjection;
            var proj = projectedMorphs(node, target);
            var names = [];
            for (var pi = 0; pi < proj.length; pi++) names.push(proj[pi].getName());
            r.projected_morphs = names;
            r.removed_morphs = [];

            if (enabled === false) {
                opts.disableMorphProjection = true;
                if (removeExisting) {
                    var obj = node.getObject();
                    for (var ri = 0; ri < proj.length; ri++) {
                        var pname = proj[ri].getName();
                        obj.removeModifier(proj[ri]);
                        r.removed_morphs.push(pname);
                    }
                    r.projected_morphs = [];
                }
            } else if (enabled === true) {
                opts.disableMorphProjection = false;
                // Nothing regenerates on its own — a re-fit queues a new
                // (deferred) projection pass.
                r.reprojection_queued = false;
                if (!r.previous_enabled && target) {
                    node.setFollowTarget(null);
                    node.setFollowTarget(target);
                    r.reprojection_queued = true;
                }
            }
            r.enabled = !opts.disableMorphProjection;
        } catch (e) {
            r.error = String(e.message || e);
        }
        results.push(r);
    }
    return {results: results};
})()
"""

# Registry entries: script_id → (description, script_text)
# Merged into _REGISTRY by _register_scripts() in _registry.py.
_REGISTRY_FORK: dict[str, tuple[str, str]] = {
    "vangard-save-wearable-preset": (
        "Save chosen items fitted to a figure as a Wearable(s) Preset via "
        "DzWearablesAssetFilter.doSave() — headless, no dialogs",
        _SAVE_WEARABLE_PRESET_SCRIPT,
    ),
    "vangard-render-asset-thumbnail": (
        "Render Content-Library thumbnails (.duf.png 91px, .tip.png 256px, transparent) "
        "of one or more nodes with the Viewport engine, restoring the scene afterwards",
        _RENDER_ASSET_THUMBNAIL_SCRIPT,
    ),
    "vangard-trigger-wearable-save": (
        "Select a figure and fire DzWearablesAssetFilterAction (File > Save As > "
        "Wearable(s) Preset) — blocks on native dialogs, submit via async endpoint only; "
        "daz_save_wearable_preset drives the resulting dialogs via UI Automation",
        _TRIGGER_WEARABLE_SAVE_SCRIPT,
    ),
    "vangard-modifier-asset-preflight": (
        "Resolve a node and check that the named morphs/modifiers exist on it "
        "before daz_save_modifier_asset opens the Modifier Asset(s) save dialog",
        _MODIFIER_ASSET_PREFLIGHT_SCRIPT,
    ),
    "vangard-save-modifier-asset": (
        "Save named morphs of a saved Figure/Prop Asset as Modifier Assets via "
        "DzModifierSupportAssetFilter.doSave() — headless, no dialogs",
        _SAVE_MODIFIER_ASSET_SCRIPT,
    ),
    "vangard-trigger-modifier-asset-save": (
        "Select a node and fire DzModifierAssetFilterAction (File > Save As > "
        "Support Asset > Modifier Asset(s)) — blocks on a modal dialog, submit via "
        "async endpoint only; daz_save_modifier_asset drives it via UI Automation",
        _TRIGGER_MODIFIER_ASSET_SAVE_SCRIPT,
    ),
    "vangard-save-pose-preset": (
        "Save a figure's pose (current frame or an animated frame range) as a "
        "Pose Preset via DzPoseAssetFilter.doSave() — headless, no dialogs",
        _SAVE_POSE_PRESET_SCRIPT,
    ),
    "vangard-create-child-bone": (
        "Create a child DzBone under an existing bone of a figure and register "
        "an (initially empty) DzBoneBinding for it on the figure's skin binding",
        _CREATE_CHILD_BONE_SCRIPT,
    ),
    "vangard-set-skin-weights": (
        "Write per-vertex general skin weights for one or more bones on a "
        "figure and re-normalize the skin binding so the deformer picks them up",
        _SET_SKIN_WEIGHTS_SCRIPT,
    ),
    "vangard-create-geometry-shell": (
        "Create a native Geometry Shell node on a target node via "
        "DzNewGeometryShellAction. BLOCKS on a DAZ Studio confirmation "
        "dialog — always submit via the async endpoint; the "
        "daz_create_geometry_shell MCP tool confirms the dialog itself "
        "via Windows UI Automation, no human click needed",
        _CREATE_GEOMETRY_SHELL_SCRIPT,
    ),
    "vangard-list-geometry-shells": (
        "List every DzGeometryShellNode in the scene with its target node and "
        "whether it has generated geometry yet",
        _LIST_GEOMETRY_SHELLS_SCRIPT,
    ),
    "vangard-get-shell-visibility": (
        "List the per-face-group facet_group_*_vis bool properties on a "
        "DzGeometryShellNode (Bug-Katalog #35 workaround)",
        _GET_SHELL_VISIBILITY_SCRIPT,
    ),
    "vangard-set-shell-visibility": (
        "Set one or more per-face-group facet_group_*_vis bool properties on a "
        "DzGeometryShellNode (Bug-Katalog #35 workaround)",
        _SET_SHELL_VISIBILITY_SCRIPT,
    ),
    "vangard-get-hidden-facets": (
        "Report Geometry-Editor hidden polygons on a mesh, per face group and "
        "material group (base DzFacetMesh isFacetHidden; Bug-Katalog #35)",
        _GET_HIDDEN_FACETS_SCRIPT,
    ),
    "vangard-set-hidden-facets": (
        "Hide or unhide whole face groups / material groups of a mesh like the "
        "Geometry Editor does, and rebuild the cached mesh so viewport and "
        "exporters see it (Bug-Katalog #35)",
        _SET_HIDDEN_FACETS_SCRIPT,
    ),
    "vangard-get-rigidity-weights": (
        "Read the rigidity weight map (Node Weight Map Brush \"Rigid\") of a "
        "figure or prop via DzShape.getRigidityMap() (Bug-Katalog #18 Teil 2)",
        _GET_RIGIDITY_WEIGHTS_SCRIPT,
    ),
    "vangard-set-rigidity-weights": (
        "Write rigidity weights per vertex or per face/material group, creating "
        "the rigidity map if missing (Bug-Katalog #18 Teil 2)",
        _SET_RIGIDITY_WEIGHTS_SCRIPT,
    ),
    "vangard-morph-projection": (
        "Report or toggle auto-follow morph projection on fitted items "
        "(DzFollowingProjectionOptions.disableMorphProjection) and remove the "
        "already projected morphs",
        _MORPH_PROJECTION_SCRIPT,
    ),
}
