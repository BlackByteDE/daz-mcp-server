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
# extra) and via daz_execute against a freshly created shell. A plain
# mesh/prop hidden via the Geometry Editor has no equivalent at all —
# DzFacetMesh/DzFacet/DzFacetShape expose no hidden-state accessor
# (see docs/daz-mcp-bridge-bugs.md #35). These two scripts do not fix that;
# they let a *shell* placed over an item be hidden/shown per face group
# instead, as a scriptable substitute.
_GET_SHELL_VISIBILITY_SCRIPT = """\
(function(){
    var args = getArguments()[0] || {};
    var label = args.shellLabel;
    var n = Scene.findNodeByLabel(label);
    if (!n) n = Scene.findNode(label);
    if (!n) throw new Error("Node not found: " + label);
    if (!n.inherits("DzGeometryShellNode")) {
        throw new Error("Node '" + label + "' is not a DzGeometryShellNode (found " +
            n.className() + "). This does NOT read Geometry-Editor \\"hide face group\\" " +
            "state on a regular mesh/prop -- no DazScript API exposes that at all " +
            "(Bug-Katalog #35). It only works on a Geometry Shell node's OWN face-group " +
            "visibility toggles. If you want a scriptable hide/show for this node, " +
            "create a shell over it first with daz_create_geometry_shell(\\"" + label +
            "\\"), then call this again with the shell's label.");
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
            n.className() + "). This does NOT set Geometry-Editor \\"hide face group\\" " +
            "state on a regular mesh/prop -- no DazScript API exposes that at all " +
            "(Bug-Katalog #35). It only works on a Geometry Shell node's OWN face-group " +
            "visibility toggles. If you want a scriptable hide/show for this node, " +
            "create a shell over it first with daz_create_geometry_shell(\\"" + label +
            "\\"), then call this again with the shell's label.");
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
}
