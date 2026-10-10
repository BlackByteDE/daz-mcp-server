"""Mock tests for daz_save_modifier_asset (Bug-Katalog #37).

Covers the headless default path (``vangard-save-modifier-asset``) and the
``use_ui_automation=True`` fallback. The dialog itself
(``_ui_automation.drive_modifier_asset_save``) needs a real DAZ Studio window
and is mocked out.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp.tools import content
from vangard_daz_mcp.tools.content import _find_saved_modifier_files, daz_save_modifier_asset

BASE_URL = "http://localhost:18811"
LIB = "C:/Users/me/Documents/DAZ 3D/Studio/My Library"
UI = "vangard_daz_mcp.tools.content._ui_automation"


def _ok(result):
    return httpx.Response(200, json={"success": True, "result": result, "output": [], "error": None})


def _async_submitted(request_id: str) -> httpx.Response:
    return httpx.Response(202, json={"request_id": request_id, "status": "queued"})


def _request_result(result) -> httpx.Response:
    return httpx.Response(200, json={"request_id": "x", "status": "completed", "result": result})


def _preflight(missing=None, saved=True, asset_dir=None):
    return {
        "assetFile": "/data/V/P/Dress/Dress.dsf" if saved else "/D:/scene.duf",
        "isSavedAsset": saved,
        "assetContentDir": asset_dir,
        "node": "Leather Dress",
        "nodeName": "Dress",
        "morphs": [{"name": "LD_PullDown", "label": "Pull Down", "type": "DzMorph"}],
        "missing": missing or [],
        "available": [{"name": "LD_PullDown", "label": "Pull Down", "type": "DzMorph"}],
        "contentDirectories": [LIB, "C:/Users/Public/Documents/My DAZ 3D Library"],
    }


@pytest_asyncio.fixture(autouse=True)
async def http_client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        set_http_client(client)
        yield client
    set_http_client(None)


@pytest.fixture
def mock_daz():
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def desktop_ok():
    with patch(f"{UI}.require_interactive_desktop"):
        yield


class TestSaveModifierAsset:
    async def test_success(self, mock_daz, desktop_ok):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight())
        )
        trigger = mock_daz.post("/scripts/vangard-trigger-modifier-asset-save/async").mock(
            return_value=_async_submitted("mod-1")
        )
        mock_daz.get("/requests/mod-1/result").mock(
            return_value=_request_result({"success": True, "node": "Leather Dress"})
        )
        written = f"{LIB}/data/V/P/Dress/Morphs/blackbyte.de/Product/LD_PullDown.dsf"
        with patch(f"{UI}.drive_modifier_asset_save",
                   return_value={"baseDataPath": LIB, "ticked": ["Pull Down"]}) as drive, \
             patch.object(content, "_find_saved_modifier_files",
                          return_value={"LD_PullDown": written}):
            result = await daz_save_modifier_asset(
                "Leather Dress", ["LD_PullDown"], "blackbyte.de", "Product", base_data_path=LIB,
                use_ui_automation=True,
            )
        assert trigger.called
        args = drive.call_args.args
        assert args[0] == _preflight()["morphs"]
        assert args[1:4] == ("blackbyte.de", "Product", LIB)
        assert result["success"] is True
        assert result["files"] == {"LD_PullDown": written}
        assert result["morphs"] == ["Pull Down"]

    async def test_missing_morph_fails_before_dialog(self, mock_daz, desktop_ok):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight(missing=["LD_Typo"]))
        )
        trigger = mock_daz.post("/scripts/vangard-trigger-modifier-asset-save/async").mock(
            return_value=_async_submitted("mod-2")
        )
        with patch(f"{UI}.drive_modifier_asset_save") as drive:
            with pytest.raises(ToolError, match="LD_Typo"):
                await daz_save_modifier_asset("Leather Dress", ["LD_Typo"], "v", "p")
        assert not trigger.called
        drive.assert_not_called()

    async def test_base_data_path_must_be_content_dir(self, mock_daz, desktop_ok):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight())
        )
        trigger = mock_daz.post("/scripts/vangard-trigger-modifier-asset-save/async").mock(
            return_value=_async_submitted("mod-3")
        )
        with pytest.raises(ToolError, match="not a configured content directory"):
            await daz_save_modifier_asset(
                "Leather Dress", ["LD_PullDown"], "v", "p", base_data_path="D:/Elsewhere",
            )
        assert not trigger.called

    async def test_preflight_receives_node_and_morphs(self, mock_daz, desktop_ok):
        captured = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return _ok(_preflight(missing=["x"]))

        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(side_effect=capture)
        with pytest.raises(ToolError):
            await daz_save_modifier_asset("Leather Dress", ["LD_PullDown"], "v", "p")
        assert captured["args"] == {"nodeLabel": "Leather Dress", "morphNames": ["LD_PullDown"]}

    async def test_no_written_file_raises(self, mock_daz, desktop_ok):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight())
        )
        mock_daz.post("/scripts/vangard-trigger-modifier-asset-save/async").mock(
            return_value=_async_submitted("mod-4")
        )
        mock_daz.get("/requests/mod-4/result").mock(return_value=_request_result({"success": True}))
        with patch(f"{UI}.drive_modifier_asset_save",
                   return_value={"baseDataPath": LIB, "ticked": ["Pull Down"]}), \
             patch.object(content, "_find_saved_modifier_files", return_value={}):
            with pytest.raises(ToolError, match="no new .dsf"):
                await daz_save_modifier_asset(
                    "Leather Dress", ["LD_PullDown"], "v", "p", dialog_timeout=0.5,
                    use_ui_automation=True,
                )

    async def test_empty_morph_list_rejected(self, mock_daz, desktop_ok):
        with pytest.raises(ToolError, match="at least one"):
            await daz_save_modifier_asset("Leather Dress", [], "v", "p")

    async def test_refuses_without_interactive_desktop(self, mock_daz):
        preflight = mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight())
        )
        with patch(f"{UI}.require_interactive_desktop", side_effect=ToolError("locked")):
            with pytest.raises(ToolError, match="locked"):
                await daz_save_modifier_asset(
                    "Leather Dress", ["LD_PullDown"], "v", "p", use_ui_automation=True,
                )
        assert not preflight.called


class TestSaveModifierAssetHeadless:
    async def test_headless_payload_and_no_dialog(self, mock_daz):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight(asset_dir="C:/Public Library"))
        )
        captured = {}

        def capture(request):
            captured.update(json.loads(request.content))
            return _ok({"success": True})

        mock_daz.post("/scripts/vangard-save-modifier-asset/execute").mock(side_effect=capture)
        trigger = mock_daz.post("/scripts/vangard-trigger-modifier-asset-save/async").mock(
            return_value=_async_submitted("never")
        )
        with patch(f"{UI}.require_interactive_desktop") as desktop:
            result = await daz_save_modifier_asset(
                "Leather Dress", ["Pull Down"], "blackbyte.de", "Product", compress_output=False,
            )
        desktop.assert_not_called()
        assert not trigger.called
        args = captured["args"]
        # Labels are resolved to internal names by the preflight; the base dir
        # defaults to the content directory holding the item's own asset.
        assert args["morphNames"] == ["LD_PullDown"]
        assert args["baseDataPath"] == "C:/Public Library"
        assert args["compressOutput"] is False
        assert "forceUniqueIds" not in args
        assert result["success"] is True
        assert result["files"] is None  # base dir not reachable from the test machine

    async def test_default_base_falls_back_to_first_content_dir(self, mock_daz):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight())
        )
        save = mock_daz.post("/scripts/vangard-save-modifier-asset/execute").mock(
            return_value=_ok({"success": True})
        )
        result = await daz_save_modifier_asset("Leather Dress", ["LD_PullDown"], "v", "p")
        assert json.loads(save.calls.last.request.content)["args"]["baseDataPath"] == LIB
        assert result["baseDataPath"] == LIB

    async def test_unsaved_item_rejected_before_save(self, mock_daz):
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(
            return_value=_ok(_preflight(saved=False))
        )
        save = mock_daz.post("/scripts/vangard-save-modifier-asset/execute").mock(
            return_value=_ok({"success": True})
        )
        with pytest.raises(ToolError, match="daz_save_prop_asset"):
            await daz_save_modifier_asset("Leather Dress", ["LD_PullDown"], "v", "p")
        assert not save.called

    async def test_missing_file_raises_when_dir_reachable(self, mock_daz, tmp_path):
        lib = str(tmp_path)
        pre = _preflight(asset_dir=lib)
        pre["contentDirectories"] = [lib]
        mock_daz.post("/scripts/vangard-modifier-asset-preflight/execute").mock(return_value=_ok(pre))
        mock_daz.post("/scripts/vangard-save-modifier-asset/execute").mock(
            return_value=_ok({"success": True})
        )
        with pytest.raises(ToolError, match="cloud-encrypted"):
            await daz_save_modifier_asset("Leather Dress", ["LD_PullDown"], "v", "p")


class TestFindSavedModifierFiles:
    def test_finds_new_file_by_name_or_label(self, tmp_path):
        morph_dir = tmp_path / "data" / "Vend" / "Prod" / "Item" / "Morphs" / "me" / "Mine"
        morph_dir.mkdir(parents=True)
        (morph_dir / "LD_PullDown.dsf").write_text("{}")
        (morph_dir / "Labelled.dsf").write_text("{}")
        morphs = [{"name": "LD_PullDown", "label": "Pull Down"},
                  {"name": "internal", "label": "Labelled"},
                  {"name": "absent", "label": "absent"}]
        found = _find_saved_modifier_files(str(tmp_path), "me", "Mine", morphs, since=0)
        assert set(found) == {"LD_PullDown", "internal"}

    def test_ignores_files_older_than_since(self, tmp_path):
        morph_dir = tmp_path / "data" / "V" / "P" / "I" / "Morphs" / "me" / "Mine"
        morph_dir.mkdir(parents=True)
        (morph_dir / "old.dsf").write_text("{}")
        found = _find_saved_modifier_files(
            str(tmp_path), "me", "Mine", [{"name": "old", "label": "old"}], since=4e9,
        )
        assert found == {}
