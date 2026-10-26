"""Fast geometry export client for the Vangard DAZ MCP server (fork-only).

Client for ``POST /geometry/frames`` (daz-script-server >= 2.9.2+bb.2): the
deformed vertices (and optionally world-space bone origins) of a figure for a
list of frames as one binary float32 payload, instead of a DazScript loop
(~140 ms/frame on 16,556 vertices). Format spec:
``daz-script-server/include/GeometryExport.h``.

Optional *override sets* (``channels`` + ``values``, DZGF v2): each frame is
evaluated once per set with the set's channel values applied temporarily (no
keys left behind) — pose search and finite differences without a DazScript
round trip per evaluation.

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
_VERSIONS = (1, 2)  # 2 = with override sets
_HEADER = struct.Struct("<4sIIIIIII")  # magic, version, numFrames, numVerts, numBones, flags, numSets, mismatches
_FLAG_INDICES = 1
_FLAG_SETS = 2


@dataclass
class GeometryFrames:
    """Decoded ``/geometry/frames`` response.

    Attributes:
        frames: int32 ``[F]`` — the frame numbers, in request order.
        verts: float32 ``[F, V, 3]`` — vertex positions per frame; with override
            sets ``[F, S, V, 3]`` (``S`` = number of sets).
        bones: float32 ``[F, B, 3]`` — world-space bone origins (``B`` may be 0);
            with override sets ``[F, S, B, 3]``.
        indices: uint32 ``[V]`` — source vertex index of each column of ``verts``,
            or ``None`` when all vertices were returned (then column = index).
        num_sets: Override sets per frame; 0 = plain response without sets axis.
        mismatches: Channel restores the server could not verify afterwards
            (should be 0; anything else means the scene was left altered).
    """

    frames: np.ndarray
    verts: np.ndarray
    bones: np.ndarray
    indices: np.ndarray | None
    num_sets: int = 0
    mismatches: int = 0


def parse_geometry_frames(payload: bytes) -> GeometryFrames:
    """Decode the binary ``DZGF`` payload into numpy arrays.

    Raises ValueError on a wrong magic/version or a payload whose length does
    not match its header.
    """
    if len(payload) < _HEADER.size:
        raise ValueError(f"payload too short for a DZGF header ({len(payload)} bytes)")
    magic, version, n_frames, n_verts, n_bones, flags, n_sets, mismatches = _HEADER.unpack_from(payload)
    if magic != _MAGIC:
        raise ValueError(f"bad magic {magic!r}, expected {_MAGIC!r}")
    if version not in _VERSIONS:
        raise ValueError(f"unsupported DZGF version {version}, expected one of {_VERSIONS}")

    has_indices = bool(flags & _FLAG_INDICES)
    has_sets = bool(flags & _FLAG_SETS)
    if has_sets != (version == 2):
        raise ValueError(f"DZGF version {version} does not match flags {flags:#x}")
    if not has_sets:
        n_sets, mismatches = 0, 0
    expected = _HEADER.size + 4 * n_frames
    if has_indices:
        expected += 4 * n_verts
    expected += 4 * 3 * n_frames * max(n_sets, 1) * (n_verts + n_bones)
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
    lead = (n_frames, n_sets) if has_sets else (n_frames,)
    n_eval = int(np.prod(lead))
    verts = take("<f4", n_eval * n_verts * 3).reshape(*lead, n_verts, 3)
    bones = take("<f4", n_eval * n_bones * 3).reshape(*lead, n_bones, 3)
    return GeometryFrames(frames=frames, verts=verts, bones=bones, indices=indices,
                          num_sets=n_sets, mismatches=mismatches)


def _build_request(
    frames: list[int],
    node: str | None,
    indices: list[int] | None,
    surfaces: list[str] | None,
    bones: list[str] | None,
    resolution: str,
    scene_update: bool,
    channels: list[dict[str, str]] | None = None,
    values: list[list[float]] | None = None,
) -> dict[str, Any]:
    if not frames:
        raise ToolError("frames must not be empty")
    if resolution not in ("base", "current"):
        raise ToolError(f"resolution must be 'base' or 'current', got {resolution!r}")
    if (channels is None) != (values is None):
        raise ToolError("channels and values must be given together")
    if channels is not None:
        if not channels:
            raise ToolError("channels must not be empty")
        for i, spec in enumerate(channels):
            if not isinstance(spec, dict) or not (spec.keys() & {"bone", "node", "morph", "property"}):
                raise ToolError(
                    f"channels[{i}] needs one of 'bone', 'node', 'morph' or 'property', got {spec!r}")
        if not values:
            raise ToolError("values must hold at least one override set")
        for i, row in enumerate(values):
            if len(row) != len(channels):
                raise ToolError(
                    f"values[{i}] has {len(row)} entries, expected {len(channels)} (one per channel)")
    body: dict[str, Any] = {"frames": [int(f) for f in frames], "resolution": resolution}
    if node is not None:
        body["node"] = node
    if indices is not None:
        body["indices"] = [int(i) for i in indices]
    if surfaces is not None:
        body["surfaces"] = list(surfaces)
    if bones is not None:
        body["bones"] = list(bones)
    if channels is not None:
        body["channels"] = [dict(c) for c in channels]
        body["values"] = [[float(v) for v in row] for row in values]
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
    channels: list[dict[str, str]] | None = None,
    values: list[list[float]] | None = None,
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
        timeout: Seconds; default scales with the number of evaluations
            (frames x override sets).
        channels: Optional override channels, each ``{"bone": "lIndex2",
            "property": "XRotate"}``, ``{"node": name, "property": p}``,
            ``{"morph": name}`` or ``{"property": p}`` (on the figure).
        values: Required with ``channels``: one row per override set, one value
            per channel. Every frame is evaluated once per set with these values
            applied temporarily; the result gets a sets axis (``verts`` is then
            ``[F, S, V, 3]``). Channels are restored afterwards, no keys remain.

    Raises ToolError for network errors, a DAZ-side error (JSON body) or a
    malformed payload.
    """
    body = _build_request(
        frames, node, indices, surfaces, bones, resolution, scene_update, channels, values)
    if timeout is None:
        timeout = max(DAZ_TIMEOUT, 10.0 + 0.5 * len(frames) * (len(values) if values else 1))
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
    channels: list[dict[str, str]] | None = None,
    values: list[list[float]] | None = None,
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
        channels: Optional override channels, each ``{"bone": "lIndex2",
                  "property": "XRotate"}``, ``{"node": name, "property": p}``,
                  ``{"morph": name}`` or ``{"property": p}`` (on the figure).
                  Needs a daz-script-server with override-set support.
        values: Required with ``channels``: one row per override set, one value
                per channel (limits/ERC apply as when set from DazScript). Each
                frame is evaluated once per set with the values applied
                temporarily — channels are restored afterwards, no keys remain.
                ``verts``/``bones`` in the file then have a sets axis:
                ``[F, S, V, 3]`` / ``[F, S, B, 3]``. Use several rows for finite
                differences or pose search instead of one DazScript call each.

    Returns:
      - path: the written file
      - num_frames, num_verts, num_bones
      - num_sets: override sets per frame (0 = none requested)
      - mismatches: channel restores the server could not verify (should be 0)
      - verts_shape / bones_shape
      - has_indices: whether ``indices`` is stored in the file
    """
    data = await fetch_geometry_frames(
        frames, node=node, indices=indices, surfaces=surfaces, bones=bones,
        resolution=resolution, scene_update=scene_update, channels=channels, values=values,
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
        "num_verts": int(data.verts.shape[-2]),
        "num_bones": int(data.bones.shape[-2]),
        "num_sets": data.num_sets,
        "mismatches": data.mismatches,
        "verts_shape": list(data.verts.shape),
        "bones_shape": list(data.bones.shape),
        "has_indices": data.indices is not None,
    }
