"""Guard the DS6 render-option contract in registered DazScript payloads."""
from vangard_daz_mcp._registry import _REGISTRY

_RENDER_IDS = (
    "vangard-render",
    "vangard-render-with-camera",
    "vangard-batch-render-cameras",
    "vangard-render-animation",
    "vangard-set-render-output",
)


def test_render_scripts_use_direct_to_file_not_zero():
    for script_id in _RENDER_IDS:
        script = _REGISTRY[script_id][1]
        assert "renderImgToId = 0" not in script, script_id
        assert "opts.DirectToFile" in script, script_id
        assert "opts.applyChanges()" in script, script_id
        if script_id != "vangard-set-render-output":
            assert "doRender(opts)" in script, script_id


def test_set_render_output_uses_image_size():
    script = _REGISTRY["vangard-set-render-output"][1]
    assert "opts.imageSize" in script
    assert "new QSize" in script
    assert "opts.aspectWidth" not in script


def test_get_render_settings_reports_image_size():
    script = _REGISTRY["vangard-get-render-settings"][1]
    assert "opts.imageSize" in script
    assert "opts.DirectToFile" in script
