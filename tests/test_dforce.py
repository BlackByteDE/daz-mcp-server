"""Mock tests for Phase 6.2 dForce tool: daz_add_dforce_dynamic_surface.

All tests use respx to intercept HTTP at the transport layer — no DAZ Studio
or DazScriptServer required.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
import respx
import httpx

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp.tools.wardrobe import daz_add_dforce_dynamic_surface

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


class TestAddDforceDynamicSurface:
    async def test_adds_modifier(self, mock_daz):
        payload = {
            "success": True,
            "node": "Tablecloth",
            "already_present": False,
            "modifier": "DzDForceModifier",
        }
        mock_daz.post("/scripts/vangard-add-dforce-dynamic-surface/execute").mock(
            return_value=_ok(payload)
        )
        result = await daz_add_dforce_dynamic_surface("Tablecloth")
        assert result["success"] is True
        assert result["already_present"] is False
        assert result["modifier"] == "DzDForceModifier"

    async def test_already_present_is_noop(self, mock_daz):
        payload = {
            "success": True,
            "node": "Outfit",
            "already_present": True,
            "modifier": "DzDForceModifier",
        }
        mock_daz.post("/scripts/vangard-add-dforce-dynamic-surface/execute").mock(
            return_value=_ok(payload)
        )
        result = await daz_add_dforce_dynamic_surface("Outfit")
        assert result["already_present"] is True

    async def test_node_not_found_raises(self, mock_daz):
        from fastmcp.exceptions import ToolError
        mock_daz.post("/scripts/vangard-add-dforce-dynamic-surface/execute").mock(
            return_value=_fail("Node not found: Ghost")
        )
        with pytest.raises(ToolError):
            await daz_add_dforce_dynamic_surface("Ghost")

    async def test_sends_node_label_in_args(self, mock_daz):
        captured = {}

        def capture(request, route):
            body = json.loads(request.content)
            captured["args"] = body.get("args", {})
            return _ok({
                "success": True,
                "node": "Cape",
                "already_present": False,
                "modifier": "DzDForceModifier",
            })

        mock_daz.post("/scripts/vangard-add-dforce-dynamic-surface/execute").mock(
            side_effect=capture
        )
        await daz_add_dforce_dynamic_surface("Cape")
        assert captured["args"]["nodeLabel"] == "Cape"
