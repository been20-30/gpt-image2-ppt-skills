import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.editable_pptx.layers import (
    LayerMetrics,
    build_ai_separation_prompt,
    choose_layer_strategy,
    extract_rgba_layer,
    paste_layer,
)


def _overlapping_fixture():
    source = Image.new("RGB", (12, 12), (240, 240, 240))
    draw = ImageDraw.Draw(source)
    draw.rectangle((2, 2, 9, 9), fill=(20, 80, 180))
    draw.ellipse((5, 4, 11, 10), fill=(240, 120, 40))
    mask = Image.new("L", source.size, 0)
    ImageDraw.Draw(mask).ellipse((5, 4, 11, 10), fill=255)
    return source, mask


def test_a1_extract_preserves_visible_pixels():
    source, mask = _overlapping_fixture()

    layer = extract_rgba_layer(source, mask)

    assert layer.getpixel((7, 6))[:3] == source.getpixel((7, 6))
    assert layer.getpixel((7, 6))[3] == 255
    assert layer.getpixel((0, 0))[3] == 0


def test_a1_layer_round_trip_at_original_position():
    source, mask = _overlapping_fixture()
    layer = extract_rgba_layer(source, mask)
    background = source.convert("RGBA")

    recomposed = paste_layer(background, layer, (0, 0))

    assert list(recomposed.getdata()) == list(source.convert("RGBA").getdata())


def test_route_order_prefers_a1_then_a2_then_b():
    assert choose_layer_strategy(LayerMetrics(0.98, 0.01, 0.08), False) == "direct_extract"
    assert choose_layer_strategy(LayerMetrics(0.95, 0.03, 0.42), False) == "occlusion_complete"
    assert choose_layer_strategy(LayerMetrics(0.61, 0.24, 0.20), False) == "ai_regenerate"
    assert choose_layer_strategy(LayerMetrics(1.0, 0.0, 0.0), True) == "ai_regenerate"


def test_ai_separation_prompt_names_preservation_constraints():
    prompt = build_ai_separation_prompt("橙色半透明玻璃球", "右侧前景，遮挡蓝色卡片")

    assert "橙色半透明玻璃球" in prompt
    assert "透视" in prompt
    assert "光线" in prompt
    assert "不要生成文字" in prompt
