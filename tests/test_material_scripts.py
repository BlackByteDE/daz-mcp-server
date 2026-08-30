"""Guard color-channel reading in registered material DazScript."""
from vangard_daz_mcp._registry import _REGISTRY


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
