"""Runtime bone/skin-weight tools for DAZ Studio figures.

Covers adding new child bones to an existing figure skeleton and writing the
per-vertex general skin weights that make those bones actually deform the
mesh. Written to close Bug-Katalog #30
(``D:\\Dev\\pinkcharakter\\docs\\bugs\\content-assets.md``): a runtime-created
``DzBone`` + ``DzBoneBinding`` reads back its own weights fine but is
silently ignored by the deformer until ``DzSkinBinding.checkAndNormalize()``
is called at least once afterward — confirmed live, not documented anywhere
in the DAZ SDK reference. Both tools below call it as their last step.

Weight maps are always sized to the figure's BASE (un-subdivided) geometry
vertex count, never the cached/rendered vertex count — those differ whenever
SubDivision is active, same gotcha as the existing dForce influence-weights
tools.
"""
from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from .._mcp import mcp, _execute_by_id


@mcp.tool()
async def daz_create_child_bone(
    parent_label: str,
    name: str,
    origin: list[float],
    endpoint: list[float] | None = None,
) -> dict[str, Any]:
    """Create a child DzBone under an existing bone of a figure.

    Adds the new bone to the figure's node hierarchy under ``parent_label``
    and registers an (initially all-zero) ``DzBoneBinding`` for it on the
    figure's skin binding, so it's immediately ready for
    ``daz_set_skin_weights``. Rotating the bone with no weights assigned yet
    has no visible effect — that's expected, assign weights next.

    Args:
        parent_label: Display label, internal name, elementID, or
            ``Parent/Label`` path of the existing bone to parent under
            (e.g. ``"Genesis 8 Female/head"`` or just ``"head"`` if unique
            in the scene).
        name: Internal name and label for the new bone (e.g. ``"hairTail1"``).
        origin: ``[x, y, z]`` bind-pose origin in figure-space cm (same
            convention as ``bone.getOrigin(false)``).
        endpoint: Optional ``[x, y, z]`` bind-pose endpoint in figure-space
            cm. Defaults to 5cm above the origin along Y if omitted.

    Returns:
        Dict with keys:
        - success: true on success
        - figure: label of the containing DzFigure
        - parent: confirmed parent bone label
        - bone: new bone's label
        - elementID: new bone's elementID (use for unambiguous lookup later)
        - vertexCount: base-geometry vertex count the weight map was sized to
        - origin / endpoint: the values actually applied

    Examples:
        daz_create_child_bone("samor_1125_111_fitted_baked_rot/head",
                               "hairTail1", origin=[0, 162.5, -1.8])
        daz_create_child_bone("hairTail1", "hairTail2",
                               origin=[0, 158.0, -3.2], endpoint=[0, 153.0, -4.5])

    Notes:
        - The parent must already belong to a figure with a skin binding
          (``getSkinBinding()``) — a bone under a plain prop will error.
        - Rest/bind-pose origin is NOT captured here (``getOrigin(true)``
          stays at the figure default) — if you need the rest pose to match
          this origin, memorize it explicitly (Joint Editor > Memorize
          Figure/Rigging, or run in bind pose before assigning weights).
    """
    if len(origin) != 3:
        raise ToolError(f"origin must have exactly 3 values [x, y, z], got {origin!r}")
    if endpoint is not None and len(endpoint) != 3:
        raise ToolError(f"endpoint must have exactly 3 values [x, y, z], got {endpoint!r}")

    payload: dict[str, Any] = {
        "parentLabel": parent_label,
        "name": name,
        "origin": origin,
    }
    if endpoint is not None:
        payload["endpoint"] = endpoint
    return await _execute_by_id("vangard-create-child-bone", payload)


