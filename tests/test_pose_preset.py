"""Mock tests for daz_save_pose_preset (headless DzPoseAssetFilter path).

All tests use respx to intercept HTTP at the transport layer — no DAZ Studio
or DazScriptServer required.
"""

from __future__ import annotations

import gzip
import json

import pytest
import pytest_asyncio
import respx
import httpx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp.tools.content import _pose_preset_stats, daz_save_pose_preset

BASE_URL = "http://localhost:18811"
SCRIPT_URL = "/scripts/vangard-save-pose-preset/execute"


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


def _preset(channels):
    return {"file_version": "0.6.0.0", "asset_info": {"type": "preset_pose"},
            "scene": {"animations": channels}}


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


class TestPosePresetStats:
    def test_counts_gzip_preset(self, tmp_path):
        path = tmp_path / "Walk.duf"
        path.write_bytes(gzip.compress(json.dumps(_preset([
            {"url": "a", "keys": [[0, 1.0], [0.033, 2.0], [0.066, 3.0]]},
            {"url": "b", "keys": [[0, 0.0]]},
        ])).encode()))
        assert _pose_preset_stats(path) == {"channels": 2, "animatedChannels": 1, "maxKeys": 3}

    def test_counts_plain_preset(self, tmp_path):
        path = tmp_path / "Empty.duf"
        path.write_text(json.dumps(_preset([])))
        assert _pose_preset_stats(path) == {"channels": 0, "animatedChannels": 0, "maxKeys": 0}


class TestSavePosePreset:
    async def test_default_args_sent(self, mock_daz, tmp_path):
        captured = {}

        def capture(request, route):
            captured["args"] = json.loads(request.content).get("args", {})
            return _ok({"success": True, "figure": "Genesis 8 Female"})

        mock_daz.post(SCRIPT_URL).mock(side_effect=capture)
        await daz_save_pose_preset("Genesis 8 Female", str(tmp_path / "Walk.duf"))
        args = captured["args"]
        assert args["figureLabel"] == "Genesis 8 Female"
        assert args["outputPath"].endswith("/Walk.duf")
        assert args["currentFrameOnly"] is False
        assert args["includeMorphs"] is True
        assert args["bypassFilter"] is False
        # Range and compression omitted when not passed — script uses the scene's range.
        assert "startFrame" not in args
        assert "endFrame" not in args
        assert "compressOutput" not in args

    async def test_extension_forced_and_range_sent(self, mock_daz, tmp_path):
        captured = {}

        def capture(request, route):
            captured["args"] = json.loads(request.content).get("args", {})
            return _ok({"success": True, "figure": "Genesis 8 Female"})

        mock_daz.post(SCRIPT_URL).mock(side_effect=capture)
        await daz_save_pose_preset(
            "Genesis 8 Female", str(tmp_path / "Walk.json"), start_frame=0, end_frame=34,
            compress_output=False,
        )
        args = captured["args"]
        assert args["outputPath"].endswith("/Walk.duf")
        assert args["startFrame"] == 0
        assert args["endFrame"] == 34
        assert args["compressOutput"] is False

    async def test_stats_added_from_written_file(self, mock_daz, tmp_path):
        out = tmp_path / "Walk.duf"
        out.write_bytes(gzip.compress(json.dumps(_preset([
            {"url": "a", "keys": [[0, 1.0], [0.033, 2.0]]},
        ])).encode()))
        mock_daz.post(SCRIPT_URL).mock(return_value=_ok({
            "success": True, "figure": "Genesis 8 Female", "outputPath": out.as_posix(),
        }))
        result = await daz_save_pose_preset("Genesis 8 Female", str(out))
        assert result["channels"] == 1
        assert result["animatedChannels"] == 1
        assert result["maxKeys"] == 2

    async def test_empty_preset_raises(self, mock_daz, tmp_path):
        out = tmp_path / "Walk.duf"
        out.write_text(json.dumps(_preset([])))
        mock_daz.post(SCRIPT_URL).mock(return_value=_ok({
            "success": True, "figure": "Genesis 8 Female", "outputPath": out.as_posix(),
        }))
        with pytest.raises(ToolError, match="no channels"):
            await daz_save_pose_preset("Genesis 8 Female", str(out))

    async def test_reversed_range_rejected(self, mock_daz):
        with pytest.raises(ToolError):
            await daz_save_pose_preset("Genesis 8 Female", "C:/Lib/x.duf", start_frame=10, end_frame=5)

    async def test_do_save_failure_raises(self, mock_daz):
        mock_daz.post(SCRIPT_URL).mock(
            return_value=_fail("DzPoseAssetFilter.doSave failed (error code 98): no root figure")
        )
        with pytest.raises(ToolError):
            await daz_save_pose_preset("Genesis 8 Female", "C:/Lib/x.duf")
