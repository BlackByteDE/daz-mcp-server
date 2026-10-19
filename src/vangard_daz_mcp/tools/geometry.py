"""Fast geometry export client for the Vangard DAZ MCP server (fork-only).

Client for ``POST /geometry/frames`` (daz-script-server >= 2.9.2+bb.2): the
deformed vertices (and optionally world-space bone origins) of a figure for a
list of frames as one binary float32 payload, instead of a DazScript loop
(~140 ms/frame on 16,556 vertices). Format spec:
``daz-script-server/include/GeometryExport.h``.

``fetch_geometry_frames`` is the library entry point (returns numpy arrays,
importable from other Python projects); ``daz_export_geometry_frames`` is the
MCP tool, which stores the arrays in an ``.npz`` file because numpy arrays
cannot travel through MCP's JSON.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Any

import httpx
import numpy as np
from fastmcp.exceptions import ToolError

from .._mcp import mcp
from .._client import DAZ_TIMEOUT, get_http_client
from .._errors import handle_network_error, check_response

_MAGIC = b"DZGF"
_VERSION = 1
_HEADER = struct.Struct("<4sIIIIIII")  # magic, version, numFrames, numVerts, numBones, flags, reserved[2]
_FLAG_INDICES = 1


@dataclass
class GeometryFrames:
    """Decoded ``/geometry/frames`` response.

    Attributes:
        frames: int32 ``[F]`` — the frame numbers, in request order.
        verts: float32 ``[F, V, 3]`` — vertex positions per frame.
        bones: float32 ``[F, B, 3]`` — world-space bone origins (``B`` may be 0).
        indices: uint32 ``[V]`` — source vertex index of each column of ``verts``,
            or ``None`` when all vertices were returned (then column = index).
    """

    frames: np.ndarray
    verts: np.ndarray
    bones: np.ndarray
    indices: np.ndarray | None


def parse_geometry_frames(payload: bytes) -> GeometryFrames:
    """Decode the binary ``DZGF`` payload into numpy arrays.

    Raises ValueError on a wrong magic/version or a payload whose length does
    not match its header.
    """
    if len(payload) < _HEADER.size:
        raise ValueError(f"payload too short for a DZGF header ({len(payload)} bytes)")
    magic, version, n_frames, n_verts, n_bones, flags, _, _ = _HEADER.unpack_from(payload)
    if magic != _MAGIC:
        raise ValueError(f"bad magic {magic!r}, expected {_MAGIC!r}")
    if version != _VERSION:
        raise ValueError(f"unsupported DZGF version {version}, expected {_VERSION}")

    has_indices = bool(flags & _FLAG_INDICES)
    expected = _HEADER.size + 4 * n_frames
    if has_indices:
        expected += 4 * n_verts
    expected += 4 * 3 * n_frames * (n_verts + n_bones)
    if len(payload) != expected:
        raise ValueError(f"payload is {len(payload)} bytes, header implies {expected}")

    offset = _HEADER.size

    def take(dtype: str, count: int) -> np.ndarray:
        nonlocal offset
        arr = np.frombuffer(payload, dtype=dtype, count=count, offset=offset)
        offset += arr.nbytes
        return arr

    frames = take("<i4", n_frames)
    indices = take("<u4", n_verts) if has_indices else None
    verts = take("<f4", n_frames * n_verts * 3).reshape(n_frames, n_verts, 3)
    bones = take("<f4", n_frames * n_bones * 3).reshape(n_frames, n_bones, 3)
    return GeometryFrames(frames=frames, verts=verts, bones=bones, indices=indices)


def _build_request(
    frames: list[int],
    node: str | None,
    indices: list[int] | None,
    surfaces: list[str] | None,
    bones: list[str] | None,
    resolution: str,
    scene_update: bool,
) -> dict[str, Any]:
    if not frames:
        raise ToolError("frames must not be empty")
    if resolution not in ("base", "current"):
        raise ToolError(f"resolution must be 'base' or 'current', got {resolution!r}")
    body: dict[str, Any] = {"frames": [int(f) for f in frames], "resolution": resolution}
    if node is not None:
        body["node"] = node
    if indices is not None:
        body["indices"] = [int(i) for i in indices]
    if surfaces is not None:
        body["surfaces"] = list(surfaces)
    if bones is not None:
        body["bones"] = list(bones)
    if not scene_update:
        body["sceneUpdate"] = False
    return body


async def fetch_geometry_frames(
    frames: list[int],
    node: str | None = None,
    indices: list[int] | None = None,
    surfaces: list[str] | None = None,
    bones: list[str] | None = None,
    resolution: str = "base",
    scene_update: bool = True,
    timeout: float | None = None,
) -> GeometryFrames:
    """Call ``POST /geometry/frames`` and return the decoded arrays.

    Args:
        frames: Frame numbers to evaluate (required, non-empty).
        node: Node name or label; default = first figure in the scene.
        indices: Optional vertex subset.
        surfaces: Optional surface names; adds every vertex of their facets
            to the subset.
        bones: Optional bone names; their world-space origins go into ``bones``.
        resolution: ``"base"`` (default) or ``"current"``.
        scene_update: ``False`` skips the final Scene update (~130 ms on a
            dressed figure) — for back-to-back calls pass ``False`` on all but
            the last one.
        timeout: Seconds; default scales with the frame count.

    Raises ToolError for network errors, a DAZ-side error (JSON body) or a
    malformed payload.
    """
    body = _build_request(frames, node, indices, surfaces, bones, resolution, scene_update)
    if timeout is None:
        timeout = max(DAZ_TIMEOUT, 10.0 + 0.5 * len(frames))
    client = get_http_client()
    try:
        response = await client.post("/geometry/frames", json=body, timeout=timeout)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as exc:
        handle_network_error(exc)

    if response.status_code == 200 and "json" not in response.headers.get("content-type", ""):
        try:
            return parse_geometry_frames(response.content)
        except ValueError as exc:
            raise ToolError(f"Invalid /geometry/frames payload: {exc}") from exc

    # Errors come as the usual JSON body (also tolerate a 200 with JSON).
    if response.status_code in (401, 403):
        check_response(response)
    try:
        err = response.json()
    except ValueError:
        err = None
    if isinstance(err, dict):
        message = err.get("error") or err.get("message") or str(err)
        if err.get("detail"):
            message = f"{message}: {err['detail']}"
        raise ToolError(f"/geometry/frames failed (HTTP {response.status_code}): {message}")
    check_response(response)
    raise ToolError(f"/geometry/frames: unexpected response (HTTP {response.status_code})")


@mcp.tool()
async def daz_export_geometry_frames(
    frames: list[int],
    output_path: str,
    node: str | None = None,
    indices: list[int] | None = None,
    surfaces: list[str] | None = None,
    bones: list[str] | None = None,
    resolution: str = "base",
    scene_update: bool = True,
) -> dict[str, Any]:
    """Export the deformed vertices of a figure for many frames to an .npz file.

    Fast binary path (``POST /geometry/frames``) instead of a DazScript loop:
    the figure alone is evaluated per frame (not the whole scene), so large
    frame ranges and 16k+ vertex figures stay quick. Needs daz-script-server
    >= 2.9.2+bb.2. Python code in the same environment can skip the file and
    call ``fetch_geometry_frames`` from ``vangard_daz_mcp.tools.geometry``.

    Args:
        frames: Frame numbers to evaluate, e.g. ``[0, 5, 10]``.
        output_path: Absolute path of the ``.npz`` to write (extension added if
                     missing). Arrays inside: ``frames`` int32 [F], ``verts``
                     float32 [F, V, 3], ``bones`` float32 [F, B, 3] and — only
                     when a vertex subset was requested — ``indices`` uint32 [V].
        node: Node name or label. Default: first figure in the scene.
        indices: Optional vertex subset (indices into the mesh).
        surfaces: Optional surface names; every vertex of their facets is added
                  to the subset.
        bones: Optional bone names whose world-space origins are returned.
        resolution: ``"base"`` (default, base cage) or ``"current"``.
        scene_update: ``False`` skips the final Scene update (~130 ms on a
                      dressed figure) — only for back-to-back calls, let the
                      last one update.

    Returns:
      - path: the written file
      - num_frames, num_verts, num_bones
      - verts_shape / bones_shape
      - has_indices: whether ``indices`` is stored in the file
    """
    data = await fetch_geometry_frames(
        frames, node=node, indices=indices, surfaces=surfaces, bones=bones,
        resolution=resolution, scene_update=scene_update,
    )
    path = os.path.abspath(output_path)
    if not path.lower().endswith(".npz"):
        path += ".npz"
    arrays: dict[str, np.ndarray] = {"frames": data.frames, "verts": data.verts, "bones": data.bones}
    if data.indices is not None:
        arrays["indices"] = data.indices
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez(path, **arrays)
    except OSError as exc:
        raise ToolError(f"Cannot write {path}: {exc}") from exc
    return {
        "path": path,
        "num_frames": int(data.frames.shape[0]),
        "num_verts": int(data.verts.shape[1]),
        "num_bones": int(data.bones.shape[1]),
        "verts_shape": list(data.verts.shape),
        "bones_shape": list(data.bones.shape),
        "has_indices": data.indices is not None,
    }
