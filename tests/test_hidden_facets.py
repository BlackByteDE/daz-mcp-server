"""Mock tests for daz_get_hidden_facets / daz_set_hidden_facets (Bug-Katalog #35).

All tests use respx to intercept HTTP at the transport layer — no DAZ Studio
or DazScriptServer required.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp._registry_fork import _REGISTRY_FORK
from vangard_daz_mcp.tools.scene import daz_get_hidden_facets, daz_set_hidden_facets

BASE_URL = "http://localhost:18811"


def _ok(result):
    return httpx.Response(
        200,
        json={"success": True, "result": result, "output": [], "error": None},
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


def _capture(mock_daz, script_id, result):
    captured = {}

    def handler(request, route):
        captured["args"] = json.loads(request.content).get("args", {})
        return _ok(result)

    mock_daz.post(f"/scripts/{script_id}/execute").mock(side_effect=handler)
    return captured


class TestScripts:
    def test_registered(self):
        assert "vangard-get-hidden-facets" in _REGISTRY_FORK
        assert "vangard-set-hidden-facets" in _REGISTRY_FORK

    def test_reads_base_mesh_not_cache(self):
        script = _REGISTRY_FORK["vangard-get-hidden-facets"][1]
        assert "shape.getGeometry()" in script
        assert "isFacetHidden" in script
        assert "getCachedGeom" not in script

    def test_set_uses_group_objects_and_refreshes_cache(self):
        script = _REGISTRY_FORK["vangard-set-hidden-facets"][1]
        assert "showFacetsByIndexList(g, false)" in script
        assert "hideSelectedFacets()" in script
        assert 'findProperty("lodlevel")' in script


class TestGetHiddenFacets:
    async def test_forwards_args(self, mock_daz):
        payload = {
            "node": "Genesis 8 Female", "total_facets": 16368, "hidden_facets": 966,
            "face_groups": [{"name": "lThigh", "facets": 483, "hidden": 483}],
            "material_groups": [],
        }
        captured = _capture(mock_daz, "vangard-get-hidden-facets", payload)
        result = await daz_get_hidden_facets("Genesis 8 Female")
        assert result["hidden_facets"] == 966
        assert captured["args"] == {"nodeLabel": "Genesis 8 Female", "onlyHidden": True}

    async def test_only_hidden_false(self, mock_daz):
        captured = _capture(mock_daz, "vangard-get-hidden-facets", {"hidden_facets": 0})
        await daz_get_hidden_facets("Cube", only_hidden=False)
        assert captured["args"]["onlyHidden"] is False


class TestSetHiddenFacets:
    async def test_hide_face_groups(self, mock_daz):
        captured = _capture(mock_daz, "vangard-set-hidden-facets", {"hidden_facets": 966})
        await daz_set_hidden_facets("Genesis 8 Female", face_groups=["lThigh", "rThigh"])
        assert captured["args"] == {
            "nodeLabel": "Genesis 8 Female",
            "faceGroups": ["lThigh", "rThigh"],
            "materialGroups": [],
            "hidden": True,
            "unhideAll": False,
        }

    async def test_unhide_material_group(self, mock_daz):
        captured = _capture(mock_daz, "vangard-set-hidden-facets", {"hidden_facets": 0})
        await daz_set_hidden_facets("Genesis 8 Female", material_groups=["Arms"], hidden=False)
        assert captured["args"]["materialGroups"] == ["Arms"]
        assert captured["args"]["hidden"] is False

    async def test_unhide_all_alone_is_allowed(self, mock_daz):
        captured = _capture(mock_daz, "vangard-set-hidden-facets", {"hidden_facets": 0})
        await daz_set_hidden_facets("Genesis 8 Female", unhide_all=True)
        assert captured["args"]["unhideAll"] is True

    async def test_nothing_to_do_raises(self, mock_daz):
        with pytest.raises(ToolError):
            await daz_set_hidden_facets("Genesis 8 Female")
