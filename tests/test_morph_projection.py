"""Mock tests for daz_set_morph_projection and daz_fit_clothing(morph_projection=False)
(Phase 6.25). respx intercepts HTTP — no DAZ Studio required."""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp._registry_fork import _REGISTRY_FORK
from vangard_daz_mcp.tools.wardrobe import daz_fit_clothing, daz_set_morph_projection

BASE_URL = "http://localhost:18811"


@pytest_asyncio.fixture(autouse=True)
async def http_client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        set_http_client(client)
        yield client
    set_http_client(None)


@pytest.fixture
def mock_daz():
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield router


def _capture(mock_daz, script_id, result, calls=None):
    captured = {}

    def handler(request, route):
        captured["args"] = json.loads(request.content).get("args", {})
        if calls is not None:
            calls.append(script_id)
        return httpx.Response(
            200, json={"success": True, "result": result, "output": [], "error": None})

    mock_daz.post(f"/scripts/{script_id}/execute").mock(side_effect=handler)
    return captured


def test_script_detects_only_real_projections():
    script = _REGISTRY_FORK["vangard-morph-projection"][1]
    assert "disableMorphProjection" in script
    # Projected = scene-local (no .dsf) AND follows the same-named target morph.
    assert "assetUri.filePath" in script
    assert "fp !== tm.getValueControl()" in script
    assert "removeModifier" in script
    # clearGeneratedMorphs() removed only inactive projections live — not used.
    assert "clearGeneratedMorphs" not in script


async def test_default_disables_and_removes(mock_daz):
    payload = {"results": [{"node": "Braid Hair", "enabled": False,
                            "removed_morphs": ["pJCMNeckBack_27"]}]}
    captured = _capture(mock_daz, "vangard-morph-projection", payload)
    result = await daz_set_morph_projection(["Braid Hair"])
    assert result == payload
    assert captured["args"] == {
        "nodeLabels": ["Braid Hair"], "enabled": False, "removeExisting": True}


async def test_report_only_passes_null(mock_daz):
    captured = _capture(mock_daz, "vangard-morph-projection", {"results": []})
    await daz_set_morph_projection(["A", "B"], enabled=None, remove_existing=False)
    assert captured["args"] == {
        "nodeLabels": ["A", "B"], "enabled": None, "removeExisting": False}


async def test_empty_node_list_rejected(mock_daz):
    with pytest.raises(ToolError):
        await daz_set_morph_projection([])


async def test_fit_default_does_not_touch_projection(mock_daz):
    calls = []
    _capture(mock_daz, "vangard-morph-projection", {"results": []}, calls)
    fit = _capture(mock_daz, "vangard-fit-clothing",
                   {"success": True, "method": "setFollowTarget"}, calls)
    result = await daz_fit_clothing("Jacket", "Genesis 9")
    assert calls == ["vangard-fit-clothing"]
    assert "morph_projection" not in result
    assert fit["args"] == {"clothingLabel": "Jacket", "figureLabel": "Genesis 9"}


async def test_fit_without_projection_switches_off_before_fitting(mock_daz):
    calls = []
    entry = {"node": "Braid Hair", "enabled": False, "removed_morphs": []}
    proj = _capture(mock_daz, "vangard-morph-projection", {"results": [entry]}, calls)
    _capture(mock_daz, "vangard-fit-clothing",
             {"success": True, "method": "setFollowTarget"}, calls)
    result = await daz_fit_clothing("Braid Hair", "Genesis 8 Female", morph_projection=False)
    # The switch has to be on before setFollowTarget() queues the projection.
    assert calls == ["vangard-morph-projection", "vangard-fit-clothing"]
    assert proj["args"] == {"nodeLabels": ["Braid Hair"], "enabled": False,
                            "removeExisting": True, "allowUnfitted": True}
    assert result["morph_projection"] == entry
    assert result["success"] is True


async def test_script_error_surfaces_as_tool_error(mock_daz):
    mock_daz.post("/scripts/vangard-morph-projection/execute").mock(
        return_value=httpx.Response(200, json={
            "success": False, "result": None, "output": [], "error": "boom"}))
    with pytest.raises(ToolError):
        await daz_set_morph_projection(["X"])
