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

# Phase 6.14: Wearable Preset save trigger (Bug-Katalog #22 Teil 2)
# Selects the target figure and fires DzWearablesAssetFilterAction. This
# BLOCKS on two native dialogs (a file-save dialog, then a Qt options
# dialog) — must be submitted via the async endpoint. The Python-side
# tool (daz_save_wearable_preset, _ui_automation.py) drives those dialogs
# via Windows UI Automation once this has fired; DzWearablesAssetFilter's
# own doSave() script API reproducibly fails with an unexplained generic
# error and is not used here (see docs/daz-mcp-bridge-bugs.md #22 Teil 2).
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

# Registry entries: script_id → (description, script_text)
# Merged into _REGISTRY by _register_scripts() in _registry.py.
_REGISTRY_FORK: dict[str, tuple[str, str]] = {
    "vangard-trigger-wearable-save": (
        "Select a figure and fire DzWearablesAssetFilterAction (File > Save As > "
        "Wearable(s) Preset) — blocks on native dialogs, submit via async endpoint only; "
        "daz_save_wearable_preset drives the resulting dialogs via UI Automation",
        _TRIGGER_WEARABLE_SAVE_SCRIPT,
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
}
