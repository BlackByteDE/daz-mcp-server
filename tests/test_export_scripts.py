"""Guard DS6 export/import contract in registered DazScript payloads."""
import json

import httpx
import pytest
import respx

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp._registry import _REGISTRY
from vangard_daz_mcp.tools.wardrobe import daz_export_obj


def test_export_scene_uses_write_file_not_do_export():
    script = _REGISTRY["vangard-export-scene"][1]
    assert "doExport" not in script
    assert "findExporter" in script
    assert "writeFile" in script
    assert 'setIntValue("RunSilent", 1)' in script
    assert "getDefaultOptions" in script


def test_export_scene_include_hidden_clears_ignore_invisible():
    """Bug-Katalog #39: the OBJ exporter's IgnoreInvisible (default true) also
    drops hidden facets, so the script must be able to switch it off."""
    script = _REGISTRY["vangard-export-scene"][1]
    assert 'setBoolValue("IgnoreInvisible", false)' in script
    assert "args.includeHidden === true" in script
    # only an explicit opt-in may change the exporter's own default
    assert script.index("getDefaultOptions") < script.index("IgnoreInvisible")


@pytest.mark.parametrize("include_hidden", [False, True])
async def test_export_obj_forwards_include_hidden(include_hidden):
    captured = {}

    def _capture(request):
        captured["args"] = json.loads(request.content)["args"]
        return httpx.Response(
            200, json={"success": True, "result": {"success": True}, "output": [], "error": None}
        )

    async with httpx.AsyncClient(base_url="http://localhost:18811") as client:
        set_http_client(client)
        with respx.mock(base_url="http://localhost:18811", assert_all_called=False) as router:
            router.post("/scripts/vangard-export-scene/execute").mock(side_effect=_capture)
            await daz_export_obj("C:/out/x.obj", include_hidden=include_hidden)
        set_http_client(None)
    assert captured["args"]["includeHidden"] is include_hidden
    assert captured["args"]["format"] == "Wavefront Object"


def test_import_obj_forces_unit_scale_and_run_silent():
    script = _REGISTRY["vangard-import-obj"][1]
    assert "DzObjImporter" in script
    assert "readFile" in script
    assert 'setFloatValue("Scale", scaleFactor)' in script
    assert 'setIntValue("RunSilent", 1)' in script
    assert "getDefaultOptions" in script


def test_set_dforce_property_searches_object_modifier_stack():
    script = _REGISTRY["vangard-set-dforce-property"][1]
    assert "getNumModifiers" in script
    assert "searchMods(obj)" in script
    assert "Freeze Simulation" in script


_RESOLVE_IDS = (
    "vangard-get-node",
    "vangard-set-property",
    "vangard-set-morph",
    "vangard-list-morphs",
    "vangard-search-morphs",
    "vangard-get-node-hierarchy",
    "vangard-list-children",
    "vangard-get-parent",
    "vangard-set-parent",
    "vangard-delete-node",
)


def test_core_node_scripts_resolve_uniquely():
    for script_id in _RESOLVE_IDS:
        script = _REGISTRY[script_id][1]
        assert "function resolveNode" in script, script_id
        assert "findNodeByElementID" in script, script_id
        assert "Ambiguous node" in script, script_id
        assert "Scene.findNodeByLabel(args.nodeLabel)" not in script, script_id


def test_get_node_returns_element_id():
    script = _REGISTRY["vangard-get-node"][1]
    assert "elementID: n.elementID" in script


def test_find_nodes_lists_collisions():
    script = _REGISTRY["vangard-find-nodes"][1]
    assert "elementID: n.elementID" in script
    assert "matches.push" in script


def test_apply_material_preset_preflights_missing_maps():
    script = _REGISTRY["vangard-apply-material-preset"][1]
    assert "Missing texture files" in script
    assert script.index("mapPaths") < script.index("openFile(presetPath")
    assert "allowMissing" in script
