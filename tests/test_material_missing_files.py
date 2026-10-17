"""daz_apply_material_preset(allow_missing=True): async load plus automatic
dismissal of the Missing Files prompts (Bug-Katalog #6). DAZ Studio and the
UI Automation layer are replaced with fakes."""

from __future__ import annotations

import json

import pytest

from vangard_daz_mcp.tools import material


@pytest.fixture
def preset(tmp_path):
    p = tmp_path / "preset.duf"
    p.write_text(json.dumps({"map": "/Runtime/Textures/zz_missing.jpg"}), encoding="utf-8")
    return str(p)


@pytest.fixture
def fakes(monkeypatch):
    calls = {}

    async def fake_sync(script_id, args):
        calls["sync"] = (script_id, args)
        return {"success": True, "material_count": 2}

    async def fake_async(script_id, args):
        calls["async"] = (script_id, args)
        return {"request_id": "script-1"}

    async def fake_wait(request_id, timeout_seconds=60):
        calls["wait"] = (request_id, timeout_seconds)
        return {"success": True, "material_count": 2}

    def fake_driver(done, timeout):
        # Returns once the request is reported finished, like the real loop.
        while not done():
            pass
        calls["driver_timeout"] = timeout
        return {"dialogs_dismissed": 3, "missing_files": ["/Runtime/Textures/zz_missing.jpg"]}

    monkeypatch.setattr(material, "_execute_by_id", fake_sync)
    monkeypatch.setattr(material, "_execute_by_id_async", fake_async)
    monkeypatch.setattr(material, "_wait_for_async_result", fake_wait)
    monkeypatch.setattr(material._ui_automation, "require_interactive_desktop", lambda: None)
    monkeypatch.setattr(material._ui_automation, "drive_missing_files_dialogs", fake_driver)
    return calls


async def test_default_stays_synchronous(fakes, preset):
    result = await material.daz_apply_material_preset("Lashes", preset)
    assert "sync" in fakes and "async" not in fakes
    assert fakes["sync"][1]["allowMissing"] is False
    assert result == {"success": True, "material_count": 2}


async def test_allow_missing_runs_async_and_dismisses_dialogs(fakes, preset):
    result = await material.daz_apply_material_preset(
        "Lashes", preset, allow_missing=True, timeout=30)
    assert "sync" not in fakes
    assert fakes["async"][0] == "vangard-apply-material-preset"
    assert fakes["async"][1]["allowMissing"] is True
    assert fakes["wait"] == ("script-1", 30)
    assert result["success"] is True
    assert result["dialogs_dismissed"] == 3
    assert result["missing_files"] == ["/Runtime/Textures/zz_missing.jpg"]


# ---------------------------------------------------------------------------
# daz_load_file + run_with_missing_files_driver
# ---------------------------------------------------------------------------

from vangard_daz_mcp import _ui_automation
from vangard_daz_mcp.tools import scene


@pytest.fixture
def load_fakes(monkeypatch):
    calls = {"loaded": 0}

    async def fake_execute_by_id(script_id, args):
        calls["loaded"] += 1
        calls["args"] = (script_id, args)
        return {"success": True, "file": args["filePath"]}

    monkeypatch.setattr(scene, "_execute_by_id", fake_execute_by_id)
    return calls


async def test_load_file_merges_dismissed_dialogs(monkeypatch, load_fakes):
    monkeypatch.setattr(_ui_automation, "missing_files_driver_available", lambda: True)
    monkeypatch.setattr(
        _ui_automation, "drive_missing_files_dialogs",
        lambda done, timeout: {
            "dialogs_dismissed": 3, "missing_files": ["/Runtime/Textures/x.jpg"]},
    )
    result = await scene.daz_load_file("C:/s.duf", merge=False)
    assert result["success"] is True
    assert result["dialogs_dismissed"] == 3
    assert result["missing_files"] == ["/Runtime/Textures/x.jpg"]


async def test_load_file_no_dialogs_keeps_result_shape(monkeypatch, load_fakes):
    monkeypatch.setattr(_ui_automation, "missing_files_driver_available", lambda: True)
    monkeypatch.setattr(
        _ui_automation, "drive_missing_files_dialogs",
        lambda done, timeout: {"dialogs_dismissed": 0, "missing_files": []},
    )
    result = await scene.daz_load_file("C:/s.duf", merge=False)
    assert result == {"success": True, "file": "C:/s.duf"}


async def test_load_file_without_ui_automation_just_loads(monkeypatch, load_fakes):
    monkeypatch.setattr(_ui_automation, "missing_files_driver_available", lambda: False)

    def boom(*_a, **_k):
        raise AssertionError("driver must not run")

    monkeypatch.setattr(_ui_automation, "drive_missing_files_dialogs", boom)
    result = await scene.daz_load_file("C:/s.duf", merge=False)
    assert result == {"success": True, "file": "C:/s.duf"}
    assert load_fakes["loaded"] == 1


async def test_load_file_opt_out_skips_driver(monkeypatch, load_fakes):
    def boom(*_a, **_k):
        raise AssertionError("driver must not run")

    monkeypatch.setattr(_ui_automation, "missing_files_driver_available", boom)
    result = await scene.daz_load_file("C:/s.duf", merge=False, dismiss_missing_files=False)
    assert result["success"] is True
