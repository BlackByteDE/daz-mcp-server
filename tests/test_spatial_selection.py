"""Mock tests for the include_types filter of daz_get_scene_layout /
daz_find_nearby_nodes and the replace mode of daz_batch_select.

The dazpy layer is replaced with fakes — no DAZ Studio required.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from vangard_daz_mcp.tools import spatial, transform

_NODES = [
    {"name": "Genesis8Female", "label": "Genesis 8 Female", "type": "figure",
     "position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "visible": True},
    {"name": "hip", "label": "Hip", "type": "bone",
     "position": [0.0, 100.0, 0.0], "rotation": [0.0, 0.0, 0.0], "visible": True},
    {"name": "cam", "label": "Camera 1", "type": "camera",
     "position": [0.0, 150.0, 200.0], "rotation": [0.0, 0.0, 0.0], "visible": True},
    {"name": "spot", "label": "Spot 1", "type": "light",
     "position": [50.0, 150.0, 50.0], "rotation": [0.0, 0.0, 0.0], "visible": True},
    {"name": "chair", "label": "Chair", "type": "prop",
     "position": [80.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "visible": True},
]


class _FakeNode:
    def __init__(self, label, scene):
        self.label = label
        self._scene = scene
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}

    def select(self, on=True):
        if on:
            self._scene.selected.add(self.label)
        else:
            self._scene.selected.discard(self.label)


class _FakeScene:
    def __init__(self, selected=()):
        self.selected = set(selected)

    def find_node_by_label(self, label):
        if label not in {n["label"] for n in _NODES}:
            raise LookupError(label)
        return _FakeNode(label, self)

    def select_all(self, on=True):
        if on:
            self.selected = {n["label"] for n in _NODES}
        else:
            self.selected.clear()


@pytest.fixture
def fake_scene(monkeypatch):
    scene = _FakeScene(selected={"Chair"})
    monkeypatch.setattr(spatial, "get_scene", lambda: scene)
    monkeypatch.setattr(transform, "get_scene", lambda: scene)
    monkeypatch.setattr(spatial, "_typed_node_transforms", lambda: list(_NODES))
    return scene


class TestSceneLayoutFilter:
    async def test_no_filter_returns_everything(self, fake_scene):
        result = await spatial.daz_get_scene_layout()
        assert result["count"] == len(_NODES)
        assert {n["type"] for n in result["nodes"]} == {
            "figure", "bone", "camera", "light", "prop"}

    async def test_filter_applied(self, fake_scene):
        result = await spatial.daz_get_scene_layout(["cameras", "lights"])
        assert [n["label"] for n in result["nodes"]] == ["Camera 1", "Spot 1"]

    async def test_invalid_type_raises(self, fake_scene):
        with pytest.raises(ToolError, match="chairs"):
            await spatial.daz_get_scene_layout(["chairs"])


class TestFindNearbyFilter:
    async def test_filter_applied(self, fake_scene):
        result = await spatial.daz_find_nearby_nodes(
            "Genesis 8 Female", radius=300, include_types=["props"])
        assert [n["label"] for n in result["nearby_nodes"]] == ["Chair"]
        assert result["nearby_nodes"][0]["type"] == "prop"

    async def test_no_filter_skips_only_center(self, fake_scene):
        result = await spatial.daz_find_nearby_nodes("Genesis 8 Female", radius=300)
        assert result["count"] == len(_NODES) - 1


class TestBatchSelect:
    async def test_replace_clears_prior_selection(self, fake_scene):
        await transform.daz_batch_select(["Camera 1"])
        assert fake_scene.selected == {"Camera 1"}

    async def test_add_keeps_prior_selection(self, fake_scene):
        await transform.daz_batch_select(["Camera 1"], add_to_selection=True)
        assert fake_scene.selected == {"Chair", "Camera 1"}
