"""Content browser tools: category listing, browsing, metadata, search, and product loading."""
from __future__ import annotations

import asyncio
import json as _json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from .._mcp import mcp, _execute_by_id, _execute_by_id_async, _wait_for_async_result
from .._client import get_content_browser_client, CONTENT_BROWSER_URL
from .. import _ui_automation


# ---------------------------------------------------------------------------
# Tools — content library (DAZ Studio Script Server registered scripts)
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_list_categories(parent_path: str = "") -> dict[str, Any]:
    """List content library category subdirectories under a parent path.

    Searches across all configured DAZ content directories and deduplicates by name.

    Args:
        parent_path: Relative path within content directories to list (e.g. "People/Genesis 9").
                     Leave empty to list top-level categories.

    Returns:
        Dict with parent, categories (list of {name, path, duf_count}), and count.

    Example:
        daz_list_categories()                      # top-level: People, Props, Environments...
        daz_list_categories("People/Genesis 9")    # sub-folders: Characters, Clothing, Hair...
    """
    return await _execute_by_id("vangard-list-categories", {"parentPath": parent_path})


@mcp.tool()
async def daz_browse_category(
    category_path: str,
    sort_by: str = "name",  # pylint: disable=unused-argument
    # Only "name" is currently supported; see docstring below.
) -> dict[str, Any]:
    """List .duf content files in a content library category path.

    Searches all configured DAZ content directories and deduplicates by filename.

    Args:
        category_path: Relative path within content directories (e.g. "People/Genesis 9/Hair").
        sort_by: Sort order — only "name" is currently supported (alphabetical).

    Returns:
        Dict with category, items (list of {name, filename, full_path}), and count.

    Example:
        daz_browse_category("People/Genesis 9/Hair")
        daz_browse_category("Props/Furniture")
    """
    return await _execute_by_id("vangard-browse-category", {"categoryPath": category_path})


@mcp.tool()
async def daz_get_content_info(file_path: str) -> dict[str, Any]:
    """Read metadata from a .duf content file without loading it into the scene.

    Parses the JSON structure of a .duf file to extract name, type, contributor,
    and other available metadata fields.

    Args:
        file_path: Absolute path to a .duf file on disk.

    Returns:
        Dict with name, type, file_version, contributor, revision, modified, and
        any scene-level asset info found in the file.

    Raises:
        ToolError: If the file does not exist, is not readable, or is not valid JSON.
    """
    path = Path(file_path)
    if not path.exists():
        raise ToolError(f"File not found: {file_path}")
    if not path.suffix.lower() == ".duf":
        raise ToolError(f"Not a .duf file: {file_path}")

    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
    except (OSError, _json.JSONDecodeError) as e:
        raise ToolError(f"Failed to read {file_path}: {e}") from e

    asset_info = data.get("asset_info", {})
    contributor = asset_info.get("contributor", {})

    result: dict[str, Any] = {
        "path": str(path),
        "name": path.stem,
        "file_version": data.get("file_version", "unknown"),
        "asset_id": asset_info.get("id", ""),
        "type": asset_info.get("type", "unknown"),
        "revision": asset_info.get("revision", ""),
        "modified": asset_info.get("modified", ""),
        "contributor": {
            "author": contributor.get("author", ""),
            "studio": contributor.get("studio", ""),
            "website": contributor.get("website", ""),
        },
    }

    # Try to extract a human-readable description from common locations
    if "scene" in data:
        scene = data["scene"]
        nodes = scene.get("nodes", [])
        if nodes:
            first = nodes[0]
            result["label"] = first.get("label", path.stem)
            if "description" in first:
                result["description"] = first["description"]

    return result


