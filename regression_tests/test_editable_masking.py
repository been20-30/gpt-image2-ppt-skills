import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.editable_pptx.masking import (
    changed_outside_mask,
    composite_masked_edit,
    make_api_edit_mask,
    prepare_letterboxed_edit,
    restore_letterboxed_edit,
)


def _solid(size, color):
    return Image.new("RGB", size, color)


def _black_mask(size):
    return Image.new("L", size, 0)


def test_composite_changes_only_white_mask_pixels():
    original = _solid((4, 4), (10, 20, 30))
    edited = _solid((4, 4), (200, 210, 220))
    mask = _black_mask((4, 4))
    mask.putpixel((2, 1), 255)

    result = composite_masked_edit(original, edited, mask)

    assert result.getpixel((2, 1)) == (200, 210, 220)
    assert result.getpixel((0, 0)) == (10, 20, 30)
    assert changed_outside_mask(original, result, mask) == 0


def test_api_mask_makes_replace_region_transparent():
    internal = _black_mask((2, 2))
    internal.putpixel((1, 0), 255)

    api_mask = make_api_edit_mask(internal)

    assert api_mask.mode == "RGBA"
    assert api_mask.getpixel((1, 0))[3] == 0
    assert api_mask.getpixel((0, 0))[3] == 255


def test_size_mismatch_is_rejected():
    original = _solid((4, 4), (10, 20, 30))
    edited = _solid((3, 4), (200, 210, 220))
    mask = _black_mask((4, 4))

    try:
        composite_masked_edit(original, edited, mask)
    except ValueError as exc:
        assert "尺寸" in str(exc)
    else:
        raise AssertionError("mismatched image sizes should fail")


def test_letterbox_round_trip_preserves_slide_aspect_ratio():
    original = Image.new("RGB", (160, 90), (12, 18, 42))
    mask = Image.new("L", original.size, 0)
    mask.putpixel((80, 45), 255)

    canvas, canvas_mask, content_box = prepare_letterboxed_edit(original, mask, (160, 100))
    restored = restore_letterboxed_edit(canvas, content_box, original.size)

    assert canvas.size == (160, 100)
    assert canvas_mask.size == (160, 100)
    assert content_box == (0, 5, 160, 90)
    assert canvas_mask.getpixel((80, 50)) == 255
    assert restored.size == original.size
    assert restored.getpixel((10, 10)) == original.getpixel((10, 10))


def test_feathered_mask_pixels_are_inside_the_allowed_edit_region():
    original = _solid((3, 1), (10, 20, 30))
    result = original.copy()
    result.putpixel((1, 0), (100, 110, 120))
    mask = Image.new("L", (3, 1), 0)
    mask.putpixel((1, 0), 64)

    assert changed_outside_mask(original, result, mask) == 0
