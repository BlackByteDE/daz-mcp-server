"""Mock tests for Phase 6.15 rigging tools: daz_create_child_bone and
daz_set_skin_weights (Bug-Katalog #30).

All tests use respx to intercept HTTP at the transport layer — no DAZ Studio
or DazScriptServer required.
"""

from __future__ import annotations

import json as _json

import pytest
import pytest_asyncio
import respx
import httpx

from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp.tools.rigging import (
    daz_create_child_bone,
    daz_set_skin_weights,
)

BASE_URL = "http://localhost:18811"


def _ok(result):
    return httpx.Response(
        200,
        json={"success": True, "result": result, "output": [], "error": None},
    )


def _fail(error):
    return httpx.Response(
        200,
        json={"success": False, "result": None, "output": [], "error": error},
    )


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


class TestCreateChildBone:
    async def test_creates_bone_with_origin_only(self, mock_daz):
        captured = {}

        def capture(request):
            captured.update(_json.loads(request.content))
            return _ok({
                "success": True,
                "figure": "samor_1125_111_fitted_baked_rot",
                "parent": "head",
                "bone": "hairTail1",
                "elementID": 4256,
                "vertexCount": 4879,
                "origin": {"x": 0, "y": 162.5, "z": -1.8},
                "endpoint": {"x": 0, "y": 167.5, "z": -1.8},
            })

        mock_daz.post("/scripts/vangard-create-child-bone/execute").mock(
            side_effect=capture
        )
        result = await daz_create_child_bone(
            "samor_1125_111_fitted_baked_rot/head", "hairTail1", origin=[0, 162.5, -1.8]
        )
        assert captured["args"]["parentLabel"] == "samor_1125_111_fitted_baked_rot/head"
        assert captured["args"]["name"] == "hairTail1"
        assert captured["args"]["origin"] == [0, 162.5, -1.8]
        assert "endpoint" not in captured["args"]
        assert result["bone"] == "hairTail1"
        assert result["vertexCount"] == 4879

    async def test_passes_explicit_endpoint(self, mock_daz):
        captured = {}

        def capture(request):
            captured.update(_json.loads(request.content))
            return _ok({"success": True})

        mock_daz.post("/scripts/vangard-create-child-bone/execute").mock(
            side_effect=capture
        )
        await daz_create_child_bone(
            "hairTail1", "hairTail2", origin=[0, 158.0, -3.2], endpoint=[0, 153.0, -4.5]
        )
        assert captured["args"]["endpoint"] == [0, 153.0, -4.5]

    async def test_rejects_malformed_origin(self, mock_daz):
        with pytest.raises(ToolError):
            await daz_create_child_bone("head", "hairTail1", origin=[0, 1])

    async def test_rejects_malformed_endpoint(self, mock_daz):
        with pytest.raises(ToolError):
            await daz_create_child_bone(
                "head", "hairTail1", origin=[0, 1, 2], endpoint=[0, 1]
            )

    async def test_script_failure_raises(self, mock_daz):
        mock_daz.post("/scripts/vangard-create-child-bone/execute").mock(
            return_value=_fail(
                "Parent node 'nope' has no DzFigure ancestor with a skin binding."
            )
        )
        with pytest.raises(ToolError):
            await daz_create_child_bone("nope", "hairTail1", origin=[0, 0, 0])


class TestSetSkinWeights:
    async def test_sparse_weights(self, mock_daz):
        captured = {}

        def capture(request):
            captured.update(_json.loads(request.content))
            return _ok({
                "success": True,
                "figure": "samor_1125_111_fitted_baked_rot",
                "vertexCount": 4879,
                "updated": [{"bone": "hairTail5", "weightsSet": 3}],
                "errors": [],
            })

        mock_daz.post("/scripts/vangard-set-skin-weights/execute").mock(
            side_effect=capture
        )
        result = await daz_set_skin_weights(
            "samor_1125_111_fitted_baked_rot",
            {"hairTail5": {"40": 0.9, "41": 0.95, "44": 0.983}},
        )
        assert captured["args"]["figureLabel"] == "samor_1125_111_fitted_baked_rot"
        assert captured["args"]["boneWeights"] == {
            "hairTail5": {"40": 0.9, "41": 0.95, "44": 0.983}
        }
        assert result["updated"][0]["weightsSet"] == 3
        assert result["errors"] == []

    async def test_dense_weights(self, mock_daz):
        captured = {}

        def capture(request):
            captured.update(_json.loads(request.content))
            return _ok({
                "success": True,
                "vertexCount": 3,
                "updated": [{"bone": "hairTail1", "weightsSet": 3}],
                "errors": [],
            })

        mock_daz.post("/scripts/vangard-set-skin-weights/execute").mock(
            side_effect=capture
        )
        await daz_set_skin_weights("Genesis 8 Female", {"hairTail1": [0.0, 0.5, 1.0]})
        assert captured["args"]["boneWeights"]["hairTail1"] == [0.0, 0.5, 1.0]

    async def test_partial_errors_do_not_raise(self, mock_daz):
        mock_daz.post("/scripts/vangard-set-skin-weights/execute").mock(
            return_value=_ok({
                "success": True,
                "vertexCount": 100,
                "updated": [],
                "errors": ["notABone: bone not found on figure"],
            })
        )
        result = await daz_set_skin_weights(
            "Genesis 8 Female", {"notABone": {"0": 1.0}}
        )
        assert result["errors"] == ["notABone: bone not found on figure"]

    async def test_script_failure_raises(self, mock_daz):
        mock_daz.post("/scripts/vangard-set-skin-weights/execute").mock(
            return_value=_fail("Node 'Prop1' has no skin binding.")
        )
        with pytest.raises(ToolError):
            await daz_set_skin_weights("Prop1", {"hairTail1": {"0": 1.0}})
