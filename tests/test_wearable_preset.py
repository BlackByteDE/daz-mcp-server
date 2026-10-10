"""Mock tests for daz_save_wearable_preset (headless DzWearablesAssetFilter path).

All tests use respx to intercept HTTP at the transport layer — no DAZ Studio
or DazScriptServer required.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
import respx
import httpx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp.tools.content import (
    _thumbnail_outputs,
    daz_render_asset_thumbnail,
    daz_save_wearable_preset,
)

BASE_URL = "http://localhost:18811"
SCRIPT_URL = "/scripts/vangard-save-wearable-preset/execute"
THUMB_URL = "/scripts/vangard-render-asset-thumbnail/execute"


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


class TestSaveWearablePreset:
    async def test_successful_save(self, mock_daz):
        payload = {
            "success": True,
            "figure": "Genesis 8 Female",
            "outputPath": "C:/Library/Presets/Wearables/Jacket.duf",
            "items": ["Jacket"],
        }
        mock_daz.post(SCRIPT_URL).mock(return_value=_ok(payload))
        result = await daz_save_wearable_preset(
            "Genesis 8 Female", "C:/Library/Presets/Wearables/Jacket.duf", items=["Jacket"],
            thumbnail=False,
        )
        assert result["success"] is True
        assert result["items"] == ["Jacket"]

    async def test_default_args_sent(self, mock_daz):
        captured = {}

        def capture(request, route):
            captured["args"] = json.loads(request.content).get("args", {})
            return _ok({"success": True})

        mock_daz.post(SCRIPT_URL).mock(side_effect=capture)
        await daz_save_wearable_preset(
            "Genesis 8 Female", "C:/Library/Presets/Wearables/All.duf", thumbnail=False
        )
        args = captured["args"]
        assert args["figureLabel"] == "Genesis 8 Female"
        assert args["outputPath"] == "C:/Library/Presets/Wearables/All.duf"
        assert args["smartParent"] is True
        assert args["poseTarget"] is False
        # Optional fields omitted entirely when not passed — not sent as null/None.
        assert "items" not in args
        assert "compressOutput" not in args
        assert "saveSimulationData" not in args

    async def test_custom_flags_sent(self, mock_daz):
        captured = {}

        def capture(request, route):
            captured["args"] = json.loads(request.content).get("args", {})
            return _ok({"success": True})

        mock_daz.post(SCRIPT_URL).mock(side_effect=capture)
        await daz_save_wearable_preset(
            "Genesis 8 Female",
            "C:/Library/Presets/Wearables/Set.duf",
            items=["Cap", "Back"],
            smart_parent=False,
            pose_target=True,
            compress_output=False,
            save_simulation_data=False,
            thumbnail=False,
        )
        args = captured["args"]
        assert args["items"] == ["Cap", "Back"]
        assert args["smartParent"] is False
        assert args["poseTarget"] is True
        assert args["compressOutput"] is False
        assert args["saveSimulationData"] is False

    async def test_do_save_failure_raises(self, mock_daz):
        mock_daz.post(SCRIPT_URL).mock(
            return_value=_fail(
                "DzWearablesAssetFilter.doSave failed (error code 100): "
                "none of the item labels resolved to a scene node"
            )
        )
        with pytest.raises(ToolError):
            await daz_save_wearable_preset("Genesis 8 Female", "C:/Library/x.duf")

    async def test_items_with_ui_automation_rejected(self, mock_daz):
        with pytest.raises(ToolError):
            await daz_save_wearable_preset(
                "Genesis 8 Female", "C:/Library/x.duf", items=["Cap"], use_ui_automation=True
            )


class TestWearableThumbnails:
    async def test_thumbnail_rendered_for_saved_items(self, mock_daz):
        mock_daz.post(SCRIPT_URL).mock(return_value=_ok({
            "success": True, "outputPath": "C:/Lib/Presets/Wearables/Set.duf", "items": ["Cap", "Back"],
        }))
        captured = {}

        def capture(request, route):
            captured["args"] = json.loads(request.content).get("args", {})
            return _ok({"success": True, "nodes": ["Cap", "Back"], "files": [{"path": "x", "size": 91}]})

        mock_daz.post(THUMB_URL).mock(side_effect=capture)
        result = await daz_save_wearable_preset("Genesis 8 Female", "C:/Lib/Presets/Wearables/Set.duf")
        assert captured["args"]["nodeLabels"] == ["Cap", "Back"]
        assert captured["args"]["outputs"] == _thumbnail_outputs("C:/Lib/Presets/Wearables/Set.duf")
        assert result["thumbnails"] == [{"path": "x", "size": 91}]

    async def test_thumbnail_failure_does_not_fail_save(self, mock_daz):
        mock_daz.post(SCRIPT_URL).mock(return_value=_ok({
            "success": True, "outputPath": "C:/Lib/Set.duf", "items": ["Cap"],
        }))
        mock_daz.post(THUMB_URL).mock(return_value=_fail("Thumbnail render failed: boom"))
        result = await daz_save_wearable_preset("Genesis 8 Female", "C:/Lib/Set.duf")
        assert result["success"] is True
        assert "boom" in result["thumbnailError"]


class TestRenderAssetThumbnail:
    def test_outputs_next_to_duf(self):
        assert _thumbnail_outputs("C:\Lib\Props\Hair.duf") == [
            {"path": "C:/Lib/Props/Hair.duf.png", "size": 91},
            {"path": "C:/Lib/Props/Hair.tip.png", "size": 256},
        ]

    async def test_empty_nodes_rejected(self, mock_daz):
        with pytest.raises(ToolError):
            await daz_render_asset_thumbnail([], "C:/Lib/x.duf")