@mcp.tool()
async def daz_set_skin_weights(
    figure_label: str,
    bone_weights: dict[str, Any],
) -> dict[str, Any]:
    """Write per-vertex general skin weights for one or more bones on a figure.

    Accepts, per bone, either a dense array of one weight per base-geometry
    vertex, or a sparse map of vertex index to weight. After writing, calls
    ``DzSkinBinding.checkAndNormalize()`` once — this is what actually makes
    the deformer pick up the new weights (see module docstring / Bug-Katalog
    #30), and it also automatically re-normalizes other bones' weights at
    the touched vertices back down so each vertex's total stays at 1.0 — you
    do not need to manually zero out the parent bone's weight first.

    Args:
        figure_label: Display label, internal name, elementID, or
            ``Parent/Label`` path of the target figure (must have a skin
            binding — i.e. be an actual ``DzFigure``, not a plain prop).
        bone_weights: Dict mapping bone name to either:
            - a dense list of floats, one per base-geometry vertex
              (``len(list) == vertexCount`` from ``daz_get_figure_info`` /
              ``daz_create_child_bone``'s ``vertexCount``), or
            - a sparse dict of ``{"<vertex_index>": weight}`` entries.
            A bone binding is created automatically if one doesn't exist yet
            (e.g. for a bone that already existed on the figure but never
            had its own weight map).

    Returns:
        Dict with keys:
        - success: true on success
        - figure: confirmed figure label
        - vertexCount: base-geometry vertex count weights were validated against
        - updated: list of {bone, weightsSet} per bone written
        - errors: list of per-bone/per-vertex problems that were skipped
          (e.g. unknown bone name, out-of-range vertex index, wrong-length
          dense array) — a non-empty list does not fail the call, check it

    Examples:
        # Sparse: only a handful of vertices near the tail tip
        daz_set_skin_weights("samor_1125_111_fitted_baked_rot", {
            "hairTail5": {"40": 0.9, "41": 0.95, "44": 0.983}
        })

        # Dense: every vertex explicitly (vertexCount from daz_create_child_bone)
        daz_set_skin_weights("Genesis 8 Female", {"hairTail1": [0.0, 0.0, ...]})

    Notes:
        - Weight indices are BASE (un-subdivided) geometry vertex indices —
          if the figure has SubDivision active, this is NOT the same count
          or indexing as the cached/rendered mesh.
        - A vertex's total weight across ALL bones does not need to sum to
          1.0 before calling this — ``checkAndNormalize()`` handles that.
    """
    return await _execute_by_id("vangard-set-skin-weights", {
        "figureLabel": figure_label,
        "boneWeights": bone_weights,
    })


@mcp.tool()
async def daz_get_rigidity_weights(
    node_label: str,
    include_weights: bool = False,
) -> dict[str, Any]:
    """Read the rigidity weight map of a figure or prop.

    This is the map the Node Weight Map Brush lists as "Rigid": per-vertex
    weights (0-1) used by the node's rigidity groups to keep parts of a mesh
    (buttons, buckles, badges) from stretching when the item is morphed or
    fitted. It is saved with the geometry in the ``.duf`` (DSON ``rigidity``).
    Not a dForce map — dForce pinning is ``daz_set_dforce_influence_weights``.

    Args:
        node_label: Display label, internal name, elementID, or
            ``Parent/Label`` path of the figure or prop.
        include_weights: If True, also return every non-zero weight as a
            sparse ``{"<vertex_index>": weight}`` dict.

    Returns:
        Dict with node, has_map, num_vertices and — when a map exists —
        num_weights, non_zero, min_non_zero, max (and weights if requested).

    Examples:
        daz_get_rigidity_weights("Genesis 8 Female")
        # → {"has_map": True, "num_vertices": 16556, "non_zero": 481, ...}
    """
    return await _execute_by_id("vangard-get-rigidity-weights", {
        "nodeLabel": node_label,
        "includeWeights": include_weights,
    })


@mcp.tool()
async def daz_set_rigidity_weights(
    node_label: str,
    weights: dict[str, float] | list[float] | None = None,
    face_groups: dict[str, float] | None = None,
    material_groups: dict[str, float] | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    """Write rigidity weights (the Node Weight Map Brush "Rigid" map).

    Creates the rigidity map if the node has none yet, then writes the given
    weights. Values are clamped to 0-1 and stored slightly quantized (0.75
    reads back as 0.749996). The map is saved with the scene/asset.

    Args:
        node_label: Display label, internal name, elementID, or
            ``Parent/Label`` path of the figure or prop.
        weights: Per-vertex weights — a sparse ``{"<vertex_index>": weight}``
            dict or a dense list with one value per BASE (un-subdivided)
            vertex.
        face_groups: ``{face_group_name: weight}`` — sets every vertex of the
            group's polygons to that weight.
        material_groups: ``{surface_name: weight}`` — same for surfaces.
        clear: If True, set every weight to 0 before writing.

    Returns:
        Dict with node, created (map was new), written (vertex writes),
        groups ({group, kind, vertices, weight}), errors (skipped entries),
        and the resulting num_weights / non_zero / min_non_zero / max.

    Examples:
        daz_set_rigidity_weights("Jacket", material_groups={"Buttons": 1.0})
        daz_set_rigidity_weights("Jacket", weights={"120": 1.0, "121": 0.5})
        daz_set_rigidity_weights("Jacket", clear=True)
    """
    if weights is None and not face_groups and not material_groups and not clear:
        raise ToolError("Pass weights, face_groups, material_groups, or clear=True.")
    return await _execute_by_id("vangard-set-rigidity-weights", {
        "nodeLabel": node_label,
        "weights": weights,
        "faceGroups": face_groups or {},
        "materialGroups": material_groups or {},
        "clear": clear,
    })