# ---------------------------------------------------------------------------
# Tools — content browser FastAPI server
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_search_content(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search the DAZ product catalog using semantic vector search.

    Calls the daz-content-browser FastAPI server (POST /api/v1/search).
    Returns a list of matching products with sku, name, description,
    compatible_figures, tags, and store_url fields.

    Returns {"available": false, "reason": "..."} gracefully if the content
    browser is not running.

    Args:
        query: Natural-language search query, e.g. "sci-fi armor for Genesis 9".
        max_results: Maximum number of results to return (default 10).
    """
    client = get_content_browser_client()
    try:
        response = await client.post(
            "/api/v1/search",
            json={"query": query, "max_results": max_results},
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {
            "available": False,
            "reason": "Content browser not reachable at " + CONTENT_BROWSER_URL,
        }
    if response.status_code != 200:
        return {
            "available": False,
            "reason": f"Content browser returned HTTP {response.status_code}",
        }
    return response.json()


@mcp.tool()
async def daz_load_product(product_name: str) -> dict[str, Any]:
    """Find a DAZ product by name and load it into the current scene.

    Queries the daz-content-browser product index (GET /api/v1/products?q=<name>)
    to resolve the absolute .duf path, then calls POST /api/v1/scene/load which
    delegates to the DazScriptServer to merge the asset into the scene.

    Returns {"available": false, "reason": "..."} gracefully if the content
    browser is not running or no matching product is found.

    Args:
        product_name: Partial or full product name to search for.
    """
    client = get_content_browser_client()
    try:
        search_response = await client.get("/api/v1/products", params={"q": product_name})
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {
            "available": False,
            "reason": "Content browser not reachable at " + CONTENT_BROWSER_URL,
        }
    if search_response.status_code != 200:
        return {
            "available": False,
            "reason": f"Content browser returned HTTP {search_response.status_code}",
        }

    products = search_response.json()
    if isinstance(products, dict):
        products = products.get("products", products.get("results", []))
    if not products:
        return {
            "available": True,
            "found": False,
            "reason": f"No product found matching '{product_name}'",
        }

    product = products[0]
    duf_path = product.get("path") or product.get("file_path") or product.get("duf_path")
    if not duf_path:
        return {
            "available": True,
            "found": True,
            "error": "Product record has no file path",
            "product": product,
        }

    try:
        load_response = await client.post("/api/v1/scene/load", json={"path": duf_path})
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {"available": False, "reason": "Content browser not reachable during load"}
    if load_response.status_code != 200:
        return {
            "available": False,
            "reason": f"Scene load returned HTTP {load_response.status_code}",
        }

    result = load_response.json()
    result["product"] = product
    return result


# ---------------------------------------------------------------------------
# Tools — asset compatibility
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_check_compatibility(asset_path: str, figure_label: str) -> dict[str, Any]:
    """Check if an asset is compatible with the specified figure generation.

    Reads the asset's .duf file to inspect compatible_figures metadata.
    """
    try:
        if not os.path.exists(asset_path):
            return {"compatible": False, "reason": "Asset file not found"}
        with open(asset_path, encoding="utf-8") as f:
            data = _json.load(f)
        asset_info = data.get("asset_info", {})
        compatible = asset_info.get("compatible_figures", [])
        return {
            "asset_path": asset_path,
            "figure_label": figure_label,
            "compatible_figures": compatible,
            "likely_compatible": any(
                figure_label.lower() in str(c).lower() or str(c).lower() in figure_label.lower()
                for c in compatible
            ) if compatible else None,
        }
    except Exception as e:
        return {"compatible": None, "error": str(e)}


# ---------------------------------------------------------------------------
# Tools — Content-Library asset creation
# ---------------------------------------------------------------------------


@mcp.tool()
async def daz_save_prop_asset(
    node_label: str,
    output_path: str,
    vendor_name: str = "Author",
    product_name: str = "Product",
    item_name: str | None = None,
    category: str | None = None,
    compatibility_base: str | None = None,
    compatible_with: str | None = None,
    smart_parent: bool | None = None,
    write_geometry: bool | None = None,
    write_parameters: bool | None = None,
    write_uvs: bool | None = None,
    force_unique_ids: bool | None = None,
    compress_output: bool | None = None,
) -> dict[str, Any]:
    """Save a node as a reusable Content-Library Prop/Figure Support Asset (.duf).

    Headless equivalent of **File > Save As > Support Asset > Prop Asset** (or
    "Figure Asset" for a rigged node), via ``DzNodeSupportAssetFilter``. Writes
    two things: the ``.duf`` preset at ``output_path``, and the actual geometry/
    UV/rigging data under ``<content dir>/data/<vendor>/<product>/<item>/...``.
    Once saved, the asset shows up like any other library prop and can be
    reloaded with ``daz_load_file`` or dragged from Smart Content/Content Library.

    Args:
        node_label: Display label, internal name, elementID, or ``Parent/Label``
            of the node to save.
        output_path: Absolute path for the ``.duf`` file. **Must be inside one of
            the DAZ Studio instance's configured content directories** (e.g.
            under "My Library" or a shared content root) — the tool resolves
            which content directory it belongs to and errors with the list of
            configured directories if it isn't inside any of them.
        vendor_name: Vendor/author name embedded in the asset metadata (default
            "Author").
        product_name: Product name embedded in the asset metadata (default
            "Product").
        item_name: Item name embedded in the asset metadata. Defaults to
            ``node_label`` if omitted.
        category: Content-Library category path to tag the asset with (e.g.
            "Props/Furniture").
        compatibility_base: Figure/base this asset declares compatibility with
            (e.g. "Genesis 9").
        compatible_with: Additional compatible-figure declaration string.
        smart_parent: Enable Smart Parent behavior when the asset is applied.
        write_geometry: Include geometry data (default plugin behavior if
            omitted — normally on).
        write_parameters: Include parameter/morph definitions (default plugin
            behavior if omitted — normally on).
        write_uvs: Include UV set definitions (default plugin behavior if
            omitted — normally on).
        force_unique_ids: Force regeneration of unique asset IDs instead of
            reusing existing ones.
        compress_output: Compress the written ``.duf``/``.dsf`` files (default
            plugin behavior if omitted — normally on).

    Returns:
        Dict with success, node, outputPath, baseDataPath (the resolved content
        directory), vendorName, productName, itemName.

    Examples:
        daz_save_prop_asset(
            "Long Wavy Hair",
            "C:/Users/me/Documents/DAZ 3D/Studio/My Library/Props/MyHair/My Hair.duf",
            vendor_name="MyStudio", product_name="Custom Hair", item_name="Long Wavy Hair",
        )

    Notes:
        - Live-verified: writes correct ``.duf`` + ``data/.../*.dsf`` files,
          fully silent (no dialog), confirmed round-trip-loadable via
          ``daz_load_file``.
        - Does **not** generate a thumbnail image — Daz's Content Library pane
          generates one lazily the first time it browses the folder, or you can
          render/place one yourself as ``<output_path>.png`` next to the .duf.
        - For a "Wearable Preset" (auto-fit-to-figure behavior when dragged
          from Smart Content, like a clothing/hair outfit), use
          ``daz_save_wearable_preset`` instead.
    """
    payload: dict[str, Any] = {
        "nodeLabel": node_label,
        "outputPath": output_path,
        "vendorName": vendor_name,
        "productName": product_name,
    }
    if item_name is not None:
        payload["itemName"] = item_name
    if category is not None:
        payload["category"] = category
    if compatibility_base is not None:
        payload["compatibilityBase"] = compatibility_base
    if compatible_with is not None:
        payload["compatibleWith"] = compatible_with
    if smart_parent is not None:
        payload["smartParent"] = smart_parent
    if write_geometry is not None:
        payload["writeGeometry"] = write_geometry
    if write_parameters is not None:
        payload["writeParameters"] = write_parameters
    if write_uvs is not None:
        payload["writeUvs"] = write_uvs
    if force_unique_ids is not None:
        payload["forceUniqueIds"] = force_unique_ids
    if compress_output is not None:
        payload["compressOutput"] = compress_output

    return await _execute_by_id("vangard-save-prop-asset", payload)


def _thumbnail_outputs(duf_path: str) -> list[dict[str, Any]]:
    """Content-Library thumbnail files for a ``.duf``: ``<name>.duf.png``
    (91x91, list view) and ``<name>.tip.png`` (256x256, tooltip). Other sizes
    show unreliably in the Content Library pane (Bug-Katalog #22)."""
    duf = duf_path.replace("\\", "/")
    stem = duf[:-4] if duf.lower().endswith(".duf") else duf
    return [{"path": f"{stem}.duf.png", "size": 91}, {"path": f"{stem}.tip.png", "size": 256}]


@mcp.tool()
async def daz_render_asset_thumbnail(node_labels: list[str], duf_path: str) -> dict[str, Any]:
    """Render Content-Library thumbnails for a saved asset ``.duf``.

    Writes ``<name>.duf.png`` (91x91) and ``<name>.tip.png`` (256x256) next to
    ``duf_path`` — RGBA with a transparent background, the sizes the Content
    Library pane shows reliably. Useful after ``daz_save_prop_asset`` and the
    headless ``daz_save_wearable_preset``, which write no thumbnail.

    Renders with the **Viewport** engine (no Iray, takes about a second):
    temporarily hides everything except ``node_labels`` and their children,
    aims a temporary camera at them (3/4 front view), renders, then restores
    visibility, render settings, viewport camera and selection.

    Args:
        node_labels: Label(s)/name(s)/elementID(s) of the node(s) to show.
            Several nodes (e.g. all items of a wearable preset) are framed
            together.
        duf_path: Path of the asset ``.duf`` the thumbnails belong to (need
            not exist yet).

    Returns:
        Dict with success, nodes and files (list of {path, size}).

    Examples:
        daz_render_asset_thumbnail(
            ["samor_1125_61_front"],
            "C:/Users/Public/Documents/My DAZ 3D Library/Props/Hair/Samor61.duf",
        )
    """
    if not node_labels:
        raise ToolError("node_labels must name at least one node.")
    return await _execute_by_id(
        "vangard-render-asset-thumbnail",
        {"nodeLabels": node_labels, "outputs": _thumbnail_outputs(duf_path)},
    )


@mcp.tool()
async def daz_save_wearable_preset(
    figure_label: str,
    output_path: str,
    items: list[str] | None = None,
    smart_parent: bool = True,
    pose_target: bool = False,
    compress_output: bool | None = None,
    save_simulation_data: bool | None = None,
    thumbnail: bool = True,
    use_ui_automation: bool = False,
    dialog_timeout: float = 30.0,
) -> dict[str, Any]:
    """Save items fitted to a figure as a reusable Wearable(s) Preset — the
    fit-to-figure asset type, as opposed to ``daz_save_prop_asset``'s plain
    geometry-only Support Asset.

    Headless equivalent of **File > Save As > Wearable(s) Preset**, via
    ``DzWearablesAssetFilter.doSave()`` — no dialogs, works with a remote
    DAZ Studio too. The written preset fits its items to whatever figure is
    selected when it is loaded (``conform_target`` = ``@selection``).

    Args:
        figure_label: Display label of the figure the items are fitted to
            (e.g. ``"Genesis 8 Female"``).
        output_path: Absolute path for the ``.duf`` file (extension is forced
            to ``.duf``). Typically under ``<content dir>/Presets/Wearables/``.
        items: Labels (or names/elementIDs) of the items to include. Only
            these end up in the preset. Defaults to every item fit or
            parented to the figure. Each item's label must be unique in the
            scene — the filter resolves items by label.
        smart_parent: Smart-parent the items to the target figure on load
            (default True, matches the dialog's default for fitted items).
        pose_target: Include the target figure's pose (default False).
        compress_output: Compress the ``.duf`` (plugin default: on).
        save_simulation_data: Include dForce simulation data (plugin
            default: on).
        thumbnail: Also render the Content-Library thumbnails
            (``.duf.png``/``.tip.png``) via ``daz_render_asset_thumbnail``
            (default True). A failed thumbnail render does not fail the
            save — it is reported as ``thumbnailError``.
        use_ui_automation: Fall back to driving the real GUI dialogs via
            Windows UI Automation (the pre-0.5.8+bb.10 behavior). Windows-only,
            same machine as DAZ Studio, always bundles *every* fitted item
            (``items`` must be omitted); thumbnails come from DAZ itself there.
        dialog_timeout: Only for ``use_ui_automation`` — seconds to wait for
            each native dialog (default 30s).

    Returns:
        Dict with success, figure, outputPath, items (labels saved) and
        thumbnails (written files) or thumbnailError.

    Examples:
        daz_save_wearable_preset(
            "Genesis 8 Female",
            "C:/Users/me/Documents/DAZ 3D/Studio/My Library/Presets/Wearables/Jacket.duf",
            items=["Female_Jacket"],
        )

    Notes:
        - Bug-Katalog #22 Teil 2: the long-standing ``errCode 98`` was a
          wrong ``NodeNames`` layout, not a broken API — see
          SKILL_DAZSCRIPT.md for the settings the filter actually reads.
    """
    if use_ui_automation:
        if items:
            raise ToolError(
                "items cannot be combined with use_ui_automation=True — the dialog "
                "path always bundles every item fitted to the figure"
            )
        _ui_automation._require_pywinauto()  # pylint: disable=protected-access
        await _execute_by_id_async("vangard-trigger-wearable-save", {"figureLabel": figure_label})
        return await asyncio.to_thread(
            _ui_automation.drive_wearable_preset_save, output_path, dialog_timeout
        )

    payload: dict[str, Any] = {
        "figureLabel": figure_label,
        "outputPath": output_path,
        "smartParent": smart_parent,
        "poseTarget": pose_target,
    }
    if items:
        payload["items"] = items
    if compress_output is not None:
        payload["compressOutput"] = compress_output
    if save_simulation_data is not None:
        payload["saveSimulationData"] = save_simulation_data
    result = await _execute_by_id("vangard-save-wearable-preset", payload)
    if thumbnail:
        try:
            thumbs = await daz_render_asset_thumbnail(result["items"], result["outputPath"])
            result["thumbnails"] = thumbs["files"]
        except ToolError as exc:
            result["thumbnailError"] = str(exc)
    return result


def _find_saved_modifier_files(
    base_data_path: str, vendor_name: str, product_name: str, morphs: list[dict], since: float,
) -> dict[str, str]:
    """Locate the ``.dsf`` written for each morph, newer than ``since``.

    DAZ Studio writes ``<base>/data/<asset vendor>/<asset product>/<item>/
    Morphs/<vendor>/<product>/<morph>.dsf`` — the first three folders come
    from the *node's* own asset (e.g. ``Elena_Shvets/Leather_Dress/Dress``),
    not from the dialog, so they are globbed rather than predicted.
    """
    data_dir = Path(base_data_path) / "data"
    found: dict[str, str] = {}
    for m in morphs:
        for stem in dict.fromkeys((m["name"], m["label"])):
            pattern = f"*/*/*/Morphs/{vendor_name}/{product_name}/{stem}.dsf"
            hits = [p for p in data_dir.glob(pattern) if p.stat().st_mtime >= since]
            if hits:
                found[m["name"]] = str(max(hits, key=lambda p: p.stat().st_mtime))
                break
    return found


@mcp.tool()
async def daz_save_modifier_asset(
    node_label: str,
    morph_names: list[str],
    vendor_name: str,
    product_name: str,
    base_data_path: str | None = None,
    compress_output: bool | None = None,
    force_unique_ids: bool | None = None,
    use_ui_automation: bool = False,
    dialog_timeout: float = 30.0,
) -> dict[str, Any]:
    """Save selected morphs of a node as Content-Library Modifier Assets (.dsf).

    Headless equivalent of **File > Save As > Support Asset > Modifier
    Asset(s)...** with exactly ``morph_names`` ticked, via
    ``DzModifierSupportAssetFilter.doSave()`` — no dialogs, works with a
    remote DAZ Studio too. Afterwards the morphs load automatically with the
    item in every scene, and a scene ``.duf`` stores only their values
    instead of the deltas. Typical use: persisting a morph created with
    ``daz_load_morph_pro`` on a clothing item.

    Args:
        node_label: Display label, internal name, elementID, or
            ``Parent/Label`` of the node carrying the morphs. The node itself
            must be backed by a saved Figure/Prop Asset (loaded from the
            content library, or saved via ``daz_save_prop_asset``) — checked
            up front, since DAZ Studio would otherwise pop a modal error.
        morph_names: Internal names or labels of the morphs to save (as
            listed by ``daz_list_morphs``).
        vendor_name: Vendor/author folder (``Morphs/<vendor>/...``), e.g.
            ``"blackbyte.de"``.
        product_name: Product folder (``Morphs/<vendor>/<product>/...``).
        base_data_path: Content directory to write into. Must be one of the
            configured content directories; defaults to the one holding the
            item's own asset (falls back to the first configured one).
        compress_output: Compress the written ``.dsf`` (plugin default: on).
        force_unique_ids: Force new unique asset IDs (plugin default: off).
        use_ui_automation: Fall back to driving the real dialog via Windows
            UI Automation (the pre-0.5.8+bb.10 behavior). Windows-only, same
            machine as DAZ Studio, needs an unlocked desktop and briefly
            brings DAZ Studio to the foreground (keyboard input).
        dialog_timeout: Only for ``use_ui_automation`` — seconds to wait for
            the dialog (default 30s).

    Returns:
        Dict with success, node, baseDataPath, vendorName, productName,
        morphs and files (morph name -> written ``.dsf`` path; ``None`` when
        the content directory isn't reachable from this machine, i.e. DAZ
        Studio runs remotely).

    Examples:
        daz_save_modifier_asset(
            "Leather Dress", ["LeatherDress_PullDown"],
            vendor_name="blackbyte.de", product_name="Product",
        )

    Notes:
        - Bug-Katalog #37: the old "returns 0, writes nothing" was a wrong
          ``NodeNames`` layout, not a broken API — see SKILL_DAZSCRIPT.md.
        - Morphs coming from cloud-encrypted (DAZ Connect) files are skipped
          by DAZ Studio itself; the tool reports them as not written.
    """
    if not morph_names:
        raise ToolError("morph_names must list at least one morph to save.")
    if use_ui_automation:
        _ui_automation.require_interactive_desktop()

    pre = await _execute_by_id(
        "vangard-modifier-asset-preflight",
        {"nodeLabel": node_label, "morphNames": morph_names},
    )
    if pre["missing"]:
        available = [a["name"] for a in pre["available"]]
        raise ToolError(
            f"Morph(s) {pre['missing']} not found on '{pre['node']}'. Available: {available}"
        )
    if not pre.get("isSavedAsset", True):
        raise ToolError(
            f"'{pre['node']}' is not backed by a saved Figure/Prop Asset (.dsf; asset file: "
            f"{pre.get('assetFile') or 'none'}). Save it with daz_save_prop_asset first."
        )
    if base_data_path is not None:
        norm = os.path.normcase(os.path.normpath(base_data_path))
        dirs = pre["contentDirectories"]
        match = next((d for d in dirs if os.path.normcase(os.path.normpath(d)) == norm), None)
        if match is None:
            raise ToolError(
                f"base_data_path {base_data_path!r} is not a configured content directory: {dirs}"
            )
        base_data_path = match

    started = time.time() - 2.0
    if not use_ui_automation:
        base = base_data_path or pre.get("assetContentDir") or pre["contentDirectories"][0]
        payload: dict[str, Any] = {
            "nodeLabel": node_label,
            "morphNames": [m["name"] for m in pre["morphs"]],
            "baseDataPath": base,
            "vendorName": vendor_name,
            "productName": product_name,
        }
        if compress_output is not None:
            payload["compressOutput"] = compress_output
        if force_unique_ids is not None:
            payload["forceUniqueIds"] = force_unique_ids
        await _execute_by_id("vangard-save-modifier-asset", payload)
        files: dict[str, str] | None = None
        if Path(base).is_dir():
            files = _find_saved_modifier_files(base, vendor_name, product_name, pre["morphs"], started)
            missing_files = [m["name"] for m in pre["morphs"] if m["name"] not in files]
            if missing_files:
                raise ToolError(
                    f"doSave succeeded, but no new .dsf found for {missing_files} under "
                    f"{base}/data/*/*/*/Morphs/{vendor_name}/{product_name}/ — DAZ Studio "
                    "skips morphs from cloud-encrypted files"
                )
        return {
            "success": True,
            "node": pre["node"],
            "baseDataPath": base,
            "vendorName": vendor_name,
            "productName": product_name,
            "morphs": [m["name"] for m in pre["morphs"]],
            "files": files,
        }

    submitted = await _execute_by_id_async(
        "vangard-trigger-modifier-asset-save", {"nodeLabel": node_label}
    )
    ui = await asyncio.to_thread(
        _ui_automation.drive_modifier_asset_save,
        pre["morphs"], vendor_name, product_name, base_data_path, dialog_timeout,
    )
    await _wait_for_async_result(submitted["request_id"], timeout_seconds=int(dialog_timeout) + 30)

    # DAZ finishes writing shortly after the dialog closes — poll briefly.
    deadline = time.monotonic() + min(dialog_timeout, 10.0)
    files = _find_saved_modifier_files(ui["baseDataPath"], vendor_name, product_name, pre["morphs"], started)
    while len(files) < len(pre["morphs"]) and time.monotonic() < deadline:
        await asyncio.sleep(0.3)
        files = _find_saved_modifier_files(ui["baseDataPath"], vendor_name, product_name, pre["morphs"], started)
    missing_files = [m["name"] for m in pre["morphs"] if m["name"] not in files]
    if missing_files:
        raise ToolError(
            f"Dialog accepted, but no new .dsf found for {missing_files} under "
            f"{ui['baseDataPath']}/data/*/*/*/Morphs/{vendor_name}/{product_name}/"
        )
    return {
        "success": True,
        "node": pre["node"],
        "baseDataPath": ui["baseDataPath"],
        "vendorName": vendor_name,
        "productName": product_name,
        "morphs": ui["ticked"],
        "files": files,
    }
