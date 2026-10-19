"""Mock tests for daz_export_geometry_frames / fetch_geometry_frames
(POST /geometry/frames, binary DZGF payload).

All tests use respx to intercept HTTP at the transport layer — no DAZ Studio
or DazScriptServer required.
"""

from __future__ import annotations

import json as _json
import struct

import httpx
import numpy as np
import pytest
import pytest_asyncio
import respx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp.tools.geometry import (
    daz_export_geometry_frames,
    fetch_geometry_frames,
    parse_geometry_frames,
)

BASE_URL = "http://localhost:18811"


def _payload(frames, verts, bones, indices=None, magic=b"DZGF", version=1):
    """Build a DZGF payload exactly as GeometryExport.h specifies it."""
    n_frames, n_verts = verts.shape[0], verts.shape[1]
    n_bones = bones.shape[1]
    flags = 1 if indices is not None else 0
    out = struct.pack("<4sIIIIIII", magic, version, n_frames, n_verts, n_bones, flags, 0, 0)
    out += np.asarray(frames, "<i4").tobytes()
    if indices is not None:
        out += np.asarray(indices, "<u4").tobytes()
    out += verts.astype("<f4").tobytes()
    out += bones.astype("<f4").tobytes()
    return out


def _ok(body: bytes):
    return httpx.Response(200, content=body, headers={"content-type": "application/octet-stream"})


@pytest_asyncio.fixture(autouse=True)
async def _client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        set_http_client(client)
        yield
    set_http_client(None)


def test_parse_full_payload():
    verts = np.arange(2 * 4 * 3, dtype="<f4").reshape(2, 4, 3)
    bones = -np.arange(2 * 1 * 3, dtype="<f4").reshape(2, 1, 3)
    data = parse_geometry_frames(_payload([3, 7], verts, bones))
    assert data.frames.tolist() == [3, 7]
    assert data.indices is None
    assert data.verts.shape == (2, 4, 3) and data.verts.dtype == np.float32
    np.testing.assert_array_equal(data.verts, verts)
    np.testing.assert_array_equal(data.bones, bones)


def test_parse_subset_payload_has_indices():
    verts = np.random.default_rng(0).random((1, 3, 3), dtype=np.float32)
    bones = np.zeros((1, 0, 3), dtype=np.float32)
    data = parse_geometry_frames(_payload([0], verts, bones, indices=[10, 20, 30]))
    assert data.indices.tolist() == [10, 20, 30]
    assert data.bones.shape == (1, 0, 3)
    np.testing.assert_array_equal(data.verts, verts)


@pytest.mark.parametrize("mutate, match", [
    (lambda b: b"XXXX" + b[4:], "bad magic"),
    (lambda b: b[:4] + struct.pack("<I", 2) + b[8:], "version"),
    (lambda b: b[:-4], "header implies"),
    (lambda b: b[:10], "too short"),
])
def test_parse_rejects_malformed(mutate, match):
    good = _payload([0], np.zeros((1, 2, 3), "<f4"), np.zeros((1, 1, 3), "<f4"))
    with pytest.raises(ValueError, match=match):
        parse_geometry_frames(mutate(good))


@respx.mock
async def test_fetch_sends_request_json_and_decodes():
    verts = np.ones((2, 2, 3), "<f4")
    bones = np.full((2, 1, 3), 2.0, "<f4")
    route = respx.post(f"{BASE_URL}/geometry/frames").mock(
        return_value=_ok(_payload([1, 2], verts, bones)))
    data = await fetch_geometry_frames(
        [1, 2], node="Genesis 8 Female", bones=["lHand"], resolution="current", scene_update=False)
    assert _json.loads(route.calls[0].request.content) == {
        "frames": [1, 2], "node": "Genesis 8 Female", "bones": ["lHand"],
        "resolution": "current", "sceneUpdate": False,
    }
    np.testing.assert_array_equal(data.verts, verts)
    np.testing.assert_array_equal(data.bones, bones)


@respx.mock
async def test_fetch_minimal_request_omits_optionals():
    route = respx.post(f"{BASE_URL}/geometry/frames").mock(
        return_value=_ok(_payload([0], np.zeros((1, 1, 3), "<f4"), np.zeros((1, 0, 3), "<f4"))))
    await fetch_geometry_frames([0])
    assert _json.loads(route.calls[0].request.content) == {"frames": [0], "resolution": "base"}


@respx.mock
async def test_fetch_json_error_body_becomes_tool_error():
    respx.post(f"{BASE_URL}/geometry/frames").mock(
        return_value=httpx.Response(400, json={
            "success": False, "error_code": "INVALID_FIELD",
            "error": "A field in the request has an invalid value",
            "detail": "figure not found: Foo"}))
    with pytest.raises(ToolError, match="invalid value: figure not found: Foo"):
        await fetch_geometry_frames([0], node="Foo")


@respx.mock
async def test_fetch_corrupt_payload_becomes_tool_error():
    respx.post(f"{BASE_URL}/geometry/frames").mock(return_value=_ok(b"DZGF" + b"\x00" * 10))
    with pytest.raises(ToolError, match="Invalid /geometry/frames payload"):
        await fetch_geometry_frames([0])


@respx.mock
async def test_fetch_connect_error_becomes_tool_error():
    respx.post(f"{BASE_URL}/geometry/frames").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ToolError, match="Cannot connect"):
        await fetch_geometry_frames([0])


async def test_fetch_validates_arguments_before_any_request():
    with pytest.raises(ToolError, match="frames must not be empty"):
        await fetch_geometry_frames([])
    with pytest.raises(ToolError, match="resolution"):
        await fetch_geometry_frames([0], resolution="huge")


@respx.mock
async def test_tool_writes_npz(tmp_path):
    verts = np.arange(2 * 3 * 3, dtype="<f4").reshape(2, 3, 3)
    bones = np.ones((2, 2, 3), "<f4")
    respx.post(f"{BASE_URL}/geometry/frames").mock(
        return_value=_ok(_payload([5, 6], verts, bones, indices=[4, 8, 15])))
    result = await daz_export_geometry_frames([5, 6], str(tmp_path / "sub" / "out"), indices=[4, 8, 15])
    assert result["path"].endswith("out.npz")
    assert (result["num_frames"], result["num_verts"], result["num_bones"]) == (2, 3, 2)
    assert result["verts_shape"] == [2, 3, 3] and result["has_indices"] is True
    with np.load(result["path"]) as npz:
        assert npz["frames"].tolist() == [5, 6]
        assert npz["indices"].tolist() == [4, 8, 15]
        np.testing.assert_array_equal(npz["verts"], verts)
        np.testing.assert_array_equal(npz["bones"], bones)
