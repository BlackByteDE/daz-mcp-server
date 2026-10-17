"""Guard color-channel reading in registered material DazScript."""
import gzip
import json
from pathlib import Path

from vangard_daz_mcp._registry import _REGISTRY
from vangard_daz_mcp.tools.material import extract_preset_map_paths


def test_set_property_and_morph_search_modifier_stack():
    for script_id in ("vangard-set-property", "vangard-set-morph", "vangard-get-node"):
        script = _REGISTRY[script_id][1]
        assert "getNumModifiers" in script, script_id
        assert "getValueChannel" in script, script_id


def test_get_material_reads_float_color_properties():
    script = _REGISTRY["vangard-get-material"][1]
    assert "getFloatColorValue" in script
    assert "DzFloatColorProperty" in script
    assert "col.red()" not in script
    assert "readColorProp" in script


def test_extract_preset_map_paths_gzip_and_plain(tmp_path: Path):
    payload = {
        "image_library": [
            {"url": "skin.jpg#0", "filename": "/Runtime/Textures/skin.jpg"},
        ],
        "note": "not a map",
    }
    plain = tmp_path / "plain.duf"
    plain.write_text(json.dumps(payload), encoding="utf-8")
    gz = tmp_path / "gz.duf"
    gz.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8")))
    assert extract_preset_map_paths(str(plain)) == ["/Runtime/Textures/skin.jpg"]
    assert extract_preset_map_paths(str(gz)) == ["/Runtime/Textures/skin.jpg"]


def test_extract_preset_map_paths_ignores_image_library_ids(tmp_path: Path):
    """A stock DAZ preset names each image_library entry after the file
    ("id"/"name"/"label" = "X.jpg") — those are not paths and used to be
    reported as missing maps, so every stock preset was refused."""
    payload = {
        "image_library": [{
            "id": "G8FBaseEyelashes_1006.jpg",
            "name": "G8FBaseEyelashes_1006.jpg",
            "map": [{
                "url": "/Runtime/Textures/DAZ/G8FBaseEyelashes_1006.jpg",
                "label": "G8FBaseEyelashes_1006.jpg",
            }],
        }],
    }
    duf = tmp_path / "stock.duf"
    duf.write_text(json.dumps(payload), encoding="utf-8")
    assert extract_preset_map_paths(str(duf)) == [
        "/Runtime/Textures/DAZ/G8FBaseEyelashes_1006.jpg",
    ]


def test_extract_preset_map_paths_decodes_url_encoding(tmp_path: Path):
    """Bug-Katalog #23: DSON stores content-relative paths URL-encoded
    (e.g. "%20" for a space) — real files on disk have literal spaces, so
    the missing-files preflight must compare against the decoded form."""
    payload = {
        "filename": "/data/DAZ%203D/Built-in%20Content/FilaToon/FilaToon_LUT_03.png",
    }
    duf = tmp_path / "encoded.duf"
    duf.write_text(json.dumps(payload), encoding="utf-8")
    assert extract_preset_map_paths(str(duf)) == [
        "/data/DAZ 3D/Built-in Content/FilaToon/FilaToon_LUT_03.png",
    ]
