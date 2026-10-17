"""Mock tests for daz_get_rigidity_weights / daz_set_rigidity_weights
(Bug-Katalog #18 Teil 2). respx intercepts HTTP — no DAZ Studio required."""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp._registry_fork import _REGISTRY_FORK
from vangard_daz_mcp.tools.rigging import (
    daz_get_rigidity_weights,
    daz_set_rigidity_weights,
)

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


def _capture(mock_daz, script_id, result):
    captured = {}

    def handler(request, route):
        captured["args"] = json.loads(request.content).get("args", {})
        return httpx.Response(
            200, json={"success": True, "result": result, "output": [], "error": None})

    mock_daz.post(f"/scripts/{script_id}/execute").mock(side_effect=handler)
    return captured


def test_scripts_use_shape_rigidity_map():
    get_s = _REGISTRY_FORK["vangard-get-rigidity-weights"][1]
    set_s = _REGISTRY_FORK["vangard-set-rigidity-weights"][1]
    assert "getRigidityMap()" in get_s
    # DzRigidMapContext.getWeightMap() is an opaque shared pointer in DazScript.
    assert "getWeightMapContext" not in set_s
    assert "setRigidityMap(map)" in set_s
    assert "setNumWeights(t.numVerts)" in set_s
    assert "hasOwnProperty" in set_s  # Bug-Katalog #38


async def test_get_forwards_args(mock_daz):
    captured = _capture(mock_daz, "vangard-get-rigidity-weights",
                        {"has_map": True, "non_zero": 3})
    result = await daz_get_rigidity_weights("Jacket", include_weights=True)
    assert result["non_zero"] == 3
    assert captured["args"] == {"nodeLabel": "Jacket", "includeWeights": True}


async def test_set_forwards_args(mock_daz):
    captured = _capture(mock_daz, "vangard-set-rigidity-weights", {"written": 2})
    await daz_set_rigidity_weights(
        "Jacket", weights={"1": 0.5}, material_groups={"Buttons": 1.0})
    assert captured["args"] == {
        "nodeLabel": "Jacket",
        "weights": {"1": 0.5},
        "faceGroups": {},
        "materialGroups": {"Buttons": 1.0},
        "clear": False,
    }


async def test_set_dense_list_passed_through(mock_daz):
    captured = _capture(mock_daz, "vangard-set-rigidity-weights", {"written": 3})
    await daz_set_rigidity_weights("Cube", weights=[0.0, 0.5, 1.0])
    assert captured["args"]["weights"] == [0.0, 0.5, 1.0]


async def test_clear_alone_allowed(mock_daz):
    captured = _capture(mock_daz, "vangard-set-rigidity-weights", {"written": 0})
    await daz_set_rigidity_weights("Cube", clear=True)
    assert captured["args"]["clear"] is True


async def test_nothing_to_do_raises():
    with pytest.raises(ToolError):
        await daz_set_rigidity_weights("Cube")
